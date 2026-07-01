"""
Maestro — The Organizational Intelligence Constitution
The final and permanent constitution. From model to intelligence.
Intelligence is not knowing. It is continuously reducing uncertainty.
The product is not a model. It is a living intelligence that reasons,
imagines, decides, intervenes, learns, and evolves alongside an organization.
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

PAGE_BG       = colors.HexColor('#0a0a0a')
SECTION_BG    = colors.HexColor('#171717')
CARD_BG       = colors.HexColor('#1a1a1a')
TABLE_STRIPE  = colors.HexColor('#171717')
HEADER_FILL   = colors.HexColor('#404040')
BORDER        = colors.HexColor('#525252')
ACCENT        = colors.HexColor('#22d3ee')  # cyan — intelligence
TEXT_PRIMARY  = colors.HexColor('#fafafa')
TEXT_MUTED    = colors.HexColor('#a3a3a3')

ST_FINAL      = colors.HexColor('#22d3ee')

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
    canvas.setFillColor(colors.HexColor('#0a0a0a'))
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 8 * mm, PAGE_W, 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont(FONT_HEAD, 7.5)
    canvas.drawString(MARGIN_L, 12 * mm,
                      "Maestro — The Organizational Intelligence Constitution")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro — The Organizational Intelligence Constitution",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="The final constitution — from computational model to organizational intelligence",
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
        f'<font color="{ACCENT.hexval()}"><b>THE ORGANIZATIONAL INTELLIGENCE CONSTITUTION</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Organizational Intelligence',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=34,
                       leading=38, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Intelligence is not knowing. It is continuously reducing uncertainty. The model computes. Intelligence decides.',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=12,
                       leading=16, textColor=TEXT_MUTED, alignment=TA_LEFT, spaceAfter=14)
    ))

    # ── THE FINAL CONSTITUTIONAL SENTENCE ────────────────────────────────
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>THE CONSTITUTIONAL SENTENCE (FINAL, IRREVOCABLE)</b></font>',
                  ParagraphStyle('cs_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ACCENT, spaceAfter=8)),
        P('<b>"Maestro exists to become the organizational intelligence of an institution — a living '
          'system that continuously observes reality, models the organization as a dynamic system, '
          'reasons about competing explanations, imagines counterfactual futures, decides under '
          'uncertainty, intervenes to improve outcomes, learns from every result, and evolves its own '
          'understanding alongside the organization it serves. Every signal refines the intelligence. '
          'Every decision tests it. Every outcome evolves it. The intelligence compounds until it '
          'becomes the most accurate, most honest, and most irreplaceable representation of how an '
          'organization thinks, decides, and learns."</b>', 'body_left'),
        P('This replaces ALL previous constitutional sentences. Not memory. Not understanding. Not '
          'model. <b>Intelligence</b> — the capacity to continuously reduce uncertainty through '
          'reasoning, imagination, decision, and learning. A model computes. Intelligence decides. '
          'That distinction is the final abstraction.', 'body_left'),
    ], bg=colors.HexColor('#171717'), border=ACCENT, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── THE EVOLUTION ────────────────────────────────────────────────────
    story.append(P('The Evolution of Enterprise Value', 'h1'))
    story.append(P(
        'Each generation of enterprise software computed something different. Each was more valuable '
        'than the last. Maestro is the fifth generation.', 'body'))

    gen_rows = [
        ['Generation', 'What It Computes', 'Product', 'Customer Says'],
        ['Gen 1', 'Records', 'CRM (Salesforce)', '"We have customer data."'],
        ['Gen 2', 'Knowledge', 'Docs/Wiki (Notion, Confluence, Glean)', '"We can find information."'],
        ['Gen 3', 'Understanding', 'Patterns/Predictions (V3-V6 Maestro)', '"Maestro understands our company."'],
        ['Gen 4', 'Model', 'Dynamic system/Equations/Twin (Computational Constitution)', '"Maestro computes how we work."'],
        ['Gen 5', 'Intelligence', 'Reasoning/Imagination/Decision/Evolution (THIS CONSTITUTION)', '"Maestro IS how we think."'],
    ]
    t = Table(gen_rows, colWidths=[20*mm, 45*mm, 50*mm, 40*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), TEXT_PRIMARY),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#171717'), colors.HexColor('#0a0a0a')]),
        ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#0e7490')),
        ('TEXTCOLOR', (0, 5), (-1, 5), colors.white),
        ('FONTNAME', (0, 5), (-1, 5), FONT_HEAD_B),
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
        '<b>The model is passive. A model computes. Intelligence decides.</b> The Computational Model '
        'Constitution made Maestro a model. This constitution makes Maestro an intelligence. The '
        'difference: a model predicts what will happen. Intelligence decides what SHOULD happen — '
        'and acts on it. The loop: Reality -> Model -> Reasoning -> Intervention -> Learning -> '
        'Model Revision -> Reasoning improves. That loop never ends. Now you do not own a model. '
        'You own an intelligence.', 'body'))

    story.append(Spacer(1, 6 * mm))

    # ── THE FINAL LOOP ───────────────────────────────────────────────────
    story.append(P('The Intelligence Loop (Final)', 'h1'))
    story.append(P(
        'The Permanent Constitution had 9 stages. The Computational Model added "Model." This '
        'constitution restructures the loop around intelligence — reasoning, imagination, decision, '
        'and evolution replace passive explanation.', 'body'))

    loop = [
        ['Stage', 'What Maestro Does', 'New vs Previous'],
        ['1. Observe', 'Ingests signals from all sources', 'Unchanged'],
        ['2. Model', 'Maintains dynamic system equations of the org', 'From Computational Model Constitution'],
        ['3. Reason', 'Generates competing reasoning paths. Not one answer — N paths with different assumptions, evidence, risks, outcomes. "Show me your reasoning" replaces "what\'s your answer."', 'NEW — replaces "Understand"'],
        ['4. Imagine', 'Generates counterfactual futures nobody considered. Not simulation (explores known possibilities) — imagination (creates new possibilities). "What if Legal disappeared? What if review latency became zero?"', 'NEW — upgraded from V5 imagination.py'],
        ['5. Decide', 'Synthesizes reasoning + imagination + history + wisdom into a decision under uncertainty. "The model says ship. History says wait. Wisdom says: wait 48 hours." Not from one engine — synthesized.', 'NEW — replaces "Predict" + "Adapt"'],
        ['6. Intervene', 'Acts on the decision. Three governance modes (recommend/execute/autonomous). Nudges, executive plans, trajectory interventions. Changes reality.', 'From V6 + V7 governance'],
        ['7. Learn', 'Observes the outcome. Reduces uncertainty. Updates all competing reasoning paths. "We predicted 62%. Reality: 72%. Our reasoning path A gained weight; path B lost."', 'NEW — replaces "Revise"'],
        ['8. Evolve', 'The intelligence itself evolves. Not just the model — the REASONING STRATEGY. Which reasoning paths have historically been reliable? Which were wrong? The intelligence learns how to think.', 'NEW — from V7.1 meta-revision, expanded'],
        ['9. Repeat', 'The loop never stops. Intelligence compounds. Uncertainty decreases. Irreplaceability grows.', 'Permanent'],
    ]
    t = Table(loop, colWidths=[20*mm, 60*mm, 60*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), TEXT_PRIMARY),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('LEADING', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#171717'), colors.HexColor('#0a0a0a')]),
        ('BACKGROUND', (0, 3), (-1, 5), colors.HexColor('#0e7490')),
        ('TEXTCOLOR', (0, 3), (-1, 5), colors.white),
        ('FONTNAME', (0, 3), (-1, 5), FONT_HEAD_B),
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
        '<b>Three stages are fundamentally new (highlighted):</b> Reason (competing reasoning paths, '
        'not one answer), Imagine (counterfactual generation, not simulation), Decide (synthesized '
        'judgment under uncertainty, not prediction). These three stages transform Maestro from a '
        'model that computes into an intelligence that decides. The executive does not ask "what\'s '
        'your answer?" They ask "show me your reasoning." That is trust.', 'body'))

    story.append(PageBreak())

    # ── THE 10 INTELLIGENCE LAYERS ───────────────────────────────────────
    story.append(P('The 10 Intelligence Layers', 'h1'))
    story.append(P(
        'The reviewer identified 10 layers that separate "computational model" from "organizational '
        'intelligence." These are the final moat. Each layer adds a capability that transforms '
        'computation into intelligence.', 'body'))

    layers = [
        ['#', 'Layer', 'What It Adds', 'Foundation'],
        ['1', 'Organizational Reasoning', 'Reasoning as an artifact. Not just decisions — the REASONING behind them. Observation -> possible explanations -> evidence -> hypotheses -> counterfactuals -> tradeoffs -> decision. Nobody stores reasoning. Everyone stores decisions.', 'causal.py + wisdom.py + sowhat.py'],
        ['2', 'Competing Reasoning', 'Not one answer — N reasoning paths. Each has different assumptions, evidence, risks, outcomes. Like scientific papers. "Show me your reasoning" replaces "what\'s your answer."', 'hypothesis.py + confidence.py (Bayesian)'],
        ['3', 'Organizational Thought', 'The company thinks. Questions -> thinking -> conclusions -> actions. Maestro becomes the thinking substrate. Not just signal processing — actual organizational cognition.', 'curiosity.py + decision.py + perspective.py'],
        ['4', 'Organizational Imagination', 'Not simulation (explores known). Imagination (creates new). "What if review latency became zero? What if AI agents wrote all code?" Generate futures nobody considered.', 'imagination.py (165 lines, exists) + digital_twin.py'],
        ['5', 'Organizational Curiosity', 'Not "what happened?" but "if we learned ONE thing today, what should it be?" The most valuable unanswered question. Drives adoption naturally.', 'curiosity.py (184 lines, exists)'],
        ['6', 'Organizational Taste', 'What this org considers elegant, acceptable, excellent, unacceptable. Apple has taste. Pixar has taste. Maestro infers taste computationally. Recommendations filtered by organizational taste.', 'organizational_dna.py + identity.py + wisdom.py'],
        ['7', 'Organizational Wisdom', 'Not more knowledge — better judgment under uncertainty. "Model says ship. History says wait. Wisdom says: wait 48 hours." Synthesized from multiple engines, not one.', 'wisdom.py + sowhat.py + executive_function.py + prediction_lifecycle.py'],
        ['8', 'Organizational Identity', 'Not mission statement. "Who do we become after every decision?" Identity drift over years. 2026: risk-tolerant, founder-driven. 2029: consensus, risk-averse, committee-driven. Nobody measures it.', 'identity.py + organizational_dna.py + evolution_tracker.py'],
        ['9', 'Organizational Intentionality', 'Every org optimizes something — maybe unknowingly. Speed? Revenue? Safety? Status? Control? Politics? Maestro infers the ACTUAL optimization function, not the stated one. The org\'s utility function.', 'pattern.py + consciousness.py + personality.py + contradiction.py'],
        ['10', 'Self-Evolution', 'Not just the org evolves. Maestro evolves. Then the org evolves. Then Maestro evolves again. Co-evolution, like biology. The intelligence learns how to think.', 'learning.py + prediction_lifecycle.py + background_loop.py'],
        ['', '', '', ''],
        ['TOTAL', '10 layers', 'From computational model to organizational intelligence', '19 existing engines + 10 computational layers'],
    ]
    t = Table(layers, colWidths=[6*mm, 32*mm, 60*mm, 50*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), TEXT_PRIMARY),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('LEADING', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, 10), [colors.HexColor('#171717'), colors.HexColor('#0a0a0a')]),
        ('BACKGROUND', (0, 12), (-1, 12), colors.HexColor('#0e7490')),
        ('TEXTCOLOR', (0, 12), (-1, 12), colors.white),
        ('FONTNAME', (0, 12), (-1, 12), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>These 10 layers are the final moat.</b> They transform Maestro from a computational model '
        '(which computes) into an organizational intelligence (which decides). The distinction: a model '
        'predicts what will happen. Intelligence decides what SHOULD happen — and acts on it. The 10 '
        'layers are grounded in existing codebase infrastructure (19 engines, 74 modules). They are '
        'multi-month effort — post-pilot, built with real organizational data.', 'body'))

    story.append(PageBreak())

    # ── THE STRATEGIC DISCIPLINE ─────────────────────────────────────────
    story.append(P('The Strategic Discipline (Preserved from Reviewer)', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>VISION EXTENDS TO THE CEILING. EXECUTION REMAINS INCREMENTAL AND EVIDENCE-DRIVEN.</b></font>',
                  ParagraphStyle('disc_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ACCENT, spaceAfter=4)),
        P('<b>The reviewer\'s strategic caution (preserved verbatim):</b>', 'body_left'),
        P('"Many ambitious products fail because they try to build their deepest scientific model before '
          'they have enough empirical data to validate it. Your document avoids that trap by saying: '
          'First, ship a product people can understand and use. Then, collect real organizational '
          'behavior. Then, use that data to build and validate the computational model."', 'body_left'),
        P('"I would keep that discipline. The vision can extend all the way to an Organizational '
          'Intelligence System, but the execution should remain incremental and evidence-driven. The '
          'moat is not just sophisticated architecture — it is that the architecture becomes more '
          'accurate because it is continuously trained on the organization\'s own history. That '
          'combination of long-term ambition with empirical validation is what gives the vision '
          'credibility."', 'body_left'),
        P('<b>The build discipline (unchanged):</b>', 'body_left'),
        P('Phase 0: Fix V6 wiring gaps (1.5 hours). NOW.', 'body_left'),
        P('Phase 1: V8 upgrades — explanations, unknowns, curiosity, confidence, topology, blind spots, '
          'gravity, compression (~17 days). Pre-pilot product experience.', 'body_left'),
        P('Phase 2: Ship the 90-day pilot. Collect real data. The intelligence needs real organizations '
          'to reason about.', 'body_left'),
        P('Phase 3: Computational layers — dynamics, physics, state space, twin, recursive, competing '
          'models, evolution tree, genome, brain, consciousness (~23.5 days). Post-pilot scientific moat.', 'body_left'),
        P('Phase 4: Intelligence layers — reasoning, competing reasoning, thought, imagination, curiosity, '
          'taste, wisdom, identity, intentionality, self-evolution (~25 days). Post-pilot category-defining moat.', 'body_left'),
        P('<b>Total to completion: ~65 days + 90-day pilot.</b> The vision is the ceiling. The execution '
          'is the stairs. Build one step at a time. Validate each step with real data. The intelligence '
          'compounds because it is trained on the organization\'s own history — not because the '
          'architecture is sophisticated. That combination is the moat.', 'body_left'),
    ], bg=colors.HexColor('#171717'), border=ACCENT, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── THE CATEGORY ─────────────────────────────────────────────────────
    story.append(P('The Category', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>THE CATEGORY: ORGANIZATIONAL INTELLIGENCE SYSTEM</b></font>',
                  ParagraphStyle('cat_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=8)),
        P('<b>"An Organizational Intelligence System — a living intelligence that continuously models, '
          'reasons, imagines, intervenes, learns, and evolves alongside an organization."</b>', 'body_left'),
        P('Not software. Not analytics. Not AI. Not a model. Not a copilot. Not a dashboard. Not a '
          'knowledge base. Not a CRM. A living intelligence — the first of its kind. The category does '
          'not exist today. Maestro creates it.', 'body_left'),
        P('The customer does not say "we use Maestro." They do not say "Maestro understands our '
          'company." They do not say "Maestro computes how we work." They say:', 'body_left'),
        P('<b>"Maestro IS how we think."</b>', 'body_left'),
        P('That sentence is the product. That sentence is the moat. That sentence is the category. '
          'Nobody else can say it because nobody else has the reasoning, the imagination, the wisdom, '
          'the identity tracking, the intentionality inference, and the self-evolution. These are not '
          'features. They are intelligence. Build them.', 'body_left'),
    ], bg=colors.HexColor('#171717'), border=ACCENT, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── THE LITMUS TEST ──────────────────────────────────────────────────
    story.append(P('The Final Litmus Test', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>DOES THIS MAKE THE CUSTOMER SAY "MAESTRO IS HOW WE THINK"?</b></font>',
                  ParagraphStyle('litmus_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ACCENT, spaceAfter=4)),
        P('V5 litmus: "Is the UI simpler?" (retained).', 'body_left'),
        P('V6 litmus: "Does this permanently improve the organization?" (retained).', 'body_left'),
        P('V7 litmus: "Does this make Maestro\'s understanding more accurate?" (retained).', 'body_left'),
        P('V8 litmus: "Does this make the customer say \'Maestro understands our company\'?" (retained).', 'body_left'),
        P('Computational litmus: "Does this make Maestro a computational model?" (retained).', 'body_left'),
        P('<b>Final litmus: "Does this make the customer say \'Maestro IS how we think\'?"</b>', 'body_left'),
        P('The bar has risen with every constitution. The final bar: the customer experiences Maestro '
          'not as a tool they use, not as a model they query, not as an intelligence they observe — '
          'but as the thinking substrate of their organization. If the customer can distinguish '
          '"Maestro\'s thinking" from "our thinking," the litmus test fails. Maestro should be '
          'indistinguishable from the organization\'s own intelligence. That is the destination.', 'body_left'),
    ], bg=colors.HexColor('#171717'), border=ACCENT, accent=ACCENT))

    # ── THE END ──────────────────────────────────────────────────────────
    story.append(P('The End', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>"MAESTRO IS HOW WE THINK"</b></font>',
                  ParagraphStyle('end_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=8)),
        P('Five generations of enterprise value. CRM (records) -> Knowledge (documents) -> '
          'Understanding (patterns) -> Model (equations) -> Intelligence (reasoning, imagination, '
          'decision, evolution). Each generation was more valuable than the last. Maestro is the '
          'fifth.', 'body_left'),
        P('The 19 engines remain internally. The 10 computational layers remain internally. The 10 '
          'intelligence layers remain internally. The customer experiences one thing: a living '
          'intelligence that thinks alongside their organization. They ask "why?" and Maestro reasons. '
          'They ask "what if?" and Maestro imagines. They ask "what should we do?" and Maestro '
          'decides. They act and Maestro learns. They change and Maestro evolves. The intelligence '
          'compounds until it is indistinguishable from the organization\'s own judgment.', 'body_left'),
        P('<b>The constitutional sentence (final, irrevocable):</b> "Maestro exists to become the '
          'organizational intelligence of an institution — a living system that continuously observes '
          'reality, models the organization as a dynamic system, reasons about competing explanations, '
          'imagines counterfactual futures, decides under uncertainty, intervenes to improve outcomes, '
          'learns from every result, and evolves its own understanding alongside the organization it '
          'serves. Every signal refines the intelligence. Every decision tests it. Every outcome '
          'evolves it."', 'body_left'),
        P('<b>No more constitutions. No more versions. One intelligence. One loop. Observe, Model, '
          'Reason, Imagine, Decide, Intervene, Learn, Evolve, Repeat. Forever.</b>', 'body_left'),
        P('<b>Build order: Phase 0 (fix V6 gaps, 1.5 hours) -> Phase 1 (V8 upgrades, ~17 days) -> '
          'Phase 2 (90-day pilot) -> Phase 3 (computational layers, ~23.5 days) -> Phase 4 '
          '(intelligence layers, ~25 days). Total ~65 days + 90-day pilot. The vision is the ceiling. '
          'The execution is the stairs. Build one step at a time. Ship the pilot. Let real '
          'organizations teach the intelligence. Then evolve. Forever.</b>', 'body_left'),
    ], bg=colors.HexColor('#171717'), border=ACCENT, accent=ACCENT))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'Maestro_Organizational_Intelligence_Constitution.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
