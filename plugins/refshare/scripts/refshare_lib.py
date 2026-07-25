from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

FRONTMATTER_DELIM = "---"

SECTION_HEADERS = {
    "description": "## Description",
    "share_text": "## Share: Plain Text",
    "share_html": "## Share: HTML",
}


class ReferenceParseError(Exception):
    pass


@dataclass
class Reference:
    id: str
    ref_type: str
    title: str
    category: str
    tags: list[str]
    links: list[dict]
    description: str
    share_text: str
    share_html: str
    created: str
    updated: str
    scope: str
    path: Path


def _parse_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def _dump_scalar(value: str) -> str:
    if re.search(r'[:#\[\]{}]', value) or value != value.strip():
        return f'"{value}"'
    return value


def parse_reference_text(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIM:
        raise ReferenceParseError("missing frontmatter delimiter")
    try:
        end = lines.index(FRONTMATTER_DELIM, 1)
    except ValueError:
        raise ReferenceParseError("unterminated frontmatter block")
    fm_lines = lines[1:end]
    body = "\n".join(lines[end + 1:]).strip("\n")

    data: dict = {}
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith(" "):
            raise ReferenceParseError(f"unexpected indent: {line!r}")
        if ":" not in line:
            raise ReferenceParseError(f"malformed line: {line!r}")
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key == "links":
            if rest:
                raise ReferenceParseError("links must be a block list")
            links: list[dict] = []
            i += 1
            current: dict = {}
            while i < len(fm_lines) and fm_lines[i].startswith("  "):
                item = fm_lines[i]
                stripped = item.strip()
                if stripped.startswith("- "):
                    if current:
                        links.append(current)
                    current = {}
                    stripped = stripped[2:]
                if ":" not in stripped:
                    raise ReferenceParseError(f"malformed link line: {item!r}")
                lk, _, lv = stripped.partition(":")
                current[lk.strip()] = _parse_scalar(lv)
                i += 1
            if current:
                links.append(current)
            data["links"] = links
            continue
        if key == "tags" and not (rest.startswith("[") and rest.endswith("]")):
            raise ReferenceParseError(f"tags must be a bracketed list: {line!r}")
        if rest.startswith("[") and rest.endswith("]"):
            inner = rest[1:-1].strip()
            data[key] = [v.strip() for v in inner.split(",") if v.strip()] if inner else []
        else:
            data[key] = _parse_scalar(rest)
        i += 1
    return data, body


def dump_reference_text(data: dict, body: str) -> str:
    lines = [FRONTMATTER_DELIM]
    for key in ("id", "ref_type", "title", "category"):
        lines.append(f"{key}: {_dump_scalar(str(data[key]))}")
    tags = data.get("tags", [])
    lines.append(f"tags: [{', '.join(tags)}]")
    lines.append("links:")
    for link in data.get("links", []):
        lines.append(f"  - type: {_dump_scalar(link['type'])}")
        lines.append(f"    label: {_dump_scalar(link['label'])}")
        lines.append(f"    url: {_dump_scalar(link['url'])}")
    lines.append(f"created: {data['created']}")
    lines.append(f"updated: {data['updated']}")
    lines.append(FRONTMATTER_DELIM)
    lines.append("")
    lines.append(body.strip("\n"))
    lines.append("")
    return "\n".join(lines)


def parse_body_sections(body: str) -> dict:
    sections = {"description": "", "share_text": "", "share_html": ""}
    pattern = re.compile(r"^## (Description|Share: Plain Text|Share: HTML)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(body))
    key_by_header = {v: k for k, v in SECTION_HEADERS.items()}

    # Verify all three required headers were found
    found_headers = set()
    for m in matches:
        header = f"## {m.group(1)}"
        found_headers.add(header)
    for expected_header in SECTION_HEADERS.values():
        if expected_header not in found_headers:
            raise ReferenceParseError(f"missing section: {expected_header}")

    for idx, m in enumerate(matches):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        header = f"## {m.group(1)}"
        key = key_by_header[header]
        sections[key] = body[start:end].strip("\n").strip()
    return sections


def dump_body_sections(sections: dict) -> str:
    return (
        f"## Description\n{sections['description'].strip()}\n\n"
        f"## Share: Plain Text\n{sections['share_text'].strip()}\n\n"
        f"## Share: HTML\n{sections['share_html'].strip()}\n"
    )


REQUIRED_FIELDS = ("id", "ref_type", "title", "category", "created", "updated")


def parse_reference_file(path: Path, scope: str) -> Reference:
    text = path.read_text(encoding="utf-8")
    try:
        data, body = parse_reference_text(text)
        for field_name in REQUIRED_FIELDS:
            if field_name not in data:
                raise ReferenceParseError(f"missing required field: {field_name}")
        sections = parse_body_sections(body)
    except ReferenceParseError as exc:
        raise ReferenceParseError(f"{path}: {exc}") from exc
    return Reference(
        id=data["id"], ref_type=data["ref_type"], title=data["title"],
        category=data["category"], tags=data.get("tags", []), links=data.get("links", []),
        description=sections["description"], share_text=sections["share_text"],
        share_html=sections["share_html"], created=data["created"], updated=data["updated"],
        scope=scope, path=path,
    )


def serialize_reference(ref: Reference) -> str:
    data = {
        "id": ref.id, "ref_type": ref.ref_type, "title": ref.title,
        "category": ref.category, "tags": ref.tags, "links": ref.links,
        "created": ref.created, "updated": ref.updated,
    }
    body = dump_body_sections({
        "description": ref.description, "share_text": ref.share_text, "share_html": ref.share_html,
    })
    return dump_reference_text(data, body)


def write_reference(ref: Reference) -> None:
    ref.path.parent.mkdir(parents=True, exist_ok=True)
    ref.path.write_text(serialize_reference(ref), encoding="utf-8")


def slugify(title: str) -> str:
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "reference"


def global_dir() -> Path:
    return Path.home() / ".claude" / "refshare" / "references"


def project_dir(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()) / ".claude" / "refshare" / "references"


def ref_types_path() -> Path:
    return Path(__file__).resolve().parent / "ref_types.json"


def load_ref_types() -> list[str]:
    with open(ref_types_path(), encoding="utf-8") as f:
        return json.load(f)


def _scan_dir(directory: Path, scope: str) -> tuple[dict, list[tuple[Path, str]]]:
    refs: dict[str, Reference] = {}
    errors: list[tuple[Path, str]] = []
    if not directory.exists():
        return refs, errors
    for path in sorted(directory.glob("*.md")):
        try:
            ref = parse_reference_file(path, scope)
        except ReferenceParseError as exc:
            errors.append((path, str(exc)))
            continue
        refs[ref.id] = ref
    return refs, errors


def load_all_references(cwd: Path | None = None) -> tuple[list[Reference], list[tuple[Path, str]]]:
    global_refs, global_errors = _scan_dir(global_dir(), "global")
    project_refs, project_errors = _scan_dir(project_dir(cwd), "project")
    merged = dict(global_refs)
    merged.update(project_refs)
    all_refs = sorted(merged.values(), key=lambda r: r.id)
    return all_refs, global_errors + project_errors


class ReferenceNotFoundError(Exception):
    pass


class AmbiguousScopeError(Exception):
    pass


def resolve_reference(ref_id: str, cwd: Path | None = None) -> Reference:
    refs, _ = load_all_references(cwd)
    for ref in refs:
        if ref.id == ref_id:
            return ref
    raise ReferenceNotFoundError(f"no reference found with id {ref_id!r}")


def resolve_mutable_reference(ref_id: str, scope: str | None, cwd: Path | None = None) -> Reference:
    global_refs, _ = _scan_dir(global_dir(), "global")
    project_refs, _ = _scan_dir(project_dir(cwd), "project")
    in_global = ref_id in global_refs
    in_project = ref_id in project_refs
    if scope == "global":
        if not in_global:
            raise ReferenceNotFoundError(f"no reference {ref_id!r} in global scope")
        return global_refs[ref_id]
    if scope == "project":
        if not in_project:
            raise ReferenceNotFoundError(f"no reference {ref_id!r} in project scope")
        return project_refs[ref_id]
    if in_global and in_project:
        raise AmbiguousScopeError(
            f"{ref_id!r} exists in both global and project scope; pass --scope global|project"
        )
    if in_project:
        return project_refs[ref_id]
    if in_global:
        return global_refs[ref_id]
    raise ReferenceNotFoundError(f"no reference found with id {ref_id!r}")


def filter_references(refs: list[Reference], category: str | None = None,
                       tag: str | None = None, ref_type: str | None = None) -> list[Reference]:
    result = refs
    if category:
        result = [r for r in result if r.category == category]
    if tag:
        result = [r for r in result if tag in r.tags]
    if ref_type:
        result = [r for r in result if r.ref_type == ref_type]
    return result


def search_references(refs: list[Reference], keyword: str) -> list[Reference]:
    needle = keyword.lower()

    def matches(r: Reference) -> bool:
        haystacks = [r.title, r.description, r.category, *r.tags,
                     *[link["label"] for link in r.links]]
        return any(needle in h.lower() for h in haystacks)

    return [r for r in refs if matches(r)]


from datetime import date


class IdCollisionError(Exception):
    pass


class UnknownRefTypeError(Exception):
    pass


def create_reference(*, title, ref_type, category, tags, links, description,
                      share_text, share_html, project: bool, cwd: Path | None = None) -> Reference:
    if ref_type not in load_ref_types():
        raise UnknownRefTypeError(
            f"unknown ref_type {ref_type!r}; valid types: {', '.join(load_ref_types())}"
        )
    scope = "project" if project else "global"
    directory = project_dir(cwd) if project else global_dir()
    ref_id = slugify(title)
    path = directory / f"{ref_id}.md"
    if path.exists():
        raise IdCollisionError(f"{ref_id!r} already exists in {scope} scope")
    today = date.today().isoformat()
    ref = Reference(
        id=ref_id, ref_type=ref_type, title=title, category=category,
        tags=tags, links=links, description=description,
        share_text=share_text, share_html=share_html,
        created=today, updated=today, scope=scope, path=path,
    )
    write_reference(ref)
    return ref


def update_reference(ref: Reference, **changes) -> Reference:
    if changes.get("ref_type") is not None and changes["ref_type"] not in load_ref_types():
        raise UnknownRefTypeError(
            f"unknown ref_type {changes['ref_type']!r}; valid types: {', '.join(load_ref_types())}"
        )
    for field_name in ("ref_type", "title", "category", "tags", "links",
                       "description", "share_text", "share_html"):
        if changes.get(field_name) is not None:
            setattr(ref, field_name, changes[field_name])
    ref.updated = date.today().isoformat()
    write_reference(ref)
    return ref


def remove_reference(ref: Reference) -> None:
    ref.path.unlink()
