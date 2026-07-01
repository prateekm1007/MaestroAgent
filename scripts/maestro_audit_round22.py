"""
Maestro Constitution V7.1 — The Self-Revising Institutional Model (Refined)
Incorporates the Fortune 100 CTO reviewer's feedback on V7.

Key refinements:
1. Bayesian competing hypotheses (not single-theory convergence)
2. Counterfactual simulation before revision
3. Epistemic precision: "observed outcomes reduce confidence" (not "reality disagrees")
4. Irreplaceability Score grounded in transparent methodology
5. Meta-revision engine (learning how to revise)
6. Removed speculative acquisition language
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
ACCENT        = colors.HexColor('#7e22ce')
TEXT_PRIMARY  = colors.HexColor('#1a1c1e')
TEXT_MUTED    = colors.HexColor('#6b7178')

ST_V7         = colors.HexColor('#7e22ce')
ST_DELIVERED  = colors.HexColor('#15803d')
ST_REFINED    = colors.HexColor('#1d4ed8')

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
                      "Maestro Constitution V7.1 — Refined Self-Revising Institutional Model")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro Constitution V7.1 — Refined",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="V7.1 refined specification incorporating Fortune 100 CTO reviewer feedback",
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
        f'<font color="{ACCENT.hexval()}"><b>CONSTITUTION V7.1 — REFINED</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'The Self-Revising Institutional Model',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=30,
                       leading=34, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Refined: Bayesian competing hypotheses, counterfactual simulation, epistemic precision, grounded metrics.',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=12,
                       leading=16, textColor=HEADER_FILL, alignment=TA_LEFT, spaceAfter=14)
    ))

    meta = Table([
        [Paragraph('<b>Baseline</b>', S['small']), P('V5 complete (8 specs, commit b3a3d72). V6 NOT started. 68 backend modules, 27 frontend files. 423 tests pass.', 'small')],
        [Paragraph('<b>V7.1 vs V7</b>', S['small']), P('V7.1 incorporates 6 refinements from the Fortune 100 CTO reviewer: Bayesian hypotheses, counterfactual simulation, epistemic wording, grounded Irreplaceability Score, meta-revision engine, removed speculative language.', 'small')],
        [Paragraph('<b>Three laws</b>', S['small']), P('Law 1: "Every interaction must permanently improve the organization." Law 2: "The organization becomes more intelligent even when nobody opens Maestro." Law 3: "Observed outcomes reduce confidence in one or more causal hypotheses, and the model revises accordingly." (V7.1 refined: "reality disagrees" -> "observed outcomes reduce confidence")', 'small')],
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

    # ── THE 6 REFINEMENTS ────────────────────────────────────────────────
    story.append(P('The 6 Refinements (V7 -> V7.1)', 'h1'))

    story.append(P('Refinement 1: Bayesian Competing Hypotheses (not single-theory convergence)', 'h2'))
    story.append(P(
        '<b>V7 problem:</b> The revision engine searched for "the corrected theory" — one explanation that '
        'replaces the old one. This risks premature convergence: one miss -> new theory -> overwrite old '
        'theory -> lose uncertainty. Real organizations are noisy. Multiple explanations are usually valid '
        'simultaneously.', 'body_left'))
    story.append(P(
        '<b>V7.1 fix:</b> The Institution Model maintains MULTIPLE COMPETING HYPOTHESES per causal question. '
        'Each hypothesis has a confidence (posterior probability) and evidence count. Predictions are '
        'WEIGHTED ACROSS HYPOTHESES, not derived from one explanation. When an observation is made, it '
        'updates the confidence of ALL hypotheses (Bayesian update), not just one. This is how scientific '
        'reasoning works — you do not collapse to one theory until the evidence is overwhelming.', 'body_left'))
    story.append(P(
        '<b>Example:</b> Engineering delays shipping. The Institution Model maintains:', 'body_left'))
    story.append(P('• Theory A: Legal reviews are slow. Confidence 0.62. Evidence 41.', 'body_left'))
    story.append(P('• Theory B: Engineering estimates are inaccurate. Confidence 0.51. Evidence 28.', 'body_left'))
    story.append(P('• Theory C: Product requirements change. Confidence 0.33. Evidence 16.', 'body_left'))
    story.append(P('• Theory D: Leadership interrupts priorities. Confidence 0.28. Evidence 12.', 'body_left'))
    story.append(P(
        'A prediction about shipping delay is weighted: 0.62*A + 0.51*B + 0.33*C + 0.28*D (normalized). '
        'When a new observation arrives (e.g., "Legal approved in 2 days but shipping still delayed"), '
        'Theory A\'s confidence drops, Theory B\'s rises. The model does NOT overwrite A with B — it '
        'adjusts both. This prevents premature convergence and preserves uncertainty.', 'body_left'))
    story.append(P(
        '<b>Codebase foundation:</b> confidence.py already uses Beta-Binomial posterior (alpha = '
        'ALPHA_PRIOR * SHR + validated_runtimes, beta = BETA_PRIOR * (1-SHR) + failed_runtimes). '
        'hypothesis.py has HypothesisStore with resolve() and calibration_report(). The V7.1 extension: '
        'apply the Bayesian framework to CAUSAL HYPOTHESES (not just laws), and maintain multiple per '
        'causal question.', 'body_left'))

    story.append(P('Refinement 2: Counterfactual Simulation Before Revision', 'h2'))
    story.append(P(
        '<b>V7 problem:</b> The revision loop was: Prediction -> Outcome -> Revision. It asked "What '
        'happened?" but not "What WOULD have happened if X were different?" This makes causal attribution '
        'weak — you cannot distinguish "Legal was slow" from "Engineering was inaccurate" without '
        'simulating the counterfactual.', 'body_left'))
    story.append(P(
        '<b>V7.1 fix:</b> Add a counterfactual step: Prediction -> Outcome -> Counterfactual Simulation '
        '-> Revision. After an observation, the engine asks: "What would have happened if Legal had '
        'approved two days earlier?" (using imagination.py, V5 #5, which already exists). If the '
        'counterfactual simulation shows the delay would have persisted even with faster Legal approval, '
        'Theory A (Legal is slow) loses confidence AND Theory B (Engineering estimates) gains confidence. '
        'The counterfactual makes causal attribution much stronger.', 'body_left'))
    story.append(P(
        '<b>Codebase foundation:</b> imagination.py (165 lines, V5 #5) already performs counterfactual '
        'reasoning ("What would happen if Legal disappeared?"). The V7.1 extension: use imagination.py '
        'not just for user-facing what-if questions, but INTERNALLY during revision — to simulate '
        'counterfactual scenarios and determine which hypothesis the observation supports.', 'body_left'))

    story.append(P('Refinement 3: Epistemic Precision ("reality disagrees" -> "observed outcomes reduce confidence")', 'h2'))
    story.append(P(
        '<b>V7 problem:</b> The document repeatedly said "reality disagrees with Maestro." This is '
        'philosophically imprecise and scientifically misleading. Reality does not disagree — reality '
        'gives observations. INTERPRETATION disagrees. The model\'s interpretation of the observation '
        'may conflict with its prediction.', 'body_left'))
    story.append(P(
        '<b>V7.1 fix:</b> Rewrite all constitutional language: "Observed outcomes reduce confidence in '
        'one or more causal hypotheses." This is how causal inference works. The model does not "discover '
        'it was wrong" — it adjusts confidence across competing hypotheses based on which ones the '
        'observation supports or contradicts. Law 3 is rewritten: "Every recommendation must make '
        'Maestro\'s understanding of the organization more accurate" becomes "Observed outcomes reduce '
        'confidence in one or more causal hypotheses, and the model revises accordingly."', 'body_left'))

    story.append(P('Refinement 4: Irreplaceability Score Grounded in Transparent Methodology', 'h2'))
    story.append(P(
        '<b>V7 problem:</b> The Irreplaceability Score said "Replacing Maestro\'s understanding would '
        'require 2.3 years." But the document did not explain HOW 2.3 was computed. A Fortune 100 CTO '
        'would ask "Explain exactly how you computed 2.3 years" and the document could not answer. This '
        'risks looking like an invented metric.', 'body_left'))
    story.append(P(
        '<b>V7.1 fix:</b> The Irreplaceability Score is an INDEX (0-100), not an estimated time. It is '
        'computed from 5 transparent factors:', 'body_left'))
    story.append(P('• <b>Resolved predictions</b> (weight 25%): each resolved prediction adds to the score. A competitor without this history cannot match the calibration.', 'body_left'))
    story.append(P('• <b>Model revisions</b> (weight 25%): each theory revision adds. Revisions encode organizational knowledge that cannot be copied.', 'body_left'))
    story.append(P('• <b>Causal chain coverage</b> (weight 20%): the percentage of organizational workflows covered by validated causal chains.', 'body_left'))
    story.append(P('• <b>Hypothesis stability</b> (weight 15%): the percentage of hypotheses whose confidence has stabilized (low variance over 30 days). Stable hypotheses are harder to displace.', 'body_left'))
    story.append(P('• <b>Evidence density</b> (weight 15%): signals per organizational workflow per month. Higher density = harder to replicate.', 'body_left'))
    story.append(P(
        'The score is: sum(weighted factors) on a 0-100 scale. A score of 50+ means "meaningful '
        'institutional memory." 70+ means "difficult to replace." 85+ means "would require years to '
        'recreate from scratch." The formula is transparent and reproducible — a CTO can inspect each '
        'factor and verify the computation.', 'body_left'))

    story.append(P('Refinement 5: Meta-Revision Engine (Learning How to Revise)', 'h2'))
    story.append(P(
        '<b>V7 problem:</b> The revision engine revises the model\'s theory. But it does not revise its '
        'own revision STRATEGY. Over time, some revisions prove reliable (the revised theory holds) and '
        'some prove unreliable (the revised theory is itself revised). The engine does not learn from '
        'this meta-level.', 'body_left'))
    story.append(P(
        '<b>V7.1 fix:</b> Add a Meta-Revision Engine that tracks: (1) Which kinds of evidence have '
        'historically produced reliable revisions? (2) Which revisions were later reversed? (3) Which '
        'parts of the model are consistently unstable? The meta-revision engine does not revise theories '
        '— it revises the REVISION PROCESS. If evidence from "contradiction signals" produces reliable '
        'revisions 80% of the time but evidence from "pattern detection" produces reliable revisions only '
        '40% of the time, the engine weights contradiction-based revisions higher.', 'body_left'))
    story.append(P(
        '<b>This is V7.1 Phase 3 (not Phase 1-2).</b> The meta-revision engine requires the core revision '
        'loop to have run for months (to accumulate revision-outcome data). It is specified here but '
        'built last.', 'body_left'))

    story.append(P('Refinement 6: Removed Speculative Acquisition Language', 'h2'))
    story.append(P(
        '<b>V7 problem:</b> The document said "Apple, Microsoft, Google, or OpenAI would look at this '
        'and think \'we need to own this.\'" Enterprise constitutions should not predict what other '
        'companies will think. Let the architecture stand on its own merits.', 'body_left'))
    story.append(P(
        '<b>V7.1 fix:</b> All speculative acquisition language removed. The constitution describes what '
        'Maestro IS and what it DOES. It does not speculate about who might buy it. The architecture '
        'stands on its own.', 'body_left'))

    story.append(Spacer(1, 6 * mm))

    # ── THE REFINED SPEC TABLE ───────────────────────────────────────────
    story.append(PageBreak())
    story.append(P('V7.1 Refined Specifications', 'h1'))

    rows = [
        ['#', 'Spec (V7.1 Refined)', 'Phase', 'Effort', 'Key Change from V7'],
        ['1', 'Institution Model (with competing hypotheses)', '1', '3.5 days', 'Maintains multiple hypotheses per causal question, not one. Bayesian competition, not single-theory convergence.'],
        ['2', 'Three-Mode Governance', '1', '2 days', 'Unchanged from V7. Recommendation / Execution / Autonomous with thresholds + audit.'],
        ['3', 'Closed Learning Loop (with counterfactual)', '2', '3 days', 'Adds counterfactual simulation step (using imagination.py) before revision. Observation -> Counterfactual -> Bayesian update across hypotheses.'],
        ['4', 'Model Revision Engine (Bayesian)', '2', '2.5 days', 'Revises confidence across ALL competing hypotheses (Bayesian update), not just one. Does not overwrite — adjusts. Prevents premature convergence.'],
        ['5', 'Living Organizational Model', '3', '3 days', 'Unchanged from V7. Merges DNA + Institution Model + Narrative + Revision History into one substrate.'],
        ['6', 'Irreplaceability Index (grounded)', '3', '1.5 days', 'INDEX (0-100) not estimated time. Computed from 5 transparent factors: resolved predictions, revisions, causal coverage, hypothesis stability, evidence density. Formula is reproducible.'],
        ['7', 'Meta-Revision Engine', '3', '2 days', 'NEW in V7.1. Tracks which revisions are reliable. Revises the revision process. Learns how to revise.'],
        ['', '', '', '', ''],
        ['TOTAL', '7 V7.1 specs (after V5+V6 backlog)', '3 phases', '~17.5 days', 'V7.1: Bayesian competing hypotheses + counterfactual + grounded metrics + meta-revision'],
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
        ('TEXTCOLOR', (4, 1), (4, 1), ST_REFINED),
        ('TEXTCOLOR', (4, 3), (4, 4), ST_REFINED),
        ('TEXTCOLOR', (4, 6), (4, 7), ST_REFINED),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>Changes from V7 (highlighted in blue):</b> Spec #1 now maintains competing hypotheses '
        '(not single theory). Spec #3 adds counterfactual simulation. Spec #4 uses Bayesian updates '
        '(not overwrite). Spec #6 is an index (not estimated time). Spec #7 (Meta-Revision) is new. '
        'Specs #2 and #5 are unchanged from V7.', 'body'))

    story.append(PageBreak())

    # ── THE EPISTEMIC LOOP ───────────────────────────────────────────────
    story.append(P('The Refined Epistemic Loop (V7.1)', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ST_REFINED.hexval()}"><b>THE REFINED LOOP — BAYESIAN + COUNTERFACTUAL</b></font>',
                  ParagraphStyle('loop_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ST_REFINED, spaceAfter=4)),
        P('<b>V7 loop (flawed):</b>', 'body_left'),
        P('Prediction -> Outcome -> Find failed assumption -> Revise theory (overwrite) -> Better prediction', 'body_left'),
        P('<b>V7.1 loop (refined):</b>', 'body_left'),
        P('1. <b>Predict</b> (weighted across competing hypotheses)', 'body_left'),
        P('2. <b>Observe</b> (the actual outcome)', 'body_left'),
        P('3. <b>Counterfactual simulation</b> (what would have happened if X were different? — using imagination.py)', 'body_left'),
        P('4. <b>Bayesian update</b> (adjust confidence of ALL hypotheses based on observation + counterfactual)', 'body_left'),
        P('5. <b>Hypothesis competition</b> (hypotheses with higher confidence contribute more to next prediction)', 'body_left'),
        P('6. <b>No overwrite</b> (the model never collapses to one theory until evidence is overwhelming)', 'body_left'),
        P('7. <b>Meta-revision</b> (track which revision strategies produce reliable results — adjust the process)', 'body_left'),
        P('<b>Key insight:</b> The model does not "discover it was wrong." It adjusts confidence across '
          'competing explanations. This is how scientific reasoning works. It is also how organizations '
          'actually think — multiple stakeholders hold different theories, and evidence shifts the '
          'balance without eliminating alternatives. Maestro should model this, not collapse it.', 'body_left'),
        P('<b>Why this matters:</b> Premature convergence (V7\'s risk) would make Maestro brittle — one '
          'wrong revision overwrites the theory, and the model cannot recover because the old theory is '
          'gone. Bayesian competition (V7.1) preserves uncertainty. The model always knows "I am 62% '
          'confident in Theory A, 51% in Theory B" — and can shift back to B if new evidence supports it. '
          'This is robust to noise, which real organizations produce in abundance.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ST_REFINED))

    # ── THE THREE LAWS (REFINED) ─────────────────────────────────────────
    story.append(P('The Three Constitutional Laws (V7.1 Refined)', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>THREE LAWS, ALL IMMUTABLE, REFINED</b></font>',
                  ParagraphStyle('laws_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=4)),
        P('<b>Law 1 (V6, unchanged):</b> "Every interaction must permanently improve the organization."', 'body_left'),
        P('<b>Law 2 (V6, unchanged):</b> "The organization should become more intelligent even when nobody opens Maestro."', 'body_left'),
        P('<b>Law 3 (V7.1 REFINED):</b> "Observed outcomes reduce confidence in one or more causal '
          'hypotheses, and the model revises accordingly." (V7 said "reality disagrees" — V7.1 replaces '
          'with epistemically precise language. Reality does not disagree. Observations reduce confidence. '
          'The model adjusts. This is Bayesian causal inference, not binary correctness.)', 'body_left'),
        P('<b>All three laws must pass for every V7.1 spec.</b> Plus the V5 litmus test (UI simpler) and '
          'V6 litmus test (permanently improves the organization). Five checks total. No exceptions.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ACCENT))

    # ── ACCEPTANCE CRITERIA FROM THE REVIEWER ────────────────────────────
    story.append(P('The Three Enterprise Adoption Criteria (from the Reviewer)', 'h1'))
    story.append(P(
        'The Fortune 100 CTO reviewer identified three criteria that would move Maestro from "interesting '
        'architecture" to "enterprise adoption." V7.1 must demonstrate all three:', 'body'))

    criteria = [
        ['Criterion', 'How V7.1 Addresses It', 'Acceptance Test'],
        ['1. Maintain multiple competing causal hypotheses (not collapse to one)', 'Spec #1 (Institution Model) maintains N hypotheses per causal question. Spec #4 (Bayesian Revision) updates confidence across ALL, never overwrites.', 'GET /api/oem/institution-model returns >= 2 hypotheses for at least 1 causal question, each with confidence + evidence. Resolving a prediction adjusts MULTIPLE hypotheses, not just one.'],
        ['2. Theory updates improve predictive performance on unseen situations', 'Spec #3 (Closed Loop) tracks accuracy BEFORE and AFTER each revision. Spec #6 (Irreplaceability Index) tracks whether accuracy is improving.', 'After 5+ revisions, prediction accuracy on NEW situations (not seen during revision) is higher than before revisions. The accuracy_trend shows improvement.'],
        ['3. Irreplaceability Score grounded in transparent methodology', 'Spec #6 is an INDEX (0-100) computed from 5 factors: resolved predictions (25%), model revisions (25%), causal coverage (20%), hypothesis stability (15%), evidence density (15%).', 'GET /api/oem/irreplaceability returns the 5 factor scores + the formula. A CTO can inspect each factor and verify the computation. No heuristic "2.3 years" — transparent index.'],
    ]
    t = Table(criteria, colWidths=[45*mm, 55*mm, PAGE_W - MARGIN_L - MARGIN_R - 100*mm])
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

    # ── BUILD ORDER ──────────────────────────────────────────────────────
    story.append(P('Build Order (V7.1)', 'h1'))

    dep_rows = [
        ['Phase', 'Specs', 'Duration', 'Prerequisite', 'Key Change'],
        ['0', 'V5 (complete) + V6 (#1-#6)', '~24 days', 'V5 done. V6 NOT started.', 'Must build V6 (adaptive nudges, evolution tracker, background adaptation, trajectory intervention, org DNA, autobiography) before V7.1.'],
        ['1', '#1 Institution Model (competing hypotheses) + #2 Governance', '~5.5 days', 'V5 causal.py + V6 org DNA.', 'Institution Model maintains N hypotheses per causal question (not 1). Bayesian competition.'],
        ['2', '#3 Closed Loop (with counterfactual) + #4 Bayesian Revision', '~5.5 days', 'V7.1 #1 Institution Model + V5 imagination.py.', 'Counterfactual simulation before revision. Bayesian update across ALL hypotheses (no overwrite).'],
        ['3', '#5 Living Model + #6 Irreplaceability Index + #7 Meta-Revision', '~6.5 days', 'V7.1 #1-#4 + V6 DNA + V6 autobiography.', 'Irreplaceability as transparent index (not estimated time). Meta-revision learns how to revise.'],
        ['', '', '', '', ''],
        ['TOTAL', '7 V7.1 specs (after V5+V6)', '~17.5 days', 'V5 complete + V6 complete (~24 days)', 'V7.1: Bayesian competing hypotheses + counterfactual + grounded metrics + meta-revision'],
    ]
    t = Table(dep_rows, colWidths=[12*mm, 45*mm, 18*mm, 35*mm, 60*mm])
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

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>Total to V7.1 completion: ~41.5 days</b> from current state (24 days V6 + 17.5 days V7.1). '
        'V5 is complete. V6 is the next task. V7.1 follows V6. Do NOT start V7.1 until V6 is complete.', 'body'))

    # ── THE PROGRESSION (FINAL) ──────────────────────────────────────────
    story.append(P('The Complete Progression (Final)', 'h1'))

    prog_rows = [
        ['Version', 'Verb', 'What Maestro Does', 'Epistemic Status'],
        ['V3', 'Observe', 'Sees what happened', 'Data collection'],
        ['V4', 'Judge', 'Synthesizes judgment', 'Pattern recognition'],
        ['V5', 'Disappear', 'Becomes invisible', 'Transparent intelligence'],
        ['V6', 'Adapt', 'Restructures work', 'Behavioral adaptation'],
        ['V7.1', 'Understand', 'Maintains competing causal theories; revises via Bayesian updates + counterfactuals', 'Epistemic loop (Bayesian causal inference)'],
        ['V8', 'Evolve', 'Meta-revision: learns how to revise; accumulated judgment becomes irreplaceable', 'Meta-epistemic (learns how to learn)'],
    ]
    t = Table(prog_rows, colWidths=[20*mm, 20*mm, 55*mm, 55*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('LEADING', (0, 0), (-1, -1), 11),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#f5d0fe')),  # V7.1 highlighted
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
        '<b>V7.1 is "Understand" — the epistemic loop.</b> The model maintains competing causal hypotheses, '
        'updates them via Bayesian inference and counterfactual simulation, and never collapses to one '
        'theory until the evidence is overwhelming. This is the first version that is scientifically '
        'defensible — not just "the model learns" but "the model learns using Bayesian causal inference '
        'with counterfactual grounding and competing hypotheses." V8 is "Evolve" — meta-revision, where '
        'the model learns HOW to learn. The accumulated judgment becomes irreplaceable.', 'body'))

    # ── FINAL NOTE ───────────────────────────────────────────────────────
    story.append(P('Final Note', 'h1'))
    story.append(P(
        'V7.1 is the first constitution that reads like a research and engineering roadmap rather than '
        'a sequence of ambitious feature ideas. The dependencies are explicit. The abstractions line up. '
        'Each phase has a clear role. The epistemic loop is sound: Bayesian competing hypotheses, '
        'counterfactual simulation, no premature convergence, transparent metrics, meta-revision. The '
        'architecture stands on its own merits.', 'body'))
    story.append(P(
        '<b>The next task for the coder:</b> build V6 Phase 1 (Adaptive Nudges + Evolution Tracker, '
        '~5 days). Then V6 Phase 2-3 (Background Adaptation + Trajectory Intervention + Org DNA + '
        'Autobiography, ~10 days). Then V7.1 Phase 1 (Institution Model with competing hypotheses + '
        'Governance, ~5.5 days). Then V7.1 Phase 2 (Closed Loop with counterfactual + Bayesian Revision, '
        '~5.5 days). Then V7.1 Phase 3 (Living Model + Irreplaceability Index + Meta-Revision, ~6.5 '
        'days). Total ~32.5 days from current state to V7.1 completion.', 'body'))
    story.append(P(
        '<b>Build V6 first. Then V7.1. Do not skip ahead. The epistemic loop requires the adaptation '
        'layer (V6) and the causal foundation (V5, complete). Build in order. Wire everything. Run the '
        'full test suite. Maintain the pattern. The Invisible Layer (V5) + Institutional Adaptation (V6) '
        '+ Self-Revising Institutional Model (V7.1) = an operating system for institutional learning. '
        'Build it.</b>', 'body'))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'MaestroAgent_Constitution_V7_1_Refined.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
