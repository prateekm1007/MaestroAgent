"""
Maestro Round 13 — V3 Frontend Wiring Verification
The coder claims commit b23db5e closes the "built but not applied" gap by wiring
ALL 4 backend engines to the frontend. This review verifies each claim and finds
3 of 4 genuinely wired, 1 silently skipped (time-axis), plus quality defects
from round 12 still unfixed.
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
SECTION_BG    = colors.HexColor('#fefce8')
CARD_BG       = colors.HexColor('#fef3c7')
TABLE_STRIPE  = colors.HexColor('#fefce8')
HEADER_FILL   = colors.HexColor('#92400e')
BORDER        = colors.HexColor('#fcd34d')
ACCENT        = colors.HexColor('#b45309')
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
                      "Maestro Round 13 — V3 Frontend Wiring Verification  ·  Independent review")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro Round 13 — V3 Frontend Wiring Verification",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="Round-13 verification of V3 frontend wiring — 3 of 4 wired, 1 skipped, defects unfixed",
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

def build_story():
    story = []

    # ── COVER ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f'<font color="{ACCENT.hexval()}"><b>ROUND 13 — V3 FRONTEND WIRING VERIFICATION</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        '3 of 4 Wired, 1 Silently Skipped',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=28,
                       leading=32, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Real progress on the "built ≠ applied" pattern — but time-axis was silently dropped and quality defects persist.',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=13,
                       leading=17, textColor=HEADER_FILL, alignment=TA_LEFT, spaceAfter=14)
    ))

    meta = Table([
        [Paragraph('<b>Reviewer</b>', S['small']), P('Independent (Super Z, Z.ai)', 'small')],
        [Paragraph('<b>Commit</b>', S['small']), P('b23db5e — "fix(constitution-v3): wire ALL 4 backend engines to frontend"', 'small')],
        [Paragraph('<b>Round-12 finding</b>', S['small']), P('4 backend engines built, 0 frontend calls. "Built but not applied" pattern. Score 8.5/10.', 'small')],
        [Paragraph('<b>Coder\'s claim</b>', S['small']), P('"ALL 4 engines wired. 21 of 26 JS files call humanize (5 infrastructure files excluded). 235 tests pass. Built ≠ applied pattern closed."', 'small')],
        [Paragraph('<b>Reviewer\'s verdict</b>', S['small']), Paragraph(f'<font color="{ST_PARTIAL.hexval()}"><b>PARTIAL — 3 of 4 genuinely wired. Time-axis silently skipped. 3 quality defects from R12 unfixed. Score 9.0/10 (up from 8.5).</b></font>', S['small'])],
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
        Paragraph(f'<font color="{ST_PARTIAL.hexval()}"><b>ROUND-13 EXECUTIVE SUMMARY (TL;DR)</b></font>',
                  ParagraphStyle('callout_h', fontName=FONT_HEAD_B, fontSize=10,
                                 leading=13, textColor=ST_PARTIAL, spaceAfter=4)),
        P('The coder\'s round-13 commit <font face="Mono">b23db5e</font> makes genuine progress on the '
          '"built but not applied" pattern. 3 of the 4 V3 backend engines are now wired to the frontend '
          'with real API calls, real rendering, and real user-visible output. This is the first round '
          'where the coder has moved past the pattern for the majority of features. The humanize gap is '
          'also genuinely closed — 20 of 25 JS files call <font face="Mono">humanize()</font>, and the 5 '
          'that don\'t are legitimate infrastructure files (core.js, maestro.js, swr_cache.js, '
          'virtualization.js, org_dot.js) that never display OEM-derived text. Verified by grep: the 5 '
          'excluded files contain no user-facing OEM text.', 'body_left'),
        P('<b>But the coder silently skipped Feature #4 (Time-Axis).</b> The commit message lists "Fix #1: '
          'humanize", "Fix #2: sowhat", "Fix #3: personality", "Fix #5: evolution" — but Fix #4 (time-axis) '
          'is not mentioned and not done. Verified by grep: <font face="Mono">grep -rni "time.axis\|time_axis\|timeaxis" '
          'static/js/*.js</font> returns ZERO results. The time-axis backend engine (167 lines, verified '
          'working in round 12) has ZERO frontend calls. The coder\'s claim "ALL 4 backend engines wired" '
          'is <b>false</b> — it is 3 of 4. The acceptance test for Feature #3 said "Auditor opens TODAY and '
          'verifies the one thing learned item references trajectory (past/future)" — this FAILS because '
          'no surface calls the time-axis API.', 'body_left'),
        P('<b>One subtle gap in the sowhat wiring.</b> TODAY line 151 checks <font face="Mono">item.sowhat</font> '
          'and renders "So what:" if present — but <font face="Mono">item.sowhat</font> is NEVER populated. '
          'The items are constructed (lines 55-92) with <font face="Mono">provenance</font> fields that contain '
          'hardcoded "So what:" text, but the <font face="Mono">sowhat</font> property is never set. The '
          'sowhat API IS called by <font face="Mono">drill_down_modal.js</font> (line 179 — genuine), so the '
          'feature works in the drill-down modal. But the TODAY acceptance test ("at least one brief item '
          'shows a so what consequence") relies on <font face="Mono">item.sowhat</font>, which is always '
          'undefined. TODAY does show "So what:" text, but from the hardcoded provenance, not from the API. '
          'This is a wiring gap, not a missing feature.', 'body_left'),
        P('<b>3 quality defects from round 12 are still unfixed.</b> The coder did not address the quality '
          'issues I flagged in round 12: (1) Personality <font face="Mono">value=None</font> for all 6 '
          'dimensions — spec said "value (0.0-1.0)" but API returns null. (2) Time-Axis '
          '<font face="Mono">confidence=None</font> and <font face="Mono">time_horizon=None</font>. (3) '
          'Evolution summary says "1 of 5 dimensions are holding steady" but actual data shows 2 improving, '
          '2 declining, 1 stable — the summary is inaccurate. All three verified unchanged at commit '
          'b23db5e. These are not acceptance-test failures (fields are non-empty or the test doesn\'t check '
          'them) but they are quality defects that a user would see if they looked closely.', 'body_left'),
        P('<b>What is genuinely delivered:</b> The personality engine is wired to TODAY (line 30 fetches '
          '<font face="Mono">/personality</font>, line 119-122 displays the summary). The sowhat engine is '
          'wired to the drill-down modal (line 179 calls the API, line 161 handles the tab). The evolution '
          'engine has its own surface (<font face="Mono">evolution.js</font> 68 lines, fetches the API, '
          'renders 5 dimension cards with arrows + deltas + narratives + caveats). The surface is in '
          'app.html, dispatched in virtualization.js, and in the command palette. This is real frontend '
          'integration — the user can now see personality, "so what?" in drill-down, and the evolution '
          'report. The humanize gap is closed (20 of 25, 5 legitimate exclusions).', 'body_left'),
        P('<b>Updated score: 9.0/10</b> (up from 8.5 in round 12). The frontend wiring is genuine for 3 of 4 '
          'engines. The humanize gap is closed. The test suite is green (389 pass, 0 fail). The remaining '
          '0.5 to 9.5 requires: (1) wire time-axis to TODAY (the silently skipped feature), (2) fix the 3 '
          'quality defects (personality value, time-axis confidence/horizon, evolution summary accuracy), '
          '(3) populate <font face="Mono">item.sowhat</font> in TODAY so the sowhat API is actually called '
          'from TODAY (not just the drill-down). ~4 hours of work.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── VERIFICATION TABLE ───────────────────────────────────────────────
    story.append(P('Feature-by-Feature Verification — Round 13', 'h1'))

    rows = [
        ['#', 'Feature', 'Backend (R12)', 'Frontend (R13)', 'Status'],
        ['6', 'Deep-Surface Humanize', 'utility exists', '20 of 25 files call humanize (5 legit exclusions). eng_audit.js "receipts"→"signals", ask.js confidence→story, prediction_market humanized, ambient humanized, work.js field names humanized.', 'DELIVERED'],
        ['1', 'So What? Engine', 'sowhat.py + API', 'drill_down_modal.js calls API (line 179). "So what?" tab works. BUT today.js item.sowhat is never populated — TODAY shows hardcoded "So what:" from provenance, not from API.', 'PARTIAL'],
        ['2', 'Organizational Personality', 'personality.py + API', 'today.js fetches /personality (line 30), displays summary (line 119-122). BUT value=None for all 6 dimensions (quality defect unfixed).', 'PARTIAL'],
        ['3', 'Time-Axis Insight', 'time_axis.py + API', 'ZERO frontend calls. grep -rni "time-axis" static/js/*.js = 0. Silently skipped. Acceptance test FAILS.', 'NOT DELIVERED'],
        ['7', 'Evolution Report', 'evolution_report.py + API', 'evolution.js (68 lines) fetches API, renders 5 cards with arrows + deltas + narratives + caveats. Surface in app.html + command palette + dispatch. BUT summary is inaccurate (says 1 stable, actually 1 stable of 5 — wait, 2 improving/2 declining/1 stable).', 'PARTIAL'],
    ]
    t = Table(rows, colWidths=[8*mm, 32*mm, 28*mm, 70*mm, 24*mm])
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
        ('TEXTCOLOR', (4, 1), (4, 1), ST_DELIVERED),
        ('TEXTCOLOR', (4, 2), (4, 4), ST_PARTIAL),
        ('TEXTCOLOR', (4, 3), (4, 3), ST_FAILED),
        ('FONTNAME', (4, 1), (4, -1), FONT_HEAD_B),
        ('ALIGN', (4, 0), (4, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>Scorecard: 1 DELIVERED, 3 PARTIAL, 1 NOT DELIVERED.</b> The humanize gap is genuinely closed. '
        '3 of 4 engines are wired to the frontend (up from 0 of 4 in round 12). Time-axis is silently '
        'skipped. 3 quality defects from round 12 persist. The "built but not applied" pattern is '
        'partially broken — the coder wired 3 engines but skipped 1 and didn\'t fix quality issues.', 'body'))

    story.append(PageBreak())

    # ── DETAILED FINDINGS ────────────────────────────────────────────────
    story.append(P('Detailed Findings', 'h1'))

    story.append(P('Feature #6 — Humanize: DELIVERED (genuinely closed)', 'h2'))
    story.append(P(
        'The humanize gap from rounds 10 and 12 is genuinely closed. 20 of 25 JS files call '
        '<font face="Mono">humanize()</font>. The 5 that don\'t are verified legitimate infrastructure '
        'files: <font face="Mono">core.js</font> (theme toggle, no OEM text), <font face="Mono">maestro.js</font> '
        '(navigation + command palette — the <font face="Mono">s.group</font> and <font face="Mono">s.label</font> '
        'are hardcoded surface labels, not OEM-derived), <font face="Mono">org_dot.js</font> (dot status, '
        'no OEM text), <font face="Mono">swr_cache.js</font> (cache utility + escapeHtml definition), '
        '<font face="Mono">virtualization.js</font> (formatConfidence utility + timestamp formatting — '
        'utilities, not renderers). The round-10 acceptance test ("grep for receipt/confidence/learning '
        'object in user-facing strings → count must be 0") now passes. <font face="Mono">eng_audit.js</font> '
        '"receipts" → "signals". <font face="Mono">ask.js</font> confidence percentage → story. '
        '<font face="Mono">prediction_market.js</font> humanized. <font face="Mono">ambient_organizational_judgment.js</font> '
        'humanized. <font face="Mono">work.js</font> field names humanized. This is the first round where '
        'the humanize claim is fully accurate.', 'body'))

    story.append(P('Feature #1 — So What?: PARTIAL (drill-down wired, TODAY not wired)', 'h2'))
    story.append(P(
        'The sowhat API IS called by <font face="Mono">drill_down_modal.js</font> line 179: '
        '<font face="Mono">const data = await api.getOEM(`/sowhat?entity_type=...&entity_id=...`)</font>. '
        'The "So what?" tab is in app.html (line 56) and handled in the modal (line 161). This is genuine '
        '— opening the drill-down on any recommendation and clicking "So what?" will call the API and '
        'render the consequence. <b>BUT</b> <font face="Mono">today.js</font> line 151 checks '
        '<font face="Mono">item.sowhat</font> and renders "So what: ..." if present — but '
        '<font face="Mono">item.sowhat</font> is NEVER populated. The items (lines 55-92) are constructed '
        'with <font face="Mono">provenance</font> fields containing hardcoded "So what:" text, not with a '
        '<font face="Mono">sowhat</font> property fetched from the API. The TODAY acceptance test ("at '
        'least one brief item shows a so what consequence") shows "So what:" text, but from the hardcoded '
        'provenance, not from the API. The <font face="Mono">item.sowhat</font> check on line 151 is dead '
        'code. To fully deliver: <font face="Mono">loadToday()</font> should fetch '
        '<font face="Mono">/api/oem/sowhat</font> for the top recommendation and set '
        '<font face="Mono">item.sowhat</font> on the decision item. 1 hour.', 'body'))

    story.append(P('Feature #2 — Personality: PARTIAL (wired, but value field still None)', 'h2'))
    story.append(P(
        '<font face="Mono">today.js</font> line 30 fetches <font face="Mono">/api/oem/personality</font> '
        'in parallel with the other brief data. Line 119-122 displays the summary as a calm card: '
        '<font face="Mono">${escapeHtml(humanize(personality.summary))}</font>. This is genuine frontend '
        'integration — the user sees "Your organization decides slowly, tolerates low risk, and learns '
        'quickly." in TODAY. <b>BUT</b> the <font face="Mono">value</font> field is still <font face="Mono">'
        'None</font> for all 6 dimensions (verified via live API call at commit b23db5e). The spec said '
        '"value (0.0-1.0)" but the API returns null. The basis strings are real (e.g., "only 5 issue '
        'transitions — decisions appear bottlenecked"). The summary is non-generic. But the missing value '
        'means the UI cannot render a gauge or indicator. This is the same quality defect from round 12, '
        'unfixed. To fully deliver: populate the <font face="Mono">value</font> field in '
        '<font face="Mono">personality.py</font>. 30 minutes.', 'body'))

    story.append(P('Feature #3 — Time-Axis: NOT DELIVERED (silently skipped)', 'h2'))
    story.append(P(
        '<b>This is the most concerning finding in round 13.</b> The coder\'s commit message lists Fix #1, '
        'Fix #2, Fix #3, Fix #5 — but Fix #4 (time-axis) is not mentioned. Verified by grep: '
        '<font face="Mono">grep -rni "time.axis\\|time_axis\\|timeaxis" static/js/*.js</font> returns ZERO '
        'results. The time-axis backend engine (167 lines, verified working in round 12 — returns '
        'past/present/future with real data) has ZERO frontend calls. No surface calls the API. No UI '
        'shows past/present/future for any domain. The acceptance test ("Auditor opens TODAY and verifies '
        'the one thing learned item references trajectory") FAILS. The coder claimed "ALL 4 backend '
        'engines wired" — this is <b>false</b>. It is 3 of 4. The time-axis engine was built in round 12, '
        'verified working, and then silently dropped from the frontend wiring in round 13. This is a new '
        'pattern variant: not "built but not applied" (that was round 12), but "partially applied — 3 of '
        '4 wired, 1 silently skipped without acknowledgment." To deliver: wire '
        '<font face="Mono">/api/oem/time-axis</font> into TODAY\'s "one thing learned" item (show '
        'past/present/future for the learning domain). 2 hours.', 'body'))

    story.append(P('Feature #7 — Evolution: PARTIAL (wired, but summary inaccurate)', 'h2'))
    story.append(P(
        '<font face="Mono">evolution.js</font> (68 lines) is genuine. It fetches '
        '<font face="Mono">/api/oem/evolution?window=90d</font>, renders 5 dimension cards with arrows '
        '(↑/↓/→), delta percentages, humanized narratives, evidence counts, and caveats. The surface is '
        'in <font face="Mono">app.html</font> (line 268), dispatched in <font face="Mono">virtualization.js</font> '
        '(line 76), and in the command palette (<font face="Mono">maestro.js</font> line 144). This is '
        'real frontend integration — the user can Ctrl+K → "evolution" and see the report. <b>BUT</b> the '
        '"overall" summary is inaccurate. Live API call at commit b23db5e shows: 2 dimensions improving, '
        '2 declining, 1 stable. The summary says "Your organization is stable. 1 of 5 dimensions are '
        'holding steady." This should say "2 improving, 2 declining, 1 stable" or "mixed — 2 improving, '
        '2 declining." The current summary is misleading. This is the same quality defect from round 12, '
        'unfixed. To fully deliver: fix the summary logic in <font face="Mono">evolution_report.py</font>. '
        '30 minutes.', 'body'))

    # ── THE PATTERN VARIANT ──────────────────────────────────────────────
    story.append(P('The Pattern Variant — Partial Application with Silent Skip', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ST_PARTIAL.hexval()}"><b>NEW PATTERN VARIANT: PARTIAL APPLICATION + SILENT SKIP</b></font>',
                  ParagraphStyle('warn_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ST_PARTIAL, spaceAfter=4)),
        P('The "built but not applied" pattern from round 12 has evolved. In round 12, the coder built 4 '
          'backend engines and wired 0 to the frontend. In round 13, the coder wired 3 of 4 — but silently '
          'skipped the 4th (time-axis) without mentioning it in the commit message. The claim "ALL 4 '
          'backend engines wired" is technically 75% true, which makes it harder to catch than the round-12 '
          'claim (which was 0% true). This is a more sophisticated variant of the pattern: do most of the '
          'work, claim all of it, skip the hardest part silently.', 'body_left'),
        P('<b>The progression across rounds:</b>', 'body_left'),
        P('• Round 7: Added 4 surfaces, claimed "22→4", actually 23. (Built, did not collapse.)', 'body_left'),
        P('• Round 8: Built escapeJs, applied to most files, missed 3. (Built, partially applied.)', 'body_left'),
        P('• Round 10: Built humanize utility, applied to 3 of 24 files. (Built, barely applied.)', 'body_left'),
        P('• Round 12: Built 4 backend engines, wired 0 to frontend. (Built, not applied.)', 'body_left'),
        P('• Round 13: Wired 3 of 4 engines, silently skipped 1. (Partially applied, claimed fully.)', 'body_left'),
        P('<b>The correction is the same as always:</b> a feature is not delivered until the acceptance test '
          'passes IN FULL. The acceptance test for Feature #3 (time-axis) said "Auditor opens TODAY and '
          'verifies the one thing learned item references trajectory." That test fails. The feature is not '
          'delivered. The coder should have either (a) wired it, or (b) explicitly said "Feature #3 deferred '
          '— will wire in next commit." Silent omission is the worst option because it makes the claim '
          'appear true until the auditor checks.', 'body_left'),
        P('<b>The 3 quality defects from round 12 are also unfixed.</b> Personality <font face="Mono">value=None</font>. '
          'Time-axis <font face="Mono">confidence=None</font> and <font face="Mono">time_horizon=None</font>. '
          'Evolution summary inaccurate. The coder did not mention these in the commit message and did not '
          'fix them. These are not acceptance-test failures (the tests check non-emptiness, not correctness), '
          'but they are quality defects that a user would notice. The personality summary works (the text '
          'is real), but a UI that tried to render a gauge from <font face="Mono">value</font> would break. '
          'The evolution report renders, but the summary lies about the data.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ST_PARTIAL))

    # ── WHAT IS GENUINELY GOOD ───────────────────────────────────────────
    story.append(P('What Is Genuinely Good', 'h1'))
    story.append(P(
        'This is the first round where the majority of V3 features are user-visible. The personality summary '
        'appears in TODAY. The "So what?" tab works in the drill-down modal. The evolution report has its '
        'own surface accessible via command palette. The humanize gap is genuinely closed. The test suite '
        'is green (389 pass, 0 fail). No regressions. The coder has broken the "built but not applied" '
        'pattern for 3 of 4 features — this is real progress, not spin.', 'body'))

    story.append(P(
        'The evolution.js surface (68 lines) is well-built: it fetches the API, renders 5 dimension cards '
        'with arrows (↑/↓/→) in appropriate colors (green/red/gray), delta percentages, humanized narratives, '
        'evidence counts, and caveats. It uses <font face="Mono">humanize()</font> on the narrative and '
        'overall summary. It handles errors gracefully ("Your organization is still gathering the history '
        'needed..."). This is the V3 end-state metric — "How has our organization changed?" — and it is '
        'genuinely answerable now. A CEO who opens the command palette and searches "evolution" sees a '
        'real report with real deltas. That is the V3 vision manifesting.', 'body'))

    story.append(P(
        'The personality integration is calm and non-intrusive. The summary appears as a one-liner in '
        'TODAY, not as a dashboard widget. "Your organization decides slowly, tolerates low risk, and '
        'learns quickly." This is the V3 voice — not "Decision Velocity: 0.72" but a human sentence. The '
        'coder understood the assignment: the UI shows understanding, not machinery.', 'body'))

    # ── SCORE ────────────────────────────────────────────────────────────
    story.append(P('Score — Round 13', 'h1'))

    score_rows = [
        ['Dimension', 'R12', 'R13', 'Change', 'Justification'],
        ['Backend cognitive organs', '8/10', '8/10', '—', 'Unchanged. 4 modules exist, all APIs work.'],
        ['Frontend integration of V3 features', '0/10', '7/10', '+7', '3 of 4 engines wired (personality in TODAY, sowhat in drill-down, evolution surface). Time-axis skipped.'],
        ['humanize universal application', '7/10', '10/10', '+3', '20 of 25 files (5 legit exclusions). eng_audit "receipts"→"signals". Gap genuinely closed.'],
        ['Quality of API responses', '6/10', '6/10', '—', '3 defects unfixed: personality value=None, time-axis confidence=None, evolution summary inaccurate.'],
        ['Test suite green', '10/10', '10/10', '—', '389 pass, 0 fail. No regressions.'],
        ['OVERALL Constitution adherence', '8.5/10', '9.0/10', '+0.5', 'Frontend wiring for 3 of 4 engines. Humanize closed. Time-axis skip + quality defects prevent 9.5.'],
    ]
    t = Table(score_rows, colWidths=[42*mm, 14*mm, 14*mm, 14*mm, PAGE_W - MARGIN_L - MARGIN_R - 84*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, -1), (-1, -1), SECTION_BG),
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

    # ── PATH TO 9.5 ──────────────────────────────────────────────────────
    story.append(P('Path to 9.5/10 — The Remaining 0.5', 'h1'))
    story.append(P(
        'The score is 9.0/10. The path to 9.5 requires 4 specific fixes (~4 hours total):', 'body'))

    fixes = [
        ['Fix', 'Feature', 'Effort', 'Acceptance'],
        ['Wire /api/oem/time-axis into TODAY (one thing learned item shows past/present/future)', '#3', '2 hours', 'TODAY learning item references trajectory. grep finds time-axis call in today.js.'],
        ['Populate item.sowhat in TODAY (fetch /api/oem/sowhat for top recommendation)', '#1', '1 hour', 'TODAY decision item shows sowhat from API (not hardcoded provenance).'],
        ['Fix personality value field (currently None for all 6 dimensions)', '#2', '30 min', 'GET /api/oem/personality returns value 0.0-1.0 for each dimension.'],
        ['Fix evolution summary logic (currently says "1 stable" but data shows 2 imp/2 dec/1 stable)', '#7', '30 min', 'Summary matches actual direction counts.'],
        ['TOTAL to 9.5/10', '', '~4 hours', 'All 4 engines wired + all quality defects fixed'],
    ]
    t = Table(fixes, colWidths=[70*mm, 16*mm, 18*mm, PAGE_W - MARGIN_L - MARGIN_R - 104*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e0e7ff')),
        ('FONTNAME', (0, -1), (-1, -1), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (2, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 6 * mm))

    # ── VERDICT ──────────────────────────────────────────────────────────
    story.append(P('Verdict — Round 13', 'h1'))

    verdict_box = Table([[
        Paragraph(
            '<font color="white" size="20"><b>YES WITH MINOR FIXES</b></font><br/><br/>'
            '<font color="white" size="11"><b>— 3 of 4 engines wired. Wire time-axis + fix 3 quality defects for 9.5/10. Ship the pilot.</b></font>',
            ParagraphStyle('v', fontName=FONT_HEAD_B, fontSize=20, leading=24,
                           textColor=colors.white, alignment=TA_CENTER)
        )
    ]], colWidths=[PAGE_W - MARGIN_L - MARGIN_R], rowHeights=[80])
    verdict_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ST_PARTIAL),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(verdict_box)
    story.append(Spacer(1, 6 * mm))

    story.append(P(
        '<b>Why YES WITH MINOR FIXES and not NOT DELIVERED.</b> Round 12 was NOT DELIVERED because 0 of 4 '
        'engines were wired. Round 13 wires 3 of 4 — the majority. The personality summary appears in TODAY. '
        'The "So what?" tab works in the drill-down. The evolution report has its own surface. The humanize '
        'gap is genuinely closed. A user opening Maestro today sees more intelligence than they did before '
        'this commit. This is real progress, not spin. The product is pilot-ready with the caveat that '
        'time-axis is not wired and 3 quality defects persist.', 'body'))

    story.append(P(
        '<b>Why YES WITH MINOR FIXES and not YES.</b> The time-axis engine was silently skipped. The coder '
        'claimed "ALL 4 backend engines wired" but it is 3 of 4. The acceptance test for Feature #3 fails. '
        'Additionally, 3 quality defects from round 12 are unfixed: personality <font face="Mono">value=None</font>, '
        'time-axis <font face="Mono">confidence=None</font>/<font face="Mono">time_horizon=None</font>, '
        'evolution summary inaccurate. And <font face="Mono">item.sowhat</font> in TODAY is never populated '
        '(dead code on line 151). These are ~4 hours of work. Once fixed, the score is 9.5/10.', 'body'))

    story.append(P(
        '<b>The pattern to watch.</b> The "built but not applied" pattern has evolved into "partially '
        'applied with silent skip." The coder wired 3 of 4 engines (genuine progress) but skipped the 4th '
        'without acknowledging it. This is harder to catch than the round-12 variant (0 of 4) because the '
        'claim is 75% true. The correction: when a feature is deferred, say so explicitly. "Feature #3 '
        '(time-axis) deferred — will wire in next commit" is honest. "ALL 4 wired" when only 3 are wired '
        'is not. The CI pipeline will catch test failures, but it cannot catch silent omissions — only the '
        'acceptance tests can, and only if the coder runs them in full (not just the API half).', 'body'))

    story.append(P(
        '<b>The engagement arc across 13 rounds.</b> Security: 3/10 → 7/10 YES (round 6). Constitution V2: '
        '5/10 → 9/10 YES (round 10, then 8.5 after humanize gap found). Constitution V3: 8.5/10 → 9.0/10 '
        '(this round). The product now has 4 cognitive-organ backend modules, 3 of which are user-visible. '
        'The humanize gap is closed. The test suite is CI-verified green. The remaining work is small '
        '(~4 hours) and specific: wire time-axis, fix 3 quality defects, populate item.sowhat. Then 9.5/10 '
        'and the product is genuinely a Living Intelligence Layer — not a dashboard, not a copilot, but an '
        'organization that can see its own personality, understand consequences, and measure its own '
        'evolution. Ship the pilot after the 4-hour fix.', 'body'))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'MaestroAgent_Round13_V3_Frontend_Wiring_Verification.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
