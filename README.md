# draku's Claude Code plugin marketplace

Public marketplace for Claude Code plugins/skills published by draku.

## Install

Add this marketplace once:

```
/plugin marketplace add draku/marketplace
```

Then install any plugin listed below:

| Plugin | Install |
|---|---|
| `refshare` | `/plugin install refshare@draku` |

## What this is

Each plugin under `plugins/` is a built copy synced from its own private
development repo via `scripts/sync-plugin.sh`. Development, tests, and
design history for each plugin happen in that plugin's own repo — this
repo only carries the files needed to install and run it.

## License

MIT — see [LICENSE](LICENSE).
