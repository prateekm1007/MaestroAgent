"""
Maestro — The Permanent Constitution
No more versions. One continuously evolving cognitive cycle.
The unit of value is not memory. It is understanding, expressed as explanations.
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
SECTION_BG    = colors.HexColor('#f8fafc')
CARD_BG       = colors.HexColor('#f1f5f9')
TABLE_STRIPE  = colors.HexColor('#f8fafc')
HEADER_FILL   = colors.HexColor('#0f172a')
BORDER        = colors.HexColor('#cbd5e1')
ACCENT        = colors.HexColor('#0f172a')  # slate-900 — final, no more color changes
TEXT_PRIMARY  = colors.HexColor('#1a1c1e')
TEXT_MUTED    = colors.HexColor('#6b7178')

ST_DELIVERED  = colors.HexColor('#15803d')
ST_PARTIAL    = colors.HexColor('#b45309')
ST_FAILED     = colors.HexColor('#b91c1c')
ST_FINAL      = colors.HexColor('#0f172a')

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
                      "Maestro — The Permanent Constitution")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro — The Permanent Constitution",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="The final constitution — no more versions. One continuously evolving cognitive cycle.",
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

def spec_block(num, name, principle, gap, build, acceptance, effort, deps):
    flowables = []
    header = Table([[
        Paragraph(f'<font color="white"><b>#{num}</b></font>',
                  ParagraphStyle('sh', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=colors.white, alignment=TA_CENTER)),
        Paragraph(f'<font color="white"><b>{name}</b></font>',
                  ParagraphStyle('st', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=colors.white, alignment=TA_LEFT))
    ]], colWidths=[18*mm, PAGE_W - MARGIN_L - MARGIN_R - 18*mm - 24])
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ST_FINAL),
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

    flowables += field('Principle', principle)
    flowables += field('Codebase gap', gap)
    flowables += field('Build', build)
    flowables += [Paragraph(f'<font color="{TEXT_MUTED.hexval()}"><b>Acceptance test</b></font>', S['label']),
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
        f'<font color="{ACCENT.hexval()}"><b>THE PERMANENT CONSTITUTION</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Organizational Understanding',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=34,
                       leading=38, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'No more versions. One continuously evolving cognitive cycle. The unit of value is explanations, not memories.',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=12,
                       leading=16, textColor=HEADER_FILL, alignment=TA_LEFT, spaceAfter=14)
    ))

    # ── THE CONSTITUTIONAL SENTENCE ──────────────────────────────────────
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>THE CONSTITUTIONAL SENTENCE</b></font>',
                  ParagraphStyle('cs_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=8)),
        P('<b>"Maestro exists to become the most accurate, continuously improving explanation of how an '
          'organization works. Every signal deepens understanding. Every decision tests understanding. '
          'Every outcome revises understanding. Every revision improves future judgment."</b>', 'body_left'),
        P('This replaces all previous constitutional laws. Not memory. Not adaptation. Not invisible '
          'intelligence. <b>Understanding</b> — expressed as <b>explanations</b>. Memories tell you what '
          'happened. Explanations tell you why it happened, what changed because of it, and what should '
          'happen next. That is what executives buy.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── THE PERMANENT LOOP ───────────────────────────────────────────────
    story.append(P('The Permanent Cognitive Cycle', 'h1'))
    story.append(P(
        'No more V8, V9, V10. One loop. Everything built belongs somewhere inside it. Every future '
        'feature, engine, or capability maps to one of these 9 stages. If it does not fit, it does not '
        'belong in Maestro.', 'body'))

    loop = [
        ['Stage', 'What Maestro Does', 'Existing Engines (V3-V6)'],
        ['1. Observe', 'Ingests signals from GitHub, Jira, Slack, Gmail, Confluence, CRM', 'signal.py, ingestion.py, historical_engine.py'],
        ['2. Understand', 'Builds causal models, detects patterns, infers norms, tracks identity', 'causal.py, pattern.py, consciousness.py, identity.py, wisdom.py'],
        ['3. Question', 'Identifies gaps, anomalies, blind spots. Asks the organization directly', 'curiosity.py, contradiction.py, skepticism.py'],
        ['4. Predict', 'Makes predictions about organizational outcomes', 'prediction_lifecycle.py, prediction_market.py, simulation.py'],
        ['5. Explain', 'Synthesizes explanations: why something happens, not just what', 'sowhat.py, narrative.py (TO BE UPGRADED)'],
        ['6. Prepare', 'Drafts execution plans, briefing memos, intervention steps', 'executive_function.py, preparation.py, adaptive_nudge.py'],
        ['7. Revise', 'Updates understanding when predictions miss. Bayesian competing hypotheses', 'learning.py, confidence.py (TO BE UPGRADED)'],
        ['8. Teach', 'Shares understanding with the organization via calm surfaces', 'today.js, learn.js, cognition.js, autobiography.js'],
        ['9. Repeat', 'The loop never stops. Understanding compounds. Irreplaceability grows.', 'background_loop.py (TO BE HOOKED INTO live_ingest)'],
    ]
    t = Table(loop, colWidths=[22*mm, 55*mm, PAGE_W - MARGIN_L - MARGIN_R - 77*mm])
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

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>19 cognitive engines already exist across these 9 stages.</b> V3-V6 built them. The Permanent '
        'Constitution does not add more engines — it upgrades the EXISTING ones to produce explanations, '
        'not just outputs. The loop is the architecture. The engines are the implementation. The '
        'explanation is the product.', 'body'))

    story.append(PageBreak())

    # ── STEP 0: FIX V6 WIRING GAPS ──────────────────────────────────────
    story.append(P('Step 0 — Fix 2 V6 Wiring Gaps (MUST DO FIRST, 1.5 hours)', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ST_FAILED.hexval()}"><b>2 GAPS FROM ROUND 24 — FIX BEFORE ANYTHING ELSE</b></font>',
                  ParagraphStyle('gap_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ST_FAILED, spaceAfter=4)),
        P('<b>Gap 1: Background loop NOT hooked into live_ingest() (30 min).</b> '
          'Fix: add <font face="Mono">BackgroundLoop.check()</font> call at end of '
          '<font face="Mono">oem_state.py live_ingest()</font>.', 'body_left'),
        P('<b>Gap 2: DNA NOT referenced in wisdom.py (1 hour).</b> '
          'Fix: modify <font face="Mono">wisdom.py</font> to import '
          '<font face="Mono">organizational_dna.py</font>, compute alignment_score per recommendation.', 'body_left'),
    ], bg=colors.HexColor('#fef3f2'), border=colors.HexColor('#fecaca'), accent=ST_FAILED))

    # ── THE 9 UPGRADES ───────────────────────────────────────────────────
    story.append(P('The 9 Upgrades (Upgrading Existing Engines to Produce Explanations)', 'h1'))
    story.append(P(
        'The Permanent Constitution does not add engines. It upgrades existing ones so that every output '
        'is an <b>explanation</b>, not just a number, a pattern, or a prediction. 9 upgrades. ~15 days.', 'body'))

    upgrades = [
        ['#', 'Upgrade', 'Stage', 'Effort', 'What Changes'],
        ['1', 'Organizational Explanations', '5. Explain', '3 days', 'sowhat.py + narrative.py upgraded to synthesize WHY, not just WHAT. Every confidence score gets an explanation graph.'],
        ['2', 'Four-Level Unknowns', '3. Question', '1.5 days', 'curiosity.py upgraded: Known / Known Unknown / Unknown Unknown / Emerging Unknown. Richer than just "we don\'t understand X."'],
        ['3', 'Conversational Curiosity', '3. Question', '2 days', 'curiosity.py upgraded: multi-turn conversation, not Q&A. Maestro asks follow-up questions based on answers.'],
        ['4', 'Bayesian Institutional Confidence', '2. Understand', '1.5 days', 'institutional_confidence.py (V8 #2, to build): living Bayesian confidence with evidence trend, uncertainty band, competing explanation %, last revised, prediction calibration.'],
        ['5', 'Causality Timeline', '5. Explain', '2 days', 'memory_timeline.py (V8 #1, to build): every moment answers "why did this permanently change us?" with a causal chain.'],
        ['6', 'Understanding Topology', '8. Teach', '2 days', 'understanding_map.py (V8 #5, to build): network graph, not bars. Connections pulse as Maestro learns. Watch understanding spread.'],
        ['7', 'Organizational Blind Spots', '3. Question', '1 day', 'NEW. "Engineering has raised deployment risk 11 times. Leadership has ignored it 11 times. Blind spot detected." Evidence exists — org ignores it.'],
        ['8', 'Institutional Gravity', '2. Understand', '2 days', 'NEW. Visualize centers of gravity (people, projects, decisions, knowledge, approvals, customers). When gravity shifts, the org changes.'],
        ['9', 'Memory Compression (Deep)', '2. Understand', '2 days', 'memory_compression.py upgraded: 10M events -> 200 principles -> 43 reflexes -> 19 institutional truths -> 7 cultural axioms. Brain-like compression.'],
        ['', '', '', '', ''],
        ['TOTAL', '9 upgrades', '5 stages', '~17 days', 'From 19 engines producing outputs to 19 engines producing explanations'],
    ]
    t = Table(upgrades, colWidths=[8*mm, 38*mm, 18*mm, 16*mm, PAGE_W - MARGIN_L - MARGIN_R - 80*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, 9), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, 11), (-1, 11), colors.HexColor('#f1f5f9')),
        ('FONTNAME', (0, 11), (-1, 11), FONT_HEAD_B),
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

    story.append(PageBreak())

    # ── UPGRADE 1: ORGANIZATIONAL EXPLANATIONS ───────────────────────────
    story.extend(spec_block(
        1, 'Organizational Explanations — the biggest moat',
        'The constitutional sentence: "Every signal deepens understanding." Understanding is not a score. It is an EXPLANATION. "Why are engineering estimates always wrong?" should produce: "We\'ve observed this for eleven months. Here is why: PRs enter review queue -> cross-team dependency -> architecture ownership -> late QA -> missed estimate." That explanation is synthesized from hundreds of observations. Nobody stores explanations. Everyone stores documents. This is a gigantic difference.',
        'sowhat.py (197 lines) produces "consequence_if_ignored" — a single sentence. narrative.py (332 lines) produces daily highlights — a list of events. Neither produces CAUSAL EXPLANATIONS — multi-step reasoning chains that explain WHY something happens. The gap: Maestro can say "bottlenecks correlate with velocity drops" but cannot explain "WHY does this bottleneck cause velocity drops in THIS organization — what is the causal chain from PR to review queue to dependency to missed estimate?"',
        'CREATE <font face="Mono">backend/maestro_oem/explanations.py</font> — the ExplanationEngine. Takes a question ("Why are engineering estimates always wrong?") and synthesizes a causal explanation: (1) retrieves relevant causal chains (from causal.py), (2) retrieves signal patterns (from pattern.py), (3) retrieves evidence (from evidence_graph.py), (4) composes a multi-step explanation graph: PR -> review queue -> cross-team dependency -> architecture ownership -> late QA -> missed estimate. Each step has evidence_count + confidence. CREATE GET /api/oem/explain?q=... endpoint. MODIFY static/js/ask_v2.js — "why" questions route to the Explanation engine and render the explanation as a visual chain (not a text paragraph). MODIFY all confidence displays (TODAY, Cognition, LEARN) — every confidence score gets a "Why?" link that opens the explanation.',
        '1) GET /api/oem/explain?q=Why+are+engineering+estimates+always+wrong returns a multi-step causal explanation (3+ steps, each with evidence_count + confidence). 2) Each step references real model data (not hardcoded). 3) ASK v2 renders the explanation as a visual chain. 4) Every confidence score in the UI has a "Why?" link that opens the explanation. 5) V5 litmus: no new panel — enhances ASK v2 + existing confidence displays. 6) Permanent Constitution litmus: does this make the customer say "Maestro understands our company"? YES — explanations are the proof of understanding.',
        '3 days (2 days explanation-synthesis engine + 0.5 day API + 0.5 day frontend visual chain)',
        'causal.py (for causal chains). evidence_graph.py (for evidence). pattern.py (for patterns). sowhat.py (for consequence logic). narrative.py (for narrative composition).'
    ))

    # ── UPGRADE 2: FOUR-LEVEL UNKNOWNS ───────────────────────────────────
    story.extend(spec_block(
        2, 'Four-Level Unknowns — Known / Known Unknown / Unknown Unknown / Emerging Unknown',
        'Currently Maestro reports "We don\'t understand HR." That is only level one. Four levels: (1) Known — "Deployment pipeline." (2) Known Unknown — "Executive hiring." (3) Unknown Unknown — "There are probably hidden decision mechanisms we have never observed." (4) Emerging Unknown — "A completely new organizational behavior appeared yesterday. We don\'t know what it is yet." That is much richer scientifically.',
        'curiosity.py (184 lines) identifies untested assumptions and unmeasured domains. But it has one level: "we don\'t understand X." The gap: no four-level taxonomy. No "emerging unknown" detection (a new signal pattern that appeared yesterday and Maestro cannot classify). No "unknown unknown" estimation (what decision mechanisms might exist that Maestro has never observed?).',
        'UPGRADE <font face="Mono">backend/maestro_oem/curiosity.py</font> — add a <font face="Mono">classify_unknowns()</font> method that categorizes organizational areas into 4 levels: Known (coverage > 60%), Known Unknown (coverage 10-60%, Maestro knows it doesn\'t understand), Unknown Unknown (coverage < 10%, Maestro suspects hidden mechanisms), Emerging Unknown (new signal pattern in last 7 days that doesn\'t match any existing learning object). CREATE GET /api/oem/unknowns?levels=all endpoint (returns all 4 levels). MODIFY static/js/today.js — "What Maestro doesn\'t know yet" section now shows 4 levels with different visual treatment.',
        '1) GET /api/oem/unknowns?levels=all returns 4 arrays: known, known_unknowns, unknown_unknowns, emerging_unknowns. 2) Each item has area + coverage + reason. 3) Emerging unknowns have "detected_at" (last 7 days). 4) TODAY shows 4 levels with different treatment. 5) V5 litmus: no new panel. 6) Constitution litmus: does this make the customer trust Maestro MORE? YES — 4-level honesty is more scientifically rigorous than 1-level.',
        '1.5 days (1 day four-level engine + 0.5 day API + frontend)',
        'curiosity.py (upgrade). institutional_confidence.py (V8 #2, for coverage thresholds). signal history (for emerging unknown detection).'
    ))

    # ── UPGRADE 3: CONVERSATIONAL CURIOSITY ──────────────────────────────
    story.extend(spec_block(
        3, 'Conversational Curiosity — multi-turn, not Q&A',
        'Instead of Question -> Answer, build Question -> Discussion -> Clarification -> Understanding Updated. "Why were approvals doubled?" "Holiday backlog." "Was this planned?" "No." "Did the backlog change delivery quality?" "Slightly." "Thank you. Institutional understanding updated." That feels alive.',
        'curiosity.py generates single questions with text input. The answer becomes a signal. But there is no FOLLOW-UP — Maestro does not ask clarifying questions based on the answer. The gap: no conversational state. No multi-turn curiosity. Maestro asks once and moves on.',
        'UPGRADE <font face="Mono">backend/maestro_oem/curiosity.py</font> — add <font face="Mono">follow_up()</font> method that takes the previous question + answer and generates a clarifying follow-up. CREATE <font face="Mono">POST /api/oem/curiosity/follow-up</font> endpoint (accepts question_id + answer, returns follow_up_question or "understanding_updated: true"). MODIFY static/js/today.js — "Maestro has questions" card becomes a conversation: question -> input -> follow-up -> input -> "Thank you. Understanding updated." (max 3 turns per topic).',
        '1) POST /api/oem/curiosity/follow-up returns either a follow_up_question or {"understanding_updated": true, "signal_created": true}. 2) Follow-up questions reference the previous answer (not generic). 3) Max 3 turns per topic (Maestro does not interrogate). 4) After the conversation, understanding is updated (a new signal is created AND the relevant model component is adjusted). 5) TODAY shows a conversation flow (not a single Q&A). 6) Constitution litmus: does this make the customer say "Maestro knows how our company works"? YES — the org teaches Maestro through conversation.',
        '2 days (1.5 days conversational engine + 0.5 day API + frontend)',
        'curiosity.py (upgrade). signal.py (for creating signals from answers).'
    ))

    story.append(PageBreak())

    # ── UPGRADE 4: BAYESIAN INSTITUTIONAL CONFIDENCE ─────────────────────
    story.extend(spec_block(
        4, 'Bayesian Institutional Confidence — living, not static',
        'Not "91%." Instead: "Understanding 91%. Evidence: Growing. Uncertainty: Low. Last revised: Yesterday. Confidence trend: up. Prediction calibration: 93%. Competing explanation: 8%." Now confidence is living, not static.',
        'confidence.py (472 lines) uses Beta-Binomial posterior for per-LAW confidence. But it is a single number, not a living state. The gap: no evidence trend (growing/stable/declining), no uncertainty band, no competing explanation percentage, no last-revised timestamp, no prediction calibration per domain.',
        'CREATE <font face="Mono">backend/maestro_oem/institutional_confidence.py</font> (V8 #2, to build) with BAYESIAN per-domain confidence: {understanding (0-1), evidence_trend (growing/stable/declining), uncertainty (low/medium/high), last_revised (timestamp), confidence_trend (up/down/flat), prediction_calibration (0-1), competing_explanation_pct (0-1), narrative}. CREATE GET /api/oem/confidence endpoint. MODIFY static/js/today.js — "Understanding" section shows living confidence with trend indicators (not static bars).',
        '1) GET /api/oem/confidence returns per-domain confidence with ALL 8 fields. 2) evidence_trend computed from signal rate over 30 days. 3) competing_explanation_pct computed from competing hypotheses (when V7.1 is built — until then, honest "insufficient competing hypotheses"). 4) TODAY shows living confidence with trend indicators. 5) Constitution litmus: does this make the customer trust Maestro? YES — living Bayesian confidence is more honest than a static number.',
        '1.5 days (1 day Bayesian engine + 0.5 day API + frontend)',
        'confidence.py (for Beta-Binomial). prediction_lifecycle.py (for calibration). signal history (for evidence trend).'
    ))

    # ── UPGRADE 5: CAUSALITY TIMELINE ────────────────────────────────────
    story.extend(spec_block(
        5, 'Causality Timeline — every moment answers "why did this permanently change us?"',
        'Today: Event -> Learning. Eventually: Observation -> Decision -> Prediction -> Outcome -> Institution Changed -> Future Decisions Changed. Every card should answer "Why did this permanently change us?" That becomes true institutional memory.',
        'memory_timeline.py (V8 #1, to build) produces moment cards with date + event + prediction + reality + learning. But the "institution_change" field is a string, not a causal chain. The gap: no link between the learning and the FUTURE decisions that changed because of it. "Every deployment recommendation since then uses this rule" is asserted but not traced.',
        'UPGRADE <font face="Mono">backend/maestro_oem/memory_timeline.py</font> (V8 #1, to build) — each moment card gets a <font face="Mono">causal_chain</font> field: {observation, decision, prediction, outcome, institution_change, future_decisions_affected (list of recommendation IDs that changed)}. CREATE GET /api/oem/memory-timeline endpoint. MODIFY the "What we\'ve learned" surface — each moment card shows the full causal chain as a visual flow.',
        '1) GET /api/oem/memory-timeline returns moments with causal_chain field (6 steps). 2) future_decisions_affected references real recommendation IDs. 3) Each moment card shows the causal chain visually. 4) Constitution litmus: does this make the customer say "Maestro knows how our company works"? YES — it shows WHY the organization changed, not just THAT it changed.',
        '2 days (1.5 days causal-chain tracing + 0.5 day frontend)',
        'memory_timeline.py (V8 #1). prediction_lifecycle.py (for predictions). adaptive_nudge.py (for interventions).'
    ))

    # ── UPGRADE 6: UNDERSTANDING TOPOLOGY ────────────────────────────────
    story.extend(spec_block(
        6, 'Understanding Topology — network graph, not bars',
        'Instead of bars, imagine a living network. Engineering -> Platform -> Security -> Legal -> Sales. Connections pulse as Maestro learns. Users literally watch understanding spread. Almost like watching neurons grow. Nobody has that today.',
        'understanding_map.py (V8 #5, to build) produces horizontal bars per domain. But bars do not show RELATIONSHIPS between domains. The gap: no network visualization showing how understanding of one domain connects to another. No "pulse" when a new signal deepens understanding.',
        'UPGRADE <font face="Mono">backend/maestro_oem/understanding_map.py</font> (V8 #5) — add <font face="Mono">topology()</font> method that returns nodes (domains with coverage) + edges (cross-domain dependencies from evidence_graph.py). Each edge has a strength (how many cross-domain signals exist). CREATE GET /api/oem/understanding-topology endpoint. CREATE <font face="Mono">static/js/understanding_topology.js</font> — renders a force-directed network graph (domains as nodes, cross-domain signals as edges). Nodes are sized by coverage. Edges pulse when new cross-domain signals arrive. MODIFY static/js/learn.js — Understanding Map section becomes Understanding Topology (network, not bars).',
        '1) GET /api/oem/understanding-topology returns nodes + edges with strength. 2) LEARN surface shows a network graph (not bars). 3) Nodes are sized by coverage. 4) Edges have strength from cross-domain signal count. 5) Constitution litmus: does this make the customer say "Maestro knows how our company works"? YES — they literally watch understanding spread.',
        '2 days (1 day topology engine + 0.5 day API + 0.5 day frontend network visualization)',
        'understanding_map.py (V8 #5). evidence_graph.py (for cross-domain edges).'
    ))

    story.append(PageBreak())

    # ── UPGRADE 7: ORGANIZATIONAL BLIND SPOTS ────────────────────────────
    story.extend(spec_block(
        7, 'Organizational Blind Spots — evidence exists, org ignores it',
        'Different from Unknown Unknowns. Unknown Unknown: "No evidence." Blind Spot: "Evidence exists. Organization ignores it." Example: "Engineering has raised deployment risk 11 times. Leadership has ignored it 11 times. Blind spot detected." This is one of the most valuable insights a CEO could ever receive.',
        'No module tracks ignored evidence. contradiction.py detects contradictions between beliefs and behavior. But it does not track PATTERNS OF IGNORED EVIDENCE — signals that were raised (in Slack, in Jira, in postmortems) but never resulted in action. The gap: Maestro cannot say "this risk has been raised 11 times and ignored 11 times."',
        'CREATE <font face="Mono">backend/maestro_oem/blind_spots.py</font> — the BlindSpotEngine. Scans for signals that indicate a raised risk/concern (Slack messages with risk keywords, Jira issues with "risk" label, postmortem recommendations) and checks whether any action was taken (was a related PR merged? was a policy changed? was a task created?). If raised_count > 3 AND action_count == 0, flag as a blind spot. CREATE GET /api/oem/blind-spots endpoint. MODIFY static/js/today.js — if blind spots exist, show them as a high-priority card: "Engineering has raised deployment risk 11 times. Leadership has not acted. This is a blind spot."',
        '1) GET /api/oem/blind-spots returns blind_spots array. 2) Each has area, raised_count, action_count, evidence (signal references), severity. 3) raised_count > 3 AND action_count == 0 required for blind spot status. 4) TODAY shows blind spot card when detected. 5) Constitution litmus: does this make the customer say "Maestro knows how our company works"? YES — it sees what the org ignores.',
        '1 day (0.5 day blind-spot detection + 0.5 day API + frontend)',
        'signal history (for raised risks). pattern.py (for recurrence detection). contradiction.py (for existing contradiction logic).'
    ))

    # ── UPGRADE 8: INSTITUTIONAL GRAVITY ─────────────────────────────────
    story.extend(spec_block(
        8, 'Institutional Gravity — visualize centers of gravity',
        'Every organization has centers of gravity. Not org charts. Real gravity. People, projects, decisions, knowledge, approvals, customers — everything bends around certain people. Maestro visualizes it. When gravity shifts, the organization changes. That is measurable.',
        'consciousness.py (204 lines) tracks organizational state (attention, knowledge, trust, etc.). personality.py (247 lines) infers traits. But neither visualizes GRAVITY — the concentration of organizational activity around specific people. The gap: no module identifies "Alice is a center of gravity for auth decisions" or "gravity shifted from Alice to Bob last month."',
        'CREATE <font face="Mono">backend/maestro_oem/institutional_gravity.py</font> — the GravityEngine. For each person (from signal actors), compute gravity_score based on: (1) decision_count (how many decisions involve them), (2) knowledge_holding (how many domains they hold knowledge in), (3) approval_count (how many approvals pass through them), (4) cross_team_connections (how many teams they interact with). Track gravity over time — when gravity shifts (one person\'s score drops > 20% while another\'s rises), flag it. CREATE GET /api/oem/gravity endpoint. MODIFY static/js/learn.js — add "Centers of gravity" section showing top 5 people by gravity_score + any recent shifts.',
        '1) GET /api/oem/gravity returns people with gravity_score + trend. 2) At least 3 people with score > 0. 3) Gravity shifts detected (person A drops, person B rises). 4) LEARN shows "Centers of gravity" section. 5) Constitution litmus: does this make the customer say "Maestro knows how our company works"? YES — it sees who the org actually revolves around (not the org chart).',
        '2 days (1.5 days gravity computation + 0.5 day API + frontend)',
        'signal.py (for actor data). consciousness.py (for state). evidence_graph.py (for knowledge holding). model.py (for approval network).'
    ))

    # ── UPGRADE 9: MEMORY COMPRESSION (DEEP) ─────────────────────────────
    story.extend(spec_block(
        9, 'Memory Compression (Deep) — 10M events to 7 cultural axioms',
        '10 million events -> 200 principles -> 43 reflexes -> 19 institutional truths -> 7 cultural axioms. Maestro compresses experience exactly like the human brain does. That is an extraordinary product.',
        'memory_compression.py (152 lines, V4) compresses into truths/habits/mistakes (3 categories). But the compression is shallow — it does not produce PRINCIPLES, REFLEXES, TRUTHS, and AXIOMS at different abstraction levels. The gap: no multi-level compression that mirrors how human institutional knowledge forms (from raw events to cultural axioms).',
        'UPGRADE <font face="Mono">backend/maestro_oem/memory_compression.py</font> — add 5-level compression: (1) Events (raw signals, filtered for relevance by forgetting.py), (2) Principles (validated laws with >= 5 runtimes — from law.py), (3) Reflexes (patterns so strong they are automatic — from pattern.py with strength > 0.8), (4) Institutional Truths (principles that have survived >= 1 year without failure — from principles.py when built), (5) Cultural Axioms (truths so fundamental they define the organization — from identity.py beliefs with drift < 0.1). CREATE GET /api/oem/compression-deep endpoint. MODIFY static/js/learn.js — add "How your organization compresses experience" section showing the 5 levels with counts and examples.',
        '1) GET /api/oem/compression-deep returns 5 levels: events_count, principles_count, reflexes_count, truths_count, axioms_count + examples for each. 2) Each level has a lower count than the one below (compression). 3) LEARN shows the 5 levels. 4) Constitution litmus: does this make the customer say "Maestro knows how our company works"? YES — it shows the org\'s compressed wisdom at every abstraction level.',
        '2 days (1.5 days multi-level compression + 0.5 day API + frontend)',
        'memory_compression.py (upgrade). law.py (for principles). pattern.py (for reflexes). identity.py (for axioms). forgetting.py (for event filtering).'
    ))

    # ── BUILD ORDER ──────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(P('Build Order', 'h1'))

    order_rows = [
        ['Step', 'Upgrade', 'Effort', 'Stage', 'Key Output'],
        ['0', 'Fix V6 wiring gaps', '1.5 hours', '9. Repeat', 'Background loop in live_ingest + DNA in wisdom.py'],
        ['1', '#1 Organizational Explanations', '3 days', '5. Explain', 'WHY, not just WHAT. Every confidence gets a "Why?" link.'],
        ['2', '#2 Four-Level Unknowns', '1.5 days', '3. Question', 'Known / Known Unknown / Unknown Unknown / Emerging Unknown'],
        ['3', '#3 Conversational Curiosity', '2 days', '3. Question', 'Multi-turn conversation, not Q&A'],
        ['4', '#4 Bayesian Institutional Confidence', '1.5 days', '2. Understand', 'Living confidence with trend + uncertainty + calibration'],
        ['5', '#5 Causality Timeline', '2 days', '5. Explain', 'Every moment answers "why did this permanently change us?"'],
        ['6', '#6 Understanding Topology', '2 days', '8. Teach', 'Network graph. Watch understanding spread.'],
        ['7', '#7 Organizational Blind Spots', '1 day', '3. Question', '"Raised 11 times. Ignored 11 times. Blind spot."'],
        ['8', '#8 Institutional Gravity', '2 days', '2. Understand', 'Centers of gravity. When gravity shifts, the org changes.'],
        ['9', '#9 Memory Compression (Deep)', '2 days', '2. Understand', '10M events -> 200 principles -> 43 reflexes -> 19 truths -> 7 axioms'],
        ['', '', '', '', ''],
        ['TOTAL', '9 upgrades + V6 fixes', '~17 days + 1.5 hours', '5 stages', 'From outputs to explanations. From memory to understanding.'],
    ]
    t = Table(order_rows, colWidths=[10*mm, 40*mm, 16*mm, 18*mm, 50*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, 10), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, 12), (-1, 12), colors.HexColor('#f1f5f9')),
        ('FONTNAME', (0, 12), (-1, 12), FONT_HEAD_B),
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

    # ── THE LITMUS TEST ──────────────────────────────────────────────────
    story.append(P('The Permanent Constitution Litmus Test', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>DOES THIS MAKE THE CUSTOMER SAY "MAESTRO UNDERSTANDS OUR COMPANY"?</b></font>',
                  ParagraphStyle('litmus_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ACCENT, spaceAfter=4)),
        P('<b>The single test that replaces all previous litmus tests.</b> Not "is the UI simpler?" Not '
          '"does the org improve?" Not "is the understanding more accurate?" All of those are necessary '
          'but insufficient. The final test: <b>does the customer experience Maestro as something that '
          'UNDERSTANDS their company?</b>', 'body_left'),
        P('Understanding is demonstrated through EXPLANATIONS. If the customer asks "why?" and Maestro '
          'can explain — with evidence, with causal chains, with historical analogues — then Maestro '
          'understands. If Maestro can only show a number, a pattern, or a prediction, it does not '
          'understand. It observes. Observing is necessary but insufficient. Understanding is the product.', 'body_left'),
        P('<b>Every upgrade in this constitution must pass this test.</b> If an upgrade produces a number '
          'without an explanation, it fails. If it produces a prediction without a "why," it fails. If it '
          'produces a recommendation without evidence the customer can inspect, it fails. The bar is '
          'understanding, expressed as explanations.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ACCENT))

    # ── THE END ──────────────────────────────────────────────────────────
    story.append(P('The End', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>"MAESTRO UNDERSTANDS OUR COMPANY"</b></font>',
                  ParagraphStyle('end_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=4)),
        P('<b>One year later, the customer does not say "We use Maestro." They say "Maestro understands '
          'our company."</b> That sentence is the product. Not a dashboard. Not a copilot. Not an '
          'intelligence layer. An understanding — continuously improving, evidence-backed, explainable, '
          'and irreplaceable.', 'body_left'),
        P('The 19 engines remain internally. The customer sees one thing: explanations. They ask "why?" '
          'and Maestro explains — with causal chains, with evidence, with historical analogues, with '
          'honest confidence and honest gaps. They see their organization\'s understanding grow on a '
          'topology map. They revisit moments where the institution changed. They answer Maestro\'s '
          'questions and watch understanding update in real time. They see blind spots Maestro detected '
          'that they were ignoring. They see centers of gravity shift. They see 10 million events '
          'compressed into 7 cultural axioms.', 'body_left'),
        P('<b>The constitutional sentence:</b> "Maestro exists to become the most accurate, continuously '
          'improving explanation of how an organization works. Every signal deepens understanding. Every '
          'decision tests understanding. Every outcome revises understanding. Every revision improves '
          'future judgment."', 'body_left'),
        P('<b>No more versions. One loop. Observe, Understand, Question, Predict, Explain, Prepare, '
          'Revise, Teach, Repeat. Forever.</b>', 'body_left'),
        P('<b>Build order: Step 0 (fix V6 gaps, 1.5 hours) -> #1 Explanations (3 days) -> #2 Four-Level '
          'Unknowns (1.5 days) -> #3 Conversational Curiosity (2 days) -> #4 Bayesian Confidence (1.5 '
          'days) -> #5 Causality Timeline (2 days) -> #6 Understanding Topology (2 days) -> #7 Blind '
          'Spots (1 day) -> #8 Institutional Gravity (2 days) -> #9 Memory Compression Deep (2 days). '
          'Total ~17 days + 1.5 hours. Then ship the 90-day pilot. The product is Organizational '
          'Understanding. Build it.</b>', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ACCENT))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'Maestro_Permanent_Constitution_Organizational_Understanding.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
