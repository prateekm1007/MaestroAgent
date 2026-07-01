"""
Maestro V5 Phase 2-3 — Strict Coding Instructions for 5 Remaining Specs
The attention quality fix is verified. V5 Phase 1 is complete. These are the
exact, step-by-step instructions for building Specs #4-#8. No vision, no
philosophy — just code, APIs, acceptance tests, and build order.
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
SECTION_BG    = colors.HexColor('#f0f9ff')
CARD_BG       = colors.HexColor('#e0f2fe')
TABLE_STRIPE  = colors.HexColor('#f0f9ff')
HEADER_FILL   = colors.HexColor('#0c4a6e')
BORDER        = colors.HexColor('#7dd3fc')
ACCENT        = colors.HexColor('#0369a1')
TEXT_PRIMARY  = colors.HexColor('#1a1c1e')
TEXT_MUTED    = colors.HexColor('#6b7178')

ST_DELIVERED  = colors.HexColor('#15803d')
ST_PARTIAL    = colors.HexColor('#b45309')
ST_V5         = colors.HexColor('#0369a1')

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
    s['mono'] = ParagraphStyle('mono', fontName=FONT_MONO, fontSize=8,
                               leading=11, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
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
                      "Maestro V5 Phase 2-3 — Strict Coding Instructions for 5 Remaining Specs")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro V5 Phase 2-3 — Strict Coding Instructions",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="Step-by-step instructions for building V5 Specs #4-#8",
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
    # Header
    header = Table([[
        Paragraph(f'<font color="white"><b>SPEC #{num}</b></font>',
                  ParagraphStyle('sh', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=colors.white, alignment=TA_CENTER)),
        Paragraph(f'<font color="white"><b>{name}</b></font>',
                  ParagraphStyle('st', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=colors.white, alignment=TA_LEFT))
    ]], colWidths=[28*mm, PAGE_W - MARGIN_L - MARGIN_R - 28*mm - 24])
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ST_V5),
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

    flowables += field('V5 Principle', principle)
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
        f'<font color="{ACCENT.hexval()}"><b>V5 PHASE 2-3 — STRICT CODING INSTRUCTIONS</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        '5 Remaining Specs: Forgetting, Causal, Temporal, Imagination, Recall',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=26,
                       leading=30, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Attention quality fix verified. V5 Phase 1 complete. These are the exact instructions for Phase 2-3.',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=13,
                       leading=17, textColor=HEADER_FILL, alignment=TA_LEFT, spaceAfter=14)
    ))

    # Verification status
    story.append(callout_box([
        Paragraph(f'<font color="{ST_DELIVERED.hexval()}"><b>ATTENTION QUALITY FIX — VERIFIED</b></font>',
                  ParagraphStyle('vh', fontName=FONT_HEAD_B, fontSize=10,
                                 leading=13, textColor=ST_DELIVERED, spaceAfter=4)),
        P('Commit <font face="Mono">a044a4a</font>. All 4 round-18 issues closed:', 'body_left'),
        P('1. <font face="Mono">narrative</font> field: ADDED. "Your organization\'s attention is well-distributed."', 'body_left'),
        P('2. "unknown" domain: FILTERED. Only 5 real domains (payments, auth, platform, deployment, incident).', 'body_left'),
        P('3. Percentages: NORMALIZED. current=100%, recommended=100% (was 136%).', 'body_left'),
        P('4. Redistribution: WORKS. Caps at 35%, redistributes proportionally. (No redistribution needed with demo data — honest.)', 'body_left'),
        P('<b>V5 Phase 1: COMPLETE.</b> Spec #1 (hide organs) DELIVERED. Spec #2 (executive function) DELIVERED. Spec #3 (attention) DELIVERED. 389 tests pass, 0 fail.', 'body_left'),
    ], bg=colors.HexColor('#f0fdf4'), border=colors.HexColor('#bbf7d0'), accent=ST_DELIVERED))

    story.append(Spacer(1, 6 * mm))

    # ── BUILD ORDER ──────────────────────────────────────────────────────
    story.append(P('Build Order (Critical — Dependencies Matter)', 'h1'))
    story.append(P(
        'The 5 specs have dependencies. Build them in this exact order. Do NOT skip ahead.', 'body'))

    order_rows = [
        ['Step', 'Spec', 'Why This Order', 'Effort'],
        ['1', '#7 Temporal Trajectories', 'Foundation for #5 (Imagination) and V6 (Trajectory Intervention). Builds on consciousness.py + time_axis.py. No deps on other V5 specs.', '1.5 days'],
        ['2', '#6 Causal Cognition', 'Foundation for #5 (Imagination needs causal models for counterfactuals). Builds on prediction_lifecycle.py + evidence_graph.py. Needs #7 for temporal context.', '2 days'],
        ['3', '#4 Forgetting Engine', 'Independent. Builds on learning.py + evidence_graph.py. Can be built in parallel with #6.', '1.5 days'],
        ['4', '#5 Imagination (Counterfactual)', 'Depends on #6 (causal) + #7 (temporal). Builds on digital_twin.py. Counterfactuals need causal chains.', '2 days'],
        ['5', '#8 Institutional Recall', 'Depends on #7 (temporal history). Builds on learning.py + signal history. Enhanced by #6 (causal context).', '2 days'],
        ['', '', '', ''],
        ['TOTAL', '5 specs', 'Build in order: #7 → #6 → #4 (parallel with #6) → #5 → #8', '~9 days'],
    ]
    t = Table(order_rows, colWidths=[10*mm, 40*mm, 70*mm, 20*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, 5), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, 7), (-1, 7), colors.HexColor('#e0f2fe')),
        ('FONTNAME', (0, 7), (-1, 7), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>The V5 litmus test applies to ALL specs:</b> "Does this make Maestro feel simpler?" Every spec '
        'must be INVISIBLE from the start — no new panels, no new organ names, no new sidebar items. '
        'Each spec enhances an EXISTING surface (TODAY, LEARN, Cognition, or ASK). If a spec adds a new '
        'visible panel, it fails the litmus test — even if the backend is brilliant.', 'body'))

    story.append(PageBreak())

    # ── SPEC #7: TEMPORAL TRAJECTORIES ──────────────────────────────────
    story.append(P('Step 1: Spec #7 — Temporal Trajectories (Build First)', 'h1'))
    story.extend(spec_block(
        7, 'Temporal Trajectories — "Trust has fallen slowly for 8 weeks"',
        'V5: "Don\'t remember snapshots. Remember trajectories." Today, consciousness.py returns a point-in-time state vector. V5 extends this to org-wide trajectory memory: every consciousness dimension (attention, knowledge, trust, conflict, energy, uncertainty, learning) becomes a trajectory — current value + trend + slope + duration + narrative.',
        'consciousness.py (204 lines) computes 7 dimensions as point-in-time values. time_axis.py (167 lines) returns past/present/future for a single domain. The gap: no org-wide trajectory tracking. Maestro can say "trust is currently 0.42" but not "trust has fallen for 8 weeks." The trajectory — the trend over time — is not tracked for organizational dimensions.',
        'CREATE <font face="Mono">backend/maestro_oem/temporal_trajectories.py</font> — the TemporalTrajectoryEngine. Maintains a rolling 90-day trajectory for each consciousness dimension. On construction, scans signal history to build trajectory data. For each dimension: {current, trend (improving/declining/stable), slope (float), duration_weeks (int), narrative (sentence)}. CREATE <font face="Mono">GET /api/oem/trajectories</font> endpoint. MODIFY <font face="Mono">backend/maestro_oem/consciousness.py</font> — enrich each state dimension with its trajectory (add a <font face="Mono">trajectory</font> sub-object to each dimension in <font face="Mono">state_vector()</font>). MODIFY <font face="Mono">static/js/cognition.js</font> — the "Right now" section (was Consciousness) now shows trajectory sentences: "Trust between Engineering and Legal has fallen for 8 weeks" instead of "Trust: 0.42".',
        'GET /api/oem/trajectories returns: { "trust": {"current": 0.42, "trend": "declining", "slope": -0.03, "duration_weeks": 8, "narrative": "Trust between Engineering and Legal has fallen slowly for 8 weeks."}, "attention": {"current": 0.65, "trend": "stable", "slope": 0.01, "duration_weeks": 12, "narrative": "Attention distribution has been stable."}, ... 7 dimensions ... }. At least 3 dimensions must have trend != "stable" (or honest "insufficient history — need 4+ weeks of data").',
        '1) GET /api/oem/trajectories returns 7 dimensions, each with current, trend, slope, duration_weeks, narrative. 2) Each narrative is a trajectory sentence (not a point metric). 3) Dimensions with < 4 weeks of data return "insufficient history" honestly. 4) Cognition surface "Right now" section shows trajectory sentences. 5) No hardcoded trajectories — all computed from signal history. 6) V5 litmus: no new panel — enhances existing Cognition surface.',
        '1.5 days',
        'None (foundation spec — build first). Builds on consciousness.py + signal history.'
    ))

    # ── SPEC #6: CAUSAL COGNITION ───────────────────────────────────────
    story.append(P('Step 2: Spec #6 — Causal Cognition (Build Second)', 'h1'))
    story.extend(spec_block(
        6, 'Causal Cognition — "A caused B because 5 interventions produced the same sequence"',
        'V5: "Today: A correlates with B. Future: We believe A caused B because five similar interventions produced the same sequence." Causal cognition moves Maestro from correlation to causation.',
        'evidence_graph.py tracks co-occurrence (correlation). prediction_lifecycle.py (859 lines) tracks resolved predictions where an intervention was recommended and an outcome was observed. But neither builds CAUSAL CHAINS — "intervention X caused outcome Y, observed N times, failed M times." The gap: Maestro can say "bottlenecks correlate with velocity drops" but not "removing the bottleneck CAUSED velocity to recover, because 3 interventions produced the same recovery."',
        'CREATE <font face="Mono">backend/maestro_oem/causal.py</font> — the CausalEngine. Scans prediction_lifecycle.py database for resolved predictions where: (1) a recommendation was made (intervention), (2) the prediction was resolved as hit or miss (outcome), (3) the same intervention-outcome pair occurred >= 3 times. Builds causal chains: {intervention, effect, sequence_count, failed_count, confidence, first_observed, evidence}. A causal claim requires sequence_count >= 3 AND failed_count == 0 (or a clear failure ratio). CREATE <font face="Mono">GET /api/oem/causal?intervention=...</font> endpoint. MODIFY <font face="Mono">backend/maestro_oem/wisdom.py</font> — when synthesizing judgment, cite causal chains where available ("This intervention caused this outcome 3 times with 0 failures"). MODIFY <font face="Mono">static/js/cognition.js</font> — the "When values compete" section (was Wisdom) now shows "Why we believe this" with causal evidence.',
        'GET /api/oem/causal?intervention=redistribute+approval+authority returns: { "intervention": "Redistribute approval authority", "causes": [{"effect": "Approval time drops below 2 days", "sequence_count": 3, "failed_count": 0, "confidence": 0.91, "evidence": ["rec-xxx: bottleneck addressed → velocity recovered in 5 days"]}], "narrative": "Redistributing approval authority causes approval time to drop. Observed 3 times, 0 failures." }. If insufficient data: { "causes": [], "narrative": "Insufficient intervention data for causal inference. The pilot needs more resolved predictions." }.',
        '1) GET /api/oem/causal returns causes array (or honest "insufficient data"). 2) Each cause has sequence_count >= 3, failed_count, confidence. 3) Narrative is a causal claim (not correlation). 4) Cognition "When values compete" section cites causal evidence. 5) No hardcoded causal claims. 6) V5 litmus: no new panel — enhances existing Wisdom section.',
        '2 days',
        'Spec #7 (Temporal) for temporal context. Builds on prediction_lifecycle.py + evidence_graph.py.'
    ))

    story.append(PageBreak())

    # ── SPEC #4: FORGETTING ─────────────────────────────────────────────
    story.append(P('Step 3: Spec #4 — Forgetting Engine (Build Third, Can Parallel #6)', 'h1'))
    story.extend(spec_block(
        4, 'Forgetting Engine — archive zero-predictive-value events',
        'V5: "Brains forget for a reason. Compression is not forgetting. Without forgetting, memory eventually becomes noise." The Forgetting Engine identifies events with zero future predictive value and archives them.',
        'memory_compression.py (152 lines) compresses experience into truths/habits/mistakes. But it does not forget — all signals remain in the active evidence graph. A 2-year-old incident that never correlated with any future outcome still occupies cognitive space. The gap: no mechanism to identify and archive zero-predictive-value events.',
        'CREATE <font face="Mono">backend/maestro_oem/forgetting.py</font> — the ForgettingEngine. For each learning object and signal in the active model, compute <font face="Mono">predictive_value</font> (0.0-1.0) based on: (1) has it been referenced in any recent recommendation? (2) has it correlated with any future outcome? (3) has it been validated/invalidated? Events with predictive_value < 0.05 AND age > 180 days are archive candidates. The engine does NOT delete — it flags candidates for archiving (cold storage). CREATE <font face="Mono">GET /api/oem/forgetting</font> endpoint. MODIFY <font face="Mono">backend/maestro_oem/engine.py</font> — on ingest, check if new signals make old events irrelevant (predictive_value drops). MODIFY <font face="Mono">static/js/cognition.js</font> — the "What it all comes down to" section (was Memory Compression) now shows a "Maestro is forgetting" line: "3 old events have produced no predictive value. Maestro is quietly archiving them."',
        'GET /api/oem/forgetting returns: { "archive_candidates": [{"entity_id": "...", "type": "signal", "age_days": 245, "predictive_value": 0.02, "reason": "No correlation with any future outcome in 245 days"}], "archived_count": 0, "active_working_set": 1247, "threshold": 0.05, "narrative": "3 events have zero predictive value. Maestro is quietly archiving them to reduce cognitive noise." }. If no candidates: { "archive_candidates": [], "narrative": "All events have predictive value. Nothing to forget yet." }.',
        '1) GET /api/oem/forgetting returns archive_candidates array + narrative. 2) Each candidate has predictive_value < 0.05 and age_days > 180 (or honest "nothing to forget"). 3) Engine does NOT delete (flags only). 4) Cognition surface shows "Maestro is forgetting" line. 5) No hardcoded candidates. 6) V5 litmus: no new panel — enhances existing Compression section.',
        '1.5 days',
        'None (independent — can parallel #6). Builds on learning.py + evidence_graph.py.'
    ))

    # ── SPEC #5: IMAGINATION ────────────────────────────────────────────
    story.append(P('Step 4: Spec #5 — Imagination / Counterfactual (Build Fourth)', 'h1'))
    story.extend(spec_block(
        5, 'Imagination (Counterfactual) — "What would happen if Legal disappeared?"',
        'V5: "Organizations don\'t only solve today\'s problems. They imagine futures." The Imagination organ performs counterfactual reasoning: given a hypothetical change, predict the organizational impact using causal models and historical data.',
        'digital_twin.py (743 lines) runs scenarios (person leaves, team doubles) via parametric simulation. But these are PARAMETRIC — they adjust inputs and compute outputs. They are not COUNTERFACTUAL — they do not reason about causality ("Legal disappeared BECAUSE of the reorg, and the reorg also affected Engineering, so..."). The gap: no causal counterfactual reasoning.',
        'CREATE <font face="Mono">backend/maestro_oem/imagination.py</font> — the ImaginationEngine. Takes a counterfactual scenario ("What would happen if Legal disappeared?") and: (1) identifies causal dependencies of the entity (from causal.py + evidence_graph.py), (2) retrieves historical analogues (has any team ever been restructured?), (3) simulates the impact using digital_twin.py, (4) produces a causal narrative. CREATE <font face="Mono">GET /api/oem/imagine?scenario=...</font> endpoint. MODIFY <font face="Mono">static/js/ask_v2.js</font> — when the user asks a "what if" question, route to the Imagination engine and render the counterfactual narrative.',
        'GET /api/oem/imagine?scenario=What+would+happen+if+Legal+disappeared returns: { "scenario": "Legal disappeared", "consequences": [{"effect": "OAuth reviews would stall", "cause": "Legal is the sole reviewer", "evidence_count": 5, "confidence": 0.82}], "historical_analogue": "The Q2 legal-team reorg produced similar dynamics.", "narrative": "If Legal disappeared, immediate effect: faster engineering. Secondary effect: more incidents within 3 weeks." }. Must have 2+ consequences with cause + evidence_count + confidence, and 1 historical analogue.',
        '1) GET /api/oem/imagine returns consequences (2+) + historical_analogue + narrative. 2) Each consequence has cause + evidence_count + confidence. 3) Historical analogue references real data. 4) ASK v2 routes "what if" questions to Imagination. 5) No hardcoded scenarios. 6) V5 litmus: no new panel — enhances existing ASK v2.',
        '2 days',
        'Spec #6 (Causal) + Spec #7 (Temporal). Builds on digital_twin.py. Counterfactuals need causal chains.'
    ))

    # ── SPEC #8: INSTITUTIONAL RECALL ───────────────────────────────────
    story.append(P('Step 5: Spec #8 — Institutional Recall (Build Last)', 'h1'))
    story.extend(spec_block(
        8, 'Institutional Recall — "When have we been here before?"',
        'V5: "Eventually Maestro owns the organization\'s autobiography." Institutional Recall answers "When have we been here before?" with 3 moments + lessons — not documents, not search results, but organizational memories.',
        'The autocomplete engine returns suggestions, not memories. learning.py tracks calibration but not narrative recall. memory_compression.py compresses but does not retrieve by situational similarity. The gap: no mechanism to take a current situation and retrieve the most similar past moments with their outcomes and lessons.',
        'CREATE <font face="Mono">backend/maestro_oem/institutional_recall.py</font> — the InstitutionalRecallEngine. Takes a situation description (from current recommendation or ASK query) and retrieves top 3 similar past moments from: learning objects, resolved predictions, contradiction history, signal history. Uses keyword overlap (or embedding if available) against the historical database. For each moment: {when, situation, what_we_did, what_we_learned, outcome}. CREATE <font face="Mono">GET /api/oem/recall?situation=...</font> endpoint. MODIFY <font face="Mono">static/js/ask_v2.js</font> — append a "When you\'ve been here before" section with up to 3 recalled moments.',
        'GET /api/oem/recall?situation=delaying+launch+for+Legal+review returns: { "moments": [{"when": "2024-08-15", "situation": "Q3 auth launch delayed 3 days for Legal review", "what_we_did": "Proceeded with Legal review", "what_we_learned": "Legal review before launch reduces post-launch incidents", "outcome": "succeeded", "evidence_count": 5}], "summary": "You\'ve been in a similar situation 3 times. In 2 of 3, proceeding with the Legal review led to better outcomes." }. If novel: { "moments": [], "summary": "This situation is novel — no similar past moments found." }.',
        '1) GET /api/oem/recall returns moments array (or honest "novel situation"). 2) Each moment has when, situation, what_we_did, what_we_learned, outcome. 3) Moments reference real historical data. 4) ASK v2 shows "When you\'ve been here before" section. 5) Summary is a narrative. 6) V5 litmus: no new panel — enhances existing ASK v2.',
        '2 days',
        'Spec #7 (Temporal) for historical context. Builds on learning.py + signal history + prediction_lifecycle.py.'
    ))

    story.append(PageBreak())

    # ── STRICT RULES ─────────────────────────────────────────────────────
    story.append(P('Strict Rules for All 5 Specs', 'h1'))

    rules = [
        ['Rule', 'Enforcement'],
        ['1. Build in order: #7 -> #6 -> #4 (parallel with #6) -> #5 -> #8', 'Dependencies are real. #5 needs #6. #8 benefits from #7. Do not skip ahead.'],
        ['2. Every spec enhances an EXISTING surface', '#7 -> Cognition "Right now". #6 -> Cognition "When values compete". #4 -> Cognition "What it all comes down to". #5 -> ASK v2. #8 -> ASK v2. NO new panels.'],
        ['3. V5 litmus test: UI must be SIMPLER after each spec', 'No new sidebar items (stays at 4). No new organ names. No new jargon. Each spec makes an existing section richer without adding visible complexity.'],
        ['4. Every API must return REAL data (not hardcoded)', 'Grep the backend module for hardcoded values. Every response field must be computed from model data. The demo seed has enough data for all 5 specs.'],
        ['5. Honest degradation when data is insufficient', 'If causal.py finds < 3 interventions: return "Insufficient intervention data for causal inference." If recall finds no similar moments: return "This situation is novel." Do NOT fabricate.'],
        ['6. Every spec must pass the 5-point checklist', '1) Ran FULL acceptance test (API + frontend)? 2) Checked APPLICATION? 3) Ran FULL test suite? 4) Verified LIVE API? 5) UI SIMPLER?'],
        ['7. Frontend text passes through humanize()', 'All user-facing strings from API responses must be passed through humanize() before rendering. No law codes, no confidence numbers, no internal terms.'],
        ['8. No silent skips', 'If a spec is deferred, say so explicitly in the commit message. Do NOT claim "all 5 specs delivered" if only 4 are built. The auditor will grep.'],
        ['9. Run the FULL test suite (not a subset)', 'python -m pytest backend/maestro_api/tests/ backend/maestro_auth/tests/ backend/maestro_oem/tests/ --tb=short. Report the exact count. Do NOT run a subset and claim it as the full suite.'],
        ['10. CI pipeline must pass', 'The .github/workflows/test.yml CI pipeline runs on every push. It must pass. If it fails, fix before claiming delivery.'],
    ]
    t = Table(rules, colWidths=[65*mm, PAGE_W - MARGIN_L - MARGIN_R - 65*mm])
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

    # ── ANTI-PATTERN WARNING ─────────────────────────────────────────────
    story.append(P('Anti-Pattern Warning (Read Twice)', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ST_DELIVERED.hexval()}"><b>THE PATTERN WAS BROKEN IN ROUND 16. MAINTAIN IT FOR V5 PHASE 2-3.</b></font>',
                  ParagraphStyle('warn_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ST_DELIVERED, spaceAfter=4)),
        P('The "built but not applied" pattern recurred 6 times (rounds 7-13) and was broken in round 16 '
          '(all 8 V4 organs wired). V5 Phase 1 maintained the break (round 18: all 3 specs wired, no new '
          'panels). <b>V5 Phase 2-3 must maintain it again.</b>', 'body_left'),
        P('<b>The specific risk for Phase 2-3:</b> Specs #4 (Forgetting), #6 (Causal), and #7 (Temporal) '
          'are backend-heavy. The temptation is to build the engine, verify via API, and claim delivery '
          'without wiring the frontend. DO NOT DO THIS. Every spec must enhance an existing frontend '
          'surface (Cognition or ASK v2) before it is claimed. The acceptance test requires: "Auditor '
          'opens [surface] and verifies [user-visible output]." If the frontend is not wired, the spec '
          'is NOT delivered — regardless of whether the API returns 200.', 'body_left'),
        P('<b>The "added visibility" risk:</b> V5 Phase 1 successfully avoided adding new panels. Phase 2-3 '
          'must do the same. Specs #4, #6, #7 enhance the Cognition surface (existing). Specs #5, #8 '
          'enhance ASK v2 (existing). If any spec adds a new sidebar item, a new surface, or a new panel, '
          'it fails the V5 litmus test. The sidebar stays at 4 items. No exceptions.', 'body_left'),
        P('<b>The "subset test reporting" risk:</b> The coder has reported subset test counts as full-suite '
          'counts twice (rounds 3 and 8). The CI pipeline now prevents this structurally. But the coder '
          'must also run the full suite locally before claiming delivery. Report the exact '
          '<font face="Mono">pytest</font> output line. Do not round. Do not subset.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ST_DELIVERED))

    # ── SUMMARY ──────────────────────────────────────────────────────────
    story.append(P('Summary — What "Done" Looks Like', 'h1'))

    done_rows = [
        ['Spec', 'Backend', 'API', 'Frontend', 'Litmus Test', 'Done When'],
        ['#7 Temporal', 'temporal_trajectories.py', 'GET /trajectories', 'Cognition "Right now" shows trajectory sentences', 'No new panel', '7 dimensions with trend + narrative in Cognition'],
        ['#6 Causal', 'causal.py', 'GET /causal?intervention=...', 'Cognition "When values compete" cites causal evidence', 'No new panel', 'Causal chains with sequence_count >= 3 (or honest "insufficient data")'],
        ['#4 Forgetting', 'forgetting.py', 'GET /forgetting', 'Cognition "What it all comes down to" shows "Maestro is forgetting"', 'No new panel', 'Archive candidates with predictive_value < 0.05 (or honest "nothing to forget")'],
        ['#5 Imagination', 'imagination.py', 'GET /imagine?scenario=...', 'ASK v2 routes "what if" questions to Imagination', 'No new panel', '2+ consequences with cause + confidence + historical analogue'],
        ['#8 Recall', 'institutional_recall.py', 'GET /recall?situation=...', 'ASK v2 shows "When you\'ve been here before"', 'No new panel', 'Moments with when/situation/what_we_did/what_we_learned/outcome (or honest "novel")'],
    ]
    t = Table(done_rows, colWidths=[20*mm, 32*mm, 28*mm, 45*mm, 22*mm, 37*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('LEADING', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>When all 5 specs are done:</b> V5 is complete (Phase 1 + Phase 2 + Phase 3). The Chrome '
        'extension (#9) already exists (183 lines content.js). The product is The Invisible Layer — '
        'cognitive organs that are invisible, executive function that acts, attention that allocates, '
        'forgetting that reduces noise, causal reasoning that explains why, temporal trajectories that '
        'show where things are heading, imagination that counterfactuals, and institutional recall that '
        'remembers when you\'ve been here before. All invisible. All enhancing existing surfaces. The UI '
        'is simpler than when we started. The intelligence is deeper. That is V5. Build it.', 'body'))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'MaestroAgent_V5_Phase2_3_Coding_Instructions.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
