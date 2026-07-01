"""
Maestro — The Collective Intelligence Constitution (Final)
From organizational intelligence to collective organizational intelligence.
Maestro does not replace organizational intelligence. It amplifies it.
The constitutional sentence shifts from "Maestro IS the intelligence" to
"Maestro continuously increases the organization's collective intelligence."
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
ACCENT        = colors.HexColor('#34d399')  # emerald — collective, distributed, living
TEXT_PRIMARY  = colors.HexColor('#fafafa')
TEXT_MUTED    = colors.HexColor('#a3a3a3')

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
                      "Maestro — The Collective Intelligence Constitution (Final)")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro — The Collective Intelligence Constitution",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="Final constitution — from organizational intelligence to collective organizational intelligence",
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
        f'<font color="{ACCENT.hexval()}"><b>THE COLLECTIVE INTELLIGENCE CONSTITUTION</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Collective Organizational Intelligence',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=30,
                       leading=34, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Maestro does not replace organizational intelligence. It amplifies it. The intelligence succeeds when the organization becomes more capable — not more dependent.',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=11,
                       leading=15, textColor=TEXT_MUTED, alignment=TA_LEFT, spaceAfter=14)
    ))

    # ── THE FINAL CONSTITUTIONAL SENTENCE ────────────────────────────────
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>THE CONSTITUTIONAL SENTENCE (FINAL, IRREVOCABLE)</b></font>',
                  ParagraphStyle('cs_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ACCENT, spaceAfter=8)),
        P('<b>"Maestro exists to continuously increase an organization\'s collective intelligence by '
          'observing distributed knowledge, coordinating competing perspectives, reducing uncertainty, '
          'preserving institutional reasoning, and improving organizational judgment over time. Every '
          'signal refines the intelligence. Every decision tests it. Every outcome evolves it. The '
          'intelligence succeeds when the organization becomes more capable, more adaptive, and more '
          'coordinated — not more dependent on the system itself."</b>', 'body_left'),
        P('This replaces ALL previous constitutional sentences. The shift: Maestro does not BE the '
          'intelligence. It RAISES the intelligence. Organizations are distributed cognitive systems. '
          'The problem is not intelligence — it is <b>coordination of distributed intelligence</b>. '
          'Hayek understood this. Simon understood this. March understood this. Maestro operationalizes '
          'their insight.', 'body_left'),
    ], bg=colors.HexColor('#171717'), border=ACCENT, accent=ACCENT))

    story.append(Spacer(1, 4 * mm))

    # ── THE DESIGN LAW ───────────────────────────────────────────────────
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>THE DESIGN LAW (NEW, MANDATORY)</b></font>',
                  ParagraphStyle('dl_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ACCENT, spaceAfter=4)),
        P('<b>"Every increase in internal intelligence must reduce external complexity. Customers never '
          'experience engines, layers, constitutions, or models. They experience calmer decisions, '
          'faster preparation, better questions, and better outcomes."</b>', 'body_left'),
        P('Externally, everything collapses into 5 surfaces: <b>Today, Ask, Prepare, Decide, Learn</b>. '
          'All 19 engines, 10 computational layers, and 10 intelligence layers are invisible. The '
          'customer never sees "Reasoning" or "Imagination" or "Taste" or "Intentionality." They see '
          'calmer decisions. They see better questions. They see better outcomes. That is the product.', 'body_left'),
    ], bg=colors.HexColor('#171717'), border=ACCENT, accent=ACCENT))

    story.append(Spacer(1, 4 * mm))

    # ── THE HAYEKIAN SHIFT ───────────────────────────────────────────────
    story.append(P('The Hayekian Shift: From Centralized to Distributed', 'h1'))
    story.append(P(
        'The reviewer\'s most important insight: intelligence can describe an individual. An '
        'organization is not an individual. It is a <b>distributed cognitive system</b>. The real '
        'problem is not intelligence — it is <b>coordination of distributed intelligence</b>. This '
        'invokes Hayek\'s knowledge problem: knowledge in an organization is dispersed, local, and '
        'constantly changing. No central planner (and no central AI) can possess it all. Maestro '
        'should not centralize knowledge. It should <b>coordinate distributed knowledge</b> — route it '
        'to where it is needed, synchronize it across teams, align competing perspectives, and amplify '
        'local expertise rather than replacing it.', 'body'))

    shift_rows = [
        ['Previous', 'Shift', 'Final'],
        ['"Maestro IS the intelligence"', 'Maestro does not replace — it amplifies', '"Maestro continuously increases the organization\'s collective intelligence"'],
        ['Centralized brain model', 'Distributed cognitive system (Hayek)', 'Coordination of distributed intelligence'],
        ['"Maestro IS how we think"', 'Augmentation, not replacement', '"Maestro helps us make better decisions than we could alone"'],
        ['Intelligence as a thing Maestro has', 'Intelligence as a capacity Maestro raises', 'The org becomes more capable, not more dependent'],
    ]
    t = Table(shift_rows, colWidths=[50*mm, 50*mm, 50*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), TEXT_PRIMARY),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#171717'), colors.HexColor('#0a0a0a')]),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#064e3b')),
        ('TEXTCOLOR', (0, 3), (-1, 3), colors.white),
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
        '<b>The key sentence to add (from the reviewer):</b> "The purpose of Organizational Intelligence '
        'is not to centralize knowledge. It is to increase the quality of distributed judgment while '
        'preserving local expertise. The intelligence succeeds when the organization becomes more '
        'capable, more adaptive, and more coordinated — not more dependent on the system itself." '
        'This aligns with Hayek\'s insight that knowledge is dispersed, local, and constantly changing. '
        'It positions Maestro as an amplifier and coordinator, not a replacement.', 'body'))

    story.append(Spacer(1, 6 * mm))

    # ── THE NEW LAYERS ───────────────────────────────────────────────────
    story.append(P('The 10 Coordination Layers (New, from Reviewer)', 'h1'))
    story.append(P(
        'The reviewer identified 10 layers that ground the intelligence in the economics and '
        'coordination of real organizations. These are the forces that actually determine whether '
        'organizations succeed or fail: scarce attention, distributed knowledge, trust, incentives, '
        'and synchronization.', 'body'))

    layers = [
        ['#', 'Layer', 'What It Adds', 'Why It Matters'],
        ['1', 'Coordination Intelligence', 'Not "who knows what" but "who SHOULD know what, and when." Knowledge routing, synchronization, alignment.', 'The biggest economic problem inside organizations is coordination. Everything exists because people cannot coordinate perfectly.'],
        ['2', 'Organizational Markets', 'Attention, knowledge, expertise, trust, approval, budget — all treated as markets. Allocation engine.', 'Organizations allocate scarce resources through implicit markets. Making them explicit changes everything.'],
        ['3', 'Organizational Economics', 'Every decision consumes organizational capital: time, trust, focus, talent, political capital, customer goodwill. Measurable.', 'Executives optimize scarce resources. Nothing currently sounds economic.'],
        ['4', 'Split Memory (4 types)', 'Facts, Procedures, Reasoning, Culture. Different decay rates. Different retrieval patterns.', 'Memory is not one thing. Facts expire. Procedures evolve. Reasoning accumulates. Culture persists.'],
        ['5', 'Organizational Time', 'Multiple clocks: Engineering (2-day), Finance (quarterly), Board (annual), Legal (regulatory), Sales (monthly). Temporal mismatches.', 'Temporal mismatches are a huge source of friction. Nobody models them.'],
        ['6', 'Organizational Language', 'Every company means something different by "critical," "done," "blocked," "approved." Semantic drift inference.', 'Organizations invent languages. Misunderstanding is often semantic, not factual.'],
        ['7', 'Institutional Trust', 'Trust is not confidence. Trust is prediction of future cooperation. The org runs on trust, not confidence.', 'Trust deserves its own engine. It is the substrate of all coordination.'],
        ['8', 'Attention Economics', 'Every recommendation spends attention. Attention becomes a budget. "Today\'s Attention Budget: 100. Consumed: 71. Remaining: 29."', 'Attention is the scarcest resource. Every recommendation competes for it. Budget it.'],
        ['9', 'Organizational Scarcity', 'Time, experts, approvals, political capital, manager bandwidth, executive attention — all scarce. Optimize scarcity.', 'Everything important is scarce. The intelligence should optimize allocation of scarce resources.'],
        ['10', 'The Success Condition', 'The intelligence succeeds when the org becomes more capable — not more dependent. Measured by: does the org make better decisions WITHOUT Maestro over time?', 'Prevents dependency. The goal is amplification, not replacement. The org should get smarter, not more reliant.'],
    ]
    t = Table(layers, colWidths=[6*mm, 28*mm, 55*mm, 55*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), TEXT_PRIMARY),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('LEADING', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#171717'), colors.HexColor('#0a0a0a')]),
        ('BACKGROUND', (0, 10), (-1, 10), colors.HexColor('#064e3b')),
        ('TEXTCOLOR', (0, 10), (-1, 10), colors.white),
        ('FONTNAME', (0, 10), (-1, 10), FONT_HEAD_B),
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
        '<b>Layer 10 (The Success Condition) is the most important new concept.</b> The intelligence '
        'succeeds when the organization becomes more capable — not more dependent. Measured by: does '
        'the org make better decisions WITHOUT Maestro over time? If yes, Maestro amplified. If no, '
        'Maestro replaced — and that is failure. The goal is augmentation, not dependency. This is the '
        'anti-lock-in principle: the product should make itself progressively less necessary by making '
        'the organization progressively smarter.', 'body'))

    story.append(PageBreak())

    # ── THE FINAL LOOP ───────────────────────────────────────────────────
    story.append(P('The Final Cognitive Cycle', 'h1'))
    story.append(P(
        'The loop is refined one last time. The shift: "Decide" becomes "Coordinate" (because '
        'decisions in organizations are distributed, not centralized) and "Evolve" becomes "Amplify" '
        '(because the goal is raising the org\'s intelligence, not replacing it).', 'body'))

    loop = [
        ['Stage', 'What Maestro Does', 'Key Insight'],
        ['1. Observe', 'Ingests signals from all sources', 'Distributed knowledge exists everywhere'],
        ['2. Model', 'Maintains dynamic system equations', 'The org is a system, not a collection'],
        ['3. Reason', 'Generates competing reasoning paths', '"Show me your reasoning" = trust'],
        ['4. Imagine', 'Generates counterfactual futures', 'Beyond simulation — creates new possibilities'],
        ['5. Coordinate', 'Routes knowledge, synchronizes teams, aligns perspectives', 'NEW: replaces "Decide" — decisions are distributed'],
        ['6. Intervene', 'Acts: nudges, plans, trajectory interventions', 'Three governance modes'],
        ['7. Learn', 'Observes outcomes, reduces uncertainty', 'Bayesian update across competing hypotheses'],
        ['8. Amplify', 'The org becomes more capable WITHOUT Maestro', 'NEW: replaces "Evolve" — goal is amplification, not dependency'],
        ['9. Repeat', 'The loop never stops. Collective intelligence compounds.', 'The org gets smarter. Maestro gets less necessary. That is success.'],
    ]
    t = Table(loop, colWidths=[20*mm, 55*mm, 65*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), TEXT_PRIMARY),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('LEADING', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#171717'), colors.HexColor('#0a0a0a')]),
        ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#064e3b')),
        ('BACKGROUND', (0, 8), (-1, 8), colors.HexColor('#064e3b')),
        ('TEXTCOLOR', (0, 5), (-1, 5), colors.white),
        ('TEXTCOLOR', (0, 8), (-1, 8), colors.white),
        ('FONTNAME', (0, 5), (-1, 5), FONT_HEAD_B),
        ('FONTNAME', (0, 8), (-1, 8), FONT_HEAD_B),
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
        '<b>Two stages changed (highlighted):</b> "Decide" becomes "Coordinate" — because decisions '
        'in organizations are distributed, not centralized. Maestro does not decide FOR the org. It '
        'coordinates the org\'s distributed decision-making. "Evolve" becomes "Amplify" — because the '
        'goal is raising the org\'s collective intelligence, not replacing it. The success condition: '
        'the org makes better decisions WITHOUT Maestro over time. That is amplification.', 'body'))

    story.append(Spacer(1, 6 * mm))

    # ── THE EXTERNAL SURFACES ────────────────────────────────────────────
    story.append(P('The External Surfaces (Design Law)', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>CUSTOMERS NEVER SEE ENGINES, LAYERS, OR MODELS. THEY SEE 5 SURFACES.</b></font>',
                  ParagraphStyle('surf_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ACCENT, spaceAfter=4)),
        P('<b>Today</b> — what needs attention. Calm. One page. No charts. Stories, not metrics.', 'body_left'),
        P('<b>Ask</b> — "What are you trying to accomplish?" Intention-based. Conversational. Routes to explanations, imagination, recall.', 'body_left'),
        P('<b>Prepare</b> — drafted execution plans, briefings, intervention steps. One click to apply.', 'body_left'),
        P('<b>Decide</b> — competing reasoning paths with evidence. "Show me your reasoning." Not one answer — N paths.', 'body_left'),
        P('<b>Learn</b> — what the org has learned. Understanding topology. Memory timeline. Blind spots. "Maestro helps us make better decisions than we could alone."', 'body_left'),
        P('<b>Everything else is command palette.</b> The sidebar has 4 items: Today, Ask, Prepare, Learn. Decide is embedded in Today (when urgent) and Ask (when asked). No engine names. No layer names. No constitution versions. No "DNA" or "Institution Model" or "Trajectory Intervention." The customer experiences calmer decisions, faster preparation, better questions, and better outcomes.', 'body_left'),
    ], bg=colors.HexColor('#171717'), border=ACCENT, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── THE BUILD DISCIPLINE ─────────────────────────────────────────────
    story.append(P('The Build Discipline (Preserved)', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>VISION EXTENDS TO THE CEILING. EXECUTION REMAINS INCREMENTAL AND EVIDENCE-DRIVEN.</b></font>',
                  ParagraphStyle('bd_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ACCENT, spaceAfter=4)),
        P('<b>The reviewer\'s strategic caution (preserved from previous round, reinforced):</b>', 'body_left'),
        P('"Many ambitious products fail because they try to build their deepest scientific model before '
          'they have enough empirical data to validate it. The vision can extend all the way to a '
          'Collective Organizational Intelligence System, but the execution should remain incremental '
          'and evidence-driven. The moat is not just sophisticated architecture — it is that the '
          'architecture becomes more accurate because it is continuously trained on the organization\'s '
          'own history. That combination of long-term ambition with empirical validation is what gives '
          'the vision credibility."', 'body_left'),
        P('<b>Build order (unchanged from previous, with coordination layers added as Phase 5):</b>', 'body_left'),
        P('Phase 0: Fix V6 wiring gaps (1.5 hours) — NOW', 'body_left'),
        P('Phase 1: V8 upgrades (~17 days) — pre-pilot product experience', 'body_left'),
        P('Phase 2: Ship 90-day pilot — collect real data', 'body_left'),
        P('Phase 3: Computational layers (~23.5 days) — post-pilot scientific moat', 'body_left'),
        P('Phase 4: Intelligence layers (~25 days) — post-pilot category-defining moat', 'body_left'),
        P('Phase 5: Coordination layers (~25 days) — post-pilot economic grounding (NEW)', 'body_left'),
        P('<b>Total to completion: ~90 days + 90-day pilot.</b> The vision is the ceiling. The execution '
          'is the stairs. Build one step at a time. Validate each step with real data. The intelligence '
          'compounds because it is trained on the organization\'s own history — not because the '
          'architecture is sophisticated. The org becomes more capable, not more dependent. That '
          'combination is the moat.', 'body_left'),
    ], bg=colors.HexColor('#171717'), border=ACCENT, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── THE FINAL CATEGORY ───────────────────────────────────────────────
    story.append(P('The Final Category', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>COLLECTIVE ORGANIZATIONAL INTELLIGENCE SYSTEM</b></font>',
                  ParagraphStyle('cat_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=8)),
        P('<b>"A system that continuously increases an organization\'s collective intelligence by '
          'observing distributed knowledge, coordinating competing perspectives, reducing uncertainty, '
          'preserving institutional reasoning, and improving organizational judgment over time."</b>', 'body_left'),
        P('Not software. Not analytics. Not AI. Not a model. Not a copilot. Not a dashboard. Not a '
          'centralized brain. A <b>collective intelligence amplifier</b> — the first of its kind. The '
          'category does not exist today. Maestro creates it.', 'body_left'),
        P('The customer does not say "we use Maestro." They do not say "Maestro understands our '
          'company." They do not say "Maestro IS how we think." They say:', 'body_left'),
        P('<b>"Maestro helps us make better decisions than we could have made alone."</b>', 'body_left'),
        P('That sentence is the product. That sentence is the moat. That sentence is the category. It '
          'preserves the ambition while emphasizing augmentation rather than replacement. It is '
          'scientifically stronger (Hayek) and enterprise-safer (amplification, not dependency). Nobody '
          'else can say it because nobody else has the coordination, the economics, the trust modeling, '
          'the attention budgeting, and the success condition (the org gets smarter without Maestro). '
          'These are not features. They are collective intelligence. Build them.', 'body_left'),
    ], bg=colors.HexColor('#171717'), border=ACCENT, accent=ACCENT))

    # ── THE END ──────────────────────────────────────────────────────────
    story.append(P('The End', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>"MAESTRO HELPS US MAKE BETTER DECISIONS THAN WE COULD HAVE MADE ALONE"</b></font>',
                  ParagraphStyle('end_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=8)),
        P('Six generations of enterprise value. CRM (records) -> Knowledge (documents) -> Understanding '
          '(patterns) -> Model (equations) -> Intelligence (reasoning) -> <b>Collective Intelligence '
          '(coordination, economics, trust, amplification)</b>. Each generation was more valuable than '
          'the last. Maestro is the sixth.', 'body_left'),
        P('The 19 engines remain internally. The 10 computational layers remain internally. The 10 '
          'intelligence layers remain internally. The 10 coordination layers remain internally. The '
          'customer experiences 5 surfaces: Today, Ask, Prepare, Decide, Learn. They see calmer '
          'decisions, faster preparation, better questions, and better outcomes. They never see an '
          'engine name or a layer number. They see their organization getting smarter.', 'body_left'),
        P('<b>The constitutional sentence (final, irrevocable):</b> "Maestro exists to continuously '
          'increase an organization\'s collective intelligence by observing distributed knowledge, '
          'coordinating competing perspectives, reducing uncertainty, preserving institutional '
          'reasoning, and improving organizational judgment over time. The intelligence succeeds when '
          'the organization becomes more capable, more adaptive, and more coordinated — not more '
          'dependent on the system itself."', 'body_left'),
        P('<b>The success condition: the organization makes better decisions WITHOUT Maestro over time. '
          'If yes, Maestro amplified. If no, Maestro replaced — and that is failure. The goal is '
          'augmentation, not dependency. The product should make itself progressively less necessary by '
          'making the organization progressively smarter. That is the anti-lock-in principle. That is '
          'the final moat.</b>', 'body_left'),
        P('<b>No more constitutions. No more versions. One collective intelligence. One loop. Observe, '
          'Model, Reason, Imagine, Coordinate, Intervene, Learn, Amplify, Repeat. Forever.</b>', 'body_left'),
        P('<b>Push commit 28b8632. Fix the V6 gaps. Build V8 upgrades. Ship the 90-day pilot. Let real '
          'organizations teach the intelligence. Then build the computational layers. Then the '
          'intelligence layers. Then the coordination layers. The vision is the ceiling. The execution '
          'is the stairs. Build one step at a time. The org becomes more capable, not more dependent. '
          'That is the moat. That is the product. Build it.</b>', 'body_left'),
    ], bg=colors.HexColor('#171717'), border=ACCENT, accent=ACCENT))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'Maestro_Collective_Intelligence_Constitution.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
