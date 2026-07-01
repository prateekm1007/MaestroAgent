"""
Maestro Constitution V7 — The Self-Revising Institutional Model
Engineering Specification for the Coder.

V3 observed. V4 judged. V5 disappeared. V6 adapts behavior. V7 adapts THEORY.
The progression: Observe → Judge → Disappear → Adapt → Understand → Evolve.
V7's constitutional law: "Every recommendation must make Maestro's understanding
of the organization more accurate." The closed learning loop: reality disagrees
with Maestro → model updates → better recommendation → better outcome.
Same discipline: every spec grounded in the actual codebase, with acceptance tests.
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
SECTION_BG    = colors.HexColor('#fdf4ff')
CARD_BG       = colors.HexColor('#f5d0fe')
TABLE_STRIPE  = colors.HexColor('#fdf4ff')
HEADER_FILL   = colors.HexColor('#581c87')
BORDER        = colors.HexColor('#d8b4fe')
ACCENT        = colors.HexColor('#7e22ce')  # deep purple — V7, the self-revising model
TEXT_PRIMARY  = colors.HexColor('#1a1c1e')
TEXT_MUTED    = colors.HexColor('#6b7178')

ST_V7         = colors.HexColor('#7e22ce')
ST_DELIVERED  = colors.HexColor('#15803d')
ST_PARTIAL    = colors.HexColor('#b45309')

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
                      "Maestro Constitution V7 — The Self-Revising Institutional Model  ·  Round 20")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro Constitution V7 — The Self-Revising Institutional Model",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="Round-20 V7 engineering specification — self-revising institutional theory",
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

def spec_block(num, name, principle, gap, files, api, acceptance, effort, deps):
    flowables = []
    header = Table([[
        Paragraph(f'<font color="white"><b>SPEC #{num}</b></font>',
                  ParagraphStyle('sh', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=colors.white, alignment=TA_CENTER)),
        Paragraph(f'<font color="white"><b>{name}</b></font>',
                  ParagraphStyle('st', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=colors.white, alignment=TA_LEFT))
    ]], colWidths=[28*mm, PAGE_W - MARGIN_L - MARGIN_R - 28*mm - 24])
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ST_V7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    flowables.append(header)

    def field(label, value):
        return [
            Paragraph(f'<font color="{TEXT_MUTED.hexval()}"><b>{label}</b></font>', S['label']),
            P(value, 'body_left'),
        ]

    flowables += field('V7 Principle', principle)
    flowables += field('Current codebase gap', gap)
    flowables += field('Files to create/modify', files)
    flowables += field('API contract', api)
    flowables += [Paragraph(f'<font color="{TEXT_MUTED.hexval()}"><b>Acceptance test (auditor will run)</b></font>', S['label']),
                  P(acceptance, 'body_left')]
    flowables += field('Effort', effort)
    flowables += field('Dependencies', deps)
    flowables.append(Spacer(1, 8))
    return flowables


def build_story():
    story = []

    # ── COVER ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f'<font color="{ACCENT.hexval()}"><b>ROUND 20 — CONSTITUTION V7: THE SELF-REVISING INSTITUTIONAL MODEL</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'The Self-Revising Institutional Model',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=28,
                       leading=32, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'V6 adapts behavior. V7 adapts THEORY. The closed learning loop: reality disagrees with Maestro, model updates, better recommendation, better outcome.',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=12,
                       leading=16, textColor=HEADER_FILL, alignment=TA_LEFT, spaceAfter=14)
    ))

    meta = Table([
        [Paragraph('<b>Reviewer</b>', S['small']), P('Independent (Super Z, Z.ai)', 'small')],
        [Paragraph('<b>Baseline</b>', S['small']), P('Commit a044a4a. V5 Phase 1 complete. V5 Specs #4-#8 NOT built. V6 NOT started. 63 backend modules, 27 frontend files.', 'small')],
        [Paragraph('<b>V7 shift</b>', S['small']), P('V6 adapts the organization\'s behavior. V7 adapts Maestro\'s own THEORY of how the organization works. The model revises itself when reality disagrees. Maestro stops being an adaptive system and becomes a compounding institutional asset.', 'small')],
        [Paragraph('<b>Three constitutional laws</b>', S['small']), P('Law 1: "Every interaction must permanently improve the organization." Law 2: "The organization becomes more intelligent even when nobody opens Maestro." Law 3 (NEW): "Every recommendation must make Maestro\'s understanding of the organization more accurate."', 'small')],
        [Paragraph('<b>Deliverable</b>', S['small']), P('6 specifications across 3 phases: (1) Institution Model + governance modes, (2) closed learning loop + model revision, (3) living organizational model + compounding judgment. Each has API + acceptance test + build order.', 'small')],
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

    # ── PREAMBLE ─────────────────────────────────────────────────────────
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>WHY V7 EXISTS</b></font>',
                  ParagraphStyle('callout_h', fontName=FONT_HEAD_B, fontSize=10,
                                 leading=13, textColor=ACCENT, spaceAfter=4)),
        P('V6 introduced adaptation: Maestro quietly restructures work, tracks eliminated failure modes, '
          'and produces the organization\'s autobiography. But V6 adapts BEHAVIOR — it changes what the '
          'organization does. It does not adapt its own THEORY of how the organization works. After two '
          'years, V6 Maestro knows "Engineering trusts Legal." But it does not know "Engineering trusts '
          'Legal ONLY when security reviews are finished before sprint planning, because three previous '
          'coordination failures established that norm." That is an internal organizational theory — a '
          'causal model that explains WHY, not just WHAT.', 'body_left'),
        P('<b>V7 is the self-revising layer.</b> V7 says: every time reality disagrees with Maestro\'s '
          'prediction, the model updates. Every recommendation makes Maestro\'s understanding more accurate. '
          'The learning loop closes: signal → recommendation → outcome → model updated → better '
          'recommendation → better outcome. Maestro stops being an adaptive system and becomes a compounding '
          'institutional asset — one that gets smarter about THIS specific organization every day, in a way '
          'that cannot be copied because it is built from years of resolved disagreements between Maestro '
          'and reality.', 'body_left'),
        P('<b>The progression is now complete:</b> V3 Observe → V4 Judge → V5 Disappear → V6 Adapt → '
          '<b>V7 Understand</b> → V8 Evolve. V7 is "Understand" — the institution model that continuously '
          'revises its causal theory of how the organization works. V8 will be "Evolve" — the point where '
          'the accumulated judgment becomes irreplaceable and the product stops being primarily software '
          'and starts being an institutional asset.', 'body_left'),
        P('<b>Three constitutional laws (all mandatory):</b>', 'body_left'),
        P('<b>Law 1 (from V6):</b> "Every interaction must permanently improve the organization."', 'body_left'),
        P('<b>Law 2 (from V6):</b> "The organization should become more intelligent even when nobody opens Maestro."', 'body_left'),
        P('<b>Law 3 (NEW in V7):</b> "Every recommendation must make Maestro\'s understanding of the '
          'organization more accurate." This closes the learning loop. After each recommendation resolves '
          '(hit or miss), the model revises. Reality disagrees → model updates → next recommendation is '
          'better. This is genuine organizational learning — not calibration (adjusting confidence), but '
          'theory revision (adjusting understanding).', 'body_left'),
        P('<b>The strategic risk principle (NEW in V7):</b> Enterprises are extremely sensitive to '
          'autonomous changes. V7 introduces three governance modes: Recommendation ("I suggest..."), '
          'Execution ("I\'ve prepared the workflow"), and Autonomous Execution ("I\'ve already changed it"). '
          'Each mode has explicit approval boundaries. This makes the system adoptable in regulated '
          'enterprises while preserving the long-term vision.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── SPEC SUMMARY ─────────────────────────────────────────────────────
    story.append(P('The 6 V7 Specifications', 'h1'))
    story.append(P(
        'V7 has 6 specs in 3 phases. Phase 0 is the V5+V6 backlog (must complete first). Phase 1 creates '
        'the Institution Model and governance modes. Phase 2 closes the learning loop. Phase 3 creates the '
        'living organizational model and compounding judgment. Total ~18 days after V5+V6 backlog.', 'body'))

    rows = [
        ['#', 'Specification', 'Phase', 'Effort', 'What It Does'],
        ['0', 'V5 Backlog (#4-#8) + V6 Specs (#1-#6)', '0', '~24 days', 'Forgetting, Causal, Temporal, Imagination, Recall + Adaptive Nudges, Evolution Tracker, Background Adaptation, Trajectory Intervention, Org DNA, Autobiography. MUST finish before V7.'],
        ['1', 'Institution Model', '1', '3 days', 'A continuously revised causal model answering "How does THIS organization actually work?"'],
        ['2', 'Three-Mode Governance', '1', '2 days', 'Recommendation / Execution / Autonomous Execution with explicit approval boundaries'],
        ['3', 'Closed Learning Loop', '2', '2.5 days', 'Reality disagrees with Maestro -> model updates -> better recommendation'],
        ['4', 'Model Revision Engine', '2', '2 days', 'When a prediction is resolved, revise the institution model\'s causal theory'],
        ['5', 'Living Organizational Model', '3', '3 days', 'Merged DNA + Narrative + Institution Model into one self-revising substrate'],
        ['6', 'Compounding Judgment Tracker', '3', '1.5 days', 'Tracks whether Maestro\'s recommendations are getting MORE accurate over time'],
        ['', '', '', '', ''],
        ['TOTAL', '6 V7 specs (after V5+V6 backlog)', '3 phases', '~14 days', 'V7: from adaptive system to compounding institutional asset'],
    ]
    t = Table(rows, colWidths=[8*mm, 42*mm, 12*mm, 18*mm, PAGE_W - MARGIN_L - MARGIN_R - 80*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, 7), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, 9), (-1, 9), colors.HexColor('#f5d0fe')),
        ('FONTNAME', (0, 9), (-1, 9), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (3, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>Build order: Phase 0 (V5+V6 backlog, ~24 days, MANDATORY) -> Phase 1 (Institution Model + '
        'Governance, ~5 days) -> Phase 2 (Closed Loop + Model Revision, ~4.5 days) -> Phase 3 (Living '
        'Model + Compounding Judgment, ~4.5 days). Total ~14 days after backlog. Do NOT start V7 until '
        'V5+V6 backlog is complete.</b>', 'body'))

    story.append(PageBreak())

    # ── PHASE 0: BACKLOG ─────────────────────────────────────────────────
    story.append(P('Phase 0 — V5+V6 Backlog (MANDATORY Prerequisite)', 'h1'))
    story.append(P(
        'V7 specs build on V5 (causal cognition, temporal trajectories, institutional recall) and V6 '
        '(adaptive nudges, evolution tracker, organizational DNA, autobiography). NONE of these exist yet. '
        'The Institution Model (V7 Spec #1) requires causal chains (V5 #6) and temporal trajectories (V5 '
        '#7). The Closed Learning Loop (V7 Spec #3) requires the evolution tracker (V6 #2). The Living '
        'Organizational Model (V7 Spec #5) merges DNA (V6 #5) and the autobiography (V6 #6).', 'body'))

    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>PHASE 0 IS MANDATORY. DO NOT BUILD V7 ON A MISSING FOUNDATION.</b></font>',
                  ParagraphStyle('warn_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ACCENT, spaceAfter=4)),
        P('V5 Specs #4-#8 are NOT BUILT (verified at commit a044a4a). V6 Specs #1-#6 are NOT BUILT. '
          'V7 specs build on ALL of them. The Institution Model needs causal chains. The Closed Learning '
          'Loop needs the evolution tracker. The Living Model needs DNA + autobiography. Build V5 Phase 2-3 '
          'first (see V5 Phase 2-3 Coding Instructions). Then build V6 Phase 1-3 (see V6 spec). Then build '
          'V7. Skipping ahead will produce a model that looks like it works but has no causal foundation.', 'body_left'),
        P('<b>Estimated backlog: ~24 days</b> (9 days V5 Phase 2-3 + 15 days V6 Phase 1-3). V7 itself is '
          '~14 days. Total to V7 completion: ~38 days from current state.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ACCENT))

    # ── PHASE 1: INSTITUTION MODEL + GOVERNANCE ──────────────────────────
    story.append(PageBreak())
    story.append(P('Phase 1 — Institution Model + Governance Modes', 'h1'))
    story.append(P(
        'Phase 1 is the V7 foundation. The Institution Model is not another engine — it is the continuously '
        'revised causal model that answers "How does THIS organization actually work?" It sits underneath '
        'DNA, nudges, trajectories, and narratives. Governance modes make autonomous action safe for '
        'regulated enterprises.', 'body'))

    # SPEC 1
    story.extend(spec_block(
        1, 'Institution Model — "How does THIS organization actually work?"',
        'V7: "What\'s missing is an explicit internal model. A continuously revised causal model answering: How does THIS organization actually work? Not how do organizations work — THIS one." After two years, Maestro should know: "Engineering trusts Legal ONLY when security reviews are finished before sprint planning, because three previous coordination failures established that norm." That is an internal organizational theory.',
        'model.py (ExecutionModel) is a static accumulator — signals are added, counts increase, but the model does not revise its causal understanding. personality.py infers traits but does not explain WHY. wisdom.py synthesizes judgment but does not maintain a causal theory. The gap: no module maintains a causal model of how the specific organization works — its norms, causal pathways, incentives, trust dynamics, informal power, bottlenecks, and hidden dependencies. Maestro knows WHAT happens but not WHY it happens in THIS organization.',
        'CREATE backend/maestro_oem/institution_model.py — the InstitutionModel. A continuously revised causal model with 5 layers: (1) Norms ("Engineering waits for Legal before deploying auth changes"), (2) Causal Pathways ("Legal review before launch causes 27% fewer post-launch bugs"), (3) Incentives ("Engineers prioritize velocity because sprint velocity is the primary review metric"), (4) Trust Dynamics ("Engineering trusts Legal only when security reviews precede sprint planning"), (5) Hidden Dependencies ("The OAuth migration depends on Alice\'s institutional knowledge of the legacy auth flow"). Each layer is populated from: causal.py (causal chains), evidence_graph.py (dependencies), contradiction.py (norms from contradictions), personality.py + identity.py (incentives from drift). The model is REVISED on every prediction resolution (see Spec #4). CREATE GET /api/oem/institution-model endpoint. MODIFY static/js/cognition.js — add a "How your organization works" section (calm narrative, not a dashboard) that renders the institution model as human sentences.',
        'GET /api/oem/institution-model returns: { "norms": [{"norm": "Engineering waits for Legal before deploying auth changes", "established_by": "3 coordination failures in Q3 2024", "evidence_count": 5, "confidence": 0.82}], "causal_pathways": [{"pathway": "Legal review before launch -> 27% fewer post-launch bugs", "sequence_count": 3, "confidence": 0.91, "source": "causal.py chain causal-xxx"}], "incentives": [{"incentive": "Engineers prioritize velocity because sprint velocity is the primary review metric", "evidence_count": 8, "inferred_from": "6 of 8 PRs merged without full review"}], "trust_dynamics": [{"relationship": "Engineering -> Legal", "condition": "trust is high ONLY when security reviews precede sprint planning", "evidence_count": 4}], "hidden_dependencies": [{"dependency": "OAuth migration depends on Alice\'s institutional knowledge of legacy auth flow", "risk": "Alice departure would block the migration", "evidence_count": 3}], "narrative": "Your organization works as follows: Engineering prioritizes velocity (sprint velocity is the primary metric). Legal review is a norm, not a rule — it is followed when security reviews precede sprint planning. The OAuth migration has a hidden dependency on Alice. Three coordination failures in Q3 established the Engineering-Legal review norm." }. Must have at least 1 item in each of the 5 layers with evidence_count > 0 (or honest "insufficient data for this layer").',
        '1) GET /api/oem/institution-model returns 5 layers, each with at least 1 item (or honest "insufficient data"). 2) Each item has evidence_count > 0 and references real model data (not hardcoded). 3) The narrative synthesizes the layers into a "how your organization works" paragraph. 4) Cognition surface shows a "How your organization works" section with human sentences. 5) No organ names, no jargon. 6) V5 litmus: no new panel — enhances existing Cognition surface. 7) V7 litmus: does this make Maestro\'s understanding more accurate? YES — it is the model OF the organization.',
        '3 days (2 days model construction from existing data + 0.5 day API + 0.5 day frontend)',
        'V5 #6 (causal.py) for causal pathways. V5 #7 (temporal_trajectories.py) for norm establishment timing. V4 identity.py for incentives. V4 contradiction.py for norms. V6 #5 (organizational DNA) for trust dynamics baseline.'
    ))

    # SPEC 2
    story.extend(spec_block(
        2, 'Three-Mode Governance — Recommendation / Execution / Autonomous Execution',
        'V7: "Enterprises are extremely sensitive to autonomous changes. I would distinguish three modes: Recommendation (I suggest), Execution (I\'ve prepared the workflow), Autonomous Execution (I\'ve already changed it). Each has very different governance, risk, and compliance implications."',
        'No governance modes exist. The executive_function.py engine produces a plan but does not distinguish between suggesting, preparing, and autonomously executing. The adaptive_nudge.py engine (V6, not yet built) will propose work restructuring but has no governance framework for approval levels. The gap: Maestro has no concept of approval boundaries — it either suggests or doesn\'t, with no middle ground of "prepared but not executed."',
        'CREATE backend/maestro_oem/governance.py — the GovernanceManager. Defines 3 modes: (1) RECOMMENDATION — Maestro suggests an action; the user must approve and execute. (2) EXECUTION — Maestro prepares the artifact (drafted memo, calendar invite, workflow change document) but does not apply it; the user reviews and clicks "Apply." (3) AUTONOMOUS_EXECUTION — Maestro applies the change directly (e.g., updates the approval routing in Jira); the user is notified after the fact. Each mode has: a confidence threshold (RECOMMENDATION: any, EXECUTION: confidence >= 0.7, AUTONOMOUS: confidence >= 0.9 AND causal sequence_count >= 5), an approval requirement (RECOMMENDATION: none, EXECUTION: user clicks "Apply," AUTONOMOUS: no approval, but logged + reversible), and a reversibility flag (all modes are reversible; autonomous changes are logged in an immutable audit trail). CREATE GET /api/oem/governance/modes endpoint (shows available modes + thresholds). MODIFY backend/maestro_oem/executive_function.py — each execution plan includes a governance_mode field. MODIFY backend/maestro_oem/adaptive_nudge.py (V6, to be built) — each nudge specifies its governance mode. MODIFY static/js/today.js — the "Prepare" button now shows the governance mode: "Maestro suggests" (Recommendation), "Maestro has prepared" (Execution), "Maestro has updated" (Autonomous). Autonomous changes include a "Revert" button.',
        'GET /api/oem/governance/modes returns: { "modes": [ {"mode": "recommendation", "description": "Maestro suggests. You decide and execute.", "confidence_threshold": 0.0, "approval_required": false, "reversible": true}, {"mode": "execution", "description": "Maestro prepares. You review and apply.", "confidence_threshold": 0.7, "approval_required": true, "reversible": true}, {"mode": "autonomous", "description": "Maestro applies. You are notified.", "confidence_threshold": 0.9, "approval_required": false, "reversible": true, "audit_logged": true} ], "current_defaults": {"recommendation": true, "execution": true, "autonomous": false}, "summary": "Autonomous execution is disabled by default. Enable it in Settings when the organization is ready for Maestro to make changes on its own." }.',
        '1) GET /api/oem/governance/modes returns 3 modes with thresholds + approval requirements. 2) executive_function.py plans include governance_mode field. 3) Autonomous mode is DISABLED by default (safety). 4) Autonomous changes are logged in an audit trail. 5) All changes are reversible (Revert button). 6) TODAY shows governance mode labels: "Maestro suggests" / "Maestro has prepared" / "Maestro has updated." 7) V5 litmus: no new panel — labels on existing Prepare button. 8) V7 litmus: does this make Maestro\'s understanding more accurate? Indirectly — it makes Maestro\'s ACTIONS governed, which is a prerequisite for the learning loop (Spec #3).',
        '2 days (1 day governance engine + 0.5 day API + 0.5 day frontend labels + audit trail)',
        'V5 #2 (executive_function.py) for plan integration. V6 #1 (adaptive_nudge.py) for nudge integration.'
    ))

    # ── PHASE 2: CLOSED LEARNING LOOP + MODEL REVISION ───────────────────
    story.append(PageBreak())
    story.append(P('Phase 2 — Closed Learning Loop + Model Revision', 'h1'))
    story.append(P(
        'Phase 2 is the V7 core. The closed learning loop is what separates an adaptive system from a '
        'compounding institutional asset. When reality disagrees with Maestro\'s prediction, the model '
        'revises. The next recommendation is better. Over years, the accumulated revisions become '
        'irreplaceable organizational judgment.', 'body'))

    # SPEC 3
    story.extend(spec_block(
        3, 'Closed Learning Loop — reality disagrees, model updates, better recommendation',
        'V7 Law 3: "Every recommendation must make Maestro\'s understanding of the organization more accurate." Current loop: Signal -> Recommendation -> Adaptation -> Improvement. V7 loop: Signal -> Recommendation -> Outcome -> Model updated -> Better recommendation -> Better outcome. Maestro improves itself because reality disagreed with it.',
        'prediction_lifecycle.py (859 lines) resolves predictions as hit/miss. learning.py (993 lines) tracks calibration (Brier score, SHR). confidence.py (472 lines) adjusts confidence based on historical accuracy. BUT: none of these UPDATE THE MODEL\'S CAUSAL THEORY after a prediction is resolved. Calibration adjusts confidence (how sure am I?) but not understanding (how does the org work?). The gap: when Maestro predicts "this bottleneck will cause a velocity drop" and it DOESN\'T (miss), the confidence drops — but the causal model is not revised. Maestro does not learn "my theory of why bottlenecks cause velocity drops was wrong in this case because..."',
        'CREATE backend/maestro_oem/closed_learning_loop.py — the ClosedLearningLoop. On every prediction resolution (hooked into prediction_lifecycle.py _resolve()), the loop: (1) compares the predicted outcome to the actual outcome, (2) if MISS (prediction was wrong), identifies which causal assumption was incorrect, (3) calls institution_model.py to revise the assumption, (4) logs the revision (what changed, why, what the old theory was, what the new theory is), (5) updates the confidence calculator to reflect the revised understanding. CREATE GET /api/oem/learning-loop endpoint (shows recent revisions). MODIFY backend/maestro_oem/prediction_lifecycle.py _resolve() — call the closed learning loop after each resolution. MODIFY static/js/cognition.js — add a "What Maestro learned" section showing recent model revisions: "Maestro predicted the auth bottleneck would cause a velocity drop. It didn\'t — because Alice ad-hoc reviewed the PRs outside the formal workflow. Maestro revised: \'Bottlenecks cause velocity drops ONLY when no informal reviewer exists. Alice\'s informal review is a hidden dependency.\'"',
        'GET /api/oem/learning-loop returns: { "revisions": [ {"prediction_id": "pred-xxx", "predicted": "Auth bottleneck will cause 20% velocity drop", "actual": "No velocity drop — Alice reviewed PRs informally", "outcome": "miss", "revised_assumption": "Bottlenecks cause velocity drops ONLY when no informal reviewer exists", "old_theory": "Bottlenecks always cause velocity drops", "new_theory": "Bottlenecks cause velocity drops when no informal reviewer compensates", "revised_at": "...", "evidence_count": 1} ], "total_revisions": 1, "accuracy_trend": [ {"period": "2025-01", "accuracy": 0.72}, {"period": "2025-02", "accuracy": 0.78} ], "narrative": "Maestro has revised its understanding 1 time. Its prediction accuracy improved from 72% to 78% after the revision. The organization is getting easier to predict." }. Must have at least 1 revision (or honest "no predictions have been resolved yet — the learning loop has not triggered").',
        '1) GET /api/oem/learning-loop returns revisions array + accuracy_trend + narrative. 2) Each revision has predicted, actual, outcome, revised_assumption, old_theory, new_theory. 3) Auditor verifies the loop runs on prediction resolution (check prediction_lifecycle.py _resolve() calls the loop). 4) Auditor resolves a prediction (via POST /api/oem/predictions/resolve) and verifies a revision is created (if the prediction was a miss). 5) Cognition surface shows "What Maestro learned" section. 6) V7 litmus: does this make Maestro\'s understanding more accurate? YES — the model literally revises when it is wrong.',
        '2.5 days (1.5 days revision logic + 0.5 day API + 0.5 day frontend)',
        'V7 #1 (Institution Model) for the model that gets revised. V5 #6 (causal.py) for causal assumptions. prediction_lifecycle.py for resolution hook.'
    ))

    # SPEC 4
    story.extend(spec_block(
        4, 'Model Revision Engine — when a prediction resolves, revise the causal theory',
        'V7: "Maestro still adapts behavior. It doesn\'t yet adapt its own theory of the organization. Those are different things." The Model Revision Engine is the mechanism: when a prediction is resolved as a miss, it identifies which causal assumption was wrong and revises the institution model.',
        'The closed learning loop (Spec #3) detects misses and calls for revision. But the REVISION LOGIC — identifying which assumption was wrong and how to update it — does not exist. The gap: Maestro knows it was wrong but not HOW to revise its theory. This spec creates the revision logic: for each miss, trace the prediction back to its causal assumptions (via causal.py), identify which assumption was violated by the actual outcome, and generate a revised assumption.',
        'CREATE backend/maestro_oem/model_revision.py — the ModelRevisionEngine. For each prediction miss: (1) trace the prediction to its linked causal chains (from causal.py), (2) identify which causal assumption the prediction depended on, (3) compare the predicted causal pathway to the actual outcome, (4) generate a revised assumption that accounts for the miss, (5) update institution_model.py with the revised assumption, (6) log the revision (old theory, new theory, evidence). The revision logic uses the actual outcome to identify the missing variable: "Maestro predicted velocity would drop because of the bottleneck. It didn\'t. The missing variable was Alice\'s informal review. Revised: bottlenecks cause velocity drops ONLY when no informal reviewer compensates." CREATE GET /api/oem/model-revisions endpoint (shows revision history). MODIFY backend/maestro_oem/closed_learning_loop.py — call the revision engine on each miss.',
        'GET /api/oem/model-revisions returns: { "revisions": [ {"id": "rev-001", "triggered_by": "pred-xxx (miss)", "old_assumption": "Bottlenecks always cause velocity drops", "new_assumption": "Bottlenecks cause velocity drops when no informal reviewer compensates", "missing_variable_identified": "Alice\'s informal PR review", "evidence_for_revision": "Prediction pred-xxx missed because Alice reviewed 3 PRs outside the formal workflow", "revised_at": "...", "institution_model_layer": "causal_pathways"} ], "total_revisions": 1, "revision_rate": "1 revision per 12 predictions", "narrative": "Maestro has revised its causal theory 1 time. The revision identified a hidden variable (Alice\'s informal review) that the original theory missed. Future predictions about bottlenecks will account for this variable." }.',
        '1) GET /api/oem/model-revisions returns revisions with old_assumption, new_assumption, missing_variable_identified. 2) Each revision references the prediction that triggered it. 3) The new_assumption is MORE SPECIFIC than the old (it adds a condition). 4) Auditor triggers a miss (resolve a prediction as incorrect) and verifies a revision is created. 5) institution_model.py is updated (the causal_pathways layer reflects the new assumption). 6) V7 litmus: does this make Maestro\'s understanding more accurate? YES — each revision adds a condition that makes the theory more precise.',
        '2 days (1.5 days revision logic + 0.5 day API)',
        'V7 #1 (Institution Model) for the model being revised. V7 #3 (Closed Learning Loop) for the trigger. V5 #6 (causal.py) for causal assumptions to revise.'
    ))

    # ── PHASE 3: LIVING MODEL + COMPOUNDING JUDGMENT ─────────────────────
    story.append(PageBreak())
    story.append(P('Phase 3 — Living Organizational Model + Compounding Judgment', 'h1'))
    story.append(P(
        'Phase 3 merges everything. The Living Organizational Model unifies DNA + Narrative + Institution '
        'Model into one self-revising substrate. The Compounding Judgment Tracker proves that Maestro\'s '
        'recommendations are getting MORE accurate over time — the evidence that the product is a '
        'compounding institutional asset, not just software.', 'body'))

    # SPEC 5
    story.extend(spec_block(
        5, 'Living Organizational Model — merged DNA + Narrative + Institution Model',
        'V7: "DNA explains who you are. Narrative explains how you became that. They\'re two projections of the same underlying model. I\'d evolve the idea toward a Living Organizational Model." The Living Model unifies DNA (static identity), Narrative (how it evolved), and Institution Model (how it works) into one continuously revised substrate.',
        'V6 Spec #5 (Organizational DNA, not yet built) would infer 7 chromosomes. V6 Spec #6 (Evolution Narrative, not yet built) would produce chapters. V7 Spec #1 (Institution Model) maintains causal theory. Currently these are 3 separate modules with no integration. The gap: DNA, Narrative, and Institution Model are three projections of the same underlying reality but are not unified. A user asking "who is my organization?" gets different answers from DNA ("consensus-driven, cautious") vs Institution Model ("Engineering waits for Legal") vs Narrative ("started fast, learned to seek consensus"). The Living Model unifies them.',
        'CREATE backend/maestro_oem/living_model.py — the LivingOrganizationalModel. Composes: (1) DNA (from organizational_dna.py, V6 #5) — who the org IS, (2) Institution Model (from institution_model.py, V7 #1) — HOW the org WORKS, (3) Narrative (from evolution_narrative.py, V6 #6) — HOW the org BECAME what it is, (4) Revision history (from model_revision.py, V7 #4) — how Maestro\'s UNDERSTANDING has evolved. Produces a unified model: {identity (DNA), mechanics (Institution Model), history (Narrative), self_awareness (revision history)}. CREATE GET /api/oem/living-model endpoint. MODIFY static/js/learn.js — replace separate DNA, Identity, and Evolution sections with a single "Your organization" section that renders the living model as a coherent narrative (not separate panels).',
        'GET /api/oem/living-model returns: { "identity": {"decision_style": "consensus", "risk_appetite": "cautious", "learning_velocity": "fast", "narrative": "Your organization decides by consensus, takes moderate risks, and learns quickly."}, "mechanics": {"norms": ["Engineering waits for Legal before auth deployments"], "causal_pathways": ["Legal review -> 27% fewer bugs"], "hidden_dependencies": ["OAuth depends on Alice"], "narrative": "Your organization works as follows: Engineering prioritizes velocity but follows the Legal review norm. The OAuth migration has a hidden dependency on Alice."}, "history": {"chapters": [{"title": "The Fast Months", "period": "2024-Q3", "narrative": "Your organization believed it was fast. It wasn\'t."}], "narrative": "Your organization started fast but fragile. It learned that review produces better outcomes."}, "self_awareness": {"total_revisions": 1, "accuracy_trend": "improving", "narrative": "Maestro has revised its understanding 1 time. Its predictions are getting more accurate."}, "unified_narrative": "Your organization is consensus-driven and cautious. It works by following norms (Engineering waits for Legal) that were established by past failures. It started fast but learned to seek review. Maestro\'s understanding of the organization has improved through 1 revision." }. Must have all 4 sections with non-empty narratives.',
        '1) GET /api/oem/living-model returns identity, mechanics, history, self_awareness, unified_narrative. 2) Each section has a narrative (not a metric dump). 3) The unified_narrative synthesizes all 4 into a coherent paragraph. 4) LEARN surface shows a single "Your organization" section (replaces separate DNA + Identity + Evolution panels). 5) V5 litmus: SIMPLER (3 panels merged into 1). 6) V7 litmus: does this make Maestro\'s understanding more accurate? YES — it unifies all projections into one self-consistent model.',
        '3 days (2 days composition engine + 0.5 day API + 0.5 day frontend merge)',
        'V6 #5 (DNA) + V6 #6 (Narrative) + V7 #1 (Institution Model) + V7 #4 (Model Revision). ALL must be built first.'
    ))

    # SPEC 6
    story.extend(spec_block(
        6, 'Compounding Judgment Tracker — "Maestro\'s recommendations are getting more accurate"',
        'V7: "Once Maestro continuously updates its own causal understanding, you move from an adaptive system to one that compounds organizational judgment over years. That\'s the point where the product stops being primarily software and starts becoming an institutional asset." The Compounding Judgment Tracker proves this: it tracks whether Maestro\'s prediction accuracy is IMPROVING over time, and whether the model revisions are making it smarter.',
        'learning.py (993 lines) tracks calibration (Brier score, hit rate). prediction_lifecycle.py tracks resolved predictions. But neither tracks whether accuracy is IMPROVING — they track current accuracy, not the trend. The gap: Maestro can say "my accuracy is 78%" but not "my accuracy has improved from 72% to 78% over 6 months, and 60% of that improvement is attributable to model revisions." The compounding judgment tracker proves the product is getting smarter — the evidence that it is an institutional asset, not just software.',
        'CREATE backend/maestro_oem/compounding_judgment.py — the CompoundingJudgmentTracker. Tracks: (1) prediction accuracy over time (monthly buckets, from prediction_lifecycle.py), (2) accuracy improvement attributable to model revisions (compare accuracy before and after each revision, from model_revision.py), (3) the compounding rate (is the improvement accelerating, linear, or plateauing?), (4) the irreplacability score (how many years of resolved predictions + revisions would a competitor need to match Maestro\'s understanding?). CREATE GET /api/oem/compounding endpoint. MODIFY static/js/learn.js — add a "Maestro is getting smarter" section: "Maestro\'s prediction accuracy has improved from 72% to 78% over 6 months. 60% of the improvement is from model revisions. At the current rate, Maestro will be 85% accurate in 12 months. Replacing Maestro\'s understanding would require 2.3 years of organizational history."',
        'GET /api/oem/compounding returns: { "accuracy_trend": [{"period": "2025-01", "accuracy": 0.72}, {"period": "2025-02", "accuracy": 0.74}, {"period": "2025-03", "accuracy": 0.78}], "improvement_rate": "+2% per month", "improvement_acceleration": "linear", "attributable_to_revisions": 0.60, "revisions_count": 3, "irreplaceability_score": {"years_of_history": 0.5, "resolved_predictions": 47, "model_revisions": 3, "estimated_replacement_time": "2.3 years", "narrative": "Replacing Maestro\'s understanding of your organization would require 2.3 years of organizational history, 47 resolved predictions, and 3 model revisions. This asset compounds over time."}, "narrative": "Maestro\'s prediction accuracy has improved from 72% to 78% over 6 months. 60% of the improvement is from model revisions. At the current rate, Maestro will be 85% accurate in 12 months." }. Must have accuracy_trend (3+ data points), irreplaceability_score with estimated_replacement_time.',
        '1) GET /api/oem/compounding returns accuracy_trend, improvement_rate, irreplaceability_score, narrative. 2) accuracy_trend has 3+ data points showing improvement (or honest "insufficient history — need 3+ months of resolved predictions"). 3) irreplaceability_score includes estimated_replacement_time. 4) LEARN surface shows "Maestro is getting smarter" section. 5) V5 litmus: no new panel — enhances existing LEARN. 6) V7 litmus: does this make Maestro\'s understanding more accurate? It PROVES it does — the tracker is the evidence.',
        '1.5 days (1 day tracking engine + 0.5 day API + frontend)',
        'V7 #3 (Closed Learning Loop) + V7 #4 (Model Revision) for revision attribution. prediction_lifecycle.py for accuracy data.'
    ))

    # ── BUILD ORDER ──────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(P('Build Order and Dependencies', 'h1'))

    dep_rows = [
        ['Phase', 'Specs', 'Duration', 'Why This Order', 'Unlocks'],
        ['0', 'V5 #4-#8 + V6 #1-#6', '~24 days', 'MANDATORY. V7 builds on causal chains, temporal trajectories, adaptive nudges, evolution tracker, DNA, autobiography. None exist.', 'Causal + temporal + adaptation + DNA + narrative foundation'],
        ['1', '#1 Institution Model + #2 Governance', '~5 days', 'The model that gets revised. The governance that makes action safe. Both required before the loop.', 'Self-revising model + safe autonomous action'],
        ['2', '#3 Closed Learning Loop + #4 Model Revision', '~4.5 days', 'The loop detects misses. The revision engine updates the theory. Both require the Institution Model.', 'Closed loop: reality -> model update -> better prediction'],
        ['3', '#5 Living Model + #6 Compounding Judgment', '~4.5 days', 'Unifies everything into one substrate. Proves the product is getting smarter.', 'Compounding institutional asset + irreplaceability evidence'],
        ['', '', '', '', ''],
        ['TOTAL', '6 V7 specs (after backlog)', '3 phases', '~14 days after V5+V6', 'V7: from adaptive system to compounding institutional asset'],
    ]
    t = Table(dep_rows, colWidths=[12*mm, 45*mm, 18*mm, 50*mm, 37*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, 4), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#f5d0fe')),
        ('FONTNAME', (0, 6), (-1, 6), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
    ]))
    story.append(t)

    # ── THE THREE LAWS ───────────────────────────────────────────────────
    story.append(P('The Three Constitutional Laws (All Mandatory)', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>THREE LAWS, ALL IMMUTABLE</b></font>',
                  ParagraphStyle('laws_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=4)),
        P('<b>Law 1 (V6): "Every interaction must permanently improve the organization."</b> Not the model. '
          'Not the UI. The organization. Checked by: does the spec create a mechanism for permanent change?', 'body_left'),
        P('<b>Law 2 (V6): "The organization should become more intelligent even when nobody opens Maestro."</b> '
          'Checked by: does the spec run in the background, not on user request?', 'body_left'),
        P('<b>Law 3 (V7 NEW): "Every recommendation must make Maestro\'s understanding of the organization '
          'more accurate."</b> Checked by: after the recommendation resolves, does the model revise? If the '
          'model does not revise when reality disagrees, the loop is open and Maestro is not learning — it '
          'is just calibrated. Calibration adjusts confidence. Revision adjusts understanding. V7 demands '
          'revision.', 'body_left'),
        P('<b>All three laws must pass for every V7 spec.</b> The V5 litmus test ("is the UI simpler?") is '
          'retained. The V6 litmus test ("does this permanently improve the organization?") is retained. '
          'The V7 litmus test ("does this make Maestro\'s understanding more accurate?") is added. Four '
          'checks. No exceptions.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ACCENT))

    # ── THE PROGRESSION ──────────────────────────────────────────────────
    story.append(P('The Complete Progression: V3 to V8', 'h1'))

    prog_rows = [
        ['Version', 'Verb', 'What Maestro Does', 'Moat'],
        ['V3', 'Observe', 'Sees what happened. Reports patterns.', 'Data'],
        ['V4', 'Judge', 'Synthesizes judgment. Recommends actions.', 'Cognitive organs'],
        ['V5', 'Disappear', 'Becomes invisible. Acts through existing tools.', 'Invisible intelligence'],
        ['V6', 'Adapt', 'Quietly restructures work. Prevents failures.', 'Institutional adaptation'],
        ['V7', 'Understand', 'Revises its own theory when reality disagrees.', 'Self-revising institutional model'],
        ['V8', 'Evolve', 'Accumulated judgment becomes irreplaceable.', 'Compounding institutional asset'],
    ]
    t = Table(prog_rows, colWidths=[20*mm, 20*mm, 58*mm, 60*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('LEADING', (0, 0), (-1, -1), 11),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#f5d0fe')),  # V7 highlighted
        ('BACKGROUND', (0, 7), (-1, 7), colors.HexColor('#fdf4ff')),  # V8
        ('FONTNAME', (0, 6), (-1, 7), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (1, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>V7 is "Understand."</b> The moat shifts from adaptation ("we no longer make this mistake") to '
        'self-revising understanding ("we know WHY we no longer make this mistake, and our theory of the '
        'organization is more accurate than it was last month"). V8 is "Evolve" — the accumulated judgment '
        'becomes irreplaceable. V7 is the bridge: it makes Maestro\'s understanding compound over time, '
        'so that replacing Maestro means losing years of revised institutional theory.', 'body'))

    # ── FINAL CHARGE ─────────────────────────────────────────────────────
    story.append(P('Final Charge to the Coder', 'h1'))
    story.append(P(
        'V6 made Maestro adapt the organization\'s behavior. V7 makes Maestro adapt its own THEORY of the '
        'organization. The closed learning loop — reality disagrees, model revises, better recommendation — '
        'is what separates an adaptive system from a compounding institutional asset. After V7, Maestro is '
        'not just software that helps the organization. It is an institutional model that gets more accurate '
        'every month, in a way that cannot be copied because it is built from years of resolved '
        'disagreements between Maestro and reality.', 'body'))

    story.append(P(
        '<b>Build order: Phase 0 (V5+V6 backlog, ~24 days, MANDATORY) -> Phase 1 (Institution Model + '
        'Governance, ~5 days) -> Phase 2 (Closed Loop + Revision, ~4.5 days) -> Phase 3 (Living Model + '
        'Compounding Judgment, ~4.5 days). Total ~38 days from current state.</b> Do NOT skip Phase 0. '
        'Do NOT build V7 on a missing foundation. The Institution Model needs causal chains. The Closed '
        'Loop needs the evolution tracker. The Living Model needs DNA + autobiography. Build the foundation '
        'first.', 'body'))

    story.append(P(
        '<b>The V7 litmus test for every commit:</b> "Does this make Maestro\'s understanding of the '
        'organization more accurate?" If yes, ship it. If it only adapts behavior without revising theory, '
        'it is V6 — useful but not V7. V7 specs must revise the model when reality disagrees. The bar is '
        'higher than V6: simpler UI AND permanent improvement AND background operation AND model revision. '
        'All four.', 'body'))

    story.append(P(
        '<b>The end state is not software. It is an institutional asset that compounds judgment over years. '
        'Every resolved disagreement between Maestro and reality makes the model more accurate. Every '
        'revision is irreplaceable — a competitor cannot recreate it without living through the same '
        'organizational history. After V7, Maestro is not just an invisible intelligence layer or an '
        'adaptive system. It is the self-revising institutional theory of how THIS organization works — '
        'continuously updated, permanently improving, impossible to copy. That is what Apple, Microsoft, '
        'Google, or OpenAI would look at and think "we need to own this." Build it.</b>', 'body'))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'MaestroAgent_Round20_Constitution_V7_Self_Revising_Institutional_Model.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
