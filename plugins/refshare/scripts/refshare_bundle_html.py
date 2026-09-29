from __future__ import annotations

import html
from urllib.parse import urlparse

MARKETPLACE_URL = "https://github.com/draku/marketplace"
INSTALL_LINES = (
    "/plugin marketplace add draku/marketplace",
    "/plugin install refshare@draku",
)
CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"

_STYLE = """
:root { --bg: #ffffff; --fg: #1d1d1f; --muted: #5f6368; --card: #f5f5f7; --line: #d8d8dc; --accent: #1a5fb4; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #16161a; --fg: #ececf0; --muted: #a0a0aa; --card: #202026; --line: #34343c; --accent: #7db3ff; }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px 64px; background: var(--bg); color: var(--fg);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 760px; margin: 0 auto; }
h1 { margin: 0 0 4px; font-size: 1.6rem; }
h2 { margin: 32px 0 12px; font-size: 1.15rem; border-bottom: 1px solid var(--line); padding-bottom: 4px; }
.meta, .ltype, .inert { color: var(--muted); font-size: 0.9rem; }
.entry { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 12px 16px; margin: 12px 0; }
.entry h3 { margin: 0 0 4px; font-size: 1.05rem; }
.tag { display: inline-block; border: 1px solid var(--line); border-radius: 999px; padding: 0 8px; margin-right: 4px; font-size: 0.8rem; color: var(--muted); }
ul.links { padding-left: 20px; margin: 8px 0; }
a { color: var(--accent); }
pre { white-space: pre-wrap; word-break: break-word; background: var(--bg); border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; margin: 8px 0; }
button { font: inherit; padding: 4px 12px; border: 1px solid var(--line); border-radius: 6px; background: var(--bg); color: var(--fg); cursor: pointer; }
.about { margin-top: 40px; border-top: 2px solid var(--line); padding-top: 16px; }
"""

_SCRIPT = (
    "document.addEventListener('click',function(e){"
    "var b=e.target.closest('button.copy');if(!b)return;"
    "var t=document.getElementById(b.dataset.target).textContent;"
    "if(navigator.clipboard){navigator.clipboard.writeText(t).then(function(){b.textContent='Copied';});}"
    "});"
)


def _e(value) -> str:
    return html.escape(str(value), quote=True)


def _is_safe_link(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _render_link(link: dict) -> str:
    url = link.get("url", "")
    label = _e(link.get("label") or url)
    ltype = _e(link.get("type", ""))
    if _is_safe_link(url):
        return (f'<li><span class="ltype">{ltype}</span> '
                f'<a href="{_e(url)}" rel="noopener noreferrer">{label}</a></li>')
    return f'<li><span class="ltype">{ltype}</span> {label} <span class="inert">{_e(url)}</span></li>'


def _render_entry(ref, index: int) -> str:
    tags = "".join(f'<span class="tag">{_e(t)}</span>' for t in ref.tags)
    links = "".join(_render_link(link) for link in ref.links)
    links_html = f'<ul class="links">{links}</ul>' if links else ""
    share_id = f"share-{index}"
    return (
        '<section class="entry">'
        f"<h3>{_e(ref.title)}</h3>"
        f'<div class="meta">{_e(ref.ref_type)} {tags}</div>'
        f"<p>{_e(ref.description)}</p>"
        f"{links_html}"
        f'<pre id="{share_id}">{_e(ref.share_text)}</pre>'
        f'<button class="copy" type="button" data-target="{share_id}">Copy text</button>'
        f"<details><summary>HTML version (source)</summary><pre>{_e(ref.share_html)}</pre></details>"
        "</section>"
    )


def _render_about() -> str:
    install = "\n".join(INSTALL_LINES)
    return (
        '<section class="about"><h2>About refshare</h2>'
        "<p>refshare keeps a small library of shareable references (sites, tools, services, "
        "resources) and helps you share them by chat or email. It runs inside Claude Code. "
        "This file is a refshare bundle: the entries above are a snapshot someone chose to share.</p>"
        f'<p>Get refshare from the marketplace: <a href="{_e(MARKETPLACE_URL)}" '
        f'rel="noopener noreferrer">{_e(MARKETPLACE_URL)}</a></p>'
        f"<pre>{_e(install)}</pre>"
        "<p>To import this bundle, ask Claude to &quot;import this refshare bundle&quot;, "
        "or run <code>refshare import &lt;file&gt;</code>. Nothing is overwritten unless you say so.</p>"
        "</section>"
    )


def render_index_html(manifest: dict, refs: list) -> str:
    name = manifest.get("source") or "refshare bundle"
    created = str(manifest.get("created", ""))[:10]
    count = len(refs)
    noun = "reference" if count == 1 else "references"
    by_category: dict[str, list] = {}
    for ref in refs:
        by_category.setdefault(ref.category, []).append(ref)
    body = []
    index = 0
    for category in sorted(by_category):
        body.append(f"<h2>{_e(category)}</h2>")
        for ref in sorted(by_category[category], key=lambda r: r.title.lower()):
            body.append(_render_entry(ref, index))
            index += 1
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">'
        f"<title>{_e(name)}</title><style>{_STYLE}</style></head><body><main>"
        f"<h1>{_e(name)}</h1>"
        f'<div class="meta">{count} {noun} · exported {_e(created)}</div>'
        f"{''.join(body)}{_render_about()}"
        f"</main><script>{_SCRIPT}</script></body></html>\n"
    )
