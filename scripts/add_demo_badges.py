"""
Add a "DEMO PROTOTYPE" banner to each <section class="surface"> in app.html.

The CEO product surfaces (inbox, simulator, hayek, etc.) are HTML prototypes
with hardcoded illustrative data. They are not yet wired to the OEM backend.
Per the verification checklist (item 5), every UI element must be backed by
real data OR explicitly labeled as placeholder. This script adds the labels.
"""

from pathlib import Path
import re

APP_HTML = Path("/home/z/my-project/download/MaestroAgent/app.html")

content = APP_HTML.read_text(encoding="utf-8")

# Pattern: <section class="surface" id="surface-XXX"> followed by <div class="p-6 ...">
# Insert a demo-banner div as the first child of the inner div.
SURFACE_PATTERN = re.compile(
    r'(<section class="surface" id="surface-([a-z\-]+)">\s*'
    r'<div class="p-[46] space-y-[45] max-w[^"]*">)',
    re.MULTILINE,
)

BANNER_TEMPLATE = (
    '<div class="flex items-center gap-2 text-[11px] text-amber-300 '
    'bg-amber-500/[0.04] border border-amber-500/20 rounded-md px-3 py-2" '
    'data-demo-banner="surface-{slug}">'
    '<span class="tag tag-amber">DEMO PROTOTYPE</span>'
    '<span>This surface is a product prototype. The decisions, laws, and '
    'recommendations shown are illustrative placeholders — wire to the OEM '
    'backend (<code class="mono text-fg-400">maestro_oem</code>) to see real '
    'organizational state.</span>'
    '</div>'
)

count = 0


def repl(match: re.Match) -> str:
    global count
    count += 1
    slug = match.group(2)
    return match.group(1) + "\n    " + BANNER_TEMPLATE.format(slug=slug)


new_content = SURFACE_PATTERN.sub(repl, content)

APP_HTML.write_text(new_content, encoding="utf-8")

print(f"Added DEMO PROTOTYPE banners to {count} surfaces in {APP_HTML}")
