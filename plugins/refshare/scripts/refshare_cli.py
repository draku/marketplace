#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

import refshare_lib as lib


def _parse_link_arg(raw: str) -> dict:
    parts = raw.split(":", 2)
    if len(parts) != 3:
        raise SystemExit(f"invalid --link value {raw!r}; expected type:label:url")
    link_type, label, url = parts
    return {"type": link_type, "label": label, "url": url}


def _reference_to_dict(ref) -> dict:
    return {
        "id": ref.id, "ref_type": ref.ref_type, "title": ref.title,
        "category": ref.category, "tags": ref.tags, "links": ref.links,
        "description": ref.description, "share_text": ref.share_text,
        "share_html": ref.share_html, "created": ref.created,
        "updated": ref.updated, "scope": ref.scope,
    }


def _emit_one(ref, args, out) -> None:
    if args.json:
        print(json.dumps(_reference_to_dict(ref)), file=out)
        return
    print(f"{ref.id}  [{ref.scope}]", file=out)
    print(f"  title:       {ref.title}", file=out)
    print(f"  type:        {ref.ref_type}", file=out)
    print(f"  category:    {ref.category}", file=out)
    print(f"  tags:        {', '.join(ref.tags)}", file=out)
    for link in ref.links:
        print(f"  link:        [{link['type']}] {link['label']} -> {link['url']}", file=out)
    print(f"  description: {ref.description}", file=out)


def _read_json_payload_from_stdin(from_json: str) -> tuple[dict | None, int | None]:
    """Validate --from-json usage and read/parse the stdin payload.

    Returns (payload, None) on success or (None, exit_code) on failure.
    """
    if from_json != "-":
        print("error: --from-json only supports '-' (stdin)", file=sys.stderr)
        return None, 2
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON on stdin: {exc}", file=sys.stderr)
        return None, 2
    if not isinstance(payload, dict):
        print("error: --from-json payload must be a JSON object", file=sys.stderr)
        return None, 2
    return payload, None


def cmd_add(args, out) -> int:
    if args.from_json is not None:
        payload, error_code = _read_json_payload_from_stdin(args.from_json)
        if error_code is not None:
            return error_code
        title = payload.get("title")
        ref_type = payload.get("ref_type")
        category = payload.get("category")
        for field_name, value in (("title", title), ("ref_type", ref_type), ("category", category)):
            if value is None:
                print(f"error: --from-json payload missing required field: {field_name}", file=sys.stderr)
                return 2
        tags = payload.get("tags") or []
        links = payload.get("links") or []
        description = payload.get("description") or ""
        share_text = payload.get("share_text") or ""
        share_html = payload.get("share_html") or ""
    else:
        if args.title is None or args.ref_type is None or args.category is None:
            print("error: --title/--ref-type/--category are required unless --from-json is given", file=sys.stderr)
            return 2
        title = args.title
        ref_type = args.ref_type
        category = args.category
        tags = args.tag or []
        links = [_parse_link_arg(v) for v in (args.link or [])]
        description = args.description or ""
        share_text = args.share_text or ""
        share_html = args.share_html or ""

    try:
        ref = lib.create_reference(
            title=title, ref_type=ref_type, category=category,
            tags=tags, links=links, description=description,
            share_text=share_text, share_html=share_html,
            project=args.project,
        )
    except (lib.IdCollisionError, lib.UnknownRefTypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _emit_one(ref, args, out)
    return 0


def cmd_edit(args, out) -> int:
    if args.from_json is not None:
        payload, error_code = _read_json_payload_from_stdin(args.from_json)
        if error_code is not None:
            return error_code
        changes = {
            "ref_type": payload.get("ref_type"),
            "title": payload.get("title"),
            "category": payload.get("category"),
            "tags": payload.get("tags"),
            "links": payload.get("links"),
            "description": payload.get("description"),
            "share_text": payload.get("share_text"),
            "share_html": payload.get("share_html"),
        }
    else:
        changes = {
            "ref_type": args.ref_type,
            "title": args.title,
            "category": args.category,
            "tags": args.tag if args.tag else None,
            "links": [_parse_link_arg(v) for v in args.link] if args.link else None,
            "description": args.description,
            "share_text": args.share_text,
            "share_html": args.share_html,
        }
    try:
        ref = lib.resolve_mutable_reference(args.id, args.scope)
        ref = lib.update_reference(ref, **changes)
    except (lib.ReferenceNotFoundError, lib.AmbiguousScopeError, lib.UnknownRefTypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _emit_one(ref, args, out)
    return 0


def cmd_remove(args, out) -> int:
    try:
        ref = lib.resolve_mutable_reference(args.id, args.scope)
        lib.remove_reference(ref)
    except (lib.ReferenceNotFoundError, lib.AmbiguousScopeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"removed": ref.id, "scope": ref.scope}), file=out)
    else:
        print(f"removed {ref.id} ({ref.scope})", file=out)
    return 0


def _emit_many(refs, errors, args, out) -> None:
    if args.json:
        print(json.dumps({
            "references": [_reference_to_dict(r) for r in refs],
            "errors": [f"{p}: {msg}" for p, msg in errors],
        }), file=out)
        return
    for ref in refs:
        print(f"{ref.id}\t[{ref.scope}]\t{ref.title}\t{ref.category}\t{', '.join(ref.tags)}", file=out)
    for path, msg in errors:
        print(f"warning: {path}: {msg}", file=sys.stderr)


def cmd_list(args, out) -> int:
    refs, errors = lib.load_all_references()
    refs = lib.filter_references(refs, category=args.category, tag=args.tag, ref_type=args.type)
    _emit_many(refs, errors, args, out)
    return 0


def cmd_search(args, out) -> int:
    refs, errors = lib.load_all_references()
    refs = lib.filter_references(refs, category=args.category, tag=args.tag, ref_type=args.type)
    refs = lib.search_references(refs, args.keyword)
    _emit_many(refs, errors, args, out)
    return 0


def cmd_show(args, out) -> int:
    try:
        ref = lib.resolve_reference(args.id)
    except lib.ReferenceNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _emit_one(ref, args, out)
    return 0


def cmd_share(args, out) -> int:
    try:
        ref = lib.resolve_reference(args.id)
    except lib.ReferenceNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    text = ref.share_text if args.format == "text" else ref.share_html
    if args.json:
        print(json.dumps({"id": ref.id, "format": args.format, "content": text}), file=out)
    else:
        print(text, file=out)
    return 0


common = argparse.ArgumentParser(add_help=False)
common.add_argument("--json", action="store_true", help="machine-readable output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="refshare")
    sub = parser.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add", parents=[common])
    add_p.add_argument("--title")
    add_p.add_argument("--ref-type", dest="ref_type")
    add_p.add_argument("--category")
    add_p.add_argument("--tag", action="append")
    add_p.add_argument("--link", action="append")
    add_p.add_argument("--description")
    add_p.add_argument("--share-text", dest="share_text")
    add_p.add_argument("--share-html", dest="share_html")
    add_p.add_argument("--project", action="store_true")
    add_p.add_argument("--from-json", dest="from_json", default=None)
    add_p.set_defaults(func=cmd_add)

    edit_p = sub.add_parser("edit", parents=[common])
    edit_p.add_argument("id")
    edit_p.add_argument("--scope", choices=["global", "project"])
    edit_p.add_argument("--ref-type", dest="ref_type")
    edit_p.add_argument("--title")
    edit_p.add_argument("--category")
    edit_p.add_argument("--tag", action="append")
    edit_p.add_argument("--link", action="append")
    edit_p.add_argument("--description")
    edit_p.add_argument("--share-text", dest="share_text")
    edit_p.add_argument("--share-html", dest="share_html")
    edit_p.add_argument("--from-json", dest="from_json", default=None)
    edit_p.set_defaults(func=cmd_edit)

    remove_p = sub.add_parser("remove", parents=[common])
    remove_p.add_argument("id")
    remove_p.add_argument("--scope", choices=["global", "project"])
    remove_p.set_defaults(func=cmd_remove)

    list_p = sub.add_parser("list", parents=[common])
    list_p.add_argument("--category")
    list_p.add_argument("--tag")
    list_p.add_argument("--type")
    list_p.set_defaults(func=cmd_list)

    search_p = sub.add_parser("search", parents=[common])
    search_p.add_argument("keyword")
    search_p.add_argument("--category")
    search_p.add_argument("--tag")
    search_p.add_argument("--type")
    search_p.set_defaults(func=cmd_search)

    show_p = sub.add_parser("show", parents=[common])
    show_p.add_argument("id")
    show_p.set_defaults(func=cmd_show)

    share_p = sub.add_parser("share", parents=[common])
    share_p.add_argument("id")
    share_p.add_argument("--format", choices=["text", "html"], required=True)
    share_p.set_defaults(func=cmd_share)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args, sys.stdout)


if __name__ == "__main__":
    sys.exit(main())
