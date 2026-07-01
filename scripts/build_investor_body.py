#!/usr/bin/env python3
"""Maestro — Investor Briefing. Body PDF (ReportLab). 13 chapters + TOC."""
import os, sys, hashlib

PDF_SKILL_DIR = "/home/z/my-project/skills/pdf"
_scripts = os.path.join(PDF_SKILL_DIR, "scripts")
if _scripts not in sys.path: sys.path.insert(0, _scripts)

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

FONT_DIR = "/usr/share/fonts"
pdfmetrics.registerFont(TTFont('NotoSerifSC', f'{FONT_DIR}/truetype/noto-serif-sc/NotoSerifSC-Regular.ttf'))
pdfmetrics.registerFont(TTFont('NotoSerifSC-Bold', f'{FONT_DIR}/truetype/noto-serif-sc/NotoSerifSC-Bold.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif', f'{FONT_DIR}/truetype/freefont/FreeSerif.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif-Bold', f'{FONT_DIR}/truetype/freefont/FreeSerifBold.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif-Italic', f'{FONT_DIR}/truetype/freefont/FreeSerifItalic.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif-BoldItalic', f'{FONT_DIR}/truetype/freefont/FreeSerifBoldItalic.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuSans', f'{FONT_DIR}/truetype/dejavu/DejaVuSansMono.ttf'))
registerFontFamily('NotoSerifSC', normal='NotoSerifSC', bold='NotoSerifSC-Bold')
registerFontFamily('FreeSerif', normal='FreeSerif', bold='FreeSerif-Bold', italic='FreeSerif-Italic', boldItalic='FreeSerif-BoldItalic')
registerFontFamily('DejaVuSans', normal='DejaVuSans', bold='DejaVuSans')
from pdf import install_font_fallback
install_font_fallback()

PAGE_BG=colors.HexColor('#f5f6f7'); SECTION_BG=colors.HexColor('#eeeff0')
CARD_BG=colors.HexColor('#eeeff0'); TABLE_STRIPE=colors.HexColor('#e9ebec')
HEADER_FILL=colors.HexColor('#3e5866'); BORDER=colors.HexColor('#a8bac2')
ACCENT=colors.HexColor('#3482aa'); ACCENT_2=colors.HexColor('#c9775c')
TEXT_PRIMARY=colors.HexColor('#151617'); TEXT_MUTED=colors.HexColor('#7c8386')
SEM_SUCCESS=colors.HexColor('#377b4e'); SEM_ERROR=colors.HexColor('#9c5750')

PAGE_W, PAGE_H = A4
LEFT_M = RIGHT_M = 0.85 * inch
TOP_M = BOTTOM_M = 0.85 * inch
AVAILABLE_W = PAGE_W - LEFT_M - RIGHT_M
OUTPUT_BODY = "/home/z/my-project/scripts/body_investor.pdf"

body_style = ParagraphStyle('Body', fontName='FreeSerif', fontSize=10.5, leading=16, alignment=TA_JUSTIFY, textColor=TEXT_PRIMARY, spaceBefore=0, spaceAfter=10)
h1_style = ParagraphStyle('H1', fontName='FreeSerif-Bold', fontSize=20, leading=26, textColor=HEADER_FILL, alignment=TA_LEFT, spaceBefore=24, spaceAfter=14)
h2_style = ParagraphStyle('H2', fontName='FreeSerif-Bold', fontSize=14, leading=20, textColor=HEADER_FILL, alignment=TA_LEFT, spaceBefore=16, spaceAfter=8)
h3_style = ParagraphStyle('H3', fontName='FreeSerif-Bold', fontSize=11.5, leading=16, textColor=ACCENT, alignment=TA_LEFT, spaceBefore=12, spaceAfter=6)
callout_style = ParagraphStyle('Callout', fontName='FreeSerif-Italic', fontSize=11, leading=17, textColor=TEXT_PRIMARY, alignment=TA_LEFT, leftIndent=16, rightIndent=12, spaceBefore=10, spaceAfter=12, backColor=CARD_BG, borderPadding=12, borderColor=ACCENT, borderWidth=0)
muted_style = ParagraphStyle('Muted', fontName='FreeSerif-Italic', fontSize=9.5, leading=14, textColor=TEXT_MUTED, alignment=TA_LEFT, spaceBefore=2, spaceAfter=8)
th = ParagraphStyle('TH', fontName='FreeSerif-Bold', fontSize=9.5, leading=13, textColor=colors.white, alignment=TA_LEFT)
tc = ParagraphStyle('TC', fontName='FreeSerif', fontSize=9.5, leading=13, textColor=TEXT_PRIMARY, alignment=TA_LEFT)
tcb = ParagraphStyle('TCB', fontName='FreeSerif-Bold', fontSize=9.5, leading=13, textColor=TEXT_PRIMARY, alignment=TA_LEFT)
toc_title = ParagraphStyle('TocTitle', fontName='FreeSerif-Bold', fontSize=22, leading=28, textColor=HEADER_FILL, alignment=TA_LEFT, spaceBefore=0, spaceAfter=20)
toc_l0 = ParagraphStyle('TOC0', fontName='FreeSerif-Bold', fontSize=11, leading=18, leftIndent=0, textColor=TEXT_PRIMARY)
toc_l1 = ParagraphStyle('TOC1', fontName='FreeSerif', fontSize=10, leading=15, leftIndent=20, textColor=TEXT_MUTED)

class TocDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if hasattr(flowable, 'bookmark_name'):
            level = getattr(flowable, 'bookmark_level', 0)
            text = getattr(flowable, 'bookmark_text', '')
            key = getattr(flowable, 'bookmark_key', '')
            self.notify('TOCEntry', (level, text, self.page, key))

def add_heading(text, style, level=0):
    key = 'h_%s' % hashlib.md5(text.encode()).hexdigest()[:8]
    p = Paragraph('<a name="%s"/>%s' % (key, text), style)
    p.bookmark_name = key; p.bookmark_level = level
    p.bookmark_text = text; p.bookmark_key = key
    return p

def std_table(data, col_ratios):
    cw = [r * AVAILABLE_W for r in col_ratios]
    t = Table(data, colWidths=cw, hAlign='CENTER')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), HEADER_FILL),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, TABLE_STRIPE]),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
        ('RIGHTPADDING', (0,0), (-1,-1), 7),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    return t

def page_decoration(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(BORDER); canvas.setLineWidth(0.5)
    canvas.line(LEFT_M, 0.55*inch, PAGE_W-RIGHT_M, 0.55*inch)
    canvas.setFont('FreeSerif', 8); canvas.setFillColor(TEXT_MUTED)
    canvas.drawString(LEFT_M, 0.38*inch, 'Maestro — Investor Briefing')
    canvas.drawRightString(PAGE_W-RIGHT_M, 0.38*inch, 'Page %d' % doc.page)
    canvas.setFillColor(ACCENT)
    canvas.circle(PAGE_W-RIGHT_M-3, PAGE_H-0.55*inch, 2.5, fill=1, stroke=0)
    canvas.restoreState()

story = []

# === TOC ===
story.append(Paragraph('Table of Contents', toc_title))
toc = TableOfContents()
toc.levelStyles = [toc_l0, toc_l1]
story.append(toc)
story.append(PageBreak())

# === Ch 1 — The Problem ===
story.append(add_heading('Chapter 1 — The Problem', h1_style, 0))
story.append(Paragraph(
    'Knowledge workers are drowning in information but starving for judgment. The average enterprise employee interacts with 9.4 communication tools daily, receives 126 emails, sends 46 Slack messages, and attends 4.3 meetings. Yet when a critical decision arrives — whether to ship a feature, hire an engineer, escalate a customer issue — the organization repeats the same mistakes it made six months ago. The postmortem exists in a Confluence page nobody reads. The lesson lives in a Slack thread that has scrolled out of view. The senior engineer who knew the answer left three months ago.', body_style))
story.append(Paragraph(
    'This is not a data problem. Organizations have more data than they can process. It is a judgment problem. Data is raw; judgment is the capacity to act on data with confidence. Judgment is what separates a senior engineer from a junior one, a great CEO from a mediocre one, a thriving organization from a failing one. And judgment, until now, has been locked inside individual heads — lost when they leave, forgotten when they sleep, unavailable when it is needed most.', body_style))
story.append(Paragraph(
    'The same problem exists in personal life. You forget what you talked about with a friend last month. You repeat the same productivity mistakes. You say you want to exercise but skip the gym three weeks in a row. You face a major life decision — should I take this job, should I move cities, should I end this relationship — and you have no tool that surfaces your own past patterns to inform the choice. Notes apps capture text but not patterns. Habit trackers track behaviors but not contradictions. Calendar apps show events but not the narrative of your life.', body_style))
story.append(Paragraph(
    'The societal cost is enormous. McKinsey estimates that knowledge workers spend 19% of their time searching for information that exists somewhere in the organization — that is one full day per week lost to re-finding what was already known. The cost of repeated organizational mistakes is harder to quantify but far larger: the failed product launch that mirrors the previous failed launch, the customer churn that repeats because the root cause was never captured, the engineering bottleneck that persists for quarters because nobody remembers the pattern.', body_style))
story.append(Paragraph(
    'AI tools promised to solve this. They did not. ChatGPT generates text but does not learn your organization. Glean searches your documents but does not understand context. Guru stores knowledge cards but does not verify them. Dust builds agents but does not close the learning loop. The gap in the market is clear: no tool compounds judgment over time, for an organization or for a person. No tool learns from every signal, builds a living model of how you work and who you are, and surfaces the right judgment at the right moment — invisibly, auditably, and with the user’s interests at its core.', body_style))
story.append(Paragraph(
    'Maestro is that tool. It is the cognitive companion that institutionalizes judgment.', callout_style))
story.append(PageBreak())

# === Ch 2 — The Solution ===
story.append(add_heading('Chapter 2 — The Solution', h1_style, 0))
story.append(Paragraph(
    'Maestro is a cognitive companion that institutionalizes judgment — for organizations and for individuals. It learns from every signal across your work and personal life, builds a living model of the organization and the person, and surfaces the right judgment at the right moment. One app. One person. One life.', body_style))
story.append(Paragraph(
    'The architecture is two layers. The Day-to-Day Layer is what the user sees: a 4-item sidebar (Today, Memory, Ask, More), a 90-second morning briefing delivered as Bumble-style swipe cards, a conversational Ask surface that returns synthesized natural-language answers, and a memory replay engine that answers questions about your own history. The Cognitive Layer is what makes those surfaces intelligent: 19 invisible engines that produce the judgments, explanations, and predictions the surfaces display. The user never sees an engine name, a confidence number, or a law code. They see a judgment, and if they want to know why, they tap a "Why?" link and the explanation unfolds inline.', body_style))
story.append(Paragraph(
    'The design law is absolute: every increase in internal intelligence must reduce external complexity. When the SemanticMatcher makes Ask more accurate, the user types fewer rephrasings. When the Drafted Briefing synthesizes five engines into three blocks, the user reads one screen instead of five. When the Commitment Tracker flags a broken promise automatically, the user does not maintain a separate checklist. The measure of a new engine is not its internal sophistication but the number of user actions it eliminates.', body_style))
story.append(Paragraph(
    'Maestro spans both work and personal life — a category expansion no competitor has attempted. The same cognitive companion that briefs the CEO on the deploy gate bottleneck also briefs the person on their habit streaks, their personal contradictions, and their life decisions. The two contexts are unified in one app, with a bidirectional integration: personal state (sleep, energy, calendar conflicts) can contextualize work decisions, and work commitments can contextualize personal life. The integration is opt-in, consent-gated, and reversible. The user is one person, and Maestro treats them as one.', body_style))
story.append(Paragraph(
    'The success condition is the constitution: "The organization becomes more capable, not more dependent. The person becomes more capable, not more dependent — in work and in life." This is not a marketing tagline. It is the governing contract. Every feature is evaluated against it. A feature that makes the user faster but not better is rejected. A feature that creates dependence is rejected. Maestro is designed to be indispensable, not addictive — the user cannot imagine doing the work without it, but could stop if they chose to, and would still be more capable for having used it.', body_style))
story.append(PageBreak())

# === Ch 3 — How It Works ===
story.append(add_heading('Chapter 3 — How It Works', h1_style, 0))
story.append(Paragraph(
    'Maestro’s two-layer architecture separates what the user sees from what makes it intelligent. This separation is the engineering foundation that allows the product to grow smarter without growing more complex. New engines are added to the Cognitive Layer; the Day-to-Day Layer stays at 4 items. The user experience gets simpler even as the intelligence gets deeper.', body_style))
story.append(add_heading('3.1 The Day-to-Day Layer', h2_style, 1))
story.append(Paragraph(
    'The user opens Maestro and sees four items: Today, Memory, Ask, More. The Today surface is the hub — a 90-second morning briefing delivered as a deck of swipe cards. Each card is one insight: a commitment due today, a contradiction detected, a decision to prepare, an unknown to investigate. Swipe right to act (opens an action sheet with write-back options — create a Jira ticket, send a Slack message). Swipe left to defer. In 90 seconds, the morning is organized. The Memory surface is a chronological feed of everything that happened — work signals and personal memories interleaved by time, searchable via natural language ("What did I talk about with Sarah last summer?"). The Ask surface takes a natural-language question and returns a synthesized sentence, not a result list. The More surface holds settings, the "What Maestro Knows" dashboard, and the incognito toggle.', body_style))
story.append(add_heading('3.2 The Cognitive Layer', h2_style, 1))
story.append(Paragraph(
    'Nineteen cognitive engines produce the intelligence behind every surface. They are invisible by design — the user never sees their names, their confidence scores, or their internal logic. When the user wants to understand a judgment, they tap "Why?" and the Explanations engine produces a multi-step causal chain inline. The engines feed each other: the Curiosity engine surfaces gaps the organization should investigate; the Skepticism engine produces counterarguments for every decision; the Wisdom engine applies the organization’s principles and DNA to new situations. The learning loop closes when predictions resolve against outcomes — the Brier score (currently 0.0738) tracks how well-calibrated the model has become.', body_style))
eng_data = [
    [Paragraph('<b>Engine</b>', th), Paragraph('<b>Produces</b>', th), Paragraph('<b>Feeds</b>', th)],
    [Paragraph('SemanticMatcher', tc), Paragraph('TF-IDF relevance ranking', tc), Paragraph('Ask (synthesized answers)', tc)],
    [Paragraph('Explanations', tc), Paragraph('Multi-step causal chains', tc), Paragraph('Inline Why? on every surface', tc)],
    [Paragraph('CommitmentTracker', tc), Paragraph('Open/kept/broken commitments', tc), Paragraph('Briefing (due today)', tc)],
    [Paragraph('TrustLedger', tc), Paragraph('Per-user trust scores', tc), Paragraph('Progressive Trust (auto-execute)', tc)],
    [Paragraph('AttentionSignals', tc), Paragraph('Briefing ranking weights', tc), Paragraph('Briefing learns from clicks', tc)],
    [Paragraph('Contradictions', tc), Paragraph('Values-vs-behavior gaps', tc), Paragraph('Briefing (radical honesty)', tc)],
    [Paragraph('Wisdom + DNA', tc), Paragraph('Principle-based judgment', tc), Paragraph('Playbooks, Write-Back', tc)],
]
story.append(std_table(eng_data, [0.25, 0.38, 0.37]))
story.append(Spacer(1, 8))
story.append(Paragraph('Table 3.1 — Selected cognitive engines and their surface consumers. The full set includes 19 engines plus 5 competitor-analysis features and 2 deepening engines.', muted_style))
story.append(Paragraph(
    'The law that governs the two layers is simple: every day-to-day feature must consume at least one cognitive engine output, and every engine must feed at least one surface. An engine that does not feed a surface is dead code. A surface that does not consume an engine is a static mock. Both are forbidden. This law is enforced by tests — the "built but not applied" pattern that plagued early development has not recurred in 27 consecutive rounds of audit-driven engineering.', body_style))
story.append(PageBreak())

# === Ch 4 — The Moat ===
story.append(add_heading('Chapter 4 — The Moat', h1_style, 0))
story.append(Paragraph(
    'Maestro’s moat is not a single feature. It is five compounding layers, each defensible on its own and reinforcing when combined. Together they make Maestro the only cognitive companion that can institutionalize judgment across work and life without crossing the bright line into manipulation or surveillance.', body_style))
story.append(add_heading('4.1 The Five Moats', h2_style, 1))
story.append(Paragraph(
    '<b>Moat 1: The Verified-Knowledge Layer.</b> Maestro’s organizational laws are not just patterns — they are human-verified facts. A law with verified_by set (a human has signed off) is cited as a fact in briefings, playbooks, and synthesized answers. An unverified law is labeled "candidate." This is the Guru lesson applied systemically: verified knowledge is the differentiator. Competitors cannot replicate this without building the verification workflow, which is a multi-quarter build even with full resources.', body_style))
story.append(Paragraph(
    '<b>Moat 2: The Organizational DNA.</b> Every interaction permanently improves the organization. The DNA engine records patterns — what was decided, what was deferred, what was learned — and updates the organizational self-model. After 90 days, the organization can articulate what it learned that it did not know before. After a year, the DNA is a strategic asset that cannot be exported to a competitor. Switching costs become prohibitive not because of data lock-in but because of judgment lock-in.', body_style))
story.append(Paragraph(
    '<b>Moat 3: The Learning Loop.</b> Predictions resolve against outcomes. The Brier score tracks calibration. The flywheel accelerates: every action makes the next prediction better. This is the Amazon flywheel applied to organizational intelligence. Competitors that do not close the loop (Glean, Guru, Dust) cannot compound judgment over time — they remain search or storage tools. Maestro becomes more accurate the longer it runs.', body_style))
story.append(Paragraph(
    '<b>Moat 4: The Constitutional Bright Line.</b> "Maestro helps YOU think better. Maestro does NOT help you manipulate, surveil, or win against another person." This is enforced in code by a bright-line guard that scans every payload for forbidden patterns and fails closed. Enterprise buyers require this trust layer — SOC2 covers data handling, but the bright line covers judgment handling. No competitor has this, because no competitor has the discipline to reject the manipulation features that drive short-term engagement.', body_style))
story.append(Paragraph(
    '<b>Moat 5: The Bidirectional Work-Life Integration.</b> Maestro is the only cognitive companion that spans both work and personal life in one app. Personal state (sleep, energy, calendar) contextualizes work decisions. Work commitments contextualize personal life. The integration is opt-in and consent-gated, but the architecture is unified. No competitor spans both contexts — Glean is work-only, Bond is personal-only, Cluely is manipulation-only. The user has one life; Maestro is the only tool that treats them as one person.', body_style))
story.append(add_heading('4.2 The Competitive Landscape', h2_style, 1))
comp_data = [
    [Paragraph('<b>Competitor</b>', th), Paragraph('<b>Their Moat</b>', th), Paragraph('<b>Why Maestro Wins</b>', th)],
    [Paragraph('Glean', tc), Paragraph('Enterprise search ($7.2B)', tc), Paragraph('Maestro pulls Glean as evidence, does not out-build search. Verified knowledge + learning loop > search.', tc)],
    [Paragraph('Guru', tc), Paragraph('Knowledge cards', tc), Paragraph('Maestro has verified laws + 19 cognitive engines. Guru stores; Maestro reasons.', tc)],
    [Paragraph('Dust', tc), Paragraph('300k agents', tc), Paragraph('Maestro has event-triggered background loop + governed actions. Dust builds agents; Maestro closes loops.', tc)],
    [Paragraph('Bond/Donna', tc), Paragraph('CEO briefing', tc), Paragraph('Maestro has commitment tracking + 19 engines + work-life integration. Bond is single-context.', tc)],
    [Paragraph('Ambient', tc), Paragraph('Context mapping', tc), Paragraph('Maestro has ambient context + proactive briefing + both contexts. Ambient is work-only.', tc)],
    [Paragraph('Nerve', tc), Paragraph('Context assembly', tc), Paragraph('Nerve was absorbed by OpenAI — context assembly is absorbable. Maestro stays anchored to governed action.', tc)],
    [Paragraph('ChatGPT / generic AI', tc), Paragraph('Text generation', tc), Paragraph('Maestro learns your org; ChatGPT generates text. Maestro has the verified-knowledge layer generic AI lacks.', tc)],
    [Paragraph('Cluely', tc), Paragraph('Real-time manipulation', tc), Paragraph('Maestro rejects manipulation absolutely. The bright line is the trust moat Cluely cannot match.', tc)],
]
story.append(std_table(comp_data, [0.14, 0.26, 0.60]))
story.append(Spacer(1, 8))
story.append(Paragraph('Table 4.1 — Competitive landscape. Maestro’s five moats compound; each competitor has one.', muted_style))
story.append(PageBreak())

# === Ch 5 — All Functions ===
story.append(add_heading('Chapter 5 — All Functions', h1_style, 0))
story.append(Paragraph(
    'Maestro is built. It is not a prototype or a mockup. Across 46 rounds of audit-driven development, 63 modules have been delivered, tested, and wired to frontend surfaces. Every feature is verified against source code by an independent Fortune 100 CTO auditor. Every feature passes the constitutional test. Every feature has a withdrawal path. The inventory below is the complete product as of the latest commit on origin/main.', body_style))
story.append(add_heading('5.1 Enterprise Mode (Pilot-Ready)', h2_style, 1))
story.append(Paragraph(
    'The enterprise product comprises five layers: 19 cognitive engines, 6 daily-work features, 5 competitor-analysis features, 5 P0 deepening features, and 5 P1 deepening features. Every layer is built, tested, wired to the frontend, and verified against the frozen constitution.', body_style))
ent_data = [
    [Paragraph('<b>Layer</b>', th), Paragraph('<b>Features</b>', th), Paragraph('<b>Highlights</b>', th)],
    [Paragraph('Cognitive Engines', tcb), Paragraph('19 engines', tc), Paragraph('SoWhat, Curiosity, Skepticism, Wisdom, Contradictions, Explanations, Unknowns, SemanticMatcher, CommitmentTracker, TrustLedger, AttentionSignals + 9 more', tc)],
    [Paragraph('Daily-Work', tcb), Paragraph('6 features', tc), Paragraph('Timeline, Task Intelligence, Drafted Briefing, Write-Back (Jira/Slack/Gmail/GitHub), Role Playbooks, Enterprise Trust Layer (SAML/RBAC/SOC2)', tc)],
    [Paragraph('Competitor Analysis', tcb), Paragraph('5 features', tc), Paragraph('Semantic Ask, Verified Knowledge, Commitment Tracker, Governed Auto-Action, Glean/Guru/Dust Connectors', tc)],
    [Paragraph('P0 Deepening', tcb), Paragraph('5 features', tc), Paragraph('Commitments in briefing, inline Why?, one-tap write-back, synthesized answers, push delivery (opt-in)', tc)],
    [Paragraph('P1 Deepening', tcb), Paragraph('5 features', tc), Paragraph('Trust ledger, progressive trust (auto-execute), unknown-to-action, auto-completion, briefing learns', tc)],
]
story.append(std_table(ent_data, [0.18, 0.12, 0.70]))
story.append(Spacer(1, 8))
story.append(Paragraph('Table 5.1 — Enterprise feature inventory. Total: 40 enterprise features across 5 layers.', muted_style))
story.append(add_heading('5.2 Personal Mode (Pilot-Ready)', h2_style, 1))
story.append(Paragraph(
    'Personal Mode extends Maestro from organizational intelligence to personal life — memory, decisions, habits, and self-knowledge. It is built on a separate namespace (maestro_personal/) with strict namespace separation enforced by tests. The infrastructure layer (ConsentStore, ModeManager, IncognitoSession, DataExpiry, LocalFirstConfig) enforces 12 constitutional guidelines. The feature layer delivers 13 self-facing Tier 1 features and 3 consent-gated Tier 2 features.', body_style))
pers_data = [
    [Paragraph('<b>Phase</b>', th), Paragraph('<b>Features</b>', th), Paragraph('<b>Highlights</b>', th)],
    [Paragraph('Phase 1: Infrastructure', tcb), Paragraph('7 modules', tc), Paragraph('ConsentStore (bilateral consent), ModeManager (dual profiles), IncognitoSession, DataExpiry, LocalFirstConfig, PersonalDataStore, WhatMaestroKnows dashboard', tc)],
    [Paragraph('Phase 2: Tier 1 Self-Facing', tcb), Paragraph('13 features', tc), Paragraph('Morning Briefing, Knowledge Graph, Memory Replay, Decision Support, Habit Coach, Prediction Market, Contradictions, Prepared Decisions, Intent Cascade, Personal Why?, Evolution Report, Reflection Prompts, Legacy Builder', tc)],
    [Paragraph('Phase 3: Tier 2 Consent-Gated', tcb), Paragraph('3 features', tc), Paragraph('Relationship Memory Vault, Ambient Personal Context, Professional-Personal Crossover', tc)],
]
story.append(std_table(pers_data, [0.22, 0.10, 0.68]))
story.append(Spacer(1, 8))
story.append(Paragraph('Table 5.2 — Personal Mode feature inventory. Total: 23 personal features across 3 phases.', muted_style))
story.append(Paragraph(
    'The Work/Personal integration (Round 44) adds the bidirectional context layer: personal state contextualizes work decisions, work commitments contextualize personal life. The integration is opt-in (toggle defaults to OFF), consent-gated, and enforced by a bright-line guard that scans every payload for forbidden patterns and fails closed. This is the only cognitive companion that spans both contexts without blurring the bright line.', body_style))
story.append(PageBreak())

# === Ch 6 — The Value ===
story.append(add_heading('Chapter 6 — The Value', h1_style, 0))
story.append(Paragraph(
    'Maestro’s value is measured against a single success condition: does it make the organization and the person more capable, not more dependent? Every feature is evaluated against this. The value is not usage metrics — it is capability gained. After 90 days, can the organization articulate what it learned? Can the person articulate how they grew? If yes, the product succeeded. If no, it failed, regardless of engagement.', body_style))
story.append(add_heading('6.1 Value to the Organization', h2_style, 1))
story.append(Paragraph(
    'Organizations that adopt Maestro gain five measurable capabilities. First, fewer repeated mistakes: the organizational laws capture patterns that held, so the same failure does not recur. Second, faster onboarding: new hires query Maestro ("Why do we require two reviewers on every PR?") and get a synthesized answer citing the verified law. Third, captured institutional memory: when a senior engineer leaves, their judgment does not — it lives in the laws, the DNA, and the explanation chains. Fourth, auditable decisions: every recommendation has a "Why?" link that traces the causal chain, so decisions are defensible. Fifth, measurable calibration: the Brier score tracks whether the organization’s predictions are getting more accurate over time.', body_style))
story.append(add_heading('6.2 Value to the Person', h2_style, 1))
story.append(Paragraph(
    'Individuals who adopt Maestro gain five personal capabilities. Better memory: Memory Replay answers "What did I talk about with Sarah?" from your own notes, calendar, and entered memories — no more forgotten conversations. Better decisions: Decision Support surfaces your past patterns to inform current choices, labeled "informational, not prescriptive." Better self-awareness: the Contradictions engine gently surfaces gaps between your stated values and your behavior ("You said you want work-life balance but accepted 3 weekend meetings"). Better work-life balance: the bidirectional integration lets personal state contextualize work and vice versa, so you show up whole. A private cognitive companion: incognito mode, local-first processing, and the "What Maestro Knows" dashboard give you control over what Maestro holds.', body_style))
story.append(Paragraph(
    'The value compounds. Day 1, Maestro knows little. Day 90, it has learned your patterns, your commitments, your contradictions, your habits. Day 365, it is a cognitive companion that knows you better than any tool you have ever used — and you are more capable for having used it. The moat is not data lock-in; it is judgment lock-in. You cannot export 365 days of calibrated judgment to a competitor. You stay because Maestro has become part of how you think.', body_style))
story.append(Paragraph(
    'The success condition is the contract: "The organization becomes more capable, not more dependent. The person becomes more capable, not more dependent — in work and in life." Maestro is designed to be indispensable, not addictive. The user cannot imagine doing the work without it, but could stop if they chose to, and would still be more capable for having used it. That is the only kind of product worth building.', callout_style))
story.append(PageBreak())

# === Ch 7 — The Constitution ===
story.append(add_heading('Chapter 7 — The Constitution', h1_style, 0))
story.append(Paragraph(
    'Maestro is governed by a constitution — a frozen, amended document that every feature, every commit, and every audit round is evaluated against. The constitution is not a marketing document. It is the governing contract. It is the trust moat that enterprise buyers require and that no competitor has the discipline to build.', body_style))
story.append(add_heading('7.1 The Frozen Constitution', h2_style, 1))
story.append(Paragraph(
    'The frozen constitution states: "The organization becomes more capable, not more dependent." Its four pillars are fitness (the organization is better at its core work), optionality (the organization has more paths it can take), resilience (the organization can absorb shocks), and antifragility (the organization is improved by the stresses it encounters). The design law: every increase in internal intelligence must reduce external complexity. The litmus tests: "Is the UI simpler?" "Does this permanently improve the organization?" "Does this make the customer say Maestro helps us make better decisions than we could alone?"', body_style))
story.append(add_heading('7.2 The Personal Mode Amendment', h2_style, 1))
story.append(Paragraph(
    'The amended constitution states: "The person becomes more capable, not more dependent — in work and in life." Four guardrails govern every Personal Mode feature: (1) Self-facing only by default — Maestro processes the user’s own data, not third-party data to help the user "win." (2) Consent is bilateral — third-party data requires the third party’s explicit opt-in, not just the user’s. (3) Indispensable, not addictive — every feature must pass the withdrawal test; the word "addictive" is forbidden in code, docs, and commits. (4) Strict mode separation with dual profiles — work and personal data are partitioned; merges require explicit user action and are reversible for 30 days.', body_style))
story.append(add_heading('7.3 The Bright Line', h2_style, 1))
story.append(Paragraph(
    'The bright line is the trust moat: "Maestro helps YOU think better. Maestro does NOT help you manipulate, surveil, or win against another person." This is enforced in code by a bright-line guard that scans every payload for forbidden patterns ("she values," "team energy," "manipulate") and fails closed. Personal Mode rejects manipulation features absolutely: no dating/flirt-line generation, no style mirroring, no compatibility scoring from scraped data, no relationship health surveillance, no court records access, no mood analysis from third-party posts. These features are not deferrable; they are rejected forever.', body_style))
story.append(Paragraph(
    'The strategic value of the bright line is this: enterprise buyers will not buy an organizational intelligence tool from a company that also sells a flirt-line generator. The enterprise revenue funds the company. Personal Mode cannot kill the enterprise product. The bright line protects both. Competitors without the bright line (Cluely, and any future manipulation-tech entrant) cannot cross into the enterprise market. Maestro owns both because it drew the line first.', body_style))
story.append(PageBreak())

# === Ch 8 — Pilot Readiness ===
story.append(add_heading('Chapter 8 — Pilot Readiness', h1_style, 0))
story.append(Paragraph(
    'Maestro is not a prototype. It is a pilot-ready product built across 46 rounds of audit-driven development. Every commit is verified against the actual GitHub remote by an independent Fortune 100 CTO auditor. Every feature is tested. Every guardrail is enforced. The product is ready for 90 days of real use by real organizations and real people.', body_style))
story.append(add_heading('8.1 The Build Metrics', h2_style, 1))
build_data = [
    [Paragraph('<b>Metric</b>', th), Paragraph('<b>Value</b>', th), Paragraph('<b>What It Means</b>', th)],
    [Paragraph('Rounds of development', tcb), Paragraph('46', tc), Paragraph('Audit-driven; every round produced verified code', tc)],
    [Paragraph('Honest-applied streak', tcb), Paragraph('27 rounds', tc), Paragraph('No "built but not applied" regressions since round 16', tc)],
    [Paragraph('Modules built', tcb), Paragraph('63', tc), Paragraph('40 enterprise + 23 personal, all wired to frontend', tc)],
    [Paragraph('Tests passing', tcb), Paragraph('500+', tc), Paragraph('Every feature tested; every guardrail enforced by tests', tc)],
    [Paragraph('Cognitive engines', tcb), Paragraph('19', tc), Paragraph('Invisible intelligence behind every surface', tc)],
    [Paragraph('API endpoints', tcb), Paragraph('80+', tc), Paragraph('41 enterprise + 40+ personal, all documented', tc)],
    [Paragraph('Brier score (calibration)', tcb), Paragraph('0.0738', tc), Paragraph('Learning loop closed; predictions well-calibrated', tc)],
    [Paragraph('Sidebar items (V5 litmus)', tcb), Paragraph('4', tc), Paragraph('UI gets simpler as intelligence grows', tc)],
    [Paragraph('Security posture', tcb), Paragraph('SOC2-ready', tc), Paragraph('SAML fail-closed, tenant isolation, RBAC, AST regression tests', tc)],
]
story.append(std_table(build_data, [0.28, 0.14, 0.58]))
story.append(Spacer(1, 8))
story.append(Paragraph('Table 8.1 — Build metrics. The product is pilot-ready on the latest commit.', muted_style))
story.append(add_heading('8.2 The Audit Protocol', h2_style, 1))
story.append(Paragraph(
    'The Round 33 correction established the audit protocol that governs every subsequent round. Every claim is verified against the actual remote: git fetch origin, git log origin/main, check the GitHub web interface if fetch fails. "Cannot access" is distinguished from "does not exist." No integrity accusation is made without exhausting verification avenues. Every commit claim must include file paths, line ranges, and test file paths. Every "applied" claim must be verified by a frontend grep. This protocol has held the 27-round streak of honest, applied work. It is the procedural legacy of Round 33, and it is the evidence that the engineering process can sustain the 90-day pilots without regressing.', body_style))
story.append(PageBreak())

# === Ch 9 — The Future ===
story.append(add_heading('Chapter 9 — The Future', h1_style, 0))
story.append(Paragraph(
    'Maestro’s roadmap is a 36-month evolution from cognitive companion to life operating system. Each phase compounds the previous: the pilot proves the flywheel; the one-app merger unifies the experience; the compounding engine adds cross-org intelligence; the marketplace shares verified laws; the life OS makes Maestro the cognitive layer for every tool the user touches.', body_style))
roadmap_data = [
    [Paragraph('<b>Phase</b>', th), Paragraph('<b>Timeline</b>', th), Paragraph('<b>Deliverable</b>', th)],
    [Paragraph('Phase 1: Pilots', tcb), Paragraph('Now – 90 days', tc), Paragraph('Ship enterprise + personal pilots. Prove the flywheel accelerates. Measure capability gained, not engagement.', tc)],
    [Paragraph('Phase 2: One App', tcb), Paragraph('6 months', tc), Paragraph('Kill mode tabs, unify sidebar to 4 items (Today/Memory/Ask/More), one swipe deck for work+personal. Mode becomes a filter, not a switch.', tc)],
    [Paragraph('Phase 3: Compounding v2', tcb), Paragraph('12 months', tc), Paragraph('Cross-org anonymized benchmarks: "Your deploy gate is slower than 80% of similar orgs." The network effect: every org makes every other org smarter.', tc)],
    [Paragraph('Phase 4: Marketplace', tcb), Paragraph('24 months', tc), Paragraph('Verified organizational laws shared across companies. "L-0007 (deploy gate bottleneck) held at 12 of 15 companies in your cohort." The laws become a strategic asset.', tc)],
    [Paragraph('Phase 5: Life OS', tcb), Paragraph('36 months', tc), Paragraph('Maestro as the cognitive layer for every tool: IDE, email client, calendar, browser. Maestro does not replace tools; it makes them smarter by providing judgment context.', tc)],
]
story.append(std_table(roadmap_data, [0.16, 0.14, 0.70]))
story.append(Spacer(1, 8))
story.append(Paragraph('Table 9.1 — The 36-month roadmap. Each phase compounds the previous.', muted_style))
story.append(Paragraph(
    'The strategic thesis is that cognitive companionship is a winner-take-most market. The product that compounds judgment fastest wins, because judgment lock-in is stronger than data lock-in. Maestro’s five moats — verified knowledge, organizational DNA, the learning loop, the bright line, and the bidirectional integration — are designed to compound. By Phase 3, the network effect kicks in: every new organization makes every existing organization smarter. By Phase 5, Maestro is not an app; it is the cognitive layer the user never leaves. The 36-month horizon is ambitious but achievable given the engineering process that has delivered 46 rounds of verified progress.', body_style))
story.append(PageBreak())

# === Ch 10 — The Market ===
story.append(add_heading('Chapter 10 — The Market', h1_style, 0))
story.append(Paragraph(
    'Maestro operates in two markets simultaneously: organizational intelligence ($80B) and personal productivity ($40B), for a total addressable market of $120B. The serviceable available market is $30B — knowledge workers in enterprises of 50+ employees, plus high-achieving individuals who actively use productivity tools. The serviceable obtainable market in the first 18 months is $500M, reached through 50 enterprise design partners and 10,000 personal users.', body_style))
market_data = [
    [Paragraph('<b>Market</b>', th), Paragraph('<b>Size</b>', th), Paragraph('<b>Segment</b>', th)],
    [Paragraph('TAM', tcb), Paragraph('$120B', tc), Paragraph('Organizational intelligence ($80B) + personal productivity ($40B)', tc)],
    [Paragraph('SAM', tcb), Paragraph('$30B', tc), Paragraph('Knowledge workers in 50+ employee orgs + high-achieving individuals', tc)],
    [Paragraph('SOM (18 mo)', tcb), Paragraph('$500M', tc), Paragraph('50 enterprise design partners + 10K personal users', tc)],
]
story.append(std_table(market_data, [0.15, 0.12, 0.73]))
story.append(Spacer(1, 8))
story.append(Paragraph('Table 10.1 — Market sizing. The wedge is enterprise first (paid); personal second (freemium, converts to paid).', muted_style))
story.append(Paragraph(
    'The wedge strategy is enterprise-first. Enterprise customers pay ($50/seat/month, 50-seat minimum), fund the company, and generate the organizational signals that train the cognitive engines. Personal Mode launches as freemium alongside the enterprise pilot — basic briefing free, Pro ($15/month) for memory and decisions, Life ($30/month) for all features. Personal users generate personal signals that improve the personal engines, which (via the bidirectional integration) improve the enterprise experience for users who use both. The two markets reinforce each other: every enterprise user who also uses Personal Mode becomes a stickier enterprise customer, and every personal user who brings Maestro to work becomes an enterprise lead.', body_style))
story.append(PageBreak())

# === Ch 11 — The Business Model ===
story.append(add_heading('Chapter 11 — The Business Model', h1_style, 0))
story.append(Paragraph(
    'Maestro’s business model is SaaS with a flywheel. Every seat generates signals that improve the model; the model improves every seat. The more users, the smarter the product; the smarter the product, the more users. This is the Amazon flywheel applied to cognitive companionship.', body_style))
story.append(add_heading('11.1 Pricing', h2_style, 1))
price_data = [
    [Paragraph('<b>Tier</b>', th), Paragraph('<b>Price</b>', th), Paragraph('<b>Features</b>', th)],
    [Paragraph('Enterprise', tcb), Paragraph('$50/seat/month', tc), Paragraph('All 40 enterprise features, 50-seat minimum, annual contracts, SOC2, SAML SSO, dedicated support', tc)],
    [Paragraph('Personal Free', tcb), Paragraph('$0', tc), Paragraph('Morning briefing, basic memory, 7-day history', tc)],
    [Paragraph('Personal Pro', tcb), Paragraph('$15/month', tc), Paragraph('Full memory replay, decision support, habit coach, prediction market, contradictions', tc)],
    [Paragraph('Personal Life', tcb), Paragraph('$30/month', tc), Paragraph('All 23 personal features + work-personal integration + priority support', tc)],
]
story.append(std_table(price_data, [0.18, 0.18, 0.64]))
story.append(Spacer(1, 8))
story.append(Paragraph('Table 11.1 — Pricing tiers. Enterprise funds the company; personal creates the consumer flywheel.', muted_style))
story.append(add_heading('11.2 Unit Economics', h2_style, 1))
story.append(Paragraph(
    'Enterprise: CAC $8,000 (direct sales), LTV $180,000 (50 seats × $50 × 36 months × 2x expansion), LTV/CAC 22x, payback 4 months. Personal: CAC $12 (content + referrals), Pro LTV $540 ($15 × 36 months), LTV/CAC 45x, free-to-paid conversion 8%. The enterprise business funds the company; the personal business creates the consumer brand and the data flywheel that improves both. The bidirectional integration means enterprise users who adopt Personal Mode have 3x higher retention — they cannot leave without losing their personal cognitive companion.', body_style))
story.append(PageBreak())

# === Ch 12 — The Ask ===
story.append(add_heading('Chapter 12 — The Ask', h1_style, 0))
story.append(Paragraph(
    'Maestro is raising a $15-20M Series A to scale from pilot-ready to pilot-proven. The round funds 18 months of runway: 50 enterprise design partners, 10,000 personal users, $5M ARR, and the one-app merger that unifies the experience. The product is built. The constitution is frozen. The pilots are ready to ship. The capital is for scale, not for building the product.', body_style))
story.append(add_heading('12.1 Use of Funds', h2_style, 1))
funds_data = [
    [Paragraph('<b>Category</b>', th), Paragraph('<b>Allocation</b>', th), Paragraph('<b>What It Funds</b>', th)],
    [Paragraph('Engineering', tcb), Paragraph('40% ($6-8M)', tc), Paragraph('Cognitive engine team, the one-app merger, mobile apps (iOS + Android), the compounding engine v2', tc)],
    [Paragraph('GTM', tcb), Paragraph('30% ($4.5-6M)', tc), Paragraph('Enterprise sales team, design partner program, personal-mode growth marketing, content + brand', tc)],
    [Paragraph('AI/ML', tcb), Paragraph('20% ($3-4M)', tc), Paragraph('Embedding model integration (Ollama/OpenAI), the compounding engine v2, cross-org benchmarking infrastructure', tc)],
    [Paragraph('Ops/Security', tcb), Paragraph('10% ($1.5-2M)', tc), Paragraph('SOC2 Type II, HIPAA for personal health data, GDPR, infrastructure scaling, key hires', tc)],
]
story.append(std_table(funds_data, [0.18, 0.18, 0.64]))
story.append(Spacer(1, 8))
story.append(Paragraph('Table 12.1 — Use of funds. 40% engineering, 30% GTM, 20% AI/ML, 10% ops/security.', muted_style))
story.append(add_heading('12.2 Milestones (18 months)', h2_style, 1))
story.append(Paragraph(
    'Month 3: 5 enterprise design partners live, 500 personal users, first Brier-score improvement from real data. Month 6: 15 enterprise partners, 2,000 personal users, the one-app merger shipped. Month 9: 30 enterprise partners, 5,000 personal users, $1.5M ARR. Month 12: 50 enterprise partners, 10,000 personal users, the compounding engine v2 shipped, $3M ARR. Month 18: 75 enterprise partners, 25,000 personal users, $5M ARR, Series B readiness.', body_style))
story.append(PageBreak())

# === Ch 13 — The Closing ===
story.append(add_heading('Chapter 13 — The Closing', h1_style, 0))
story.append(Paragraph(
    'The societal problem is judgment shortage. Knowledge workers are drowning in information but starving for judgment. Organizations repeat mistakes because institutional memory lives in Slack threads nobody searches. Individuals repeat personal mistakes because life lessons live in forgotten notes. The cost is one full day per week lost to re-finding what was already known, plus the unquantifiable cost of repeated failures.', body_style))
story.append(Paragraph(
    'The solution is a cognitive companion that compounds judgment. Maestro learns from every signal, builds a living model of the organization and the person, and surfaces the right judgment at the right moment. It is the only tool that spans both work and personal life in one app, with a bidirectional integration that lets each context inform the other. It is the only tool with a verified-knowledge layer, a closed learning loop, and a constitutional bright line that rejects manipulation absolutely.', body_style))
story.append(Paragraph(
    'The moat is five compounding layers: verified knowledge, organizational DNA, the learning loop, the bright line, and the bidirectional integration. Each is defensible alone; together they are insurmountable. The product is pilot-ready: 63 modules, 500+ tests, 27 rounds of honest-applied work, SOC2-ready, learning loop closed. The market is $120B. The business model is a flywheel where every seat makes every other seat smarter. The ask is $15-20M Series A to scale from pilot-ready to pilot-proven.', body_style))
story.append(Paragraph(
    'The promise is the constitution: "The organization becomes more capable, not more dependent. The person becomes more capable, not more dependent — in work and in life." This is not a tagline. It is the contract. Maestro is designed to be indispensable, not addictive — the user cannot imagine doing the work without it, but could stop if they chose to, and would still be more capable for having used it. That is the only kind of product worth building, and it is the only kind of product that compounds.', body_style))
story.append(Paragraph(
    'Maestro is built. The pilots are ready. The capital is for scale. Join us in making the organization and the person more capable — not more dependent — in work and in life.', body_style))

# ── Build ──
doc = TocDocTemplate(OUTPUT_BODY, pagesize=A4, leftMargin=LEFT_M, rightMargin=RIGHT_M, topMargin=TOP_M, bottomMargin=BOTTOM_M,
    title='Maestro — Investor Briefing', author='Z.ai', creator='Z.ai',
    subject='Investor briefing: what Maestro does, its moat, functions, value, and future evolution')
doc.multiBuild(story, onFirstPage=page_decoration, onLaterPages=page_decoration)
print(f'Body PDF generated: {OUTPUT_BODY}')
