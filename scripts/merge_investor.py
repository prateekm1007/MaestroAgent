#!/usr/bin/env python3
"""Merge investor cover + body into final PDF."""
from pypdf import PdfReader, PdfWriter
import os

A4_W, A4_H = 595.28, 841.89
COVER = "/home/z/my-project/scripts/cover_investor.pdf"
BODY = "/home/z/my-project/scripts/body_investor.pdf"
FINAL = "/home/z/my-project/download/Maestro-Investor-Briefing.pdf"

def normalize_page_to_a4(page):
    box = page.mediabox
    w, h = float(box.width), float(box.height)
    if abs(w - A4_W) > 0.5 or abs(h - A4_H) > 0.5:
        page.scale_to(A4_W, A4_H)
    return page

writer = PdfWriter()
writer.add_page(normalize_page_to_a4(PdfReader(COVER).pages[0]))
for page in PdfReader(BODY).pages:
    writer.add_page(normalize_page_to_a4(page))

writer.add_metadata({
    '/Title': 'Maestro — Investor Briefing',
    '/Author': 'Z.ai',
    '/Creator': 'Z.ai',
    '/Subject': 'Investor briefing: what Maestro does, its moat, functions, value, and future evolution',
    '/Keywords': 'Maestro, investor, Series A, cognitive companion, organizational intelligence, personal mode',
})

with open(FINAL, 'wb') as f:
    writer.write(f)

size = os.path.getsize(FINAL)
print(f"Final PDF: {FINAL}")
print(f"Size: {size/1024:.1f} KB")
print(f"Pages: {len(writer.pages)}")
