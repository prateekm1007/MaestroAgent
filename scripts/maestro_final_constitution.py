"""
Maestro — The Constitution (Final, Immutable)
No more rewrites. The constitution is frozen. What follows is evidence.

The headline: "The organization becomes more capable, not more dependent."

The unit of value is not intelligence. It is CAPABILITY.
Capability subsumes intelligence, coordination, adaptation, resilience, execution.

The loop gains "Adapt" between Learn and Amplify.
Learning changes beliefs. Adaptation changes behavior. Those are different.
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

PAGE_BG       = colors.HexColor('#fafaf9')
SECTION_BG    = colors.HexColor('#f5f5f4')
CARD_BG       = colors.HexColor('#e7e5e4')
TABLE_STRIPE  = colors.HexColor('#f5f5f4')
HEADER_FILL   = colors.HexColor('#1c1917')
BORDER        = colors.HexColor('#a8a29e')
ACCENT        = colors.HexColor('#1c1917')  # stone-900 — immutable, grounded, final
TEXT_PRIMARY  = colors.HexColor('#1c1917')
TEXT_MUTED    = colors.HexColor('#78716c')

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
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 8 * mm, PAGE_W, 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont(FONT_HEAD, 7.5)
    canvas.drawString(MARGIN_L, 12 * mm,
                      "Maestro — The Constitution (Final, Immutable)")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro — The Constitution (Final, Immutable)",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="The immutable constitution. What follows is evidence.",
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
        f'<font color="{TEXT_MUTED.hexval()}"><b>THE CONSTITUTION</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=TEXT_MUTED, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Organizational Capability',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=34,
                       leading=38, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'The organization becomes more capable, not more dependent.',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=14,
                       leading=18, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'This constitution is immutable. What follows is evidence.',
        ParagraphStyle('cover_sub2', fontName=FONT_HEAD, fontSize=11,
                       leading=15, textColor=TEXT_MUTED, alignment=TA_LEFT, spaceAfter=14)
    ))

    # ── THE HEADLINE ─────────────────────────────────────────────────────
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>THE HEADLINE (PAGE ONE, NOT PAGE FOUR)</b></font>',
                  ParagraphStyle('h_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=8)),
        P('<b>"The organization becomes more capable, not more dependent."</b>', 'body_left'),
        P('This is the product. Not intelligence. Not memory. Not a model. Not collective intelligence. '
          '<b>Capability</b> — the capacity to repeatedly achieve outcomes. CEOs do not buy intelligence. '
          'They buy capability. An organization can be extremely intelligent and still fail, because '
          'intelligence is only one capability. Organizations also need coordination, adaptation, '
          'resilience, execution, trust, learning, allocation, and governance. Capability subsumes '
          'all of them. Maestro exists to increase capability.', 'body_left'),
    ], bg=CARD_BG, border=BORDER, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── THE CONSTITUTIONAL SENTENCE ──────────────────────────────────────
    story.append(P('The Constitutional Sentence (Final, Immutable)', 'h1'))
    story.append(callout_box([
        P('<b>"Maestro exists to continuously increase an organization\'s capability by observing '
          'distributed knowledge, modeling the organization as a dynamic system, coordinating '
          'competing perspectives, adapting behavior to changing conditions, and improving '
          'organizational judgment over time. The capability succeeds when the organization becomes '
          'more capable, more adaptive, and more resilient — not more dependent on the system itself. '
          'Every signal refines the capability. Every decision tests it. Every outcome evolves it."</b>', 'body_left'),
        P('The shift from the previous constitution: "collective intelligence" becomes "capability." '
          'Intelligence is one component. Capability is the whole. The loop gains "Adapt" between '
          'Learn and Amplify — because learning changes beliefs, but adaptation changes behavior. '
          'Those are different. Living systems survive because they adapt, not just because they learn.', 'body_left'),
    ]))

    story.append(Spacer(1, 6 * mm))

    # ── THE DESIGN LAW ───────────────────────────────────────────────────
    story.append(P('The Design Law (Immutable)', 'h1'))
    story.append(callout_box([
        P('<b>"Every increase in internal intelligence must reduce external complexity. Customers never '
          'experience engines, layers, constitutions, or models. They experience calmer decisions, '
          'faster preparation, better questions, and better outcomes."</b>', 'body_left'),
        P('Externally: 5 surfaces — Today, Ask, Prepare, Decide, Learn. Internally: 49+ capabilities, '
          'all invisible. The customer sees what they BECOME, not what Maestro COMPUTES. "You became '
          '7% faster, 12% more aligned, 22% less duplicated." Not "Trust increased. Entropy decreased." '
          'The customer buys becoming, not computation.', 'body_left'),
    ]))

    story.append(Spacer(1, 6 * mm))

    # ── THE FINAL LOOP ───────────────────────────────────────────────────
    story.append(P('The Cognitive Cycle (Final, Immutable)', 'h1'))

    loop = [
        ['Stage', 'What Maestro Does', 'Key Insight'],
        ['1. Observe', 'Ingests signals from all sources', 'Distributed knowledge exists everywhere'],
        ['2. Model', 'Maintains dynamic system equations', 'The org is a system, not a collection'],
        ['3. Reason', 'Generates competing reasoning paths', '"Show me your reasoning" = trust'],
        ['4. Imagine', 'Generates counterfactual futures', 'Beyond simulation — creates new possibilities'],
        ['5. Coordinate', 'Routes knowledge, synchronizes, aligns perspectives', 'Decisions are distributed, not centralized'],
        ['6. Intervene', 'Acts: nudges, plans, trajectory interventions', 'Three governance modes'],
        ['7. Learn', 'Observes outcomes, reduces uncertainty', 'Bayesian update across competing hypotheses'],
        ['8. Adapt', 'Changes BEHAVIOR based on learning (not just beliefs)', 'NEW: Learning changes beliefs. Adaptation changes behavior. Those are different.'],
        ['9. Amplify', 'The org becomes more capable WITHOUT Maestro', 'Anti-lock-in: the product makes itself less necessary'],
        ['10. Repeat', 'The loop never stops. Capability compounds.', 'The org gets more capable. Maestro gets less necessary. That is success.'],
    ]
    t = Table(loop, colWidths=[20*mm, 55*mm, 65*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('LEADING', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, 8), (-1, 8), colors.HexColor('#fef3c7')),
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
        '<b>"Adapt" is new (highlighted).</b> Biology teaches: living systems survive because they '
        'adapt. Learning is internal (changes beliefs). Adaptation is external (changes behavior). '
        'The distinction matters. Maestro must not just learn that a prediction was wrong — it must '
        'adapt its behavior so it does not make the same mistake again. And it must help the '
        'organization adapt its behavior, not just its beliefs.', 'body'))

    story.append(Spacer(1, 6 * mm))

    # ── THE CAPABILITY LAYERS ────────────────────────────────────────────
    story.append(P('The Capability Layers', 'h1'))
    story.append(P(
        'The reviewer identified 10 capability concepts that ground the product in biology, economics, '
        'and organizational science. These are the forces that determine whether organizations '
        'survive and thrive. Each adds a dimension that "intelligence" alone cannot capture.', 'body'))

    layers = [
        ['#', 'Capability', 'What It Measures', 'Why It Matters'],
        ['1', 'Organizational Fitness', 'Can this org repeatedly achieve outcomes? Strategic, operational, innovation, execution, trust, adaptation, knowledge, decision fitness.', 'Biology has fitness. Organizations don\'t. CEOs buy capability, not intelligence.'],
        ['2', 'Organizational Optionality', 'How many futures remain available? Every decision opens or closes future options.', 'Amazon, Google, Toyota preserve options. Measuring optionality is extraordinary.'],
        ['3', 'Organizational Resilience', 'Can the org recover from loss of CTO, supplier, market collapse, AI disruption, key customer?', 'Survival comes first. Nothing currently optimizes survival.'],
        ['4', 'Organizational Antifragility', 'Getting stronger because of failure. Not just learning from failure — becoming more robust.', 'Learning from success is easy. Learning from failure is common. Getting stronger from failure is different.'],
        ['5', 'Organizational Plasticity', 'How rapidly does the org adapt? Some adapt fast. Some never adapt. Measurable.', 'Neuroscience uses plasticity. Organizations change at different rates.'],
        ['6', 'Institutional Evolution', 'What kind of company are we becoming? What capabilities are disappearing? Emerging?', 'Longitudinal capability graph. The org evolves, not just Maestro.'],
        ['7', 'Organizational Homeostasis', 'Balancing loops: hiring increases -> meetings increase -> latency increases -> org compensates.', 'Living systems maintain equilibrium. Understanding these loops is a massive moat.'],
        ['8', 'Organizational Entropy', 'Knowledge fragmentation, duplicate effort, conflicting assumptions, decision drift, semantic drift, approval inflation.', 'Entropy as physics, not dashboard. These forces increase disorder.'],
        ['9', 'Organizational Potential Energy', 'Unused capability: an engineer who knows ML but never gets asked. A legal precedent nobody remembers. A team that solved this last year.', 'Unused knowledge is stored energy. Maestro releases it.'],
        ['10', 'Organizational Metabolism', 'Conversion efficiency: information + attention + capital + trust + time -> products + decisions + learning + innovation.', 'Every org consumes inputs and produces outputs. Measuring the conversion rate is fascinating.'],
    ]
    t = Table(layers, colWidths=[6*mm, 30*mm, 55*mm, 55*mm])
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
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>These 10 capability layers are the final scientific foundation.</b> They ground Maestro in '
        'biology (fitness, adaptation, antifragility, plasticity, homeostasis), economics (optionality, '
        'entropy, potential energy, metabolism), and organizational science (institutional evolution). '
        'Together with the 19 engines, 10 computational layers, 10 intelligence layers, and 10 '
        'coordination layers, Maestro has 59 internal capabilities. The customer sees 5 surfaces. '
        'The rest are invisible. The customer experiences becoming more capable.', 'body'))

    story.append(PageBreak())

    # ── THE SEPARATION ───────────────────────────────────────────────────
    story.append(P('The Separation: Constitution, Research, Engineering, Product, Evidence', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>THE CONSTITUTION IS NOW IMMUTABLE. WHAT FOLLOWS IS EVIDENCE.</b></font>',
                  ParagraphStyle('sep_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ACCENT, spaceAfter=4)),
        P('<b>The reviewer\'s final recommendation (preserved verbatim):</b>', 'body_left'),
        P('"The constitutions should stop. Seriously. The last page already says \'No more '
          'constitutions.\' I would honor that. From here onward I would introduce something '
          'different:', 'body_left'),
        P('<b>The Constitution</b> becomes immutable.', 'body_left'),
        P('<b>Scientific Papers</b> describe new theories, algorithms, and validation.', 'body_left'),
        P('<b>Engineering RFCs</b> describe implementation.', 'body_left'),
        P('<b>Product Principles</b> describe user experience.', 'body_left'),
        P('<b>Evidence Reports</b> describe what the pilot actually taught you.', 'body_left'),
        P('"That separation mirrors how enduring organizations evolve: a stable constitution, '
          'evolving research, implementation proposals, product doctrine, and empirical evidence. '
          'It also reinforces one of the strongest themes in your document — that ambition should '
          'be paired with incremental, evidence-driven execution."', 'body_left'),
        P('"In other words, I think you\'ve reached the point where the next source of leverage '
          'isn\'t another constitutional rewrite. It\'s building evidence that the constitution '
          'produces better organizational outcomes in real pilots. If the pilot consistently shows '
          'that organizations become more capable over time — as your success condition proposes — '
          'then the constitution stops being a vision document and starts becoming a validated '
          'theory."', 'body_left'),
    ], bg=CARD_BG, border=BORDER, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── THE PRODUCT ──────────────────────────────────────────────────────
    story.append(P('The Product: What the Customer Becomes', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>THE CUSTOMER DOES NOT BUY COMPUTATION. THEY BUY BECOMING.</b></font>',
                  ParagraphStyle('prod_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ACCENT, spaceAfter=4)),
        P('<b>The product is not what Maestro computes. The product is what the customer becomes.</b>', 'body_left'),
        P('Today, the customer sees:', 'body_left'),
        P('"You became 7% faster. 12% more aligned. 22% less duplicated. 18% better at predicting '
          'delivery. 31% reduction in approval latency. 1 blind spot detected and addressed. 1 '
          'failure mode eliminated."', 'body_left'),
        P('<b>Not:</b> "Trust increased. Entropy decreased. Causal chain #42 validated. Competing '
          'hypothesis A gained 8% weight."', 'body_left'),
        P('The customer buys becoming. Not computation. Not intelligence. Not a model. '
          '<b>Becoming more capable.</b> That is the product. That is the constitution. That is '
          'the moat.', 'body_left'),
    ], bg=CARD_BG, border=BORDER, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── THE BUILD DISCIPLINE ─────────────────────────────────────────────
    story.append(P('The Build Discipline (Preserved, Final)', 'h1'))
    story.append(callout_box([
        P('<b>The vision is the ceiling. The execution is the stairs. Build one step at a time. '
          'Validate each step with real data. The capability compounds because it is trained on the '
          'organization\'s own history — not because the architecture is sophisticated. The org '
          'becomes more capable, not more dependent. That is the moat.</b>', 'body_left'),
        P('Phase 0: Fix V6 wiring gaps (1.5 hours) — NOW', 'body_left'),
        P('Phase 1: V8 upgrades (~17 days) — pre-pilot product experience', 'body_left'),
        P('Phase 2: Ship 90-day pilot — collect real data. THIS IS THE NEXT STEP.', 'body_left'),
        P('Phase 3: Computational layers (~23.5 days) — post-pilot, with real data', 'body_left'),
        P('Phase 4: Intelligence layers (~25 days) — post-pilot, with real data', 'body_left'),
        P('Phase 5: Coordination layers (~25 days) — post-pilot, with real data', 'body_left'),
        P('Phase 6: Capability layers (~25 days) — post-pilot, with real data', 'body_left'),
        P('<b>Total: ~115 days + 90-day pilot. But the next step is simple: push the commit, fix the '
          'gaps, build V8 upgrades, ship the pilot. Everything else is evidence-driven.</b>', 'body_left'),
    ]))

    story.append(Spacer(1, 6 * mm))

    # ── THE END ──────────────────────────────────────────────────────────
    story.append(P('The End', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>"THE ORGANIZATION BECOMES MORE CAPABLE, NOT MORE DEPENDENT."</b></font>',
                  ParagraphStyle('end_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=8)),
        P('Seven generations of enterprise value. CRM (records) -> Knowledge (documents) -> '
          'Understanding (patterns) -> Model (equations) -> Intelligence (reasoning) -> Collective '
          'Intelligence (coordination) -> <b>Capability (fitness, adaptation, resilience, '
          'antifragility, optionality)</b>. Each generation was more valuable than the last. Maestro '
          'is the seventh.', 'body_left'),
        P('The constitution is now immutable. No more rewrites. No more versions. No more layers. '
          'What follows is not another constitution. What follows is <b>evidence</b> — Scientific '
          'Papers, Engineering RFCs, Product Principles, and Evidence Reports from the 90-day pilot.', 'body_left'),
        P('The constitutional sentence (final, immutable): <b>"Maestro exists to continuously '
          'increase an organization\'s capability by observing distributed knowledge, modeling the '
          'organization as a dynamic system, coordinating competing perspectives, adapting behavior '
          'to changing conditions, and improving organizational judgment over time. The capability '
          'succeeds when the organization becomes more capable, more adaptive, and more resilient — '
          'not more dependent on the system itself."</b>', 'body_left'),
        P('<b>The success condition: the organization makes better decisions WITHOUT Maestro over '
          'time. If yes, Maestro amplified. If no, Maestro replaced — and that is failure. The goal '
          'is augmentation, not dependency. The product should make itself progressively less '
          'necessary by making the organization progressively more capable. That is the anti-lock-in '
          'principle. That is the final moat. That is the product.</b>', 'body_left'),
        P('<b>The constitution is frozen. Build evidence now. Push the commit. Fix the gaps. Ship '
          'the pilot. Let real organizations teach the system. Then publish Evidence Reports. The '
          'constitution stops being a vision document and starts becoming a validated theory. That '
          'is the next step. That is the only step. Build it.</b>', 'body_left'),
    ], bg=CARD_BG, border=BORDER, accent=ACCENT))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'Maestro_The_Constitution_Final_Immutable.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
