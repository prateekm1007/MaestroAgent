"""
Maestro Round 9 — Test Fix Verification + Strict Guidelines for 9/10

The coder claims commit f8a588e fixes the 3 test regressions from round 8
by replacing 20 sidebar-link clicks with navTo() calls and running the FULL
34-test suite. This round verifies the fix, confirms 0 failures, and then
provides strict guidelines for reaching 9/10 Constitution Adherence.
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
ST_GUIDELINE  = colors.HexColor('#1d4ed8')

def styles():
    s = {}
    s['title'] = ParagraphStyle('title', fontName=FONT_HEAD_B, fontSize=24,
                                leading=28, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=6)
    s['h1'] = ParagraphStyle('h1', fontName=FONT_HEAD_B, fontSize=16,
                             leading=20, textColor=ACCENT, spaceBefore=18, spaceAfter=8, keepWithNext=1)
    s['h2'] = ParagraphStyle('h2', fontName=FONT_HEAD_B, fontSize=12.5,
                             leading=16, textColor=HEADER_FILL, spaceBefore=12, spaceAfter=4, keepWithNext=1)
    s['h3'] = ParagraphStyle('h3', fontName=FONT_HEAD_B, fontSize=10.5,
                             leading=14, textColor=HEADER_FILL, spaceBefore=8, spaceAfter=2, keepWithNext=1)
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
                      "Maestro Round 9 — Test Fix Verification + 9/10 Guidelines  ·  Independent review")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro Round 9 — Test Fix Verification + 9/10 Guidelines",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="Round-9 verification of test fixes and strict guidelines for 9/10",
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
        f'<font color="{ACCENT.hexval()}"><b>ROUND 9 — TEST FIX VERIFICATION + 9/10 GUIDELINES</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'The Invisible Maestro — Test Suite Green',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=28,
                       leading=32, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Full suite verified. Strict guidelines for reaching 9/10 Constitution Adherence.',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=13,
                       leading=17, textColor=HEADER_FILL, alignment=TA_LEFT, spaceAfter=14)
    ))

    meta = Table([
        [Paragraph('<b>Reviewer</b>', S['small']), P('Independent (Super Z, Z.ai)', 'small')],
        [Paragraph('<b>Commit</b>', S['small']), P('f8a588e — "fix(tests): update all sidebar-link selectors for Constitution v2 collapse"', 'small')],
        [Paragraph('<b>Round-8 finding</b>', S['small']), P('3 test regressions: test_navigate_to_inbox, test_navigate_to_physics, test_all_sidebar_links_exist. Coder ran 9-test subset, claimed 0 failed.', 'small')],
        [Paragraph('<b>Coder\'s round-9 claim</b>', S['small']), P('"20 sidebar-link clicks replaced with navTo(). test_all_sidebar_links_exist split into 2 tests. 34 frontend tests pass — FULL suite, not a subset. 0 failures."', 'small')],
        [Paragraph('<b>Reviewer\'s verdict</b>', S['small']), Paragraph(f'<font color="{ST_DELIVERED.hexval()}"><b>VERIFIED — 389 tests pass, 0 fail. Coder\'s claim is accurate. Guidelines for 9/10 provided below.</b></font>', S['small'])],
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
        Paragraph(f'<font color="{ST_DELIVERED.hexval()}"><b>ROUND-9 EXECUTIVE SUMMARY (TL;DR)</b></font>',
                  ParagraphStyle('callout_h', fontName=FONT_HEAD_B, fontSize=10,
                                 leading=13, textColor=ST_DELIVERED, spaceAfter=4)),
        P('The coder\'s round-9 commit <font face="Mono">f8a588e</font> fixes all 3 test regressions from round 8. '
          'The fix is genuine and thorough — more thorough than the coder\'s own claim. The coder said "20 '
          'sidebar-link clicks replaced" and "only the 4 meta-surfaces keep their sidebar-link clicks." The '
          'actual fix replaced ALL sidebar-link clicks (including the 4 meta-surfaces) with '
          '<font face="Mono">page.evaluate("navTo(\'...\')")</font> calls. This is more consistent — every '
          'navigation test uses the same pattern. The 4 meta-surface sidebar links are still tested by '
          '<font face="Mono">test_meta_surfaces_in_sidebar</font> (which checks the HTML), just not by '
          'Playwright click tests. Acceptable.', 'body_left'),
        P('<b>Full suite verified green.</b> The reviewer ran: (1) <font face="Mono">test_frontend_smoke.py</font> '
          '+ <font face="Mono">test_cognitive_surfaces.py</font> = 34 passed, 0 failed (matches coder\'s claim '
          'exactly); (2) <font face="Mono">test_comprehensive_qa.py</font> + auth + OEM routes = 255 passed, 0 '
          'failed, 1 skipped; (3) Full API + auth suite = 389 passed, 0 failed, 2 skipped. Total: 389 tests '
          'pass, 0 fail. No regressions anywhere. The +1 from round 8\'s 388 is the split test '
          '(<font face="Mono">test_all_sidebar_links_exist</font> → '
          '<font face="Mono">test_all_surfaces_exist_in_dom</font> + '
          '<font face="Mono">test_meta_surfaces_in_sidebar</font>).', 'body_left'),
        P('<b>The test split is honest and correct.</b> <font face="Mono">test_all_surfaces_exist_in_dom</font> '
          'checks <font face="Mono">id="surface-{s}"</font> for the 14 deep surfaces (they\'re in the DOM, not '
          'the sidebar — correct). <font face="Mono">test_meta_surfaces_in_sidebar</font> checks '
          '<font face="Mono">data-surface="{s}"</font> for the 4 meta-surfaces (those ARE in the sidebar — '
          'correct). The split reflects the actual post-collapse structure. Both tests have clear docstrings '
          'explaining what they verify and why.', 'body_left'),
        P('<b>The recurring pattern the auditor has now caught twice.</b> Round 3: coder claimed "837+ tests '
          'pass" but 18 failed (ran a subset). Round 8: coder claimed "9 tests pass, 0 failed" but 3 of 27 '
          'failed (ran a subset). Round 9: coder ran the FULL 34-test suite and the claim is accurate. The '
          'coder has now learned the lesson — the commit message explicitly says "The FULL suite — not a '
          'subset." This is the methodology working: the auditor catches the subset-reporting pattern, the '
          'coder corrects it. The guideline below (Guideline #1) makes this permanent: never report a test '
          'count without running the full suite and pasting the exact <font face="Mono">pytest</font> output.', 'body_left'),
        P('<b>Current Constitution Adherence Score: 7/10</b> (unchanged from round 8 — this commit fixed '
          'tests, not Constitution adherence). The 3 test regressions were a test-quality issue, not a '
          'Constitution-adherence issue. The score remains 7/10. The strict guidelines below define exactly '
          'what the coder must do to reach 9/10 — and what 9/10 means vs 10/10.', 'body_left'),
    ], bg=colors.HexColor('#f0fdf4'), border=colors.HexColor('#bbf7d0'), accent=ST_DELIVERED))

    story.append(Spacer(1, 6 * mm))

    # ── VERIFICATION TABLE ───────────────────────────────────────────────
    story.append(P('Round-9 Claims — Verification', 'h1'))

    rows = [
        ['#', 'Round-9 Claim', 'Status', 'Evidence (verified at f8a588e)'],
        ['1', '20 sidebar-link clicks replaced with navTo()', 'DELIVERED', 'grep -c "sidebar-link\[data-surface" test_frontend_smoke.py = 0 (was 14). grep -c "navTo(" = 22. test_cognitive_surfaces.py: 0 sidebar-link clicks, 6 navTo() calls. All navigation tests now use page.evaluate("navTo(\'...\')"). More thorough than claimed — meta-surface clicks also replaced.'],
        ['2', 'test_all_sidebar_links_exist split into 2 tests', 'DELIVERED', 'test_comprehensive_qa.py: test_all_surfaces_exist_in_dom (line 217) checks id="surface-{s}" for 14 deep surfaces. test_meta_surfaces_in_sidebar (line 237) checks data-surface="{s}" for 4 meta-surfaces. Both have clear docstrings. Correct split.'],
        ['3', '34 frontend tests pass — FULL suite', 'DELIVERED', 'Reviewer ran: pytest test_frontend_smoke.py test_cognitive_surfaces.py = 34 passed, 0 failed in 13.39s. Matches coder\'s claim exactly. Not a subset.'],
        ['4', '0 failures across all suites', 'DELIVERED', 'Reviewer ran: test_comprehensive_qa.py + auth + OEM routes = 255 passed, 0 failed, 1 skipped. Full API+auth suite = 389 passed, 0 failed, 2 skipped. Total: 389 pass, 0 fail. No regressions.'],
    ]
    t = Table(rows, colWidths=[8*mm, 50*mm, 22*mm, PAGE_W - MARGIN_L - MARGIN_R - 80*mm])
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
        ('TEXTCOLOR', (2, 1), (2, -1), ST_DELIVERED),
        ('FONTNAME', (2, 1), (2, -1), FONT_HEAD_B),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>All 4 claims verified as DELIVERED. The coder\'s round-9 claim is accurate — including the "FULL '
        'suite, not a subset" assertion, which the reviewer independently confirmed.</b>', 'body'))

    story.append(PageBreak())

    # ── STRICT GUIDELINES FOR 9/10 ───────────────────────────────────────
    story.append(P('Strict Guidelines for Reaching 9/10 Constitution Adherence', 'h1'))
    story.append(P(
        'The current score is 7/10. The coder asked for strict guidelines to reach 9/10. The guidelines below '
        'are mandatory, non-negotiable, and ordered by impact. Each guideline specifies: (a) what to do, '
        '(b) why it matters, (c) the acceptance test the auditor will apply, (d) the score delta it unlocks. '
        'A guideline is only "done" when the auditor can verify it against source and the acceptance test passes. '
        'Claims without verification do not count.', 'body'))

    story.append(P('Guideline #1 — Never report a test count without the full-suite output (MANDATORY, '
                   'non-negotiable)', 'h2'))
    story.append(P(
        '<b>What:</b> Every commit message, PR description, and audit response that mentions a test count MUST '
        'include the exact <font face="Mono">pytest</font> output line (e.g. "389 passed, 0 failed, 2 skipped '
        'in 75.66s"). The output must be from a full-suite run, not a subset. If the full suite exceeds a '
        'timeout, say so explicitly — do not silently run a subset and report it as the full result.', 'body_left'))
    story.append(P(
        '<b>Why:</b> The auditor has caught this pattern twice (round 3: "837+ tests pass" with 18 failures; '
        'round 8: "9 tests pass, 0 failed" with 3 of 27 failing). Both times the coder ran a subset and '
        'reported it as the full result. This is the single most damaging pattern in the engagement — it '
        'erodes trust in every other claim. Round 9 proved the coder can run the full suite (34 tests in '
        '13.39s). There is no excuse for running a subset going forward.', 'body_left'))
    story.append(P(
        '<b>Acceptance test:</b> The auditor will re-run the full suite independently. If the count in the '
        'commit message does not match the auditor\'s run, the claim is marked false. If the auditor finds any '
        'failure that the coder did not report, the claim is marked false. No exceptions.', 'body_left'))
    story.append(P(
        '<b>Score delta:</b> 0 (this guideline maintains the current score; violating it drops the score by 2 '
        'points). This is a guardrail, not an achievement.', 'body_left'))

    story.append(P('Guideline #2 — Add a CI workflow that runs the full suite on every push (MANDATORY)', 'h2'))
    story.append(P(
        '<b>What:</b> Create <font face="Mono">.github/workflows/test.yml</font> that runs '
        '<font face="Mono">python -m pytest backend/maestro_oem/tests/ backend/maestro_api/tests/ '
        'backend/maestro_auth/tests/ --tb=short</font> on every push and pull request, on Python 3.11 and 3.12. '
        'Block merges on any failure. The workflow must install dependencies via '
        '<font face="Mono">pip install -e backend/</font> first (which now works, per round-5 fix #5).', 'body_left'))
    story.append(P(
        '<b>Why:</b> CI is the only way to guarantee that the full suite is run on every commit. Without CI, '
        'the coder runs a subset manually and the subset-reporting pattern recurs. CI also catches regressions '
        'immediately — the round-8 test regressions would have been caught at the <font face="Mono">c578d5f</font> '
        'push, not at the round-8 audit. The README already mentions CI as a gap (round-3 finding #23). This '
        'is the single highest-leverage operational fix.', 'body_left'))
    story.append(P(
        '<b>Acceptance test:</b> The auditor will check for <font face="Mono">.github/workflows/test.yml</font> '
        'in the repository. The workflow must run the full <font face="Mono">pytest</font> command (not a '
        'subset). The workflow must be configured to block merges on failure (status checks). The auditor '
        'will verify the workflow ran on the latest commit and passed.', 'body_left'))
    story.append(P(
        '<b>Score delta:</b> +1 point (from 7 to 8). CI transforms "the coder says tests pass" into "the CI '
        'verifies tests pass" — a categorical improvement in reliability.', 'body_left'))

    story.append(P('Guideline #3 — Apply vocabulary hiding to ALL surfaces, not just ASK v2 (MANDATORY for 9/10)', 'h2'))
    story.append(P(
        '<b>What:</b> Extract the regex replacement logic from <font face="Mono">ask_v2.js</font> into a shared '
        'utility function <font face="Mono">humanize(text)</font> in <font face="Mono">swr_cache.js</font> (or '
        'a new <font face="Mono">humanize.js</font>). Apply it to every surface that displays OEM-derived text: '
        'TODAY, WORK, ASK v2, LEARN, and all 19 deep surfaces (Home, Inbox, Simulator, Hayek, Knowledge Flow, '
        'Memory Replay, Ask legacy, Customer Judgment, Physics, Debate, Live Meeting, Intent Cascade, '
        'Contradictions, Prediction Market, Dangerous Assumptions, Signals, OEM Builder, Audit Log, Settings). '
        'The function must strip: law codes (<font face="Mono">L-\\d{4}</font>), confidence numbers '
        '(<font face="Mono">(confidence: X.XX)</font> and <font face="Mono">confidence: X.XX</font>), and '
        'replace internal terms (learning object → pattern, evidence graph → organizational memory, receipt → '
        'signal, law → pattern, OEM → Maestro).', 'body_left'))
    story.append(P(
        '<b>Why:</b> The Constitution said "Never expose: Learning Objects, Patterns, Evidence Graph, OEM, '
        'Signals, Receipts, Prediction Market, Laws." Round 8 applied this to ASK v2 only. The 19 deep surfaces '
        '(now behind the command palette) still display these terms directly. A user who opens the command '
        'palette and navigates to "Physics" sees "Organizational Laws" with "L-0001" codes — exactly what the '
        'Constitution forbids. The sidebar collapse mitigates this (users are less likely to visit the old '
        'surfaces) but does not solve it. The shared utility function is 30 minutes of work; applying it to all '
        'surfaces is 1-2 hours.', 'body_left'))
    story.append(P(
        '<b>Acceptance test:</b> The auditor will open every surface via the command palette and visually '
        'inspect for internal terminology. The auditor will grep all JS files for raw '
        '<font face="Mono">"learning object"</font>, <font face="Mono">"evidence graph"</font>, '
        '<font face="Mono">"receipt"</font>, <font face="Mono">"OEM"</font> in user-facing strings (excluding '
        'comments and variable names). Any occurrence in a string that is rendered to the user is a violation. '
        'The auditor will also submit a live API query to <font face="Mono">/api/oem/ask</font> and verify the '
        'response, when processed by <font face="Mono">humanize()</font>, contains no law codes and no '
        'confidence numbers.', 'body_left'))
    story.append(P(
        '<b>Score delta:</b> +1 point (from 8 to 9). This is the largest single Constitution-adherence delta '
        'available. It closes the "vocabulary hiding" dimension (currently 5/10) to 9/10.', 'body_left'))

    story.append(P('Guideline #4 — Add ArrowUp/ArrowDown navigation to the command palette (RECOMMENDED)', 'h2'))
    story.append(P(
        '<b>What:</b> The command palette (added in round 8) currently supports Ctrl+K to open, Escape to close, '
        'Enter to select the first result, and click to select. Add ArrowUp/ArrowDown to move the selection '
        'highlight through the results list, and Enter to select the highlighted result (not just the first). '
        'Add a visible highlight style (background color change) on the selected result. Add '
        '<font face="Mono">aria-selected="true"</font> to the highlighted result for screen readers.', 'body_left'))
    story.append(P(
        '<b>Why:</b> A command palette without arrow-key navigation is a mouse-first tool, not a keyboard-first '
        'tool. The Constitution said "Ensure the command palette and keyboard shortcuts remain first-class." '
        'First-class means the user can use it without touching the mouse. Currently the user must either click '
        'a result or press Enter on the first result (which requires the desired result to be first). '
        'Arrow-key navigation is the expected behavior in every command palette (Linear, Raycast, Spotlight, '
        'VS Code).', 'body_left'))
    story.append(P(
        '<b>Acceptance test:</b> The auditor will open the command palette, type a query, press ArrowDown twice, '
        'and press Enter. The third result must be selected (not the first). The selected result must have a '
        'visible highlight. The auditor will also verify <font face="Mono">aria-selected</font> updates '
        'correctly for screen-reader users.', 'body_left'))
    story.append(P(
        '<b>Score delta:</b> +0.5 points (from 9 to 9.5). This is a polish item that moves the command palette '
        'from "functional" to "first-class."', 'body_left'))

    story.append(P('Guideline #5 — Build ONE real ambient integration as a proof of concept (REQUIRED for 10/10, '
                   'not for 9/10)', 'h2'))
    story.append(P(
        '<b>What:</b> Build a Chrome extension that injects a Maestro contextual card into GitHub PR pages. The '
        'card should appear when a user views a PR and should say something like "You\'ve solved this before. '
        'Review?" (per the Constitution\'s example). The card should fetch data from the Maestro API '
        '(<font face="Mono">/api/oem/ask?q=...</font> with the PR title). The extension should be packaged and '
        'installable from the <font face="Mono">maestro-ambient-extension/</font> directory that already exists '
        'in the repository.', 'body_left'))
    story.append(P(
        '<b>Why:</b> The Constitution\'s WORK surface vision was "The user never opens Maestro. Maestro quietly '
        'appears [inside GitHub/Slack/Jira/Zoom]." Round 8 made the WORK surface cards fetch real data, but '
        'WORK is still a page inside Maestro. The ambient-integration vision requires a native integration. '
        'One real integration (Chrome extension for GitHub) is worth more than 4 static cards describing '
        'hypothetical integrations. This is the difference between "Invisible Maestro" as a marketing claim and '
        '"Invisible Maestro" as a product reality.', 'body_left'))
    story.append(P(
        '<b>Acceptance test:</b> The auditor will install the Chrome extension, navigate to a GitHub PR page, '
        'and verify the Maestro card appears. The card must fetch real data from the Maestro API (not '
        'hardcoded). The card must be dismissible. The card must not appear on non-PR pages. The extension '
        'manifest must request only the minimum permissions.', 'body_left'))
    story.append(P(
        '<b>Score delta:</b> +0.5 points (from 9.5 to 10). This is the hardest guideline — it requires building '
        'a browser extension, which is a separate codebase with its own packaging. It is not required for 9/10. '
        'It IS required for 10/10. Post-pilot milestone.', 'body_left'))

    # ── SCORE ROADMAP ────────────────────────────────────────────────────
    story.append(P('Score Roadmap: 7/10 → 9/10 → 10/10', 'h1'))

    roadmap_rows = [
        ['Guideline', 'Effort', 'Score Delta', 'Required For', 'Status'],
        ['#1 Full-suite output in every claim', '0 min (habit)', '0 (guardrail)', 'Maintaining 7/10', 'Coder learned this in round 9'],
        ['#2 CI workflow (.github/workflows/test.yml)', '30 min', '+1 (7→8)', '8/10', 'Not yet done'],
        ['#3 Universal vocabulary hiding (humanize() utility)', '1-2 hours', '+1 (8→9)', '9/10', 'Not yet done'],
        ['#4 Arrow-key nav in command palette', '30 min', '+0.5 (9→9.5)', '9.5/10', 'Not yet done'],
        ['#5 ONE real ambient integration (Chrome ext for GitHub)', '1-2 weeks', '+0.5 (9.5→10)', '10/10', 'Post-pilot'],
        ['', '', '', '', ''],
        ['TOTAL to reach 9/10', '~2-3 hours', '+2', '9/10', 'Guidelines #2 + #3'],
        ['TOTAL to reach 10/10', '~2-3 weeks', '+3', '10/10', 'Guidelines #2 + #3 + #4 + #5'],
    ]
    t = Table(roadmap_rows, colWidths=[55*mm, 22*mm, 25*mm, 25*mm, PAGE_W - MARGIN_L - MARGIN_R - 127*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, 5), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, 7), (-1, 8), colors.HexColor('#f0fdf4')),
        ('FONTNAME', (0, 7), (-1, 8), FONT_HEAD_B),
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
        '<b>Path to 9/10: ~2-3 hours of work.</b> Do Guideline #2 (CI, 30 min) and Guideline #3 (universal '
        'vocabulary hiding, 1-2 hours). That is all. The coder has demonstrated the ability to do both: CI is '
        'a standard GitHub Actions workflow, and the vocabulary hiding is extracting an existing function and '
        'applying it to more surfaces. No new capabilities required. No architectural changes. Just thoroughness.', 'body'))

    story.append(P(
        '<b>Path to 10/10: ~2-3 weeks of work.</b> Add Guidelines #4 (arrow-key nav, 30 min) and #5 (one real '
        'ambient integration, 1-2 weeks). Guideline #5 is the hard one — it requires building a Chrome '
        'extension, which is a separate codebase. But it is also the guideline that would make Maestro '
        'genuinely "invisible" — appearing inside GitHub without the user opening Maestro. That is the '
        'Constitution\'s vision. Post-pilot.', 'body'))

    # ── WHAT 9/10 MEANS ──────────────────────────────────────────────────
    story.append(P('What 9/10 Means vs 10/10', 'h1'))
    story.append(P(
        '<b>9/10</b> means: the Constitution is honored at the structural level (sidebar collapsed, command '
        'palette, 4 meta-surfaces), the vocabulary is hidden universally (no internal terms visible anywhere), '
        'confidence numbers are replaced with stories, the Organizational Dot works, the test suite is green '
        'AND verified by CI on every push, and the product feels calm. The remaining 1 point is the ambient '
        'integration — the Constitution\'s vision of Maestro appearing inside other tools. 9/10 is pilot-ready '
        'and procurement-defensible. A Fortune 100 CTO would not object to the interface.', 'body'))

    story.append(P(
        '<b>10/10</b> means: 9/10 PLUS one real ambient integration (Maestro appears inside GitHub via Chrome '
        'extension). This is the "new category" the Constitution asked for. 10/10 is not pilot-ready — it is '
        'category-defining. It requires building a browser extension, which is a separate product surface. '
        'Post-pilot.', 'body'))

    story.append(P(
        '<b>The coder should target 9/10 before the pilot.</b> Guidelines #2 and #3 are 2-3 hours of work and '
        'they close every remaining Constitution-adherence gap that is closeable without building a new product '
        'surface. Once those are done, the product is genuinely pilot-ready on both axes (security: YES per '
        'round 6; Constitution adherence: 9/10). The pilot then determines whether 10/10 (ambient integration) '
        'is worth the investment.', 'body'))

    # ── RECURRING PATTERNS ───────────────────────────────────────────────
    story.append(P('Recurring Patterns the Auditor Has Caught (For the Coder\'s Reference)', 'h1'))
    story.append(P(
        'Across 9 rounds, the auditor has identified four recurring patterns in the coder\'s work. The coder '
        'has corrected each one when pointed out. The guidelines below make the corrections permanent.', 'body'))

    story.append(P('Pattern 1: Subset test reporting', 'h2'))
    story.append(P(
        'Round 3: "837+ tests pass" (18 failed). Round 8: "9 tests pass, 0 failed" (3 of 27 failed). Round 9: '
        'FULL suite run, claim accurate. <b>Correction:</b> Guideline #1 (always paste full-suite output). '
        '<b>Status:</b> Coder learned this in round 9. Maintain it.', 'body'))

    story.append(P('Pattern 2: Adding instead of collapsing', 'h2'))
    story.append(P(
        'Round 7: coder added 4 surfaces on top of 22 (sidebar went 19 → 23, claimed 22 → 4). Round 8: coder '
        'genuinely collapsed (sidebar went 23 → 5). <b>Correction:</b> When the Constitution says "collapse," '
        'remove, do not add. The fundamental law is "less interface," not "more interface on top of old '
        'interface." <b>Status:</b> Coder learned this in round 8. Maintain it.', 'body'))

    story.append(P('Pattern 3: Fixing half a vulnerability', 'h2'))
    story.append(P(
        'Round 4: coder fixed OIDC ImportError fail-open but left algorithm injection on the same line. Round 5: '
        'coder fixed algorithm injection. Round 6: coder added AST regression test (but it only caught the '
        'typo\'d pattern). <b>Correction:</b> When fixing a vulnerability, re-read the finding carefully and '
        'fix ALL of it, not just the first half. Add a regression test that catches ALL variants, not just the '
        'exact string that was present. <b>Status:</b> Coder learned this in round 6. Maintain it.', 'body'))

    story.append(P('Pattern 4: Honest docstrings instead of algorithmic improvements', 'h2'))
    story.append(P(
        'Round 5: coder added honesty docstrings to Ask (keyword search) and Simulator (linear formulas) '
        'instead of improving the algorithms. This was the right call for the pilot — document the limitation, '
        'let pilot data decide whether to invest. <b>Correction:</b> None needed. This is the right pattern. '
        'The pilot determines whether the algorithms need upgrading. <b>Status:</b> Correct behavior. '
        'Maintain it.', 'body'))

    # ── FINAL VERDICT ────────────────────────────────────────────────────
    story.append(P('Final Verdict — Round 9', 'h1'))

    verdict_box = Table([[
        Paragraph(
            '<font color="white" size="20"><b>YES</b></font><br/><br/>'
            '<font color="white" size="11"><b>— test suite green, claim verified. Do Guidelines #2 + #3 for 9/10, then ship the pilot.</b></font>',
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
        '<b>The round-9 commit is verified. 389 tests pass, 0 fail. The coder\'s claim is accurate, including '
        'the "FULL suite, not a subset" assertion.</b> The recurring pattern of subset-test-reporting has been '
        'corrected. The test split is honest and reflects the post-collapse structure. No regressions anywhere.', 'body'))

    story.append(P(
        '<b>The path to 9/10 is clear and small.</b> Two guidelines, 2-3 hours: (1) add CI '
        '(<font face="Mono">.github/workflows/test.yml</font>), (2) extract the vocabulary-hiding regex into a '
        'shared <font face="Mono">humanize()</font> utility and apply it to all surfaces. Once those are done, '
        'the product is at 9/10 Constitution adherence and YES on security. That is the threshold for shipping '
        'the pilot. The 90-day pilot then determines whether 10/10 (ambient integration) is worth the '
        'investment.', 'body'))

    story.append(P(
        '<b>The engagement has converged.</b> Nine rounds. The security axis went 3/10 → 7/10 (YES). The '
        'product-philosophy axis went 5/10 → 7/10 (YES WITH MINOR FIXES). The test suite went 18 failures → 0 '
        'failures. The sidebar went 23 surfaces → 5. The coder fixed real bugs each round, admitted what they '
        'missed, and corrected recurring patterns when pointed out. The auditor retracted false claims and '
        'stood by true ones. The methodology — every claim checkable, every claim checked — is what made the '
        'convergence possible. The next step is empirical: run the pilot. Let real users decide whether the '
        'Invisible Maestro is a new category or a calm reskin. The code is ready.', 'body'))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'MaestroAgent_Round9_Test_Verification_and_9of10_Guidelines.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
