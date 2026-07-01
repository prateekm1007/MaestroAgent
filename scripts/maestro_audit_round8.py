"""
Maestro Product Philosophy Re-Review — Round 8
The Invisible Maestro, take 2: did the coder actually collapse the sidebar?

The round-7 review found the coder ADDED 4 surfaces on top of 22 old ones
(23 total) and claimed "22 → 4." This round verifies whether commit c578d5f
genuinely collapses the sidebar as claimed. Every claim re-verified against
source. Test regressions checked.
"""

from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)

FONT_BODY = "NotoSerif"
FONT_BODY_B = "NotoSerifB"
FONT_HEAD = "NotoSans"
FONT_HEAD_B = "NotoSansB"
FONT_MONO = "Mono"

pdfmetrics.registerFont(TTFont(FONT_BODY, "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"))
pdfmetrics.registerFont(TTFont(FONT_BODY_B, "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"))
pdfmetrics.registerFont(TTFont(FONT_HEAD, "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"))
pdfmetrics.registerFont(TTFont(FONT_HEAD_B, "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont(FONT_MONO, "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"))

PAGE_BG       = colors.HexColor('#ffffff')
SECTION_BG    = colors.HexColor('#f3f4f5')
CARD_BG       = colors.HexColor('#f1f3f4')
TABLE_STRIPE  = colors.HexColor('#f5f6f7')
HEADER_FILL   = colors.HexColor('#1f2937')
BORDER        = colors.HexColor('#c7ccd1')
ACCENT        = colors.HexColor('#7c3aed')
TEXT_PRIMARY  = colors.HexColor('#1a1c1e')
TEXT_MUTED    = colors.HexColor('#6b7178')

ST_DELIVERED  = colors.HexColor('#15803d')
ST_PARTIAL    = colors.HexColor('#b45309')
ST_FAILED     = colors.HexColor('#b91c1c')

def styles():
    s = {}
    s['title'] = ParagraphStyle('title', fontName=FONT_HEAD_B, fontSize=24,
                                leading=28, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=6)
    s['h1'] = ParagraphStyle('h1', fontName=FONT_HEAD_B, fontSize=16,
                             leading=20, textColor=ACCENT, spaceBefore=18, spaceAfter=8, keepWithNext=1)
    s['h2'] = ParagraphStyle('h2', fontName=FONT_HEAD_B, fontSize=12.5,
                             leading=16, textColor=HEADER_FILL, spaceBefore=12, spaceAfter=4, keepWithNext=1)
    s['body'] = ParagraphStyle('body', fontName=FONT_BODY, fontSize=9.5,
                               leading=14, textColor=TEXT_PRIMARY, alignment=TA_JUSTIFY, spaceAfter=6)
    s['body_left'] = ParagraphStyle('body_left', fontName=FONT_BODY, fontSize=9.5,
                                    leading=14, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=6)
    s['callout'] = ParagraphStyle('callout', fontName=FONT_BODY, fontSize=9.5,
                                  leading=14, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4,
                                  leftIndent=10, rightIndent=10)
    s['small'] = ParagraphStyle('small', fontName=FONT_BODY, fontSize=8.5,
                                leading=12, textColor=TEXT_MUTED, alignment=TA_LEFT, spaceAfter=4)
    s['label'] = ParagraphStyle('label', fontName=FONT_HEAD_B, fontSize=8.5,
                                leading=11, textColor=TEXT_MUTED, alignment=TA_LEFT, spaceAfter=2)
    s['verdict'] = ParagraphStyle('verdict', fontName=FONT_HEAD_B, fontSize=14,
                                  leading=18, textColor=colors.white, alignment=TA_CENTER, spaceAfter=6)
    return s

S = styles()

PAGE_W, PAGE_H = A4
MARGIN_L = 18 * mm
MARGIN_R = 18 * mm
MARGIN_T = 22 * mm
MARGIN_B = 20 * mm

def _draw_chrome(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 8 * mm, PAGE_W, 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont(FONT_HEAD, 7.5)
    canvas.drawString(MARGIN_L, 12 * mm,
                      "Maestro Product Philosophy Re-Review — Round 8  ·  The Invisible Maestro, take 2  ·  Independent review")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro Product Philosophy Re-Review — Round 8",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="Round-8 re-review of the Invisible Maestro sidebar collapse",
        creator="Z.ai",
    )
    frame = Frame(MARGIN_L, MARGIN_B, PAGE_W - MARGIN_L - MARGIN_R,
                  PAGE_H - MARGIN_T - MARGIN_B, id='main',
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=_draw_chrome)])
    return doc

def P(text, style='body'):
    return Paragraph(text, S[style])

def callout_box(text, bg=SECTION_BG, border=BORDER, accent=None):
    if isinstance(text, str):
        content = [P(text, 'callout')]
    else:
        content = text
    t = Table([[content]], colWidths=[PAGE_W - MARGIN_L - MARGIN_R])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('BOX', (0, 0), (-1, -1), 0.5, border),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LINEBEFORE', (0, 0), (0, -1), 3, accent or border),
    ]))
    return t

def status_tag(status):
    color_map = {
        'DELIVERED': (ST_DELIVERED, 'DELIVERED'),
        'PARTIAL':   (ST_PARTIAL, 'PARTIAL'),
        'FAILED':    (ST_FAILED, 'REGRESSION'),
    }
    c, label = color_map[status]
    t = Table([[Paragraph(f'<font color="white"><b>{label}</b></font>', S['verdict'])]],
              colWidths=[72], rowHeights=[14])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t

def claim_block(num, claim, status, evidence, detail):
    status_color = {'DELIVERED': ST_DELIVERED, 'PARTIAL': ST_PARTIAL, 'FAILED': ST_FAILED}[status]
    header = Table([[
        status_tag(status),
        Paragraph(f'<font color="{status_color.hexval()}"><b>Claim #{num}</b></font>',
                  ParagraphStyle('claim_title', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=TEXT_PRIMARY, alignment=TA_LEFT))
    ]], colWidths=[76, PAGE_W - MARGIN_L - MARGIN_R - 76 - 24])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    body_flow = [
        Paragraph(f'<font color="{TEXT_MUTED.hexval()}"><b>Round-7 claim</b></font>', S['label']),
        P(claim, 'body_left'),
        Paragraph(f'<font color="{TEXT_MUTED.hexval()}"><b>Evidence verified at c578d5f</b></font>', S['label']),
        P(evidence, 'body_left'),
        Paragraph(f'<font color="{TEXT_MUTED.hexval()}"><b>Detail</b></font>', S['label']),
        P(detail, 'body_left'),
    ]
    body = Table([[body_flow]], colWidths=[PAGE_W - MARGIN_L - MARGIN_R - 24])
    body.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CARD_BG),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LINEBEFORE', (0, 0), (0, -1), 3, status_color),
    ]))
    return KeepTogether([header, body, Spacer(1, 8)])

def build_story():
    story = []

    # ── COVER ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f'<font color="{ACCENT.hexval()}"><b>ROUND 8 — PRODUCT PHILOSOPHY RE-REVIEW</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'The Invisible Maestro, take 2',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=30,
                       leading=34, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Did the coder actually collapse the sidebar, or add another layer?',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=14,
                       leading=18, textColor=HEADER_FILL, alignment=TA_LEFT, spaceAfter=14)
    ))

    meta = Table([
        [Paragraph('<b>Reviewer</b>', S['small']), P('Independent (Super Z, Z.ai)', 'small')],
        [Paragraph('<b>Commit</b>', S['small']), P('c578d5f — "fix(constitution-v2): collapse sidebar to 4 + fix dot orange + remove confidence numbers + fix law code leakage + real WORK data"', 'small')],
        [Paragraph('<b>Round-7 finding</b>', S['small']), P('Sidebar went 19 → 23 surfaces (coder claimed 22 → 4). Fundamental law violated. 5 of 13 Constitution claims NOT DELIVERED.', 'small')],
        [Paragraph('<b>Coder\'s round-8 claim</b>', S['small']), P('"Sidebar now 5 items (4 meta-surfaces + More…). Command palette (Ctrl+K). All 4 dot colors work. Confidence removed. Law codes stripped. WORK uses real data. 9 tests pass."', 'small')],
        [Paragraph('<b>Reviewer\'s verdict</b>', S['small']), Paragraph(f'<font color="{ST_DELIVERED.hexval()}"><b>DELIVERED — the sidebar collapse is genuine. 5 of 5 claimed fixes verified. 2 test regressions found (coder undercounted).</b></font>', S['small'])],
    ], colWidths=[35*mm, PAGE_W - MARGIN_L - MARGIN_R - 35*mm])
    meta.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LINEABOVE', (0, 0), (-1, 0), 0.5, BORDER),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, BORDER),
    ]))
    story.append(meta)
    story.append(Spacer(1, 6 * mm))

    # TL;DR
    story.append(callout_box([
        Paragraph(f'<font color="{ST_DELIVERED.hexval()}"><b>ROUND-8 EXECUTIVE SUMMARY (TL;DR)</b></font>',
                  ParagraphStyle('callout_h', fontName=FONT_HEAD_B, fontSize=10,
                                 leading=13, textColor=ST_DELIVERED, spaceAfter=4)),
        P('The coder\'s round-8 commit <font face="Mono">c578d5f</font> <b>genuinely collapses the sidebar</b>. '
          'This is the single biggest improvement in the entire 8-round engagement. '
          '<font face="Mono">grep -c "data-surface=" app.html</font> returns 4 (was 23 in round 7). The sidebar '
          'now shows: Today, Work, Ask, Learn, and a "More…" command-palette trigger. That is 5 items. The 22 '
          'old surfaces remain in the DOM (for backward compat + deep links) but are NOT in the sidebar. They '
          'are accessible only via Ctrl+K command palette or Ctrl+5-9 keyboard shortcuts. The Constitution\'s '
          'fundamental law — "more intelligence → less interface" — is now honored at the sidebar level.', 'body_left'),
        P('<b>All 5 claimed fixes are verified as delivered:</b> (1) sidebar collapsed to 5 items — verified by '
          'grep; (2) command palette is real — Ctrl+K handler, fuzzy search, grouped results, '
          '<font face="Mono">escapeJs</font> on surface ids, Escape/Enter/click-outside all work; (3) orange dot '
          'now works — <font face="Mono">pollOrgDotStatus()</font> fetches <font face="Mono">/contradictions</font> '
          'separately, and a live API test confirms 1 contradiction exists in the demo data, so the dot WILL turn '
          'orange; (4) confidence numbers removed from TODAY — line 55 now reads "Based on organizational '
          'patterns" (was "Based on 38% confidence"); (5) law codes + confidence stripped from ASK v2 — three '
          'new regex replacements (<font face="Mono">\\bL-\\d{4}\\b</font>, '
          '<font face="Mono">\\(confidence:\\s*[\\d.]+\\)</font>, '
          '<font face="Mono">\\bconfidence:\\s*[\\d.]+\\b</font>) verified end-to-end with a live API call: the '
          'answer "L-0001: priya.m@acme.com is a bottleneck - 3 evidence signals (confidence: 1.00)" becomes '
          '": priya.m@acme.com is a bottleneck - 3 evidence signals" with law codes and confidence both stripped.', 'body_left'),
        P('<b>WORK surface now uses real data.</b> GitHub, Slack, and Jira cards fetch from <font face="Mono">'
          '/dashboard</font> API — <font face="Mono">metrics.signals_processed</font>, '
          '<font face="Mono">metrics.learning_objects</font>, <font face="Mono">metrics.laws_inferred</font>, '
          '<font face="Mono">providers_connected</font>, and the contradiction count. Cards show "not connected" '
          'when the provider isn\'t configured. The round-7 "hardcoded placeholder" finding is closed for 3 of 4 '
          'cards. The Outlook card remains a bookmarklet prompt — honest, because there is no Outlook integration.', 'body_left'),
        P('<b>Two test regressions found</b> (coder undercounted). The coder claimed "9 tests pass, 0 failed" '
          'but only ran <font face="Mono">TestAppLoads</font> + <font face="Mono">TestOEMDataLoads</font> (9 '
          'tests). The full <font face="Mono">test_frontend_smoke.py</font> suite has 27 tests. At least 3 fail: '
          '<font face="Mono">test_navigate_to_inbox</font> and <font face="Mono">test_navigate_to_physics</font> '
          'click <font face="Mono">.sidebar-link[data-surface="inbox"]</font> and '
          '<font face="Mono">.sidebar-link[data-surface="physics"]</font> which no longer exist (they were '
          'removed in the collapse). Additionally, <font face="Mono">test_all_sidebar_links_exist</font> in '
          '<font face="Mono">test_comprehensive_qa.py</font> asserts all 19 old sidebar links exist — it now '
          'fails because the links were removed. These are legitimate test regressions: the tests test the old '
          'sidebar structure, which was correctly removed. The tests need to be updated to use '
          '<font face="Mono">navTo()</font> or the command palette instead of clicking sidebar links. '
          'Estimated fix: 30 minutes.', 'body_left'),
        P('<b>Updated Constitution adherence score: 7/10</b> (up from 5/10 in round 7). The sidebar collapse — '
          'the single most important finding from round 7 — is delivered. The fundamental law is now honored at '
          'the structural level. The remaining gaps from round 7 are: (a) WORK is still a page inside Maestro, '
          'not ambient tool-following (no browser extension/Slack bot/Jira add-on); (b) ASK v2 is still keyword '
          'search underneath (the frontend rephrases; the backend doesn\'t translate intentions); (c) 6-question '
          'narratives not implemented; (d) vocabulary hiding still only applies to ASK v2, not the 22 old '
          'surfaces (though they are now hidden behind the command palette, so a user is less likely to see '
          'them); (e) 2 test regressions need fixing. Items (a)-(c) are multi-week work; (d) is partially '
          'mitigated by the sidebar collapse; (e) is a 30-minute fix.', 'body_left'),
        P('<b>Updated verdict: YES WITH MINOR FIXES.</b> The sidebar collapse is the paradigm shift the '
          'Constitution demanded. The product now genuinely feels calmer — 4 surfaces + a command palette, not '
          '22 surfaces + 4 layers. The 2 test regressions are the only blocker; once fixed, the product returns '
          'to the round-6 "YES" status for the security/operational axis AND achieves "YES WITH MINOR FIXES" '
          'on the product-philosophy axis. The remaining Constitution gaps (ambient WORK, intention translation, '
          '6-question narratives) are post-pilot milestones, not blockers.', 'body_left'),
    ], bg=colors.HexColor('#f0fdf4'), border=colors.HexColor('#bbf7d0'), accent=ST_DELIVERED))

    story.append(Spacer(1, 6 * mm))

    # ── CLAIM-BY-CLAIM ───────────────────────────────────────────────────
    story.append(P('Round-8 Claims — Delivery Status', 'h1'))

    rows = [
        ['#', 'Round-8 Claim', 'Status', 'Evidence (verified at c578d5f)'],
        ['1', 'Sidebar collapsed: 22 surfaces → 4 (+ More…)', 'DELIVERED', 'grep -c "data-surface=" app.html = 4. Sidebar shows: Today, Work, Ask, Learn, More…. 19 old surfaces removed from sidebar, remain in DOM. Command palette (Ctrl+K) provides access.'],
        ['2', 'Command palette (Ctrl+K) is real and functional', 'DELIVERED', 'maestro.js lines 113-211: Ctrl+K handler, openCommandPalette(), filterCommandPalette() with fuzzy search, renderPaletteResults() with grouped headers, selectFirstPaletteResult() on Enter, Escape closes, click-outside closes, escapeJs on surface ids. 19 surfaces listed in _hiddenSurfaces array.'],
        ['3', 'Organizational Dot orange state works', 'DELIVERED', 'org_dot.js pollOrgDotStatus() now fetches /contradictions API separately (line 4-5). today.js determineDotColor() accepts contradictions array and checks length > 0 for orange (line 162). Live API test: /contradictions returns 1 contradiction in demo data → dot WILL turn orange. All 4 colors work.'],
        ['4', 'Confidence numbers removed from TODAY', 'DELIVERED', 'today.js line 55: provenance: ot.rec_id ? `Based on organizational patterns` : \'\' — the "% confidence" string is gone. Replaced with Constitution-compliant "Based on organizational patterns."'],
        ['5', 'Law codes + confidence stripped from ASK v2', 'DELIVERED', 'ask_v2.js lines 95-98: three new regex replacements. Live API test: "L-0001: priya.m@acme.com is a bottleneck — 3 evidence signals (confidence: 1.00)" → ": priya.m@acme.com is a bottleneck — 3 evidence signals." Law codes stripped. Confidence stripped. Internal terms stripped.'],
        ['6', 'WORK surface uses real API data, not hardcoded', 'DELIVERED', 'work.js lines 18-21: fetches /dashboard API. Lines 63-90: GitHub card uses metrics.signals_processed + providers.includes("github"). Slack card uses contradiction count. Jira card uses metrics.learning_objects + metrics.laws_inferred. All show "not connected" if provider unconfigured. Outlook card is honestly a bookmarklet prompt.'],
        ['7', 'No test regressions ("9 tests pass, 0 failed")', 'REGRESSION', 'Coder ran only TestAppLoads + TestOEMDataLoads (9 tests). Full test_frontend_smoke.py has 27 tests. test_navigate_to_inbox + test_navigate_to_physics fail (click removed sidebar links). test_all_sidebar_links_exist in test_comprehensive_qa.py fails (asserts 19 old links exist). At least 3 regressions.'],
    ]
    t = Table(rows, colWidths=[8*mm, 50*mm, 24*mm, PAGE_W - MARGIN_L - MARGIN_R - 82*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TEXTCOLOR', (2, 1), (2, 6), ST_DELIVERED),
        ('TEXTCOLOR', (2, 7), (2, 7), ST_FAILED),
        ('FONTNAME', (2, 1), (2, -1), FONT_HEAD_B),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>Scorecard: 6 DELIVERED, 1 REGRESSION.</b> The 6 delivered fixes are genuine and verified. The '
        'regression is a test-suite issue (3 tests assert the old sidebar structure), not a product defect. '
        'The coder should have run the full <font face="Mono">test_frontend_smoke.py</font> suite, not just '
        'the 9-test subset. 30-minute fix.', 'body'))

    story.append(PageBreak())

    # ── DETAILED FINDINGS ────────────────────────────────────────────────
    story.append(P('Detailed Findings', 'h1'))

    story.append(claim_block(
        1,
        '"Sidebar collapsed: 22 surfaces → 4 (+ More…)." (The headline round-7 finding, now claimed fixed)',
        'DELIVERED',
        'grep -c "data-surface=" app.html returns 4 (was 23 in round 7, 19 in round 6). The sidebar now contains exactly: Today, Work, Ask, Learn, and a "More…" command-palette trigger with a ⌘K hint. The 19 old sidebar links (home, inbox, simulator, hayek, flow, memory, ask, customer, physics, debate, live, intents, contradictions, predictions, assumptions, eng-signals, eng-oem, eng-audit, eng-settings) are removed from the sidebar HTML. They remain in the DOM as <section class="surface" id="surface-{name}"> elements for backward compatibility, deep links, and the command palette. The old "CEO Product" and "Cognitive Model" and "Engineering" section labels are gone. The HTML comment in the sidebar explicitly says: "the 22 old surfaces are NOT in the sidebar. They remain in the DOM (for backward compat + deep links) but are accessible only via the command palette (Ctrl+K or More…)."',
        'This is the most important fix in the entire 8-round engagement. The Constitution\'s fundamental law — "every increase in intelligence must reduce the amount of interface exposed" — was violated in round 7 because the interface increased (19 → 23). It is now honored: the sidebar went from 23 to 5. A first-time CEO sees 4 calm surfaces + a search trigger, not a 22-item feature catalogue. The old surfaces are still accessible (via Ctrl+K or navTo()), so no capability is lost — only clutter is removed. This is exactly what "collapse, compress, hide" means.'
    ))

    story.append(claim_block(
        2,
        '"Command palette (Ctrl+K) is real and functional."',
        'DELIVERED',
        'maestro.js lines 113-211 implement a genuine Linear/Raycast-style command palette: (a) Ctrl+K handler (line 113) calls openCommandPalette() with e.preventDefault(); (b) openCommandPalette() (line 145) creates a modal with a search input + results div, appends to body, focuses input; (c) filterCommandPalette() (line 181) does fuzzy substring search on label + id; (d) renderPaletteResults() (line 193) groups results by category (CEO Product / Cognitive Model / Engineering) with uppercase headers; (e) each result has onclick="navTo(\'{id}\');closeCommandPalette()" with escapeJs on the id; (f) Escape closes (line 158); (g) Enter selects first result (line 158); (h) click-outside closes (line 162-164). The _hiddenSurfaces array (line 123) lists all 19 deep surfaces with human-readable labels. The sidebar "More…" trigger (app.html) calls openCommandPalette() on click and Enter/Space.',
        'This is a real command palette, not a stub. It has the expected keyboard ergonomics (Ctrl+K, Escape, Enter), fuzzy search, grouped results, and click-outside-to-close. The escapeJs on the surface id is defense-in-depth (the ids are hardcoded, not user-controlled, but the pattern is correct). One minor gap: there is no ArrowUp/ArrowDown navigation through results — the user must use the mouse or Enter-on-first-result. This is a 15-minute enhancement, not a blocker.'
    ))

    story.append(claim_block(
        3,
        '"Organizational Dot orange state works." (Round-7 finding: orange was dead code)',
        'DELIVERED',
        'org_dot.js pollOrgDotStatus() (line 1-13) now does Promise.all([api.getOEM(\'/ceo-briefing\'), api.getOEM(\'/contradictions\').catch(() => ({contradictions: []}))]) — fetching the contradictions API separately with a fallback. today.js determineDotColor() (line 156-168) accepts a second parameter (contradictionsOrPulse) that can be an array or an object with .contradictions, and checks contradictions.length > 0 to return "orange". loadToday() (line 26-33) also fetches /contradictions and passes the array to renderMorningBrief. Live API verification: GET /api/oem/contradictions returns {"contradictions": [{"contradiction_id": "contr-bbf6d678c212", "title": "Commitment integrity gap: 2 broken vs 1 kept", ...}], "total": 1}. With 1 contradiction, contradictions.length = 1 > 0, so the dot returns "orange". All 4 colors now work.',
        'The round-7 finding was that determineDotColor checked briefing.contradictions, which does not exist in the /ceo-briefing response. The fix correctly fetches /contradictions separately. The dot can now be green (default), yellow (overnight changes), orange (contradictions exist), or red (urgent one_thing). The round-7 "dead code" finding is closed.'
    ))

    story.append(claim_block(
        4,
        '"Confidence numbers removed from TODAY." (Constitution: "Never expose confidence numbers alone")',
        'DELIVERED',
        'today.js line 55 (was line 53 in round 7): provenance: ot.rec_id ? `Based on organizational patterns` : \'\' — the old Math.round(ot.confidence * 100) + \'% confidence\' string is gone. The provenance now reads "Based on organizational patterns" — Constitution-compliant. The confidence value is still used internally for ranking (determineDotColor checks urgency, not confidence), but it is no longer displayed as a percentage to the user.',
        'The Constitution said "Never expose confidence numbers alone. Trust through provenance, never through percentages." TODAY no longer exposes percentages. The fix is a one-line change but it closes a Constitution violation. The confidence-as-story pattern (from ASK v2: "We\'ve seen this pattern consistently") is not yet applied to TODAY — TODAY just says "Based on organizational patterns" without the story. This is acceptable for the pilot; the story pattern could be added later.'
    ))

    story.append(claim_block(
        5,
        '"Law codes + confidence stripped from ASK v2." (Round-7 finding: L-0001 and (confidence: 1.00) leaked through)',
        'DELIVERED',
        'ask_v2.js lines 95-98 add three new regex replacements after the existing vocabulary replacements: (1) .replace(/\\bL-\\d{4}\\b/g, \'\') — strips law codes like "L-0001"; (2) .replace(/\\(confidence:\\s*[\\d.]+\\)/gi, \'\') — strips "(confidence: 1.00)" parentheticals; (3) .replace(/\\bconfidence:\\s*[\\d.]+\\b/gi, \'\') — strips bare "confidence: 1.00". Line 100 also adds .replace(/\\s+/g, \' \') to clean up double spaces left by the removals. Live API verification: raw answer "Based on 2 relevant execution law(s): • L-0001: priya.m@acme.com is a bottleneck — 3 evidence signals across 3 observations (confidence: 1.00) • L-0002: carlos.r@acme.com..." becomes "Based on 2 relevant execution pattern(s): • : priya.m@acme.com is a bottleneck — 3 evidence signals across 3 observations • : carlos.r@acme.com..." — law codes stripped, confidence stripped, internal terms replaced.',
        'The fix works. There is a minor cosmetic issue: the "• :" with an empty code looks slightly awkward (the law code was stripped but the bullet and colon remain). This is a cosmetic polish item, not a Constitution violation. A better fix would be to also strip the "• :" prefix when the code is removed, but the current state is acceptable — the user sees a clean narrative without internal identifiers. The round-7 "law code leakage" finding is closed.'
    ))

    story.append(claim_block(
        6,
        '"WORK surface uses real API data, not hardcoded." (Round-7 finding: GitHub/Slack/Jira cards were hardcoded placeholders)',
        'DELIVERED',
        'work.js loadWork() (line 18-21) now does Promise.all([api.getOEM(\'/ceo-briefing\'), api.getOEM(\'/contradictions\').catch(...), api.getOEM(\'/dashboard\').catch(() => null)]). renderWorkSurface() (line 33) accepts dashboard as a third parameter. Lines 37-38: const metrics = dashboard ? dashboard.metrics || {} : {}; const providers = dashboard ? dashboard.providers_connected || [] : [];. GitHub card (line 63-70): githubConnected = providers.includes(\'github\'); message shows metrics.signals_processed + decision count if connected, "GitHub is not connected" if not. Slack card (line 73-81): shows contradiction count if connected, "not connected" if not. Jira card (line 84-90): shows metrics.learning_objects + metrics.laws_inferred if connected, "not connected" if not. Outlook card (line 93-97): still a bookmarklet prompt (honest — no Outlook integration exists).',
        '3 of 4 cards now use real data. The round-7 "hardcoded placeholder" finding is closed for GitHub, Slack, and Jira. The Outlook card is honestly a configuration prompt, not a fake data display. The WORK surface is still not "ambient tool-following" (the Constitution\'s vision of Maestro appearing inside GitHub/Slack/Jira/Zoom) — it is still a page inside Maestro that shows what Maestro sees in your tools. But the data is now real, not fabricated. The ambient-integration gap remains a post-pilot milestone (requires building a Chrome extension, Slack bot, etc.).'
    ))

    story.append(claim_block(
        7,
        '"9 tests pass, 0 failed." (Coder\'s claim of no test regressions)',
        'FAILED',
        'The coder ran only TestAppLoads (6 tests) + TestOEMDataLoads (3 tests) = 9 tests, all of which pass. But the full test_frontend_smoke.py suite has 27 tests. The coder did not run TestNavigation (5 tests), of which at least 2 fail: test_navigate_to_inbox (line 169) clicks .sidebar-link[data-surface="inbox"] which no longer exists in the sidebar — Playwright times out. test_navigate_to_physics (line 183) clicks .sidebar-link[data-surface="physics"] — same failure. Additionally, test_comprehensive_qa.py::TestEveryInteractiveElement::test_all_sidebar_links_exist (line 217) asserts data-surface="home" through data-surface="eng-settings" are all in the HTML — this now fails because the sidebar links were removed (the surfaces still exist as <section id="surface-{name}">, but the data-surface attribute is only on sidebar links). At least 3 test regressions confirmed.',
        'These are legitimate test regressions, not product defects. The tests test the old sidebar structure, which was correctly removed. The tests need to be updated: (1) test_navigate_to_inbox and test_navigate_to_physics should use page.evaluate("navTo(\'inbox\')") instead of clicking sidebar links; (2) test_all_sidebar_links_exist should check for id="surface-{name}" instead of data-surface="{name}", since the surfaces are now in the DOM but not the sidebar. Estimated fix: 30 minutes. The coder should have run the full suite before claiming "0 failed." This is the same pattern as round 3 (coder claimed "837+ tests pass" but 18 failed) — the coder tends to run a subset and report the subset\'s result as the full result.'
    ))

    # ── WHAT REMAINS FROM ROUND 7 ────────────────────────────────────────
    story.append(P('Round-7 Findings Still Open (Not Addressed in c578d5f)', 'h1'))
    story.append(P(
        'The following round-7 findings were NOT addressed in commit <font face="Mono">c578d5f</font>. They are '
        'listed here for tracking. Most are multi-week work items, not single-commit fixes.', 'body'))

    story.append(P(
        '<b>WORK is still a page inside Maestro, not ambient tool-following.</b> The Constitution\'s vision was '
        '"The user never opens Maestro. Maestro quietly appears [inside GitHub/Slack/Jira/Zoom]." The actual '
        'WORK surface is a page inside Maestro with cards that fetch real data. To deliver the vision requires '
        'building native integrations: a Chrome extension for GitHub/Jira, a Slack bot, a Zoom app, an Outlook '
        'add-in. That is weeks of work per platform. The round-8 fix made the cards real (no more hardcoded '
        'placeholders), which is a genuine improvement, but the ambient-integration vision is not delivered. '
        'Post-pilot milestone.', 'body'))

    story.append(P(
        '<b>ASK v2 is still keyword search underneath.</b> The frontend rephrases the experience as '
        'intention-based; the backend still does keyword substring matching (decision.py answer_question, '
        'unchanged since round 3). The Constitution said "The system translates intentions into organizational '
        'knowledge." The system does not translate — it searches. To deliver this requires an LLM or '
        'semantic-matching layer. Post-pilot milestone.', 'body'))

    story.append(P(
        '<b>6-question narratives not implemented.</b> The Constitution required every recommendation to '
        'automatically answer: Why now? Why me? Why this? What if ignored? How do we know? Who already solved '
        'it? None of the 4 new surfaces do this. TODAY shows label + title + context + provenance (4 fields, '
        'not 6 questions). This is a significant backend + frontend task. Post-pilot milestone.', 'body'))

    story.append(P(
        '<b>Vocabulary hiding still only applies to ASK v2.</b> The 22 old surfaces (now hidden behind the '
        'command palette) still display "Law", "Learning Object", "Receipt", "OEM" directly. A user who opens '
        'the command palette and navigates to "Physics" sees "Organizational Laws" with "L-0001" codes. The '
        'sidebar collapse mitigates this (users are less likely to visit the old surfaces), but does not solve '
        'it. The regex replacement utility should be extracted and applied to all surfaces. 1-2 days of work.', 'body'))

    story.append(P(
        '<b>2 test regressions need fixing.</b> test_navigate_to_inbox, test_navigate_to_physics, and '
        'test_all_sidebar_links_exist fail because they test the old sidebar structure. 30-minute fix: update '
        'the tests to use navTo() or check id="surface-{name}" instead of data-surface="{name}".', 'body'))

    # ── SCORES ───────────────────────────────────────────────────────────
    story.append(P('Updated Constitution Adherence Score — Round 8', 'h1'))

    score_rows = [
        ['Constitution Dimension', 'R7', 'R8', 'Change', 'Justification'],
        ['Sidebar collapse (fundamental law)', '2/10', '9/10', '+7', 'Sidebar genuinely collapsed: 23 → 5 items. Command palette provides access. Fundamental law honored.'],
        ['TODAY calm morning brief', '7/10', '8/10', '+1', 'Confidence numbers removed. Now fully Constitution-compliant. Could add confidence-as-story.'],
        ['WORK ambient tool-following', '2/10', '3/10', '+1', 'Cards now fetch real data (was hardcoded). Still a page inside Maestro, not ambient. Post-pilot.'],
        ['ASK intention translation', '3/10', '3/10', '—', 'Law codes + confidence stripped (good). Still keyword search underneath. Post-pilot.'],
        ['LEARN stories not metrics', '8/10', '8/10', '—', 'Unchanged from round 7. Already genuine.'],
        ['Organizational Dot', '6/10', '9/10', '+3', 'Orange state now works (fetches /contradictions). All 4 colors functional.'],
        ['Vocabulary hiding', '4/10', '5/10', '+1', 'Law codes + confidence stripped from ASK v2. Still only ASK v2, but sidebar collapse mitigates.'],
        ['Contextual whispers', '4/10', '4/10', '—', 'Still inside the Maestro app, not ambient overlays. Unchanged.'],
        ['No charts / stories instead', '5/10', '5/10', '—', '4 new surfaces have no charts. 19 old surfaces (behind command palette) still do.'],
        ['Backend preserved', '10/10', '10/10', '—', 'No backend changes. All APIs intact.'],
        ['6-question narratives', '1/10', '1/10', '—', 'Not implemented. Post-pilot milestone.'],
        ['Test suite green', '10/10', '7/10', '-3', '3 test regressions from the sidebar collapse (tests assert old structure). 30-min fix.'],
        ['OVERALL Constitution adherence', '5/10', '7/10', '+2', 'Sidebar collapse is the big win. Fundamental law now honored. Remaining gaps are post-pilot.'],
    ]
    t = Table(score_rows, colWidths=[42*mm, 12*mm, 12*mm, 14*mm, PAGE_W - MARGIN_L - MARGIN_R - 80*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0fdf4')),
        ('TEXTCOLOR', (2, -1), (2, -1), ST_DELIVERED),
        ('FONTNAME', (1, 1), (3, -1), FONT_HEAD_B),
        ('ALIGN', (1, 0), (3, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    story.append(Spacer(1, 6 * mm))

    # ── VERDICT ──────────────────────────────────────────────────────────
    story.append(P('Updated Verdict — Round 8', 'h1'))

    verdict_box = Table([[
        Paragraph(
            '<font color="white" size="20"><b>YES WITH MINOR FIXES</b></font><br/><br/>'
            '<font color="white" size="11"><b>— sidebar collapse is the paradigm shift. Fix the 3 test regressions and ship the pilot.</b></font>',
            ParagraphStyle('v', fontName=FONT_HEAD_B, fontSize=20, leading=24,
                           textColor=colors.white, alignment=TA_CENTER)
        )
    ]], colWidths=[PAGE_W - MARGIN_L - MARGIN_R], rowHeights=[80])
    verdict_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ST_DELIVERED),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(verdict_box)
    story.append(Spacer(1, 6 * mm))

    story.append(P(
        '<b>Why YES WITH MINOR FIXES and not PARTIAL.</b> The round-7 verdict was PARTIAL ("genuine visual '
        'craft, but the fundamental law is violated — the interface INCREASED"). The round-8 commit fixes the '
        'fundamental law. The sidebar went from 23 surfaces to 5. The 22 old surfaces are hidden behind a '
        'command palette. A first-time CEO now sees 4 calm surfaces + a search trigger. This is the collapse '
        'the Constitution demanded. The paradigm shift — at the structural level — is delivered. The remaining '
        'gaps (ambient WORK, intention translation, 6-question narratives) are multi-week post-pilot milestones, '
        'not single-commit fixes. They do not block the pilot.', 'body'))

    story.append(P(
        '<b>Why YES WITH MINOR FIXES and not YES.</b> Three test regressions need fixing first. '
        '<font face="Mono">test_navigate_to_inbox</font> and <font face="Mono">test_navigate_to_physics</font> '
        'click sidebar links that were correctly removed. <font face="Mono">test_all_sidebar_links_exist</font> '
        'asserts the old sidebar structure. These are 30-minute fixes (update the tests to use '
        '<font face="Mono">navTo()</font> or check <font face="Mono">id="surface-{name}"</font> instead of '
        '<font face="Mono">data-surface="{name}"</font>). Once fixed, the test suite returns to green and the '
        'product is pilot-ready on both the security axis (round 6: YES) and the product-philosophy axis '
        '(round 8: YES WITH MINOR FIXES).', 'body'))

    story.append(P(
        '<b>The engagement arc across 8 rounds.</b> The product-philosophy axis moved PARTIAL (round 7, 5/10) '
        '→ YES WITH MINOR FIXES (round 8, 7/10). The security axis held at YES (round 6, 7/10). The single '
        'biggest improvement was the sidebar collapse — the one round-7 finding that mattered most. The coder '
        'listened to the round-7 review ("the coder added instead of collapsed"), understood the fundamental '
        'law, and delivered the collapse. The 5 additional fixes (command palette, orange dot, confidence '
        'removal, law code stripping, real WORK data) are all genuine. The one regression (3 test failures) '
        'is the same pattern as round 3: the coder ran a subset of tests and reported the subset\'s result as '
        'the full result. The coder should run the full <font face="Mono">test_frontend_smoke.py</font> suite '
        'before claiming "0 failed."', 'body'))

    story.append(P(
        '<b>What this review credits the coder with.</b> The round-8 commit is the right response to the '
        'round-7 review. The coder did not argue with the finding ("the auditor is right — I added instead of '
        'collapsed"). They fixed it. The sidebar collapse is a structural change, not a cosmetic one — it '
        'changes what the user sees first, what they navigate by, and how they think about the product. The '
        'command palette is the right access pattern for the hidden surfaces. The orange dot fix, the '
        'confidence removal, the law code stripping, and the real WORK data are all genuine. The 2 test '
        'regressions are an oversight, not a misrepresentation — the coder fixed the product but forgot to '
        'update the tests that tested the old product. Fix the tests, and the engagement can move to the '
        'pilot phase.', 'body'))

    story.append(P(
        '<b>The path forward.</b> Fix the 3 test regressions (30 minutes). Then the product is pilot-ready on '
        'both axes. The remaining Constitution gaps (ambient WORK, intention translation, 6-question narratives, '
        'universal vocabulary hiding) are post-pilot milestones — let the 90-day pilot determine whether they '
        'are needed. The sidebar collapse is the proof that the coder can deliver the Invisible Maestro vision '
        'when pushed. The next push should be the ambient-integration proof of concept (one real Chrome '
        'extension for GitHub). But that is post-pilot. Ship the pilot.', 'body'))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'MaestroAgent_Round8_Product_Philosophy_ReReview.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
