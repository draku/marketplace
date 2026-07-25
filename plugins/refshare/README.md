# refshare

A Claude Code plugin for managing a personal library of shareable references
— sites, tools, services, or any other resource — and sharing them via chat
or email.

If you've ever wanted a quick way to say "here's that thing" during a
conversation — a tool, a doc site, an internal service — refshare keeps a
searchable library of those references and hands back ready-to-paste content
(plain text or simplified HTML) for whatever channel you're using.

## Install

```
/plugin marketplace add draku/marketplace
/plugin install refshare@draku
/reload-plugins
```

Requires Python 3 (standard library only — no dependencies to install).

## How it works

Each reference is a single markdown file with frontmatter, stored in one of
two scopes:

- **Global** — `~/.claude/refshare/references/`, available in every project
- **Project** — `<repo>/.claude/refshare/references/`, scoped to the current
  project (shadows a global reference with the same id)

A reference has:

- `ref_type` — a category like `site`, `tool`, `service` (editable list in
  `scripts/ref_types.json`)
- `category` — an **audience scope**: who it's appropriate to share this
  with (e.g. `public`, or a named org like `acme-corp`)
- `tags` — freeform topical labels (e.g. `devtool`, `creative-writing`)
- `links` — one or more `{type, label, url}` entries
- a description, plus separate plain-text and simplified-HTML blurbs for
  sharing in different channels

refshare only produces that content — it never talks to Slack, email, or any
other communication API directly. Delivery is left to whatever tools are
already available in the session (or to you, copying and pasting).

## Usage

Once installed, just ask Claude naturally:

- "Save this as a reference: \<url\>"
- "Create a refshare reference for project blue-jaguar"
- "What references do I have tagged devtool?"
- "Share the Anthropic docs reference with me as plain text"

Or drive the CLI directly:

```bash
python3 scripts/refshare_cli.py add \
  --title "Anthropic Docs" --ref-type site --category public \
  --tag docs --tag ai \
  --link "page:Homepage:https://docs.anthropic.com" \
  --description "Official Anthropic developer documentation." \
  --share-text "Check out the Anthropic docs: https://docs.anthropic.com" \
  --share-html "<p>Check out the Anthropic docs.</p>"

python3 scripts/refshare_cli.py list
python3 scripts/refshare_cli.py search anthropic
python3 scripts/refshare_cli.py show anthropic-docs
python3 scripts/refshare_cli.py share anthropic-docs --format text
```

See `skills/refshare/SKILL.md` for the full command reference and agent
workflow guidance.

## License

MIT — see [LICENSE](LICENSE).
