"""
Maestro Round 23 — V6 Phase 1 Verification + V6 Phase 2-3 Coding Instructions
V6 Phase 1 (Adaptive Nudges + Evolution Tracker) verified. Both DELIVERED.
Pattern maintained for 4 consecutive rounds. Next: V6 Phase 2-3.
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
SECTION_BG    = colors.HexColor('#fff7ed')
CARD_BG       = colors.HexColor('#ffedd5')
TABLE_STRIPE  = colors.HexColor('#fff7ed')
HEADER_FILL   = colors.HexColor('#7c2d12')
BORDER        = colors.HexColor('#fdba74')
ACCENT        = colors.HexColor('#c2410c')
TEXT_PRIMARY  = colors.HexColor('#1a1c1e')
TEXT_MUTED    = colors.HexColor('#6b7178')

ST_DELIVERED  = colors.HexColor('#15803d')
ST_PARTIAL    = colors.HexColor('#b45309')
ST_V6         = colors.HexColor('#c2410c')

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
                      "Maestro Round 23 — V6 Phase 1 Verified + V6 Phase 2-3 Instructions")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro Round 23 — V6 Phase 1 Verified + Phase 2-3 Instructions",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="Round-23 V6 Phase 1 verification + V6 Phase 2-3 coding instructions",
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
        f'<font color="{ACCENT.hexval()}"><b>ROUND 23 — V6 PHASE 1 VERIFIED + PHASE 2-3 INSTRUCTIONS</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'V6 Phase 1 Delivered. Pattern Holds for 4 Rounds.',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=28,
                       leading=32, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Adaptive Nudges + Evolution Tracker built and wired. Next: Background Adaptation + Trajectory Intervention.',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=12,
                       leading=16, textColor=HEADER_FILL, alignment=TA_LEFT, spaceAfter=14)
    ))

    # ── V6 PHASE 1 VERIFICATION ──────────────────────────────────────────
    story.append(P('V6 Phase 1 — Verification', 'h1'))

    v6_rows = [
        ['#', 'Spec', 'Backend', 'API', 'Frontend', 'Status'],
        ['1', 'Adaptive Nudge Engine', '193 lines, 3 nudge sources', '200, 3 nudges', 'TODAY nudge card with Accept/Dismiss (8 refs)', 'DELIVERED'],
        ['2', 'Evolution Tracker', '195 lines, 4 failure-mode sources', '200, 1 failure mode', 'LEARN "Mistakes no longer made" section', 'DELIVERED'],
    ]
    t = Table(v6_rows, colWidths=[6*mm, 28*mm, 30*mm, 22*mm, 50*mm, 22*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('LEADING', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TEXTCOLOR', (5, 1), (5, -1), ST_DELIVERED),
        ('FONTNAME', (5, 1), (5, -1), FONT_HEAD_B),
        ('ALIGN', (5, 0), (5, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))

    # TL;DR
    story.append(callout_box([
        Paragraph(f'<font color="{ST_DELIVERED.hexval()}"><b>V6 PHASE 1: DELIVERED. PATTERN HOLDS FOR 4 ROUNDS.</b></font>',
                  ParagraphStyle('callout_h', fontName=FONT_HEAD_B, fontSize=10,
                                 leading=13, textColor=ST_DELIVERED, spaceAfter=4)),
        P('Commit <font face="Mono">dd818aa</font>. 476 insertions across 5 files. 2 new backend modules '
          '(388 lines: adaptive_nudge.py 193, evolution_tracker.py 195). Both APIs return 200 with real '
          'data. Both wired to existing frontend surfaces (TODAY for nudges, LEARN for evolution tracker). '
          '<b>The "built but not applied" pattern has NOT recurred for 4 consecutive rounds</b> (rounds 16, '
          '18, 21, 23). This is the longest streak in the engagement.', 'body_left'),
        P('<b>V5 + V6 litmus tests: PASS.</b> Sidebar: 4 items (unchanged). No new panels. No new sidebar '
          'items. Nudge card in TODAY (8 refs). Evolution tracker in LEARN (1 ref). Both enhance existing '
          'surfaces. V5: UI simpler. V6: permanently improves the organization (nudges restructure work; '
          'tracker measures elimination).', 'body_left'),
        P('<b>Test suite: 423 pass, 0 fail, 2 skipped.</b> (389 API+auth + 34 frontend+cognitive). No '
          'regressions.', 'body_left'),
        P('<b>Nudge quality:</b> 3 nudges generated. Nudge 1 (Globex buying committee): evidence references '
          'causal data ("produced the same positive outcome 85 times"). Intervention is actionable. Nudge 2 '
          '(priya.m bottleneck): evidence references causal data ("81 times"). BUT intervention is generic '
          '("Proactively address the bottleneck") — not specific enough per the spec. Nudge 3 (deployment '
          'concentration): structural evidence (not causal — "only priya.m holds knowledge"). Intervention '
          'is specific ("Cross-train carlos.r on deployment"). Mixed quality — 2 of 3 nudges have causal '
          'evidence; 2 of 3 have actionable interventions; 1 of 3 has both. Pilot polish: improve the '
          '_derive_intervention() function to produce specific restructuring for all nudge types.', 'body_left'),
        P('<b>Evolution tracker quality:</b> 1 failure mode tracked (commitment integrity gap, status: '
          'active). 0 eliminated (honest: "the pilot is too young — needs 90+ days without recurrence"). '
          'This is correct honest degradation. frequency_history has 0 entries (the demo data does not '
          'have enough temporal resolution for per-period frequency). Minor data quality issue, not a '
          'blocker.', 'body_left'),
        P('<b>Score: V6 Phase 1 DELIVERED.</b> Both specs built, wired, verified. The product now has 15 '
          'cognitive engines across 6 constitutional versions. The organization can now be nudged toward '
          'better work patterns and its mistakes can be tracked toward elimination. Next: V6 Phase 2-3.', 'body_left'),
    ], bg=colors.HexColor('#f0fdf4'), border=colors.HexColor('#bbf7d0'), accent=ST_DELIVERED))

    story.append(Spacer(1, 6 * mm))

    # ── V6 PHASE 2-3 INSTRUCTIONS ────────────────────────────────────────
    story.append(PageBreak())
    story.append(P('V6 Phase 2-3 — Strict Coding Instructions (Next Task)', 'h1'))
    story.append(P(
        'V6 Phase 1 is complete. The next task is V6 Phase 2-3: Background Adaptation + Trajectory '
        'Intervention + Organizational DNA + Evolution Narrative. 4 specs, ~10.5 days. Build in order.', 'body'))

    # Spec #3
    story.append(P('V6 Spec #3 — Background Adaptation Loop (Build First, 2 days)', 'h2'))
    story.append(P(
        '<b>What:</b> V6 Law 2: "The organization should become more intelligent even when nobody opens '
        'Maestro." The Background Adaptation Loop runs on every signal ingest (not on user request), '
        'checks for improvement opportunities, and queues nudges for the next interaction.', 'body_left'))
    story.append(P(
        '<b>Build:</b>', 'body_left'))
    story.append(P('1. CREATE <font face="Mono">backend/maestro_oem/background_adaptation.py</font> — the '
                   'BackgroundAdaptationLoop. On every signal ingest (hooked into <font face="Mono">'
                   'oem_state.py live_ingest()</font>), the loop: (a) checks if the new signal creates a '
                   'new pattern that warrants a nudge, (b) checks if any active nudge should be escalated '
                   '(problem worsening), (c) checks if any resolved failure mode is recurring (regression '
                   'detection), (d) queues any generated nudges for the next user interaction.', 'body_left'))
    story.append(P('2. CREATE <font face="Mono">GET /api/oem/adaptation/status</font> endpoint.', 'body_left'))
    story.append(P('3. MODIFY <font face="Mono">backend/maestro_api/oem_state.py live_ingest()</font> — '
                   'call the background loop after each signal batch.', 'body_left'))
    story.append(P('4. MODIFY <font face="Mono">static/js/today.js</font> — if background-detected nudges '
                   'exist, show them with a "Maestro noticed this while you were away" label.', 'body_left'))
    story.append(P(
        '<b>Acceptance test:</b> 1) GET /api/oem/adaptation/status returns background_nudges + '
        'regression_alerts + escalation_alerts. 2) The loop runs on signal ingest (check '
        'oem_state.py calls it). 3) TODAY shows "while you were away" label for background nudges. '
        '4) V5 litmus: no new panel. 5) V6 litmus: runs in background (not on user request).', 'body_left'))

    # Spec #4
    story.append(P('V6 Spec #4 — Trajectory Intervention (Build Second, 2.5 days)', 'h2'))
    story.append(P(
        '<b>What:</b> Weak signal -> trajectory change -> quiet intervention -> failure prevented. The user '
        'never realizes something was prevented. "Trust between Engineering and Legal is declining. If '
        'unchecked, coordination will fail within 3 weeks. A joint review session reversed it before."', 'body_left'))
    story.append(P(
        '<b>Build:</b>', 'body_left'))
    story.append(P('1. CREATE <font face="Mono">backend/maestro_oem/trajectory_intervention.py</font> — '
                   'composes trajectories.py (V5 #7, exists) + institutional_recall.py (V5 #8, exists) + '
                   'adaptive_nudge.py (V6 #1, exists). Detects: trajectory declining, projected threshold '
                   'crossing, time_to_failure, historical analogue, intervention.', 'body_left'))
    story.append(P('2. CREATE <font face="Mono">GET /api/oem/interventions</font> endpoint.', 'body_left'))
    story.append(P('3. MODIFY <font face="Mono">static/js/today.js</font> — if a trajectory intervention '
                   'exists with high urgency, show it as the TOP item: "Maestro detected a risk..."', 'body_left'))
    story.append(P(
        '<b>Acceptance test:</b> 1) GET /api/oem/interventions returns interventions array (or honest '
        '"stable"). 2) Each has trajectory, time_to_failure, intervention, evidence_count, urgency. '
        '3) time_to_failure computed from trajectory slope. 4) TODAY shows trajectory intervention as '
                   'top item when urgency is high. 5) V5 litmus: no new panel. 6) V6 litmus: prevents '
                   'failures before they occur.', 'body_left'))

    # Spec #5
    story.append(P('V6 Spec #5 — Organizational DNA (Build Third, 3 days)', 'h2'))
    story.append(P(
        '<b>What:</b> "This is what YOUR organization would do when it is at its best." Not industry best '
        'practice — the org\'s own best self. 7 chromosomes that evolve over time and drive recommendation '
        'filtering.', 'body_left'))
    story.append(P(
        '<b>Build:</b>', 'body_left'))
    story.append(P('1. CREATE <font face="Mono">backend/maestro_oem/organizational_dna.py</font> — extends '
                   'personality.py (V3, exists) with: evolution tracking (then vs now), decision-style '
                   'inference, recommendation alignment filtering.', 'body_left'))
    story.append(P('2. 7 chromosomes: decision_style, risk_appetite, learning_velocity, '
                   'communication_style, conflict_style, innovation_style, execution_style. Each with value, '
                   'confidence, evidence_count, basis.', 'body_left'))
    story.append(P('3. CREATE <font face="Mono">GET /api/oem/dna</font> endpoint.', 'body_left'))
    story.append(P('4. MODIFY <font face="Mono">backend/maestro_oem/wisdom.py</font> — filter recommendations '
                   'by DNA alignment ("This aligns with your consensus-driven style").', 'body_left'))
    story.append(P('5. MODIFY <font face="Mono">static/js/learn.js</font> — add "Who your organization has '
                   'become" section showing DNA evolution.', 'body_left'))
    story.append(P(
        '<b>Acceptance test:</b> 1) GET /api/oem/dna returns 7 chromosomes with value + confidence + '
        'evidence_count. 2) At least 1 evolution entry (then/now/narrative). 3) recommendation_alignment '
        'includes a real rec_id. 4) wisdom.py references DNA alignment. 5) LEARN shows DNA section. '
        '6) V5 litmus: no new panel. 7) V6 litmus: DNA evolves and drives better-aligned recommendations.', 'body_left'))

    # Spec #6
    story.append(P('V6 Spec #6 — Evolution Narrative Engine (Build Last, 2 days)', 'h2'))
    story.append(P(
        '<b>What:</b> The organization\'s autobiography. Not CRM, not Slack history — its autobiography. '
        'Chapters with titles, periods, narratives, lessons. "Your organization started fast but fragile. '
        'It learned that review produces better outcomes."', 'body_left'))
    story.append(P(
        '<b>Build:</b>', 'body_left'))
    story.append(P('1. CREATE <font face="Mono">backend/maestro_oem/evolution_narrative.py</font> — composes '
                   'organizational_dna.py (V6 #5, just built) + evolution_tracker.py (V6 #2, exists) + '
                   'identity.py (V4, exists) + skepticism.py (V4, exists) + principles.py (V4, exists).', 'body_left'))
    story.append(P('2. Produces chapters: {title, period, narrative (3+ sentences), lessons (2+), '
                   'evidence_count}. Plus overall_story and next_chapter_prediction.', 'body_left'))
    story.append(P('3. CREATE <font face="Mono">GET /api/oem/autobiography</font> endpoint.', 'body_left'))
    story.append(P('4. CREATE <font face="Mono">static/js/autobiography.js</font> — surface (command-palette '
                   'only, NOT in sidebar). Renders the autobiography as a calm narrative.', 'body_left'))
    story.append(P(
        '<b>Acceptance test:</b> 1) GET /api/oem/autobiography returns chapters (2+ or honest "first '
        'chapter"). 2) Each chapter has title, period, narrative (3+ sentences), lessons (2+), '
        'evidence_count. 3) overall_story and next_chapter_prediction non-empty. 4) Autobiography surface '
        'accessible via Ctrl+K. 5) V5 litmus: command-palette only (no new sidebar item). 6) V6 litmus: '
        'makes the institution\'s evolution visible and irreversible.', 'body_left'))

    # ── BUILD ORDER + RULES ──────────────────────────────────────────────
    story.append(P('Build Order', 'h1'))

    order_rows = [
        ['Step', 'Spec', 'Effort', 'Frontend Surface', 'Key Dependency'],
        ['1', '#3 Background Adaptation', '2 days', 'TODAY (while-you-were-away label)', 'oem_state.py live_ingest() hook + adaptive_nudge.py (V6 #1)'],
        ['2', '#4 Trajectory Intervention', '2.5 days', 'TODAY (top item when urgent)', 'trajectories.py (V5 #7) + recall.py (V5 #8) + adaptive_nudge.py (V6 #1)'],
        ['3', '#5 Organizational DNA', '3 days', 'LEARN (who you\'ve become)', 'personality.py (V3) + wisdom.py (V4)'],
        ['4', '#6 Evolution Narrative', '2 days', 'Autobiography surface (Ctrl+K only)', 'organizational_dna.py (V6 #5) + evolution_tracker.py (V6 #2) + identity.py (V4)'],
        ['', '', '', '', ''],
        ['TOTAL', '4 specs', '~10 days', 'TODAY + LEARN + Autobiography (all existing or command-palette)', 'V5 complete + V6 Phase 1 complete'],
    ]
    t = Table(order_rows, colWidths=[10*mm, 35*mm, 16*mm, 45*mm, 55*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, 4), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#ffedd5')),
        ('FONTNAME', (0, 6), (-1, 6), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]))
    story.append(t)

    # ── STRICT RULES ─────────────────────────────────────────────────────
    story.append(P('Strict Rules for V6 Phase 2-3', 'h1'))

    rules = [
        ['Rule', 'Enforcement'],
        ['1. Build in order: #3 -> #4 -> #5 -> #6', 'Dependencies are real. #4 needs #3 (background nudges). #6 needs #5 (DNA) + #2 (tracker).'],
        ['2. Background Adaptation MUST hook into live_ingest()', 'Not a user-triggered API. Must run on signal ingest. V6 Law 2: "even when nobody opens Maestro."'],
        ['3. Trajectory Intervention MUST compute time_to_failure from slope', 'Not hardcoded. The trajectory slope (from trajectories.py) projects when the dimension crosses the danger threshold.'],
        ['4. DNA MUST filter recommendations (wisdom.py)', 'Not just display. wisdom.py must reference DNA alignment when synthesizing judgment. "This aligns with your consensus-driven style."'],
        ['5. Autobiography is command-palette ONLY', 'NOT in the sidebar (stays at 4 items). V5 litmus: no new sidebar items.'],
        ['6. V5 litmus: UI SIMPLER', 'No new panels in sidebar. New content enhances TODAY, LEARN, or command-palette surfaces.'],
        ['7. V6 litmus: permanently improves the organization', '#3: background adaptation (runs without user). #4: prevents failures. #5: DNA evolves and drives recommendations. #6: makes evolution visible and irreversible.'],
        ['8. 5-point checklist (all YES)', '1) Full acceptance test. 2) Application not existence. 3) Full test suite. 4) Live API. 5) UI simpler + org permanently improved.'],
        ['9. No silent skips', 'If a spec is deferred, say so explicitly. Do NOT claim "all 4 delivered" if only 3 are built.'],
        ['10. Run FULL test suite', '423+ tests. Report exact count. No subsets.'],
    ]
    t = Table(rules, colWidths=[55*mm, PAGE_W - MARGIN_L - MARGIN_R - 55*mm])
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
    ]))
    story.append(t)

    story.append(Spacer(1, 6 * mm))

    # ── FINAL CHARGE ─────────────────────────────────────────────────────
    story.append(P('Final Charge', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ST_V6.hexval()}"><b>V6 PHASE 1 DONE. PHASE 2-3 NEXT.</b></font>',
                  ParagraphStyle('charge_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ST_V6, spaceAfter=4)),
        P('V6 Phase 1 is delivered. Adaptive Nudges restructure work. Evolution Tracker measures '
          'eliminated mistakes. The pattern has held for 4 consecutive rounds. The test suite is green. '
          '15 cognitive engines across 6 constitutional versions, all invisible, all enhancing existing '
          'surfaces.', 'body_left'),
        P('<b>Build V6 Phase 2-3 next.</b> 4 specs, ~10 days. Background Adaptation makes Maestro active '
          'when nobody is looking. Trajectory Intervention prevents failures before they occur. '
          'Organizational DNA encodes the institution\'s evolving judgment. Evolution Narrative produces '
          'the autobiography. Build in order: #3 -> #4 -> #5 -> #6.', 'body_left'),
        P('<b>The V6 constitutional law:</b> "Every interaction must permanently improve the organization." '
          'Background adaptation improves without interaction. Trajectory intervention prevents failures. '
          'DNA evolves and filters recommendations. Autobiography makes evolution irreversible. All four '
          'permanently improve the organization. Build them.', 'body_left'),
        P('<b>After V6 Phase 2-3:</b> V6 is complete. Then V7.1 (self-revising institutional model with '
          'Bayesian competing hypotheses). The path is clear. Build V6 Phase 2-3. Then V7.1. Then ship '
          'the 90-day pilot. The Invisible Layer + Institutional Adaptation + Self-Revising Model = an '
          'operating system for institutional learning. Build it.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ST_V6))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'MaestroAgent_Round23_V6_Phase1_Verified_Phase2_3_Instructions.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
