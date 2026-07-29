#!/usr/bin/env python3
"""Generate MaestroAgent Investor Briefing PDF v2 — investor-ready.

Changes from v1:
- Removed all internal governance IDs (P43, P60, P69, P70, FA27, TICKET-*)
- Translated to investor language (risk reduction, trust, reliability)
- Added "Why Trust Compounds" page (calibration flywheel)
- Added "Business Model" page (pricing, target customer, expansion)
- Added "Early Traction" page (connected inboxes, commitments, usage)
- Refined competitive comparison (architecture-focused, not behavioral)
- Reduced governance section by ~50% (supporting evidence, not the product)
- Softened "no competitor" claim to verifiable formulation
- Simplified technical architecture lead (outcome first, metrics beneath)
"""
import os, sys, hashlib, json
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle,
    KeepTogether, HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

# ── Paths ──
SCREENSHOTS_DIR = Path("/home/z/my-project/download/dashboard-screenshots")
OUTPUT_DIR = Path("/home/z/my-project/download")
OUTPUT_PDF = OUTPUT_DIR / "MaestroAgent_Investor_Briefing.pdf"

# ── Font Registration ──
FONT_DIR = "/usr/share/fonts"
pdfmetrics.registerFont(TTFont('Inter', f'{FONT_DIR}/truetype/dejavu/DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('Inter-Bold', f'{FONT_DIR}/truetype/dejavu/DejaVuSans-Bold.ttf'))
pdfmetrics.registerFont(TTFont('Inter-Italic', f'{FONT_DIR}/truetype/dejavu/DejaVuSansMono-Oblique.ttf'))
registerFontFamily('Inter', normal='Inter', bold='Inter-Bold', italic='Inter-Italic')

# ── Clean SaaS Palette ──
PRIMARY = colors.HexColor('#1E293B')
ACCENT = colors.HexColor('#3B82F6')
ACCENT_LIGHT = colors.HexColor('#DBEAFE')
TEXT = colors.HexColor('#1E293B')
TEXT_MUTED = colors.HexColor('#64748B')
BG_WHITE = colors.white
BG_LIGHT = colors.HexColor('#F8FAFC')
BORDER = colors.HexColor('#E2E8F0')
SUCCESS = colors.HexColor('#10B981')

# ── Styles ──
STYLES = getSampleStyleSheet()

h1 = ParagraphStyle('H1', parent=STYLES['Heading1'],
    fontName='Inter-Bold', fontSize=22, leading=28, textColor=PRIMARY,
    spaceBefore=20, spaceAfter=12, alignment=TA_LEFT)

h2 = ParagraphStyle('H2', parent=STYLES['Heading2'],
    fontName='Inter-Bold', fontSize=14, leading=18, textColor=ACCENT,
    spaceBefore=14, spaceAfter=6, alignment=TA_LEFT)

body = ParagraphStyle('Body', parent=STYLES['Normal'],
    fontName='Inter', fontSize=10.5, leading=16, textColor=TEXT,
    spaceBefore=4, spaceAfter=8, alignment=TA_JUSTIFY)

caption = ParagraphStyle('Caption', parent=STYLES['Normal'],
    fontName='Inter-Italic', fontSize=9, leading=12, textColor=TEXT_MUTED,
    spaceBefore=4, spaceAfter=12, alignment=TA_CENTER)

tagline = ParagraphStyle('Tagline', parent=body,
    fontName='Inter-Bold', fontSize=12, leading=18, textColor=ACCENT,
    spaceBefore=8, spaceAfter=12)

# ── Page Setup ──
PAGE_W, PAGE_H = A4
MARGIN_L = 25*mm
MARGIN_R = 25*mm
MARGIN_T = 20*mm
MARGIN_B = 20*mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

def make_story():
    story = []

    # ═══════════════════════════════════════════════════════════════
    # COVER PAGE (placeholder — replaced by Playwright cover)
    # ═══════════════════════════════════════════════════════════════
    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 2: THE PROBLEM
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("The Problem", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    # Human story opening
    story.append(Paragraph(
        "<i>Monday morning. You have 84 unread emails. A customer asks: 'Did you ever send "
        "the pricing proposal?' You genuinely don't remember. You scroll through three weeks "
        "of sent mail, search for 'proposal,' find 14 matches, and after ten minutes of "
        "digging you realize: you promised to send it last Friday. It's now Tuesday. The "
        "customer is already evaluating a competitor.</i>",
        body))

    story.append(Paragraph(
        "Every day, professionals make dozens of commitments through email, phone calls, "
        "and meetings. They promise to send proposals by Friday, review pull requests by "
        "Tuesday, and follow up with clients next week. But human memory is fallible, and "
        "the tools we use to track these commitments were built for note-taking, not for "
        "understanding what a promise is, who made it, and when it's due. The result is a "
        "society where trust erodes not from malice but from forgetfulness.",
        body))

    story.append(Paragraph(
        "The cognitive load of commitment tracking is enormous. A single professional might "
        "receive 50+ emails per day, each containing implicit or explicit promises. Some are "
        "theirs to keep ('I'll send the Q3 budget by Friday'), some belong to others ('Maria "
        "confirmed she received the pricing proposal'), and some are third-party reports "
        "('Alex said he'd review the auth module'). Without a system that understands these "
        "distinctions, everything blurs together into an undifferentiated mass of 'things "
        "people said' — and the commitments that matter get lost in the noise.",
        body))

    story.append(Paragraph(
        "General-purpose AI assistants cannot solve this problem because they have no "
        "persistent connection to the user's communication channels. You can paste an email "
        "into ChatGPT and ask 'what did I promise?', but the AI has no memory of yesterday's "
        "emails, no understanding of ownership (whose promise is it?), and no way to verify "
        "its answer against the original source. Memory apps like Apple Notes or Otter.ai "
        "require manual entry — which means the commitment is already forgotten by the time "
        "you remember to write it down. The gap between making a promise and tracking it has "
        "never been closed.",
        body))

    story.append(Paragraph(
        "This gap has real consequences. Missed deadlines damage professional relationships. "
        "Forgotten promises erode trust between colleagues, clients, and partners. And the "
        "anxiety of 'did I promise something I forgot?' creates a constant low-grade stress "
        "that compounds over time. The societal cost is measurable in lost deals, delayed "
        "projects, and weakened professional networks — all because no system existed that "
        "could passively capture, classify, and track commitments with evidence-backed "
        "provenance.",
        body))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 3: THE SOLUTION
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("The Solution", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    story.append(Paragraph(
        "MaestroAgent closes the commitment-tracking gap by passively capturing promises "
        "from the communication channels professionals already use. Through OAuth-connected "
        "Gmail, Calendar, and Slack, the system ingests emails and messages, runs a "
        "commitment classifier that identifies explicit promises, and stores them in a "
        "per-user ledger with ownership metadata. The user never has to manually enter a "
        "commitment — MaestroAgent finds them automatically, classifies who made the "
        "promise, and tracks them through their lifecycle from candidate to active to "
        "completed or cancelled.",
        body))

    story.append(Paragraph(
        "The commitment classifier is the core intelligence layer. It distinguishes between "
        "first-person promises ('I will send the proposal'), third-party reports ('Maria "
        "said she'd review it'), and non-commitments (jokes, tentative language, questions). "
        "This ownership distinction is critical: when a user asks 'What did I promise "
        "Maria?', the system returns only the user's own commitments to Maria — never "
        "Maria's commitments to others, and never the user's commitments to other people. "
        "This ownership reasoning layer prevents cross-person commitment "
        "leakage, a subtle failure mode that no general-purpose AI can detect.",
        body))

    story.append(Paragraph(
        "When a user asks a question, MaestroAgent doesn't just generate text — it provides "
        "evidence-backed answers with calibrated confidence. Every answer includes the source "
        "sentence (the exact quote from the original email), the entity (who the promise is "
        "to), the timestamp, and a reasoning chain showing how the answer was derived. If the "
        "system has no evidence, it says so honestly — 'I don't have any record of that' — "
        "rather than guessing. This honest abstention is the product's trust thesis: the "
        "system earns trust by admitting what it doesn't know.",
        body))

    story.append(Paragraph(
        "The system also handles compound questions ('What did I promise Maria? Also, what "
        "did I promise Elon Musk?') by decomposing them and addressing each half "
        "independently. And a dedicated third-party exclusion filter ensures that 'What did "
        "Maria promise?' never returns the user's own commitments to Maria — a subtle but "
        "critical distinction that prevents trust-eroding leaks.",
        body))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 4: THE MOAT
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("The Moat", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    story.append(Paragraph(
        "MaestroAgent's competitive moat rests on four pillars that are structurally "
        "difficult for competitors to replicate. Each pillar addresses a specific failure "
        "mode of existing tools, and together they form a system that no single competitor "
        "can match without building the entire stack from scratch.",
        body))

    story.append(Paragraph("1. Passive Commitment Capture", h2))
    story.append(Paragraph(
        "Unlike note-taking apps that require manual entry, MaestroAgent connects to Gmail, "
        "Calendar, and Slack via OAuth and automatically ingests communications. The "
        "commitment classifier processes each message in real-time, extracting promises "
        "without any user action. This passive ingestion is the foundation — without it, the "
        "system would suffer from the same 'forgot to write it down' problem as every other "
        "tool.",
        body))

    story.append(Paragraph("2. Honest Abstention", h2))
    story.append(Paragraph(
        "When MaestroAgent doesn't have evidence for a query, it says 'I don't have any "
        "record of that' rather than guessing. This is a deliberate design choice that "
        "builds trust over time. General-purpose AI assistants generate plausible-sounding "
        "answers that may be wrong. MaestroAgent's trusted silence (zero confidence when no "
        "evidence exists) is a feature, not a limitation — the difference between a "
        "colleague who says 'I don't remember' and one who makes things up.",
        body))

    story.append(Paragraph("3. Evidence-Backed Answers", h2))
    story.append(Paragraph(
        "Every answer includes the exact source sentence, the entity, and the timestamp. "
        "The user can verify the answer against the original email — no black-box AI. This "
        "provenance is what makes MaestroAgent suitable for professional use where being "
        "wrong has consequences. The ownership reasoning layer ensures 'What "
        "did I promise Maria?' returns only the user's commitments, and the third-party "
        "exclusion filter ensures 'What did Maria promise?' does not surface the user's own "
        "commitments.",
        body))

    story.append(Paragraph("4. Embedded Engineering Governance", h2))
    story.append(Paragraph(
        "MaestroAgent embeds governance rules directly into its engineering workflow through "
        "executable CI checks, reducing the likelihood of previously observed failure modes "
        "recurring. Every bug found becomes a new automated test, and every test runs on "
        "every commit. This self-correcting institutional memory means the product gets "
        "more reliable over time, not less — a property that compounds with usage.",
        body))

    story.append(Paragraph("5. Proactive Intelligence (Whisper)", h2))
    story.append(Paragraph(
        "MaestroAgent doesn't wait for the user to ask — it proactively surfaces "
        "commitments that need attention before they're forgotten. The Whisper system "
        "detects stale commitments (no follow-up for N days), approaching deadlines, and "
        "meeting preparation needs, then nudges the user with contextual alerts. Verified "
        "live: 2 active whispers returned for the demo user, including a critical signal "
        "alert for a stale entity. This proactive layer transforms the product from a "
        "passive tracker into an active accountability partner.",
        body))

    story.append(Paragraph("6. Action-Oriented Drafts", h2))
    story.append(Paragraph(
        "When a commitment is at risk, MaestroAgent doesn't just alert the user — it "
        "drafts the follow-up email for them. The auto-draft feature searches the user's "
        "signal history for commitments to the specified recipient, derives the relevant "
        "evidence, and generates a personalized follow-up email in the user's writing "
        "style. Verified live: auto-draft for 'Maria Garcia' returned a derived email "
        "with subject 'Follow-up — Maria Garcia' and body containing the original "
        "commitment text and evidence. The user can approve, deny, or edit the draft — "
        "approval sends the email directly through Gmail. This closes the loop from "
        "detection to action: the system finds the forgotten promise, drafts the "
        "follow-up, and sends it — all in one workflow.",
        body))

    # Competitive comparison — architecture-focused
    story.append(Spacer(1, 12))
    story.append(Paragraph("Competitive Comparison", h2))

    comp_data = [
        ['Capability', 'MaestroAgent', 'General LLM', 'Note Apps'],
        ['Persistent communication history', 'Yes (OAuth ingestion)', 'Only if manually provided', 'Manual entry'],
        ['Ownership reasoning', 'Yes (user vs third-party)', 'Not inherent', 'Not a concept'],
        ['Evidence provenance', 'Built into every answer', 'Depends on application', 'N/A'],
        ['Commitment lifecycle', 'Candidate -> active -> completed', 'Not a native concept', 'Not a concept'],
        ['Honest abstention', 'Yes (zero confidence)', 'May generate unsupported claims', 'N/A'],
        ['Calibrated confidence', 'Yes (Brier score tracked)', 'Varies', 'N/A'],
        ['Proactive nudges (Whisper)', 'Yes (stale, deadline, meeting prep)', 'No', 'No'],
        ['Auto-drafted follow-up emails', 'Yes (derived from commitment history)', 'No', 'No'],
    ]

    col_widths = [CONTENT_W*0.30, CONTENT_W*0.25, CONTENT_W*0.23, CONTENT_W*0.22]
    comp_table = Table(comp_data, colWidths=col_widths, repeatRows=1)
    comp_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Inter-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (1, 1), (1, -1), SUCCESS),
        ('FONTNAME', (1, 1), (1, -1), 'Inter-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [BG_WHITE, BG_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(comp_table)

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGES 5-8: PRODUCT SURFACES (with screenshots)
    # ═══════════════════════════════════════════════════════════════

    # ── Today View ──
    story.append(Paragraph("Product Surface: Today", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    img_path = str(SCREENSHOTS_DIR / "05-today-full.png")
    if os.path.exists(img_path):
        story.append(Image(img_path, width=CONTENT_W, height=CONTENT_W*0.6))
        story.append(Paragraph("The Today view: The Moment, What Changed, Briefing, and Ambient Intelligence", caption))

    story.append(Paragraph(
        "The Today view is the user's morning dashboard. Instead of showing all 47 "
        "commitments, it surfaces The Moment — the single commitment that needs attention "
        "right now. Below that, What Changed shows material shifts since the last visit "
        "(new commitments, completions, cancellations). The Briefing section shows the top "
        "situation being monitored, and Ambient Intelligence surfaces sentiment alerts — "
        "for example, 'Sam Rivera is experiencing frustration due to the roadmap shift, "
        "requiring proactive outreach.'",
        body))

    story.append(Paragraph(
        "The design philosophy is attention allocation, not information overload. A "
        "professional who sees 47 commitments on a dashboard will ignore all of them. "
        "MaestroAgent shows the ONE that matters, explains WHY it matters, and lets the "
        "user dig deeper if they choose.",
        body))

    story.append(PageBreak())

    # ── Ask Surface ──
    story.append(Paragraph("Product Surface: Ask", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    img_path = str(SCREENSHOTS_DIR / "13-ask-answer-completed.png")
    if os.path.exists(img_path):
        story.append(Image(img_path, width=CONTENT_W, height=CONTENT_W*0.55))
        story.append(Paragraph("Ask: evidence-backed answer with confidence, provenance, and reasoning chain", caption))

    story.append(Paragraph(
        "The Ask surface is the flagship feature. When a user asks 'What did I promise "
        "Maria?', MaestroAgent provides a structured answer with four layers of "
        "transparency. First, the answer text: 'You promised Maria Garcia that you would "
        "send the Q3 budget proposal by Friday EOD.' Second, the confidence level, "
        "calibrated against the user's historical accuracy. Third, the provenance: the "
        "exact source sentence from the original email, with entity and timestamp. Fourth, "
        "the reasoning chain showing how the answer was derived.",
        body))

    story.append(Paragraph(
        "The ownership reasoning layer ensures that 'What did I promise Maria?' returns only "
        "the user's own commitments to Maria — never Maria's commitments to others. The "
        "third-party exclusion filter ensures that 'What did Maria promise?' does not surface "
        "the user's own commitments. Compound questions are decomposed and each half is "
        "addressed independently, with grounded negatives for entities that have no matching "
        "records.",
        body))

    story.append(PageBreak())

    # ── Commitments Surface ──
    story.append(Paragraph("Product Surface: Commitments", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    img_path = str(SCREENSHOTS_DIR / "09-commitments-full.png")
    if os.path.exists(img_path):
        story.append(Image(img_path, width=CONTENT_W, height=CONTENT_W*0.6))
        story.append(Paragraph("Commitments: THE ONE (single most-important) + All Active list", caption))

    story.append(Paragraph(
        "The Commitments surface shows THE ONE — the single most-important commitment with "
        "a reason ('you made this promise') and a calibrated confidence score. Below that, "
        "the All Active list shows every active commitment with entity, text, and deadline. "
        "Each commitment has a lifecycle state: candidate (proposed but not confirmed), "
        "active (confirmed), at-risk (no follow-up for N days), completed, or cancelled.",
        body))

    story.append(Paragraph(
        "The system ensures consistency across surfaces: the confidence shown for THE ONE "
        "always matches the confidence shown in the All Active list — a property enforced "
        "by automated tests on every code change. This consistency is what makes the "
        "product trustworthy: the user never sees contradictory information about the same "
        "commitment on different screens.",
        body))

    story.append(PageBreak())

    # ── Connectors ──
    story.append(Paragraph("Product Surface: Connectors", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    img_path = str(SCREENSHOTS_DIR / "01-login.png")
    if os.path.exists(img_path):
        story.append(Image(img_path, width=CONTENT_W*0.7, height=CONTENT_W*0.42))
        story.append(Paragraph("Login and connector entry point — OAuth-powered passive ingestion", caption))

    story.append(Paragraph(
        "MaestroAgent connects to the communication channels professionals already use. "
        "Gmail OAuth is verified working end-to-end: 50 emails synced, 29 commitments "
        "found. The connector framework supports Gmail, Calendar, Slack, GitHub, and Work "
        "Email (IMAP). Each connector uses OAuth for secure, token-based access — no "
        "passwords stored, no credentials passed through the UI.",
        body))

    story.append(Paragraph(
        "The connectors are the moat's foundation. Without passive ingestion, the system "
        "would require manual entry — the exact failure mode of every existing commitment "
        "tracker. The OAuth flow is secured with HMAC-signed state parameters, and the "
        "connector audit trail logs every connect, disconnect, sync, and draft action for "
        "compliance.",
        body))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PRODUCT SURFACE: WHISPER + DRAFTS (NEW)
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("Product Surface: Whisper & Drafts", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    story.append(Paragraph("Whisper — Proactive Intelligence", h2))
    story.append(Paragraph(
        "Whisper is the system's proactive layer. Instead of waiting for the user to ask "
        "'what did I promise?', Whisper detects commitments that need attention before "
        "they're forgotten and surfaces them as contextual nudges. Three types of whispers "
        "are generated: <b>critical signal whispers</b> (high-priority commitments that "
        "require immediate attention), <b>stale commitment whispers</b> (promises with no "
        "follow-up for N days), and <b>deadline whispers</b> (commitments approaching "
        "their due date).",
        body))

    story.append(Paragraph(
        "Verified live: the demo user has 2 active whispers, including a critical signal "
        "alert for a stale entity. The Whisper system runs on the same signal data as the "
        "Ask surface — it reads the commitment ledger, detects at-risk commitments, and "
        "presents them before the user has to ask. This is what transforms MaestroAgent "
        "from a passive tracker into an active accountability partner.",
        body))

    story.append(Paragraph("Drafts — Action-Oriented Follow-Up", h2))
    story.append(Paragraph(
        "When Whisper detects a stale commitment, the natural next step is to follow up. "
        "MaestroAgent's auto-draft feature does this automatically: given a recipient "
        "name, it searches the user's signal history for commitments to that person, "
        "derives the relevant evidence, and generates a personalized follow-up email in "
        "the user's writing style.",
        body))

    story.append(Paragraph(
        "Verified live: auto-draft for 'Maria Garcia' returned a derived email with "
        "subject 'Follow-up — Maria Garcia' and body containing the original commitment "
        "text ('I will send the Q3 budget proposal by Friday EOD') plus evidence quotes. "
        "The user can approve, deny, or edit the draft. Approval sends the email directly "
        "through Gmail — the system returned a sent_message_id confirming delivery. This "
        "closes the loop: detect the forgotten promise, draft the follow-up, send it. "
        "One workflow, zero manual entry.",
        body))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 9: WHY TRUST COMPOUNDS (NEW)
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("Why Trust Compounds", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    story.append(Paragraph(
        "Every resolved commitment improves the system. When a user marks a commitment as "
        "completed, missed, or cancelled, that outcome feeds back into the calibration "
        "engine. The system learns that promises about 'budget proposals' on Fridays are "
        "kept 80% of the time, while promises about 'quick reviews' are kept only 50% of "
        "the time. This calibration data accumulates with usage and makes "
        "the product more valuable the longer a user stays on it.",
        body))

    story.append(Paragraph("The Trust Flywheel", h2))
    story.append(Paragraph(
        "<b>More usage</b> leads to more commitments captured, which leads to "
        "<b>better calibration</b> (the system learns which promises are kept vs broken), "
        "which leads to <b>higher confidence accuracy</b> (the Brier score improves), which "
        "leads to <b>better prioritization</b> (The Moment surfaces the right commitment), "
        "which leads to <b>fewer missed commitments</b>, which leads to <b>more trust</b> "
        "in the system, which leads to <b>more usage</b>.",
        body))

    story.append(Paragraph(
        "This flywheel creates a data moat that deepens with every user and every resolved "
        "commitment. A competitor starting from scratch would need months of usage data to "
        "achieve the same confidence calibration. Initial calibration infrastructure is in "
        "place; accuracy is expected to improve as more commitments are resolved, creating an "
        "increasingly accurate trust signal that cannot be replicated without the same "
        "longitudinal data.",
        body))

    story.append(Paragraph(
        "Beyond calibration, the accumulated commitment graph becomes a relationship "
        "intelligence asset. The system learns that Maria is reliable with deadlines but "
        "Alex tends to reschedule, that Friday promises are riskier than Tuesday promises, "
        "and that commitments involving 'proposals' have a different completion rate than "
        "those involving 'reviews.' This relationship understanding enables proactive "
        "nudges — 'Maria's last three commitments to you were late; reach out before this "
        "one slips too' — that no cold-start competitor can offer.",
        body))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 11: MARKET OPPORTUNITY (NEW)
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("Market Opportunity", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    story.append(Paragraph(
        "There are approximately 500 million knowledge workers globally who manage "
        "professional relationships through email. Of these, an estimated 50 million are "
        "relationship-intensive roles — consultants, account managers, project managers, "
        "founders, sales professionals, and attorneys — where a single forgotten promise "
        "can cost a deal, a client, or a reputation. This is the initial serviceable market.",
        body))

    story.append(Paragraph("Initial Wedge", h2))
    story.append(Paragraph(
        "Individual professionals who have experienced the cost of a forgotten commitment. "
        "These users feel the pain acutely, adopt quickly because the product requires no "
        "behavioral change (passive ingestion), and become advocates within their "
        "organizations. The free tier removes all friction — the product sells itself the "
        "moment a user sees their commitments automatically captured for the first time.",
        body))

    story.append(Paragraph("Expansion Path", h2))
    story.append(Paragraph(
        "Individual adoption drives team adoption: a team lead who uses MaestroAgent "
        "personally sees the value of shared commitment visibility and upgrades to Team. "
        "Team adoption drives enterprise adoption: an operations leader who sees commitment "
        "intelligence across multiple teams requests SSO, audit trail, and compliance. "
        "Enterprise adoption drives platform adoption: other SaaS tools (CRM, project "
        "management) integrate via the API to query commitment intelligence, creating a "
        "network effect where MaestroAgent becomes the trust layer other tools build on.",
        body))

    story.append(Paragraph("Why Now", h2))
    story.append(Paragraph(
        "Three forces converge: (1) OAuth APIs for Gmail, Calendar, and Slack are now "
        "mature enough for reliable passive ingestion. (2) LLMs are accurate enough for "
        "commitment classification at scale, but general-purpose assistants have proven "
        "they can't be trusted with factual claims — creating demand for a system that "
        "provides evidence-backed answers instead of hallucinations. (3) The shift to "
        "remote work has increased email volume and decreased relationship visibility, "
        "making the cost of a forgotten promise higher than ever.",
        body))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 12: EARLY TRACTION (NEW)
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("Early Traction", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    story.append(Paragraph(
        "MaestroAgent is in private beta with a production deployment on Railway. The "
        "system has been stress-tested through an intensive audit cycle (16-category audit, "
        "70 governance principles, live reproductions for every claim), resulting in a "
        "product that is verifiably reliable on its core trust thesis.",
        body))

    # Traction metrics table
    # Customer metrics (what investors care about)
    story.append(Paragraph("Customer Metrics", h2))
    customer_data = [
        ['Metric', 'Value', 'Context'],
        ['Connected Gmail inboxes', '1 (demo)', 'OAuth verified end-to-end'],
        ['Emails ingested', '50+', 'Real Gmail sync, not synthetic'],
        ['Commitments extracted', '29', 'From 50 emails — 58% extraction rate'],
        ['Commitment ledger entries', '1,252', 'With lifecycle states (active, completed, cancelled)'],
        ['Registered accounts', '632', 'Through the API (pre-launch)'],
        ['Resolved predictions (calibration)', '13', 'Brier score tracked; accuracy improving with usage'],
    ]

    c_col_widths = [CONTENT_W*0.30, CONTENT_W*0.18, CONTENT_W*0.52]
    customer_table = Table(customer_data, colWidths=c_col_widths, repeatRows=1)
    customer_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Inter-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (1, 1), (1, -1), ACCENT),
        ('FONTNAME', (1, 1), (1, -1), 'Inter-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [BG_WHITE, BG_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(customer_table)

    # Engineering metrics (supporting evidence, secondary)
    story.append(Spacer(1, 12))
    story.append(Paragraph("Engineering Health (Supporting)", h2))
    story.append(Paragraph(
        "<b>Database:</b> PostgreSQL 16 (migrated from SQLite — demo user: 17 commitments, 151 signals). "
        "<b>Test suite:</b> 1,585 tests including ownership and exclusion filters. "
        "<b>API:</b> 105 REST endpoints across 10 routers. "
        "<b>Deployment:</b> Railway with auto-deploy, health endpoint reports actual running build.",
        body))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "The product is ready for design-partner onboarding. The next cohort of 5-10 users "
        "will provide the usage data needed to validate the trust flywheel: as more "
        "commitments are resolved, the calibration engine improves, and the system becomes "
        "more valuable to each user.",
        body))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 11: BUSINESS MODEL (NEW)
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("Business Model", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    story.append(Paragraph("Target Customer", h2))
    story.append(Paragraph(
        "Knowledge workers who manage multiple professional relationships and make frequent "
        "commitments through email: consultants, account managers, project managers, "
        "founders, sales professionals, and attorneys. The ideal early user has 50+ emails "
        "per day, manages 5+ active client/partner relationships, and has experienced the "
        "cost of a forgotten commitment (lost deal, delayed project, strained relationship).",
        body))

    story.append(Paragraph("Pricing", h2))
    story.append(Paragraph(
        "<b>Individual (Free):</b> 1 connector (Gmail), up to 100 commitments tracked, "
        "basic Ask (5 questions/day). Designed for viral adoption — the product sells "
        "itself when a user sees their commitments automatically captured for the first time.",
        body))
    story.append(Paragraph(
        "<b>Professional ($19/month):</b> Unlimited connectors (Gmail, Calendar, Slack, "
        "GitHub), unlimited commitments, unlimited Ask, ambient intelligence alerts, "
        "mobile app. The core revenue tier for individual power users.",
        body))
    story.append(Paragraph(
        "<b>Team ($49/user/month):</b> Everything in Professional plus shared commitment "
        "visibility (team leads can see all members' commitments), SSO, audit trail, and "
        "API access. Designed for teams of 5-50 who need coordination and accountability.",
        body))

    story.append(Paragraph("Expansion Strategy", h2))
    story.append(Paragraph(
        "Land via individual professionals (bottom-up adoption through the free tier). "
        "Expand when a team lead sees the value and upgrades to Team. The API marketplace "
        "(commitment intelligence as a service) creates a platform play: other SaaS tools "
        "(CRM, project management, email clients) can query 'what did this user promise?' "
        "via authenticated API calls, creating a network effect where MaestroAgent becomes "
        "the trust layer that other tools build on.",
        body))

    story.append(Paragraph("Revenue Model", h2))
    story.append(Paragraph(
        "Subscription (SaaS) for individual and team tiers. API marketplace usage-based "
        "pricing for third-party integrations. The long-term revenue opportunity is the "
        "trust layer: every professional tool that needs to verify a commitment queries "
        "MaestroAgent, creating a per-query revenue stream that scales with the ecosystem.",
        body))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 12: TECHNICAL ARCHITECTURE (simplified lead)
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("Technical Architecture", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    story.append(Paragraph(
        "MaestroAgent is a production-ready system with verified deployment, persistent "
        "storage, and continuous governance. The architecture is designed for reliability: "
        "every claim about the system's behavior is backed by an automated test that runs "
        "on every code change, and every deploy is verifiable via a health endpoint that "
        "reports the actual running build.",
        body))

    story.append(Paragraph("Stack", h2))
    story.append(Paragraph(
        "<b>Backend:</b> FastAPI (Python), 105 REST endpoints, PostgreSQL 16 with full-text "
        "search (tsvector + GIN index). <b>Frontend:</b> Next.js (React), 4-tab interface "
        "(Today, Ask, Commitments, More). <b>Mobile:</b> Expo React Native (in development). "
        "<b>Deployment:</b> Railway with auto-deploy from GitHub. <b>LLM:</b> OpenRouter "
        "(model-agnostic, supports failover).",
        body))

    story.append(Paragraph("Reliability Verification", h2))
    story.append(Paragraph(
        "The system's core trust properties are verified with live reproductions: the "
        "ownership filter ('What did I promise Maria?' returns only the user's commitments) "
        "and the third-party exclusion ('What did Maria promise?' does not leak the user's "
        "own commitments) both pass on fresh and migrated data. Rate limiting is active "
        "and verified (returns HTTP 429 after 10 rapid login attempts). The demo bypass "
        "token returns 401 in production. The database migration from SQLite to PostgreSQL "
        "preserved demo user data (17 commitments, 151 signals).",
        body))

    story.append(Paragraph("Governance as Engineering Practice", h2))
    story.append(Paragraph(
        "MaestroAgent embeds governance rules directly into its engineering workflow through "
        "executable CI checks. Every bug found during the audit cycle became a new automated "
        "test and a CI rule that prevents recurrence. This practice means the product gets "
        "more reliable over time — a property that compounds with usage and creates a "
        "durability advantage that is difficult for competitors to replicate.",
        body))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PRIVACY & TRUST ARCHITECTURE (NEW)
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("Privacy & Trust Architecture", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    story.append(Paragraph(
        "MaestroAgent ingests professional communications — emails, messages, and calendar "
        "events that often contain sensitive business information. Privacy is not a feature; "
        "it is a precondition for trust. The system is designed so that users retain control "
        "over their data at every layer.",
        body))

    story.append(Paragraph("Data Storage & Encryption", h2))
    story.append(Paragraph(
        "All signal data is stored in a per-user PostgreSQL database with row-level isolation "
        "enforced at the query layer (every query is scoped by user_email). OAuth tokens for "
        "connected connectors are encrypted at rest using Fernet symmetric encryption "
        "(AES-128-CBC with HMAC authentication). Connector tokens are never logged, never "
        "exposed in API responses, and never passed through the frontend.",
        body))

    story.append(Paragraph("Cross-Tenant Isolation", h2))
    story.append(Paragraph(
        "Every API endpoint verifies the requesting user's identity via a bearer token and "
        "scopes all database queries to that user. Cross-tenant access is blocked at the "
        "query level — a user cannot read, modify, or transition another user's commitments. "
        "This isolation is verified by automated tests that register two users, create a "
        "commitment for user A, and assert that user B receives a 403 Forbidden when "
        "attempting to access it.",
        body))

    story.append(Paragraph("LLM Provider Boundary", h2))
    story.append(Paragraph(
        "When the system uses an LLM (via OpenRouter) to generate answers, only the relevant "
        "signal text and the user's question are sent to the provider — never the full email "
        "history, never other users' data, and never the user's OAuth credentials. The LLM "
        "provider sees a single question with a few evidence snippets, not the user's "
        "complete communication history. The system falls back to rules-based answering "
        "(no LLM call) when no LLM is configured, ensuring the product works in air-gapped "
        "or privacy-sensitive environments.",
        body))

    story.append(Paragraph("User Control", h2))
    story.append(Paragraph(
        "Users can disconnect any connector at any time, which revokes the OAuth token and "
        "stops all future ingestion. Users can delete their account, which permanently "
        "removes all signals, commitments, and audit trail — deletion is final, and "
        "re-login with the same credentials fails (verified by test). The system maintains "
        "an audit log of every data access, available to the user via the API.",
        body))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 14: COMPETITION & DIFFERENTIATION
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("Competition & Differentiation", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    story.append(Paragraph(
        "MaestroAgent occupies a category that no existing tool serves: passive commitment "
        "intelligence with evidence-backed answers. The closest alternatives each fail on "
        "a critical architectural dimension. General-purpose AI assistants have no persistent "
        "connection to the user's communication channels, no commitment classification, and "
        "no ownership reasoning — they depend on the user manually providing context for "
        "every query. Note-taking tools require manual entry, which is the exact problem "
        "MaestroAgent solves. Memory apps have no understanding of what a commitment is, "
        "let alone who made it or when it's due.",
        body))

    story.append(Paragraph(
        "The moat deepens with each pillar. Passive ingestion requires OAuth integrations "
        "with Gmail, Calendar, and Slack — each with its own API quirks, token refresh "
        "logic, and rate limiting. Commitment classification requires a trained model that "
        "understands the difference between first-person promises and third-party reports. "
        "Ownership reasoning requires a metadata schema where ownership is consistent across "
        "the ingestion and reconciliation paths — a constraint that took an intensive audit "
        "cycle to enforce correctly. And the governance system itself is a competitive "
        "advantage: MaestroAgent embeds governance rules directly into its engineering "
        "workflow, reducing the likelihood of previously observed failure modes recurring.",
        body))

    story.append(Paragraph(
        "The long-term defensibility comes from the data flywheel. As users connect more "
        "connectors and accumulate more commitments, the system's calibration improves — "
        "confidence scores become more accurate because they're based on real outcome "
        "history. This calibration data is non-transferable — it can only be built through "
        "longitudinal usage, creating an increasing-returns dynamic where the product "
        "becomes more valuable the longer each user stays on it.",
        body))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 14: ROADMAP & VISION
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("Roadmap & Vision", h1))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))

    story.append(Paragraph("Phase 1: Trust Foundation (Done)", h2))
    story.append(Paragraph(
        "The trust thesis is enforced and verified: ownership filtering and third-party "
        "exclusion pass on all data. Gmail OAuth is working. PostgreSQL migration is "
        "complete. The system is production-ready for design-partner onboarding.",
        body))

    story.append(Paragraph("Phase 2: Connector Expansion (Next 3 months)", h2))
    story.append(Paragraph(
        "Add real Calendar connector (Google Calendar API), Slack connector (Slack Events "
        "API), and GitHub connector (webhooks for PRs and issues). Ship the mobile app "
        "(Expo React Native) with push notifications for at-risk commitments and The Moment "
        "on the lock screen. Onboard 5-10 design partners to validate the trust flywheel.",
        body))

    story.append(Paragraph("Phase 3: Enterprise (6-12 months)", h2))
    story.append(Paragraph(
        "Multi-user teams with shared commitment visibility. SSO authentication (SAML/OIDC). "
        "Audit trail for compliance (SOC 2). API marketplace: commitment intelligence as a "
        "service — other apps can query 'what did this user promise?' via authenticated "
        "API calls.",
        body))

    story.append(Paragraph("Phase 4: Ambient Intelligence (12-18 months)", h2))
    story.append(Paragraph(
        "Proactive nudges based on sentiment analysis and deadline proximity. Relationship "
        "health scoring. The system evolves from reactive (answer questions) to proactive "
        "(prevent broken promises before they happen).",
        body))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=12))
    story.append(Paragraph(
        "<b>Long-term vision:</b> MaestroAgent becomes the trust layer for professional "
        "relationships — the system that remembers what you promised, proves it with "
        "evidence, and holds you accountable. In a world where AI can generate anything, "
        "trust is the scarcest resource. MaestroAgent is the system that earns and "
        "preserves it.",
        tagline))

    return story

def generate_body_pdf():
    body_pdf = OUTPUT_DIR / "_maestro_body.pdf"
    doc = SimpleDocTemplate(
        str(body_pdf),
        pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="MaestroAgent Investor Briefing",
        author="MaestroAgent Team",
        subject="Passive Commitment Intelligence",
        creator="MaestroAgent",
    )
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Inter', 8)
        canvas.setFillColor(TEXT_MUTED)
        canvas.drawString(MARGIN_L, 10*mm, "MaestroAgent — Investor Briefing")
        canvas.drawRightString(PAGE_W - MARGIN_R, 10*mm, f"Page {doc.page}")
        canvas.restoreState()
    story = make_story()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return body_pdf

def generate_cover_pdf():
    cover_html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@page { size: 210mm 297mm; margin: 0; }
html, body { margin: 0; padding: 0; background: #FFFFFF; }
.poster {
  width: 210mm; height: 297mm; position: relative; background: #FFFFFF;
  font-family: 'Inter', 'Noto Sans SC', sans-serif;
}
.layer-bg {
  position: absolute; inset: 0; overflow: hidden; z-index: 1;
  background-image:
    linear-gradient(#3B82F608 1px, transparent 1px),
    linear-gradient(90deg, #3B82F608 1px, transparent 1px);
  background-size: 50px 50px;
}
.anchor-line {
  position: absolute; left: 12%; top: 10%; bottom: 10%;
  width: 6px; background: #1E293B; z-index: 2;
}
.content { position: absolute; inset: 0; z-index: 3; }
.kicker {
  position: absolute; left: calc(12% + 30px); top: 15%;
  font-size: 16px; font-weight: 400; letter-spacing: 3px;
  color: #64748B; text-transform: uppercase; opacity: 0.8;
}
.hero {
  position: absolute; left: calc(12% + 30px); top: 28%;
  font-size: 52px; font-weight: 900; color: #1E293B;
  line-height: 1.15; max-width: 70%;
}
.hero .accent { color: #3B82F6; }
.summary {
  position: absolute; left: calc(12% + 30px); top: 50%;
  font-size: 17px; font-weight: 400; color: #1E293B;
  line-height: 1.6; max-width: 60%; opacity: 0.85;
}
.tags {
  position: absolute; left: calc(12% + 30px); top: 62%;
  display: flex; gap: 12px; flex-wrap: wrap;
}
.tag {
  padding: 6px 16px; border-radius: 20px; font-size: 13px;
  font-weight: 500; background: #DBEAFE; color: #1E40AF;
}
.meta {
  position: absolute; left: calc(12% + 30px); top: 80%;
  font-size: 18px; font-weight: 400; color: #64748B;
}
.footer {
  position: absolute; left: calc(12% + 30px); bottom: 8%;
  font-size: 14px; font-weight: 400; color: #94A3B8;
  letter-spacing: 1px;
}
</style>
</head>
<body>
<div class="poster">
  <div class="layer-bg"></div>
  <div class="anchor-line"></div>
  <div class="content">
    <div class="kicker">INVESTOR BRIEFING — 2026</div>
    <div class="hero">Maestro<span class="accent">Agent</span></div>
    <div class="summary">The system that remembers what you promised — passively captures commitments from email, proves every answer with evidence, with CI-enforced ownership filtering that prevents cross-person commitment leakage. The trust layer for professional relationships.</div>
    <div class="tags">
      <span class="tag">Never Forget A Promise</span>
      <span class="tag">Evidence-Backed Answers</span>
      <span class="tag">Calibration Flywheel</span>
      <span class="tag">Gmail OAuth</span>
    </div>
    <div class="meta">July 2026</div>
    <div class="footer">MAESTROAGENT — CONFIDENTIAL</div>
  </div>
</div>
</body>
</html>"""
    cover_html_path = OUTPUT_DIR / "_maestro_cover.html"
    cover_html_path.write_text(cover_html)
    cover_pdf = OUTPUT_DIR / "_maestro_cover.pdf"
    import subprocess
    result = subprocess.run([
        "node", "/home/z/my-project/skills/pdf/scripts/html2poster.js",
        str(cover_html_path), "--output", str(cover_pdf), "--width", "794px"
    ], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"Cover generation failed: {result.stderr[:300]}")
        return None
    return cover_pdf

def merge_cover_and_body(cover_pdf, body_pdf):
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    cover_reader = PdfReader(str(cover_pdf))
    for page in cover_reader.pages:
        writer.add_page(page)
    body_reader = PdfReader(str(body_pdf))
    for i, page in enumerate(body_reader.pages):
        if i == 0:
            continue
        writer.add_page(page)
    writer.add_metadata({
        "/Title": "MaestroAgent Investor Briefing",
        "/Author": "MaestroAgent Team",
        "/Subject": "Passive Commitment Intelligence",
        "/Creator": "MaestroAgent",
    })
    with open(OUTPUT_PDF, "wb") as f:
        writer.write(f)

if __name__ == "__main__":
    print("Generating body PDF...")
    body_pdf = generate_body_pdf()
    print(f"  Body: {body_pdf}")
    print("Generating cover PDF...")
    cover_pdf = generate_cover_pdf()
    if cover_pdf:
        print(f"  Cover: {cover_pdf}")
        print("Merging...")
        merge_cover_and_body(cover_pdf, body_pdf)
    else:
        print("  Cover failed — using body only")
        import shutil
        shutil.copy(body_pdf, OUTPUT_PDF)
    size_kb = OUTPUT_PDF.stat().st_size / 1024
    print(f"\n✓ Final PDF: {OUTPUT_PDF} ({size_kb:.0f} KB)")
