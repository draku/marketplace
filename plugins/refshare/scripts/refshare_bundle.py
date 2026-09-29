from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import os
import re
import stat
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import refshare_lib as lib
from refshare_bundle_html import render_index_html

FORMAT = "refshare-bundle"
FORMAT_VERSION = 1
MAX_ENTRIES = 10_000
MAX_MEMBER_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CONFLICT_POLICIES = ("skip", "overwrite", "rename", "newer")
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


class BundleError(Exception):
    def __init__(self, message: str, problems: list[dict] | None = None):
        super().__init__(message)
        self.problems = problems or []


def select_references(refs, *, categories=(), tags=(), types=(), ids=()):
    """Repeated values of one kind are OR; different kinds are AND."""
    def keep(ref) -> bool:
        if categories and ref.category not in categories:
            return False
        if tags and not (set(tags) & set(ref.tags)):
            return False
        if types and ref.ref_type not in types:
            return False
        if ids and ref.id not in ids:
            return False
        return True

    return [r for r in refs if keep(r)]


def resolve_output_path(out: str | None, today: str) -> Path:
    name = f"refshare-{today}.refshare.zip"
    if out is None:
        return Path.cwd() / name
    path = Path(out)
    return path / name if path.is_dir() else path


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _plugin_version() -> str:
    plugin_json = Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"
    try:
        return str(json.loads(plugin_json.read_text(encoding="utf-8")).get("version", "unknown"))
    except (OSError, ValueError):
        return "unknown"


def _zip_bytes(members: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    return buf.getvalue()


def build_bundle(refs, out_path, *, selection: dict, source: str | None = None,
                 include_html: bool = True, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    ordered = sorted(refs, key=lambda r: r.id)
    members: list[tuple[str, bytes]] = []
    entries: list[dict] = []
    for ref in ordered:
        problems = export_problems(ref)
        if problems:
            raise BundleError(f"cannot export {ref.id!r}: {'; '.join(problems)}")
        data = ref.path.read_bytes()
        member = f"references/{ref.id}.md"
        members.append((member, data))
        entries.append({
            "id": ref.id, "path": member, "sha256": hashlib.sha256(data).hexdigest(),
            "ref_type": ref.ref_type, "title": ref.title, "category": ref.category,
            "updated": ref.updated,
        })
    manifest: dict = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "created": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": {"name": "refshare", "version": _plugin_version()},
    }
    if source:
        manifest["source"] = source
    manifest["selection"] = selection
    manifest["entries"] = entries
    files = [("manifest.json", (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))] + members
    if include_html:
        files.append(("index.html", render_index_html(manifest, ordered).encode("utf-8")))
    _atomic_write(Path(out_path), _zip_bytes(files))
    return manifest


LINK_KEYS = ("type", "label", "url")
IDENTITY_UNREADABLE = "<existing file>"
DEST_SHARED = "<destination already used by another entry>"


def validate_reference(ref) -> list[str]:
    """Import-side checks on a parsed entry (everything except id, which callers check)."""
    problems = []
    if ref.ref_type not in lib.load_ref_types():
        problems.append(f"unknown ref_type {ref.ref_type!r}")
    for date_field in ("created", "updated"):
        if not DATE_RE.fullmatch(str(getattr(ref, date_field))):
            problems.append(f"{date_field} must be YYYY-MM-DD")
    if not all(isinstance(link.get(k), str) for link in ref.links for k in LINK_KEYS):
        problems.append("each link needs type, label and url")
    return problems


def export_problems(ref) -> list[str]:
    problems = [] if ID_RE.fullmatch(ref.id) else [f"id {ref.id!r} is not a valid slug"]
    return problems + validate_reference(ref)


def partition_exportable(refs) -> tuple[list, list]:
    """Split refs into (importable, [(ref, problems)]) so one bad file can't poison a bundle."""
    ok, excluded = [], []
    for ref in refs:
        problems = export_problems(ref)
        if problems:
            excluded.append((ref, problems))
        else:
            ok.append(ref)
    return ok, excluded


def _problem(path: str, message: str) -> dict:
    return {"path": path, "message": message}


@dataclass
class BundleEntry:
    id: str
    member: str
    raw: bytes | None = None
    ref: lib.Reference | None = None
    problems: list = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.problems


@dataclass
class Bundle:
    path: Path
    manifest: dict | None
    entries: list
    problems: list

    @property
    def valid(self) -> bool:
        return not self.problems and all(e.valid for e in self.entries)

    def all_problems(self) -> list[dict]:
        found = list(self.problems)
        for entry in self.entries:
            found.extend(entry.problems)
        return found


def _classify_member(name: str) -> str | None:
    """Return 'manifest', 'html', 'ref', 'dir', or None for an unacceptable name."""
    if name == "manifest.json":
        return "manifest"
    if name == "index.html":
        return "html"
    if name.endswith("/"):
        return "dir"
    if "\\" in name or "\x00" in name or name.startswith("/"):
        return None
    parts = name.split("/")
    if (len(parts) == 2 and parts[0] == "references"
            and parts[1].endswith(".md") and len(parts[1]) > len(".md")):
        return "ref"
    return None


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF)


def _read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, problems: list) -> bytes | None:
    try:
        with zf.open(info) as handle:
            data = handle.read(MAX_MEMBER_BYTES + 1)
    except (zipfile.BadZipFile, OSError, zlib.error, NotImplementedError, RuntimeError) as exc:
        problems.append(_problem(info.filename, f"cannot read member: {exc}"))
        return None
    if len(data) > MAX_MEMBER_BYTES:
        problems.append(_problem(info.filename, f"member larger than {MAX_MEMBER_BYTES} bytes"))
        return None
    return data


def load_bundle(path) -> Bundle:
    path = Path(path)
    bundle = Bundle(path=path, manifest=None, entries=[], problems=[])
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        bundle.problems.append(_problem(str(path), f"cannot open bundle: {exc}"))
        return bundle
    with zf:
        _load_from_zip(zf, bundle)
    return bundle


def _load_from_zip(zf: zipfile.ZipFile, bundle: Bundle) -> None:
    problems = bundle.problems
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES + 2:
        problems.append(_problem("(archive)", f"too many members (limit {MAX_ENTRIES} entries)"))
        return
    members: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in infos:
        name = info.filename
        kind = _classify_member(name)
        if kind == "dir":
            continue
        if kind is None:
            problems.append(_problem(name, "unexpected archive member"))
            continue
        if _is_symlink(info):
            problems.append(_problem(name, "symbolic links are not allowed"))
            continue
        if name in members:
            problems.append(_problem(name, "duplicate member"))
            continue
        if info.file_size > MAX_MEMBER_BYTES:
            problems.append(_problem(name, f"member larger than {MAX_MEMBER_BYTES} bytes"))
            continue
        total += info.file_size
        members[name] = info
    if total > MAX_TOTAL_BYTES:
        problems.append(_problem("(archive)", f"total size exceeds {MAX_TOTAL_BYTES} bytes"))
        return
    if "manifest.json" not in members:
        problems.append(_problem("manifest.json", "missing manifest.json"))
        return

    raw = _read_member(zf, members["manifest.json"], problems)
    if raw is None:
        return
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        problems.append(_problem("manifest.json", f"manifest is not valid JSON: {exc}"))
        return
    if not isinstance(manifest, dict):
        problems.append(_problem("manifest.json", "manifest must be a JSON object"))
        return
    if manifest.get("format") != FORMAT:
        problems.append(_problem(
            "manifest.json", f"not a refshare bundle (format={manifest.get('format')!r})"))
        return
    version = manifest.get("format_version")
    if type(version) is not int or version != FORMAT_VERSION:
        problems.append(_problem(
            "manifest.json",
            f"unsupported format_version {version!r}; supported: {FORMAT_VERSION}"))
        return
    entries_meta = manifest.get("entries")
    if not isinstance(entries_meta, list) or not all(isinstance(e, dict) for e in entries_meta):
        problems.append(_problem("manifest.json", "entries must be a list of objects"))
        return
    bundle.manifest = manifest

    seen: set[str] = set()
    listed: set[str] = set()
    for meta in entries_meta:
        entry = BundleEntry(id=str(meta.get("id")), member=str(meta.get("path")))
        bundle.entries.append(entry)
        listed.add(entry.member)
        _validate_entry(zf, members, meta, entry, seen)
    for name in members:
        if _classify_member(name) == "ref" and name not in listed:
            problems.append(_problem(name, "member not listed in manifest"))


def _validate_entry(zf, members, meta: dict, entry: BundleEntry, seen: set) -> None:
    def fail(message: str) -> None:
        entry.problems.append(_problem(entry.member, message))

    entry_id = meta.get("id")
    if not isinstance(entry_id, str) or not ID_RE.fullmatch(entry_id):
        fail(f"invalid id {entry_id!r}")
        return
    if entry_id in seen:
        fail(f"duplicate id {entry_id!r}")
        return
    seen.add(entry_id)
    expected = f"references/{entry_id}.md"
    if meta.get("path") != expected:
        fail(f"path must be {expected!r}")
        return
    info = members.get(expected)
    if info is None:
        fail("listed in manifest but missing from archive")
        return
    raw = _read_member(zf, info, entry.problems)
    if raw is None:
        return
    sha = meta.get("sha256")
    if not isinstance(sha, str) or hashlib.sha256(raw).hexdigest() != sha.lower():
        fail("sha256 does not match manifest")
        return
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        fail("entry is not valid UTF-8")
        return
    try:
        ref = lib.parse_reference_content(text, "global", Path(expected))
    except lib.ReferenceParseError as exc:
        message = str(exc)
        prefix = f"{expected}: "
        fail(message[len(prefix):] if message.startswith(prefix) else message)
        return
    if ref.id != entry_id:
        fail(f"frontmatter id {ref.id!r} does not match filename id {entry_id!r}")
    for message in validate_reference(ref):
        fail(message)
    for key in ("ref_type", "title", "category", "updated"):
        if key in meta and meta[key] != getattr(ref, key):
            fail(f"manifest {key} does not match the entry")
    if not entry.problems:
        entry.raw, entry.ref = raw, ref


def read_bundle(path) -> Bundle:
    bundle = load_bundle(path)
    if not bundle.valid:
        raise BundleError(f"invalid bundle: {path}", bundle.all_problems())
    return bundle


IDENTITY_FIELDS = ("id", "ref_type", "title", "category", "tags", "links",
                   "description", "share_text", "share_html")
ACTIONS = ("created", "unchanged", "skipped_conflict", "overwritten", "renamed")


def _canonical(ref) -> dict:
    data = {name: getattr(ref, name) for name in IDENTITY_FIELDS}
    data["tags"] = sorted(data["tags"])
    return data


def diff_fields(a, b) -> list[str]:
    """Fields whose content differs; created/updated, scope and path never count."""
    ca, cb = _canonical(a), _canonical(b)
    return [name for name in IDENTITY_FIELDS if ca[name] != cb[name]]


@dataclass
class PlanItem:
    id: str
    action: str
    final_id: str
    differs: list
    dest: Path | None = None
    data: bytes | None = None


@dataclass
class Plan:
    target_scope: str
    target_dir: Path
    on_conflict: str
    items: list
    not_selected: int
    warnings: list

    def summary(self) -> dict:
        counts = {action: 0 for action in ACTIONS}
        for item in self.items:
            counts[item.action] += 1
        counts["not_selected"] = self.not_selected
        return counts

    def to_dict(self, *, dry_run: bool, bundle) -> dict:
        return {
            "command": "import", "dry_run": dry_run, "target_scope": self.target_scope,
            "on_conflict": self.on_conflict, "bundle": str(bundle),
            "summary": self.summary(),
            "entries": [{"id": i.id, "action": i.action, "final_id": i.final_id,
                         "differs": i.differs} for i in self.items],
            "warnings": list(self.warnings),
        }


def _resolve_conflict(policy: str, incoming, existing) -> str:
    if policy == "skip":
        return "skipped_conflict"
    if policy == "overwrite":
        return "overwritten"
    if policy == "rename":
        return "renamed"
    if (existing is not None and DATE_RE.fullmatch(str(existing.updated))
            and incoming.updated > existing.updated):
        return "overwritten"
    return "skipped_conflict"


def _rename_bytes(raw: bytes, ref, new_id: str, new_dest: Path) -> bytes:
    """Change only the frontmatter id line, keeping every other byte of the entry."""
    text = raw.decode("utf-8")
    end = text.find("\n---", 3)
    pattern = re.compile(rf'^id:[ \t]*"?{re.escape(ref.id)}"?[ \t]*(\r?)$', re.MULTILINE)
    head, tail = text[:end], text[end:]
    if end != -1 and pattern.search(head):
        head = pattern.sub(lambda m: f"id: {new_id}{m.group(1)}", head, count=1)
        return (head + tail).encode("utf-8")
    renamed = dataclasses.replace(ref, id=new_id, path=new_dest)
    return lib.serialize_reference(renamed).encode("utf-8")


def _next_free(entry_id: str, reserved: set) -> str:
    n = 2
    while f"{entry_id}-{n}" in reserved:
        n += 1
    return f"{entry_id}-{n}"


def plan_import(bundle: Bundle, target_scope: str, cwd=None, *, on_conflict: str = "skip",
                categories=(), tags=(), types=(), ids=()) -> Plan:
    if on_conflict not in CONFLICT_POLICIES:
        raise ValueError(f"unknown conflict policy {on_conflict!r}")
    target_dir = lib.scope_dir(target_scope, cwd)
    local, _errors = lib.load_scope(target_scope, cwd)
    local_taken = set(local)
    if target_dir.exists():
        local_taken |= {p.stem for p in target_dir.glob("*.md")}

    incoming = {e.ref.id: e for e in bundle.entries}
    chosen = select_references([e.ref for e in bundle.entries], categories=categories,
                               tags=tags, types=types, ids=ids)
    reserved = local_taken | {r.id for r in chosen}
    warnings = [f"no entry with id {i!r} in bundle" for i in ids if i not in incoming]

    items: list[PlanItem] = []
    for ref in sorted(chosen, key=lambda r: r.id):
        entry = incoming[ref.id]
        existing = local.get(ref.id)
        dest = target_dir / f"{ref.id}.md"
        if existing is None and ref.id not in local_taken:
            items.append(PlanItem(ref.id, "created", ref.id, [], dest, entry.raw))
            continue
        if existing is not None:
            differs = diff_fields(ref, existing)
            if not differs:
                items.append(PlanItem(ref.id, "unchanged", ref.id, []))
                continue
            dest = existing.path
        else:
            differs = [IDENTITY_UNREADABLE]
        action = _resolve_conflict(on_conflict, ref, existing)
        if action == "renamed":
            final_id = _next_free(ref.id, reserved)
            reserved.add(final_id)
            new_dest = target_dir / f"{final_id}.md"
            data = _rename_bytes(entry.raw, ref, final_id, new_dest)
            items.append(PlanItem(ref.id, "renamed", final_id, differs, new_dest, data))
        elif action == "overwritten":
            items.append(PlanItem(ref.id, "overwritten", ref.id, differs, dest, entry.raw))
        else:
            items.append(PlanItem(ref.id, "skipped_conflict", ref.id, differs))
    claimed: set = set()
    for index, item in enumerate(items):
        if item.data is None:
            continue
        if item.dest in claimed:
            items[index] = PlanItem(item.id, "skipped_conflict", item.id, [DEST_SHARED])
        else:
            claimed.add(item.dest)
    return Plan(target_scope, target_dir, on_conflict, items,
                len(bundle.entries) - len(chosen), warnings)


def apply_plan(plan: Plan) -> None:
    undo: list[tuple[Path, bytes | None]] = []
    try:
        for item in plan.items:
            if item.data is None:
                continue
            prior = item.dest.read_bytes() if item.dest.exists() else None
            _atomic_write(item.dest, item.data)
            undo.append((item.dest, prior))
    except BaseException as exc:
        stuck = []
        for dest, prior in reversed(undo):
            try:
                if prior is None:
                    dest.unlink(missing_ok=True)
                else:
                    _atomic_write(dest, prior)
            except OSError:
                stuck.append(str(dest))
        if not isinstance(exc, Exception):
            raise  # KeyboardInterrupt and friends propagate after the rollback attempt
        if stuck:
            raise BundleError(
                f"import failed: {exc}; these files could not be restored: {', '.join(stuck)}"
            ) from exc
        raise BundleError(f"import failed and was rolled back: {exc}") from exc
