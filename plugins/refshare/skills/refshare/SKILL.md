---
name: refshare
description: Use when the user wants to save, browse, search, edit, categorize/tag, or share a reference (a site, tool, service, or other resource) — including adding a reference from a URL, creating one from a description with no URL, and preparing plain-text or HTML content to paste into chat or email.
---

# refshare

Manages a personal library of shareable references using
`scripts/refshare_cli.py`. Every reference has a required `category`, which
is an **audience scope** (who it's appropriate to share this with — use
`public` for no restriction, or a named org like `acme-corp`), separate
from freeform `tags` (topical labels like `devtool`, `creative-writing`).

Invoke the CLI as:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/refshare_cli.py" <command> [flags]
```

Always pass `--json` when you need to parse the result programmatically;
omit it when showing output directly to the user isn't necessary (the
human-readable format is also fine to relay in your own words).

## Commands

All commands additionally accept `--json` for machine-readable output.

| Command | Flags |
|---|---|
| `add` | `--title` `--ref-type` `--category` (required unless `--from-json -` is given), `--tag` (repeatable), `--link type:label:url` (repeatable), `--description`, `--share-text`, `--share-html`, `--project` (defaults to global scope), `--from-json -` (stdin JSON payload, alternative to individual content flags) |
| `edit <id>` | `--scope global\|project` (required only if `<id>` exists in both scopes), plus any of add's content fields: `--title`, `--ref-type`, `--category`, `--tag` (repeatable), `--link` (repeatable), `--description`, `--share-text`, `--share-html`, `--from-json -` (stdin JSON payload, alternative to individual content flags) |
| `remove <id>` | `--scope global\|project` (CLI requires this only on scope collision — always confirm with the user before removing regardless, see Workflows) |
| `list` | `--category`, `--tag` (single value only, not repeatable), `--type` |
| `search <keyword>` | `--category`, `--tag` (single value only, not repeatable), `--type` |
| `show <id>` | (no extra flags) |
| `share <id>` | `--format text\|html` (required) |
| `export [OUT]` | `--category` `--tag` `--type` `--id` (each repeatable; same kind = OR, different kinds = AND), `--scope all\|global\|project` (default `all`), `--source NAME`, `--no-html`, `--force`. `OUT` is a file or directory; default name is `refshare-YYYY-MM-DD.refshare.zip` in the current directory. |
| `inspect <bundle>` | (no extra flags) validates a bundle and lists its contents; writes nothing |
| `import <bundle>` | `--project` (default target is global), `--category` `--tag` `--type` `--id` (repeatable filters), `--on-conflict skip\|overwrite\|rename\|newer` (default `skip`), `--dry-run` |

`ref_type` must be one of the values in `scripts/ref_types.json`; if a
command rejects your `--ref-type`, the error message lists the valid types.
Add a new type by editing that file directly.

`--link`'s `type` (in `type:label:url`) is freeform and not validated —
prefer `page`, `chat-channel`, `repo`, or `doc` for consistency, but any
value works.

## Workflows

**Add a reference from a URL.** Fetch the URL with WebFetch, draft a brief
description plus a plain-text blurb and a simplified-HTML blurb suitable for
pasting elsewhere. If the right audience scope (`category`) isn't obvious
from context, ask the user before saving — it gates who this can be shared
with later. Then call `add` with all of these fields. If the content is
large enough to be awkward as individual flags (e.g. a long `--share-html`
blurb), pipe a JSON payload with those same fields (`title`, `ref_type`,
`category`, `tags`, `links`, `description`, `share_text`, `share_html`) to
`add --from-json -` instead.

**Add a reference via a direct request** (e.g. "create a refshare reference
about project blue-jaguar"), with no URL: compose the same fields from
conversation context/your own knowledge instead of a fetched page, then
call `add` the same way.

**Edit a reference.** Resolve which reference the user means — by id if
they gave one, otherwise via `search`/`list` and asking them to pick — then
call `edit` with only the fields that changed.

**Categorize or tag.** There's no separate command; set `--category`/`--tag`
on `add` or `edit`. Confirm the audience scope with the user before saving a
new reference if it isn't already clear.

**Remove a reference.** This is destructive. Confirm the specific reference
and scope with the user before calling `remove` — never guess which scope
to delete from.

**View, browse, or search.** Use `list`/`search`/`show` and present the
results conversationally — don't paste raw CLI JSON at the user.

**Share a reference.** Once a reference is chosen, call `share --format
text` for a plain-chat destination (e.g. a Slack DM) or `share --format
html` for a rich-text destination (e.g. an email body). Then deliver that
content using whatever tool is already available in the session — an
installed Slack or Gmail integration, for instance — or simply present the
text for the user to copy themselves. refshare's own responsibility stops
at producing that content; it never calls a Slack/email API directly.

## Bundles

A bundle is a `*.refshare.zip` file holding a selection of references, so a
set can be shared with someone else, backed up, or moved to another machine.
It also contains an `index.html` that a recipient without refshare can open in
a browser to read the entries and copy share text.

**Export.** To share part of the library, run `export` with the filters the
user described (for example `--category acme-corp --tag devtool`). Export
everything with no filters for a backup. Tell the user where the file was
written and that it includes an `index.html`. If `--json` reports `warnings`
(for example an `--id` that matched nothing), relay them.

**Import.** Always look before you merge:

1. Run `inspect <bundle> --json` if the bundle came from someone else; treat it
   like any downloaded file.
2. Run `import <bundle> --dry-run --json` and summarize the plan for the user:
   what would be created, what is unchanged, and which entries conflict and
   which fields differ.
3. Only then run the real `import`. The default `--on-conflict skip` never
   overwrites local entries. Do not pass `overwrite`, `rename` or `newer` unless
   the user chose it after seeing the conflicts (`rename` keeps both copies,
   `newer` keeps whichever has the later `updated` date and skips ties).

Imports go to the global library unless the user asks for `--project`. An
invalid bundle is rejected as a whole and nothing is written. Import never
deletes anything.
