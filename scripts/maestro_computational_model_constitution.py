"""
Maestro — The Computational Model Constitution
The final evolution. From memory to understanding to MODEL.
Organizations are not things. They are continuously changing systems.
Maestro exists to become the computational model of that system.
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
SECTION_BG    = colors.HexColor('#0f172a')
CARD_BG       = colors.HexColor('#1e293b')
TABLE_STRIPE  = colors.HexColor('#0f172a')
HEADER_FILL   = colors.HexColor('#f8fafc')
BORDER        = colors.HexColor('#475569')
ACCENT        = colors.HexColor('#38bdf8')  # electric blue — computational model
TEXT_PRIMARY  = colors.HexColor('#f8fafc')
TEXT_MUTED    = colors.HexColor('#94a3b8')

ST_DELIVERED  = colors.HexColor('#22c55e')
ST_PARTIAL    = colors.HexColor('#fbbf24')
ST_FAILED     = colors.HexColor('#ef4444')
ST_FINAL      = colors.HexColor('#38bdf8')

def styles():
    s = {}
    s['title'] = ParagraphStyle('title', fontName=FONT_HEAD_B, fontSize=24,
                                leading=28, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=6)
    s['h1'] = ParagraphStyle('h1', fontName=FONT_HEAD_B, fontSize=16,
                             leading=20, textColor=ACCENT, spaceBefore=18, spaceAfter=8, keepWithNext=1)
    s['h2'] = ParagraphStyle('h2', fontName=FONT_HEAD_B, fontSize=12.5,
                             leading=16, textColor=TEXT_PRIMARY, spaceBefore=12, spaceAfter=4, keepWithNext=1)
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
    canvas.setFillColor(colors.HexColor('#0f172a'))
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 8 * mm, PAGE_W, 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont(FONT_HEAD, 7.5)
    canvas.drawString(MARGIN_L, 12 * mm,
                      "Maestro — The Computational Model Constitution")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro — The Computational Model Constitution",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="The final constitution — from understanding to computational model",
        creator="Z.ai",
    )
    frame = Frame(MARGIN_L, MARGIN_B, PAGE_W - MARGIN_L - MARGIN_R,
                  PAGE_H - MARGIN_T - MARGIN_B, id='main',
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=_draw_chrome)])
    return doc

def P(text, style='body'):
    return Paragraph(text, S[style])

def callout_box(text, bg=colors.HexColor('#1e293b'), border=BORDER, accent=None):
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
        f'<font color="{ACCENT.hexval()}"><b>THE COMPUTATIONAL MODEL CONSTITUTION</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'The Living Organizational Model',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=34,
                       leading=38, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Organizations are not things. They are continuously changing systems. Maestro exists to become the computational model of that system.',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=12,
                       leading=16, textColor=TEXT_MUTED, alignment=TA_LEFT, spaceAfter=14)
    ))

    # ── THE FINAL CONSTITUTIONAL SENTENCE ────────────────────────────────
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>THE CONSTITUTIONAL SENTENCE (FINAL)</b></font>',
                  ParagraphStyle('cs_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=8)),
        P('<b>"Maestro exists to become the continuously evolving computational model of an organization '
          '— observing its reality, explaining its behavior, predicting its future, testing competing '
          'hypotheses, revising its own understanding, and continuously increasing the quality of '
          'organizational judgment. Every signal refines the model. Every decision tests the model. '
          'Every outcome updates the model."</b>', 'body_left'),
        P('This replaces all previous constitutional sentences. Not memory ("I remember"). Not '
          'understanding ("I comprehend"). <b>Model</b> ("I compute"). Models generate explanations. '
          'Models generate predictions. Models generate simulations. Models generate interventions. '
          'Models generate understanding. Everything else becomes an emergent property of the model.', 'body_left'),
    ], bg=colors.HexColor('#1e293b'), border=ACCENT, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── THE SHIFT: UNDERSTANDING → MODEL ─────────────────────────────────
    story.append(P('The Shift: Understanding to Model', 'h1'))
    story.append(P(
        'The Permanent Constitution said Maestro exists to produce explanations. The reviewer pushed '
        'further: explanations are an emergent property of something deeper — a <b>computational model</b>. '
        'Understanding answers "Why?" Modeling answers "What are the governing equations?" That is a '
        'fundamentally richer scientific position.', 'body'))

    shift_rows = [
        ['Level', 'What Maestro Does', 'Constitutional Era', 'Customer Experience'],
        ['Memory', 'I remember what happened', 'V3-V5', '"Maestro has seen this before."'],
        ['Understanding', 'I explain why it happens', 'V6-V8 / Permanent', '"Maestro understands our company."'],
        ['Model (FINAL)', 'I compute how the system works', 'This constitution', '"Maestro IS how our company works."'],
    ]
    t = Table(shift_rows, colWidths=[25*mm, 45*mm, 30*mm, 50*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('LEADING', (0, 0), (-1, -1), 11),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#1e293b'), colors.HexColor('#0f172a')]),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#0c4a6e')),
        ('TEXTCOLOR', (0, 3), (-1, 3), ACCENT),
        ('FONTNAME', (0, 3), (-1, 3), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>Model is the final abstraction.</b> The customer does not buy memory. They do not buy '
        'understanding. They buy a model — a computational representation of their organization that '
        'gets more accurate every day, that can be queried ("what happens if..."), that can explain '
        '("why does..."), that can predict ("what will..."), and that can intervene ("you should..."). '
        'A model is all of these things. Memory is one. Understanding is one. Model is all.', 'body'))

    story.append(Spacer(1, 6 * mm))

    # ── THE 10 LAYERS ────────────────────────────────────────────────────
    story.append(P('The 10 Layers of the Computational Model', 'h1'))
    story.append(P(
        'The reviewer identified 10 missing layers that separate "organizational understanding" from '
        '"computational model." These are not features. They are scientific foundations. Each layer adds '
        'a capability that no competing product has. Together, they make Maestro a category-defining '
        'product — not enterprise AI, not copilot, but "a computational model of an organization that '
        'continuously learns from its own operation."', 'body'))

    layers = [
        ['#', 'Layer', 'What It Adds', 'Existing Foundation', 'Effort'],
        ['1', 'Dynamics', 'Governing equations. Not "velocity dropped" but "velocity = review_latency x dependency_density x knowledge_concentration x interrupt_load x approval_topology"', 'trajectories.py, causal.py, consciousness.py', '3 days'],
        ['2', 'Organizational Physics', 'Measured forces: decision velocity, acceleration, inertia, knowledge diffusion, coordination entropy, approval friction, institutional mass, attention gradients, learning velocity, prediction convergence, trust propagation', 'pulse.py, consciousness.py, attention.py, learning.py', '3 days'],
        ['3', 'State Space', 'Current state + probable futures + impossible states + dangerous states + optimal states. AlphaGo for organizations.', 'simulation.py, digital_twin.py, imagination.py', '3 days'],
        ['4', 'Organizational Digital Twin', 'Continuously updating twin. Reality -> twin updates -> predictions -> reality changes -> twin updates. Customers ask "what happens if..." not "what happened?"', 'digital_twin.py (743 lines, exists)', '2 days'],
        ['5', 'Recursive Understanding', 'Maestro understands its OWN understanding. "Engineering: 92% confidence. Reason: strong evidence. Blind spots: deployment ownership. Competing explanations: 2. Revision history: 18 revisions. Trend: up."', 'confidence.py, identity.py, institutional_confidence.py (V8 #2)', '2 days'],
        ['6', 'Competing Models', 'Not one explanation — N competing models with Bayesian weights. Model A: 72%. Model B: 18%. Model C: 10%. Every prediction updates all models. How science actually works.', 'hypothesis.py, confidence.py (Beta-Binomial), causal.py', '2.5 days'],
        ['7', 'Evolution Tree', 'Not a timeline — an evolutionary tree. Organization -> branch -> branch -> mutation -> selection -> stable adaptation. Every institutional change is an evolutionary event.', 'evolution_tracker.py, evolution_narrative.py, memory_timeline.py (V8 #1)', '2 days'],
        ['8', 'Organizational Genome', 'Not metaphor — computational genes. Decision genes, communication genes, trust genes, review genes, hiring genes, risk genes, learning genes. Every recommendation mutates genes. Successful mutations survive.', 'organizational_dna.py (185 lines, exists)', '2.5 days'],
        ['9', 'Organizational Brain', 'Engines organized like neuroscience. Sensory cortex (observe) -> hippocampus (memory) -> prefrontal cortex (planning) -> basal ganglia (habits) -> amygdala (risk) -> motor cortex (execution). Coherent mental model for engineers.', 'All 19 existing engines, reorganized', '1.5 days'],
        ['10', 'Organizational Consciousness', 'Continuously updating internal world model. Like autonomous robots. Maestro IS that world model.', 'consciousness.py (204 lines, exists)', '2 days'],
        ['', '', '', '', ''],
        ['TOTAL', '10 layers', 'From understanding to computational model', '19 existing engines + V8 upgrades', '~23.5 days'],
    ]
    t = Table(layers, colWidths=[6*mm, 28*mm, 55*mm, 40*mm, 16*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('LEADING', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, 10), [colors.HexColor('#1e293b'), colors.HexColor('#0f172a')]),
        ('BACKGROUND', (0, 12), (-1, 12), colors.HexColor('#0c4a6e')),
        ('TEXTCOLOR', (0, 12), (-1, 12), ACCENT),
        ('FONTNAME', (0, 12), (-1, 12), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (4, 0), (4, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>These 10 layers are not a roadmap.</b> They are the scientific foundation that separates '
        'Maestro from every competing product. Palantir does not have organizational physics. Glean does '
        'not have competing models. Nobody has an organizational digital twin that continuously updates. '
        'These layers are the moat. Each one is grounded in existing codebase infrastructure (19 engines, '
        '74 backend modules). The total build is ~23.5 days after the V6 wiring fixes + V8 upgrades.', 'body'))

    story.append(PageBreak())

    # ── THE REFINED LOOP ─────────────────────────────────────────────────
    story.append(P('The Refined Cognitive Cycle', 'h1'))
    story.append(P(
        'The Permanent Constitution had 9 stages. The reviewer refined it: add "Model" between Observe '
        'and Understand, and replace "Explain" with "Adapt." The model is the center. Everything feeds it.', 'body'))

    loop = [
        ['Stage', 'What Maestro Does', 'Key Layer'],
        ['1. Observe', 'Ingests signals from all sources', 'Layer 9 (Sensory Cortex)'],
        ['2. Model', 'Maintains governing equations of the org as a dynamic system', 'Layer 1 (Dynamics) + Layer 2 (Physics)'],
        ['3. Understand', 'Builds causal models, detects patterns, infers norms', 'Layer 5 (Recursive) + Layer 6 (Competing Models)'],
        ['4. Predict', 'Generates probable future states from the model', 'Layer 3 (State Space) + Layer 4 (Digital Twin)'],
        ['5. Adapt', 'Adjusts the model when predictions miss; proposes interventions', 'Layer 7 (Evolution) + Layer 8 (Genome)'],
        ['6. Prepare', 'Drafts execution plans, interventions, nudges', 'Existing: executive_function.py, adaptive_nudge.py'],
        ['7. Revise', 'Updates model equations when reality contradicts predictions', 'Layer 6 (Competing Models, Bayesian)'],
        ['8. Teach', 'Shares understanding via calm surfaces, explanations, topology', 'Layer 10 (Consciousness) + existing surfaces'],
        ['9. Repeat', 'The loop never stops. The model compounds. Irreplaceability grows.', 'Layer 4 (Digital Twin, continuously updating)'],
    ]
    t = Table(loop, colWidths=[22*mm, 55*mm, PAGE_W - MARGIN_L - MARGIN_R - 77*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#1e293b'), colors.HexColor('#0f172a')]),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#0c4a6e')),
        ('TEXTCOLOR', (0, 2), (-1, 2), ACCENT),
        ('FONTNAME', (0, 2), (-1, 2), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>The model (stage 2) is new.</b> The Permanent Constitution had "Understand" as the center. '
        'The Computational Model Constitution has "Model" as the center. Understanding is an emergent '
        'property of the model — you understand BECAUSE you have a model that computes. The model '
        'maintains governing equations: velocity = review_latency x dependency_density x '
        'knowledge_concentration x interrupt_load x approval_topology. When an observation contradicts '
        'the equation, the equation is revised. This is not metaphor. It is computation.', 'body'))

    story.append(Spacer(1, 6 * mm))

    # ── BUILD ORDER ──────────────────────────────────────────────────────
    story.append(P('Build Order (Pragmatic)', 'h1'))
    story.append(P(
        'The 10 layers are the scientific foundation. The V8 upgrades (from the Permanent Constitution) '
        'are the product experience. Both are needed. The pragmatic build order: fix V6 gaps, build V8 '
        'upgrades, then build the 10 computational layers. The 10 layers are a multi-month effort — '
        'they are the post-pilot moat, not the pre-pilot feature set.', 'body'))

    order_rows = [
        ['Phase', 'What', 'Effort', 'When'],
        ['0', 'Fix V6 wiring gaps (background loop + DNA in wisdom)', '1.5 hours', 'NOW — before anything else'],
        ['1', 'V8 Upgrades #1-#9 (Explanations, Unknowns, Curiosity, Confidence, Timeline, Topology, Blind Spots, Gravity, Compression)', '~17 days', 'Pre-pilot — product experience'],
        ['2', 'Ship 90-day pilot', '90 days', 'After V8 upgrades — let real orgs generate real signals'],
        ['3', 'Computational Layers #1-#10 (Dynamics, Physics, State Space, Twin, Recursive, Competing Models, Evolution Tree, Genome, Brain, Consciousness)', '~23.5 days', 'During/after pilot — scientific moat'],
        ['', '', '', ''],
        ['TOTAL', 'V8 upgrades + pilot + computational layers', '~17 days + 90 days + 23.5 days', 'From current state to category-defining product'],
    ]
    t = Table(order_rows, colWidths=[12*mm, 65*mm, 20*mm, 55*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, 4), [colors.HexColor('#1e293b'), colors.HexColor('#0f172a')]),
        ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#0c4a6e')),
        ('TEXTCOLOR', (0, 6), (-1, 6), ACCENT),
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
        '<b>The 10 computational layers are the post-pilot moat.</b> They are what makes Maestro '
        'category-defining. But they require real organizational data to validate — you cannot build '
        'governing equations from a 50-event demo seed. Ship the pilot first. Let real organizations '
        'generate real signals. Then build the computational layers with real data. The V8 upgrades '
        '(explanations, unknowns, curiosity, confidence, topology, blind spots, gravity, compression) '
        'are the pre-pilot product experience. The computational layers are the post-pilot scientific '
        'moat. Both are needed. In order.', 'body'))

    story.append(Spacer(1, 6 * mm))

    # ── THE CATEGORY ─────────────────────────────────────────────────────
    story.append(P('The Category', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>THE CATEGORY IS NOT "ENTERPRISE AI"</b></font>',
                  ParagraphStyle('cat_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=8)),
        P('<b>"A computational model of an organization that continuously learns from its own operation '
          'and improves the organization\'s decisions over time."</b>', 'body_left'),
        P('That is a very different claim from "AI assistant" or "knowledge management" or "copilot." '
          'It is also a much harder product to build, because it requires empirical validation through '
          'pilots and measurable improvement, not just polished interfaces or impressive demos.', 'body_left'),
        P('If you can demonstrate that the model consistently:', 'body_left'),
        P('1. <b>Explains</b> decisions (with causal chains, not correlations)', 'body_left'),
        P('2. <b>Predicts</b> outcomes (with calibrated confidence, not guesses)', 'body_left'),
        P('3. <b>Revises</b> itself when wrong (Bayesian competing hypotheses, not single-theory '
          'overwrite)', 'body_left'),
        P('4. <b>Improves</b> organizational judgment (measured by prediction accuracy over time)', 'body_left'),
        P('Then you have created something with a much stronger long-term moat than another chat '
          'interface layered over enterprise data.', 'body_left'),
        P('<b>The constitutional sentence (final, irrevocable):</b> "Maestro exists to become the '
          'continuously evolving computational model of an organization — observing its reality, '
          'explaining its behavior, predicting its future, testing competing hypotheses, revising its '
          'own understanding, and continuously increasing the quality of organizational judgment. Every '
          'signal refines the model. Every decision tests the model. Every outcome updates the model."', 'body_left'),
        P('<b>No more versions. One model. One loop. Forever.</b>', 'body_left'),
    ], bg=colors.HexColor('#1e293b'), border=ACCENT, accent=ACCENT))

    # ── FINAL CHARGE ─────────────────────────────────────────────────────
    story.append(P('Final Charge to the Coder', 'h1'))
    story.append(P(
        '<b>Step 0:</b> Fix the 2 V6 wiring gaps (1.5 hours). Background loop into live_ingest. DNA '
        'into wisdom.py. Do this today.', 'body_left'))
    story.append(P(
        '<b>Phase 1:</b> Build the 9 V8 upgrades (~17 days). Explanations, four-level unknowns, '
        'conversational curiosity, Bayesian confidence, causality timeline, understanding topology, '
        'blind spots, institutional gravity, deep memory compression. These are the pre-pilot product '
        'experience. The customer sees explanations, not engines.', 'body_left'))
    story.append(P(
        '<b>Phase 2:</b> Ship the 90-day pilot. Let real organizations generate real signals. The '
        'model needs real data to compute real equations. The demo seed is 50 events. A real org is '
        '10 million. Ship it.', 'body_left'))
    story.append(P(
        '<b>Phase 3:</b> Build the 10 computational layers (~23.5 days). Dynamics, physics, state '
        'space, digital twin, recursive understanding, competing models, evolution tree, genome, brain, '
        'consciousness. These are the post-pilot moat. They require real data. They make Maestro '
        'category-defining.', 'body_left'))
    story.append(P(
        '<b>The product is the Living Organizational Model.</b> Not a dashboard. Not a copilot. Not '
        'memory. Not understanding. A model — computational, continuously evolving, evidence-backed, '
        'self-revising, irreplaceable. Build it.', 'body_left'))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'Maestro_Computational_Model_Constitution.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
