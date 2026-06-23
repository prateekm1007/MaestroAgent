#!/usr/bin/env python3
"""Generate PWA PNG icons from the SVG source.

Requires: pip install cairosvg pillow
(or use any SVG-to-PNG converter; this script just wraps cairosvg).
"""
import sys
from pathlib import Path

try:
    import cairosvg
except ImportError:
    print("cairosvg not installed. Run: pip install cairosvg pillow", file=sys.stderr)
    sys.exit(1)

PUBLIC_DIR = Path(__file__).parent.parent / "public"
ICONS_DIR = PUBLIC_DIR / "icons"
ICONS_DIR.mkdir(parents=True, exist_ok=True)

svg_path = PUBLIC_DIR / "icon.svg"
if not svg_path.exists():
    print(f"SVG not found: {svg_path}", file=sys.stderr)
    sys.exit(1)

svg_content = svg_path.read_text()

# Generate icons at standard PWA sizes.
for size in [192, 512]:
    out = ICONS_DIR / f"icon-{size}.png"
    cairosvg.svg2png(
        bytestring=svg_content.encode(),
        write_to=str(out),
        output_width=size,
        output_height=size,
    )
    print(f"  generated {out}")

# Favicon
favicon = PUBLIC_DIR / "favicon.ico"
cairosvg.svg2png(
    bytestring=svg_content.encode(),
    write_to=str(PUBLIC_DIR / "favicon-32.png"),
    output_width=32,
    output_height=32,
)
print(f"  generated {PUBLIC_DIR / 'favicon-32.png'}")
print("Done.")
