"""
Maestro Round 15 — V3 Gap Closure Verification
The coder claims commit 17a64fe closes all 4 V3 gaps from round 13. This review
verifies each fix against source AND via live API. 3 of 4 are genuinely fixed.
1 has a design flaw: time-axis is wired but hardcoded to a domain that 404s
with the demo seed, so the trajectory will never display.
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
SECTION_BG    = colors.HexColor('#f0fdf4')
CARD_BG       = colors.HexColor('#dcfce7')
TABLE_STRIPE  = colors.HexColor('#f0fdf4')
HEADER_FILL   = colors.HexColor('#14532d')
BORDER        = colors.HexColor('#86efac')
ACCENT        = colors.HexColor('#15803d')
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
                      "Maestro Round 15 — V3 Gap Closure Verification  ·  Independent review")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro Round 15 — V3 Gap Closure Verification",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="Round-15 verification of 4 V3 gap fixes — 3 delivered, 1 has design flaw",
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
        f'<font color="{ACCENT.hexval()}"><b>ROUND 15 — V3 GAP CLOSURE VERIFICATION</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        '3 of 4 Gaps Genuinely Closed',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=28,
                       leading=32, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Time-axis is wired but hardcoded to a domain that 404s with the demo seed.',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=13,
                       leading=17, textColor=HEADER_FILL, alignment=TA_LEFT, spaceAfter=14)
    ))

    meta = Table([
        [Paragraph('<b>Reviewer</b>', S['small']), P('Independent (Super Z, Z.ai)', 'small')],
        [Paragraph('<b>Commit</b>', S['small']), P('17a64fe — "fix(constitution-v3): wire time-axis to TODAY + populate sowhat from API + fix personality value + fix evolution summary"', 'small')],
        [Paragraph('<b>Round-13 gaps</b>', S['small']), P('4 gaps: time-axis not wired, item.sowhat dead code, personality value=None, evolution summary inaccurate', 'small')],
        [Paragraph('<b>Coder\'s claim</b>', S['small']), P('"All 4 fixes delivered. No silent skips, no dead code. 235 tests pass, 0 failed. All 4 V3 engines genuinely wired."', 'small')],
        [Paragraph('<b>Reviewer\'s verdict</b>', S['small']), Paragraph(f'<font color="{ST_DELIVERED.hexval()}"><b>3 of 4 DELIVERED. Time-axis is wired but hardcoded to "engineering" which 404s with demo data — trajectory will never display. Score 9.5/10.</b></font>', S['small'])],
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
        Paragraph(f'<font color="{ST_DELIVERED.hexval()}"><b>ROUND-15 EXECUTIVE SUMMARY (TL;DR)</b></font>',
                  ParagraphStyle('callout_h', fontName=FONT_HEAD_B, fontSize=10,
                                 leading=13, textColor=ST_DELIVERED, spaceAfter=4)),
        P('The coder\'s round-15 commit <font face="Mono">17a64fe</font> closes 3 of the 4 V3 gaps from '
          'round 13 genuinely and completely. The personality <font face="Mono">value</font> field is now '
          'populated (all 6 dimensions return 0.0-1.0, verified via live API). The evolution summary is now '
          'accurate (says "2 improving, 2 declining, 1 stable" matching the actual data, verified via live '
          'API). The sowhat API is now called from TODAY and <font face="Mono">item.sowhat</font> is '
          'populated from <font face="Mono">sowhatData.consequence_if_ignored</font> (line 79) — no longer '
          'dead code. These 3 fixes are real, verified, and complete.', 'body_left'),
        P('<b>The 4th fix (time-axis) is wired but has a design flaw.</b> <font face="Mono">today.js</font> '
          'line 38 fetches <font face="Mono">/api/oem/time-axis?domain=engineering</font>. The domain '
          '"engineering" is hardcoded. Verified via live API: <font face="Mono">GET /api/oem/time-axis?'
          'domain=engineering</font> returns 404 ("Insufficient data for domain \'engineering\'. Need at '
          'least 5 signals; found fewer."). The <font face="Mono">.catch(() => null)</font> on line 39 '
          'means TODAY still renders, but <font face="Mono">timeAxis</font> is always null, so the '
          'trajectory provenance on line 104 falls through to "From organizational patterns" — the '
          'trajectory never displays. The API is called (wired), but the call is guaranteed to fail with '
          'the demo seed. Only <font face="Mono">payments</font> and <font face="Mono">auth</font> domains '
          'return 200 from time-axis with the demo data. The coder should have derived the domain from the '
          'actual knowledge traps or overnight changes, or used a domain that exists in the demo seed.', 'body_left'),
        P('<b>This is a subtler variant of the "built but not applied" pattern.</b> The code calls the API '
          '(wired). The API returns data for some domains. But the hardcoded domain never works with the '
          'demo seed. A user opening TODAY with the demo seed will never see trajectory text. The feature '
          'is technically wired but functionally invisible. The acceptance test I specified ("Auditor opens '
          'TODAY and verifies the one thing learned item references trajectory") would FAIL with the demo '
          'seed — the trajectory line is never populated because the API 404s. This is not a silent skip '
          '(the coder did wire it) and not dead code (the code runs), but it is a design flaw that makes '
          'the feature invisible in practice.', 'body_left'),
        P('<b>The test-suite fix is honest but broad.</b> The coder added "404" to the console error filter '
          'in both test files, documenting that "404s from time-axis when domain has insufficient data" are '
          '"honest API responses, not JS errors." This is true — the 404 is honest. But filtering ALL 404s '
          'from the console error check means the test will not catch OTHER 404s that might be real errors '
          '(e.g., a broken API endpoint). A narrower filter (only filter 404s from <font face="Mono">'
          '/api/oem/time-axis</font>) would be more precise. Minor test-quality trade-off, not a blocker.', 'body_left'),
        P('<b>Test suite is green.</b> 389 passed (API + auth) + 34 passed (frontend + cognitive) = 423 '
          'tests pass, 0 fail, 2 skipped. No regressions. The CI pipeline will verify this on every push.', 'body_left'),
        P('<b>Updated score: 9.5/10</b> (up from 9.0 in round 13). 3 of 4 gaps are genuinely closed. The '
          'time-axis design flaw (hardcoded domain that 404s) prevents 10/10. Fix: derive the domain from '
          'the knowledge traps or use a domain that exists in the demo seed. 30 minutes. Once fixed, the '
          'V3 features are fully delivered and the coder can proceed to V4 (Organ #1 Identity + Organ #2 '
          'Curiosity, already committed as c448ab1 — pending review).', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── VERIFICATION TABLE ───────────────────────────────────────────────
    story.append(P('Round-13 Gap Closure — Verification', 'h1'))

    rows = [
        ['#', 'Gap (from R13)', 'Fix Claimed', 'Status', 'Evidence (verified at 17a64fe)'],
        ['1', 'Time-axis not wired to TODAY', 'Wired', 'PARTIAL', 'today.js line 38 fetches /time-axis?domain=engineering. BUT domain "engineering" 404s with demo seed (verified via live API: "Insufficient data"). .catch(()=>null) means TODAY renders but trajectory never displays. Wired but functionally invisible. Fix: derive domain from data or use "payments"/"auth".'],
        ['2', 'item.sowhat never populated (dead code)', 'Populated from API', 'DELIVERED', 'today.js line 48 fetches /sowhat for top recommendation. Line 79: sowhat: sowhatData ? sowhatData.consequence_if_ignored : \'\'. Line 178 renders it. Verified via live API: /sowhat returns consequence_if_ignored. No longer dead code.'],
        ['3', 'Personality value=None for all 6 dimensions', 'value field added', 'DELIVERED', 'Live API: GET /api/oem/personality returns value=0.3, 0.8, etc. for all 6 dimensions (was None). value is alias for score. All dimensions have numeric value 0.0-1.0. FIXED.'],
        ['4', 'Evolution summary inaccurate', 'Summary logic fixed', 'DELIVERED', 'Live API: GET /api/oem/evolution returns "Your organization is mixed. 2 improving, 2 declining, 1 stable." Actual data: 2 improving, 2 declining, 1 stable. Summary matches data. FIXED.'],
    ]
    t = Table(rows, colWidths=[8*mm, 42*mm, 22*mm, 22*mm, PAGE_W - MARGIN_L - MARGIN_R - 94*mm])
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
        ('TEXTCOLOR', (3, 1), (3, 1), ST_PARTIAL),
        ('TEXTCOLOR', (3, 2), (3, 4), ST_DELIVERED),
        ('FONTNAME', (3, 1), (3, -1), FONT_HEAD_B),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>Scorecard: 3 DELIVERED, 1 PARTIAL.</b> The 3 delivered fixes are genuine and verified via live '
        'API. The 1 partial fix (time-axis) is wired but hardcoded to a domain that 404s with the demo '
        'seed. The "built but not applied" pattern has not recurred — the coder wired everything and fixed '
        'the quality defects. The time-axis issue is a design flaw, not a pattern recurrence.', 'body'))

    story.append(PageBreak())

    # ── DETAILED FINDINGS ────────────────────────────────────────────────
    story.append(P('Detailed Findings', 'h1'))

    story.append(P('Fix 1 — Time-axis: PARTIAL (wired but hardcoded domain 404s)', 'h2'))
    story.append(P(
        '<font face="Mono">today.js</font> line 38: <font face="Mono">timeAxis = await api.getOEM('
        "'/time-axis?domain=engineering');</font>. The domain \"engineering\" is hardcoded. Live API "
        'verification: <font face="Mono">GET /api/oem/time-axis?domain=engineering</font> returns 404 with '
        'body <font face="Mono">{"detail":"Insufficient data for domain \'engineering\'. Need at least 5 '
        'signals; found fewer."}</font>. The <font face="Mono">.catch(() => null)</font> on line 39 means '
        '<font face="Mono">timeAxis</font> is set to null. Line 104: <font face="Mono">provenance: timeAxis '
        '&& timeAxis.future ? ... : \'From organizational patterns\'</font> — since timeAxis is null, the '
        'trajectory is never displayed. The "one thing learned" item falls back to the static "From '
        'organizational patterns" string.', 'body'))

    story.append(P(
        '<b>Which domains work with the demo seed?</b> Verified via live API: <font face="Mono">payments</font> '
        'returns 200, <font face="Mono">auth</font> returns 200. All other domains (engineering, platform, '
        'deployment, legal, frontend, backend, infrastructure, qa) return 404. The demo seed only has '
        'enough signals in payments and auth. The coder hardcoded "engineering" — the one domain that '
        'never works with the demo data.', 'body'))

    story.append(P(
        '<b>The fix:</b> derive the domain from the actual data. The knowledge traps (from '
        '<font face="Mono">/api/oem/ceo-briefing</font> → <font face="Mono">knowledge.traps</font>) '
        'reference domains like "deployment" — but that also 404s. The overnight changes reference '
        'entities/domains. The coder should either: (a) try multiple domains and use the first that '
        'returns 200, or (b) derive the domain from the learning item\'s actual domain, or (c) use '
        '"payments" or "auth" as the default (since those work with the demo seed). 30 minutes. Once fixed, '
        'the trajectory will display and the time-axis feature is fully delivered.', 'body'))

    story.append(P(
        '<b>Why this is not the "built but not applied" pattern.</b> The coder DID wire the API (line 38 '
        'calls it). The coder DID handle the failure gracefully (line 39 catches it). The code runs. But '
        'the hardcoded domain means the feature is functionally invisible with the demo seed. This is a '
        'design flaw (wrong default domain), not a wiring gap (the wiring is correct). The distinction '
        'matters: the pattern from rounds 7-13 was "build without wiring." This is "wire with a bad '
        'default." The correction is different: change the default, do not add wiring.', 'body'))

    story.append(P('Fix 2 — Sowhat in TODAY: DELIVERED (dead code resurrected)', 'h2'))
    story.append(P(
        '<font face="Mono">today.js</font> line 44-49: <font face="Mono">let sowhatData = null; ... '
        'sowhatData = await api.getOEM(`/sowhat?entity_type=recommendation&entity_id=${encodeURIComponent('
        'ot.title)}`);</font>. Line 79: <font face="Mono">sowhat: sowhatData ? sowhatData.consequence_if_'
        'ignored : \'\'</font>. Line 178: <font face="Mono">${item.sowhat ? ... : \'\'}</font>. The '
        '<font face="Mono">item.sowhat</font> field is now populated from the API response. Live API '
        'verification: <font face="Mono">GET /api/oem/sowhat?entity_type=recommendation&entity_id=...</font> '
        'returns <font face="Mono">consequence_if_ignored: "This pattern has appeared 0 times. If ignored, '
        'it will likely recur..."</font>. This value will appear in TODAY as the "So what:" line. The dead '
        'code from round 13 is genuinely resurrected. <b>FIXED.</b>', 'body'))

    story.append(P(
        '<b>Minor quality note:</b> the sowhat response says "This pattern has appeared 0 times" — the '
        'engine returns generic placeholder text when it cannot find the entity\'s evidence count. This is '
        'not wrong (the engine is honest about limited data), but the user sees "0 times" which is '
        'slightly confusing. A better phrasing: "This is an emerging pattern. If ignored, it will likely '
        'recur." The current phrasing is acceptable for a pilot but could be improved.', 'body'))

    story.append(P('Fix 3 — Personality value: DELIVERED (None → 0.0-1.0)', 'h2'))
    story.append(P(
        'Live API verification: <font face="Mono">GET /api/oem/personality</font> now returns '
        '<font face="Mono">value=0.3</font> for decision_velocity, <font face="Mono">value=0.8</font> for '
        'knowledge_mobility, etc. All 6 dimensions have numeric <font face="Mono">value</font> (was '
        '<font face="Mono">None</font> in round 13). The <font face="Mono">value</font> field is an alias '
        'for <font face="Mono">score</font> — both are populated. The spec said "value (0.0-1.0)" and the '
        'API now delivers it. <b>FIXED.</b>', 'body'))

    story.append(P('Fix 4 — Evolution summary: DELIVERED (inaccurate → accurate)', 'h2'))
    story.append(P(
        'Live API verification: <font face="Mono">GET /api/oem/evolution?window=90d</font> now returns '
        '<font face="Mono">"Your organization is mixed. 2 improving, 2 declining, 1 stable."</font> The '
        'actual data shows 2 improving (decision_making, knowledge_mobility), 2 declining '
        '(knowledge_discipline, cross_functional_trust), 1 stable (prediction_accuracy). The summary '
        'matches the data. The round-13 bug (said "1 of 5 holding steady" when the data showed 2/2/1) is '
        'fixed. <b>FIXED.</b>', 'body'))

    # ── TEST SUITE ────────────────────────────────────────────────────────
    story.append(P('Test Suite Verification', 'h1'))

    test_rows = [
        ['Suite', 'Passed', 'Failed', 'Skipped', 'Notes'],
        ['API + auth (full)', '389', '0', '2', 'No regressions. CI-verified.'],
        ['Frontend smoke + cognitive', '34', '0', '0', '34 pass. 404 filter added for time-axis honest 404s.'],
        ['TOTAL VERIFIED', '423', '0', '2', 'Full suite green. No regressions.'],
    ]
    t = Table(test_rows, colWidths=[60*mm, 16*mm, 14*mm, 16*mm, PAGE_W - MARGIN_L - MARGIN_R - 106*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0fdf4')),
        ('FONTNAME', (0, -1), (-1, -1), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (3, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>The 404 console filter.</b> The coder added "404" to the console error filter in both test '
        'files, with a comment: "404s from time-axis when domain has insufficient data) ... honest API '
        'responses, not JS errors." This is true — the 404 is honest. But the filter is broad: it filters '
        'ALL 404s, not just time-axis 404s. A narrower filter (only filter 404s from '
        '<font face="Mono">/api/oem/time-axis</font>) would be more precise and would catch other 404s '
        'that might indicate real broken endpoints. Minor test-quality trade-off. Not a blocker — the '
        'CI pipeline and the acceptance tests are the primary verification, not the console error filter.', 'body'))

    # ── SCORE ────────────────────────────────────────────────────────────
    story.append(P('Score — Round 15', 'h1'))

    score_rows = [
        ['Dimension', 'R13', 'R15', 'Change', 'Justification'],
        ['Frontend integration of V3 features', '7/10', '9/10', '+2', 'All 4 APIs now called by frontend (was 3 of 4). Time-axis wired but domain 404s. Sowhat dead code fixed.'],
        ['Quality of API responses', '6/10', '9/10', '+3', 'Personality value populated (was None). Evolution summary accurate (was wrong). Time-axis confidence/horizon still None but feature works.'],
        ['humanize universal application', '10/10', '10/10', '—', 'Unchanged. Gap closed in R13.'],
        ['Backend cognitive organs', '8/10', '8/10', '—', 'Unchanged. 4 V3 modules exist. V4 organs pending.'],
        ['Test suite green', '10/10', '10/10', '—', '423 pass, 0 fail. No regressions.'],
        ['OVERALL Constitution adherence', '9.0/10', '9.5/10', '+0.5', '3 of 4 gaps closed. Time-axis design flaw (hardcoded domain 404s) prevents 10/10. V4 organs pending.'],
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

    # ── THE REMAINING 0.5 ────────────────────────────────────────────────
    story.append(P('The Remaining 0.5 to 10/10', 'h1'))
    story.append(P(
        'The score is 9.5/10. The path to 10/10 requires:', 'body'))

    remaining = [
        ['Item', 'Effort', 'Score Delta'],
        ['Fix time-axis domain derivation (use payments/auth or derive from data, not hardcoded "engineering")', '30 min', '+0.5 → 10/10'],
        ['V4 Organ #1 Identity (already committed as c448ab1, pending review)', 'Already built', '+1.0 (capped)'],
        ['V4 Organ #2 Curiosity (already committed as c448ab1, pending review)', 'Already built', '+1.0 (capped)'],
        ['V4 Organs #3-#8 (Skepticism, Wisdom, Metacognition, Principles, Memory Compression, Consciousness)', '~14 days', '+3.0 (capped)'],
    ]
    t = Table(remaining, colWidths=[80*mm, 30*mm, 30*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
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

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>The 30-minute fix to 10/10 on the V3 axis:</b> change <font face="Mono">today.js</font> line 38 '
        'from <font face="Mono">domain=engineering</font> to derive the domain from the actual data (or use '
        '"payments" which works with the demo seed). Once fixed, the time-axis trajectory displays in '
        'TODAY and all 4 V3 features are fully delivered. The V4 organs (already started in commit '
        'c448ab1) then build on a fully-delivered V3 foundation.', 'body'))

    # ── VERDICT ──────────────────────────────────────────────────────────
    story.append(P('Verdict — Round 15', 'h1'))

    verdict_box = Table([[
        Paragraph(
            '<font color="white" size="20"><b>YES WITH MINOR FIXES</b></font><br/><br/>'
            '<font color="white" size="11"><b>— 3 of 4 gaps closed. Fix time-axis domain (30 min) for 10/10 on V3. V4 organs pending review.</b></font>',
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
        '<b>Why YES WITH MINOR FIXES.</b> 3 of the 4 round-13 gaps are genuinely and completely closed. '
        'The personality <font face="Mono">value</font> field is populated. The evolution summary is '
        'accurate. The sowhat API is called from TODAY and <font face="Mono">item.sowhat</font> is '
        'populated. The test suite is green (423 pass, 0 fail). The "built but not applied" pattern has '
        'NOT recurred — the coder wired everything, fixed the quality defects, and did not silently skip '
        'anything. This is the first round where the coder\'s claim is almost entirely accurate.', 'body'))

    story.append(P(
        '<b>The one remaining issue is a design flaw, not a pattern recurrence.</b> The time-axis API is '
        'wired (line 38 calls it). The failure is handled gracefully (line 39 catches it). But the '
        'hardcoded domain "engineering" 404s with the demo seed, so the trajectory never displays. This is '
        '"wired with a bad default," not "built but not applied." The correction is to change the default '
        'domain (30 minutes), not to add wiring. The distinction matters: the pattern from rounds 7-13 was '
        'structural (build without wiring). This is a parameter error (wrong default). The coder has '
        'genuinely broken the pattern.', 'body'))

    story.append(P(
        '<b>The engagement arc across 15 rounds.</b> Security: 3/10 → 7/10 YES (round 6). Constitution V2: '
        '5/10 → 9/10 (round 10). Constitution V3: 8.5/10 → 9.0/10 → 9.5/10 (this round). Constitution V4: '
        'Organs #1-#2 already committed (c448ab1, pending review). The product now has 4 V3 cognitive '
        'engines, all wired to the frontend, 3 of 4 fully functional with the demo seed. The test suite is '
        'CI-verified green. The remaining 0.5 to V3 10/10 is a 30-minute domain fix. The V4 cognitive stack '
        '(Identity, Curiosity, Skepticism, Wisdom, Metacognition, Principles, Memory Compression, '
        'Consciousness) is the next frontier. The coder has demonstrated the ability to build and wire — '
        'the remaining work is to build with correct defaults. Ship the V3 pilot after the 30-minute fix. '
        'Review V4 Organs #1-#2 next.', 'body'))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'MaestroAgent_Round15_V3_Gap_Closure_Verification.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
