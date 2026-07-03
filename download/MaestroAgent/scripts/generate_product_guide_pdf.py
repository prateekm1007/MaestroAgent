#!/usr/bin/env python3
"""Generate MaestroAgent_Product_Guide.pdf from PRODUCT_GUIDE.md.

Converts the markdown to styled HTML, then renders to PDF with WeasyPrint.
The PDF embeds all 30 screenshots and is saved to /home/z/my-project/download/.
"""
from __future__ import annotations
import subprocess, sys
from pathlib import Path

ROOT = Path("/home/z/my-project/maestro-audit/MaestroAgent/download/MaestroAgent")
MD = ROOT / "docs/PRODUCT_GUIDE.md"
OUT_DIR = Path("/home/z/my-project/download")
OUT_DIR.mkdir(parents=True, exist_ok=True)
PDF = OUT_DIR / "MaestroAgent_Product_Guide.pdf"

# Step 1: markdown → HTML (via pandoc, with proper image base path)
html_body = subprocess.run(
    ["pandoc", str(MD), "-f", "markdown", "-t", "html5", "--no-highlight"],
    capture_output=True, text=True, check=True,
).stdout

# Step 2: wrap in styled HTML with print-friendly CSS
# Images use relative paths (screenshots/xxx.png) — we set the base URL to docs/
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Maestro — Product Guide</title>
<style>
  @page {{
    size: A4;
    margin: 18mm 16mm 18mm 16mm;
    @bottom-center {{
      content: counter(page) " / " counter(pages);
      font-family: 'Helvetica', sans-serif;
      font-size: 9pt;
      color: #888;
    }}
  }}
  body {{
    font-family: 'Helvetica', 'Arial', sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1a1a1a;
    max-width: 100%;
  }}
  h1 {{
    font-size: 26pt;
    color: #000;
    border-bottom: 3px solid #FFC629;
    padding-bottom: 8pt;
    margin-top: 0;
    margin-bottom: 16pt;
  }}
  h2 {{
    font-size: 16pt;
    color: #000;
    border-bottom: 1px solid #ddd;
    padding-bottom: 4pt;
    margin-top: 28pt;
    page-break-after: avoid;
  }}
  h3 {{
    font-size: 12.5pt;
    color: #3A3A3A;
    margin-top: 18pt;
    margin-bottom: 6pt;
    page-break-after: avoid;
  }}
  p {{
    margin: 4pt 0 8pt 0;
  }}
  blockquote {{
    border-left: 3px solid #FFC629;
    background: #FFF8E1;
    padding: 8pt 12pt;
    margin: 8pt 0;
    font-size: 9.5pt;
    color: #444;
  }}
  blockquote p {{
    margin: 3pt 0;
  }}
  img {{
    max-width: 100%;
    height: auto;
    border: 1px solid #e5e5e5;
    border-radius: 8px;
    display: block;
    margin: 8pt 0;
  }}
  hr {{
    border: none;
    border-top: 1px solid #eee;
    margin: 14pt 0;
  }}
  em {{
    color: #666;
    font-size: 9pt;
  }}
  strong {{
    color: #000;
  }}
  code {{
    background: #f4f4f4;
    padding: 1pt 3pt;
    border-radius: 3px;
    font-size: 9pt;
    font-family: 'Menlo', 'Monaco', monospace;
  }}
  /* Each surface section starts on a new page for clean demo flow */
  h3 {{
    page-break-before: auto;
  }}
</style>
</head>
<body>
{html_body}
</body>
</html>
"""

# Step 3: HTML → PDF via WeasyPrint (base_url so relative image paths resolve)
from weasyprint import HTML
HTML(string=html, base_url=str(ROOT / "docs")).write_pdf(str(PDF))
print(f"Wrote {PDF} ({PDF.stat().st_size // 1024} KB)")
