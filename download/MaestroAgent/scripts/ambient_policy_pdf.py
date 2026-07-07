#!/usr/bin/env python3
"""Generate the Maestro Ambient Intelligence Execution Policy PDF."""
from __future__ import annotations
import os, sys
sys.path.insert(0, '/home/z/my-project/scripts')
from roadmap_pdf import (
    TocDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    A4, cm, colors, STYLES, heading, p, callout, spacer, make_table, on_page,
    BODY_FONT, BODY_BOLD, HEAD_FONT, HEAD_BOLD, HEADER_FILL, ACCENT,
    TEXT_PRIMARY, TEXT_MUTED, BORDER, CARD_BG, TABLE_STRIPE, datetime,
)
from reportlab.platypus.tableofcontents import TableOfContents

OUTPUT = '/home/z/my-project/download/MAESTRO_AMBIENT_INTELLIGENCE_EXECUTION_POLICY.pdf'

def build_cover(story):
    story.append(Spacer(1, 3.5*cm))
    story.append(Paragraph(
        '<para alignment="left"><font color="#5CC8FF" size="9">MAESTRO AMBIENT INTELLIGENCE · GOVERNED EXECUTION POLICY</font></para>',
        STYLES['caption']))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(
        '<para alignment="left"><font name="' + HEAD_BOLD + '" size="28" color="#151513">'
        'Beyond Cluely: 24/7<br/>Organizational Intelligence</font></para>', STYLES['title']))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        '<para alignment="left"><font name="' + HEAD_FONT + '" size="13" color="#86847c">'
        'A 20-phase, 153-day governed execution policy integrating the Live Copilot<br/>'
        'and Ambient Intelligence roadmaps. Every phase verified by execution.<br/>'
        'The anti-Cluely: ambient, deep, rich, learning, evidence-backed.</font></para>',
        STYLES['subtitle']))
    story.append(Spacer(1, 2*cm))
    meta = [
        ['Document', 'Maestro Ambient Intelligence — Governed Execution Policy'],
        ['Audience', 'CEO, Engineering, Auditor, Investors'],
        ['Date', datetime.now().strftime('%Y-%m-%d')],
        ['Current HEAD', 'd9026e2 (origin/main)'],
        ['Total scope', '20 phases, 153 days, ~612 hours, $480K-720K'],
        ['Source', 'MAESTRO_AMBIENT_INTELLIGENCE_ROADMAP.md (1111 lines, 12 phases)'],
        ['Companion', 'MAESTRO_LIVE_COPILOT_ROADMAP_GOVERNED.md (8 phases)'],
        ['CEO promise', 'Ambient org intelligence layer — works 24/7, not just during calls'],
    ]
    t = Table(meta, colWidths=[3.5*cm, 12*cm])
    t.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), HEAD_BOLD), ('FONTNAME', (1,0), (1,-1), BODY_FONT),
        ('FONTSIZE', (0,0), (-1,-1), 9.5), ('LEADING', (0,0), (-1,-1), 14),
        ('TEXTCOLOR', (0,0), (0,-1), TEXT_MUTED), ('TEXTCOLOR', (1,0), (1,-1), TEXT_PRIMARY),
        ('LEFTPADDING', (0,0), (-1,-1), 0), ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4), ('LINEBELOW', (0,0), (-1,-1), 0.3, BORDER),
    ]))
    story.append(t)
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph(
        '<para alignment="left"><font color="#86847c" size="8.5">'
        'GOVERNANCE LOOP READ RECEIPT (Coder) — 2026-07-07T05:50:00Z<br/>'
        'GOVERNANCE_LOOP.md: "THE LOOP CANNOT BE BROKEN." · '
        'P20: "If M of N call sites pass it, the fix is (M/N)% done." · '
        'P26: "Principles don\'t enforce themselves. Re-application does." · '
        'P27: "Read at least the key assertions." · '
        'P34: "The auditor\'s method is not a memory — it\'s a checklist."<br/>'
        '> Auditor: Read GOVERNANCE_LOOP.md, AUDITOR_GOVERNANCE.md, and '
        'ENTROPY_RECOVERY.md Part Four + Part Five from disk before auditing.'
        '</font></para>', STYLES['caption']))
    story.append(PageBreak())

def build_ch_ethics(story):
    story.append(heading('Chapter 1 — The Non-Negotiable Ethical Line', STYLES['h1'], level=0))
    story.append(p(
        'The Ambient Intelligence layer extends the Live Copilot ethical line. The differentiator '
        'from Cluely is absolute: Maestro is ambient (works between calls), deep (multi-layer), rich '
        '(full context), learning (compounds), evidence-backed (every suggestion cites organizational '
        'data). Cluely helps you cheat in the moment. Maestro helps your organization learn.'))
    story.append(p('The following code paths are FORBIDDEN. Any appearance rejects the entire phase:'))
    forbidden = [
        ['Forbidden path', 'Why rejected'],
        ['Hiding from meeting software', 'Stealth framing violates the bright line'],
        ['Bypassing screen-share detection', 'Deception; enterprise buyers will not tolerate it'],
        ['Unconsented recording (audio/video/email/Slack/calendar)', 'Consent MUST precede every capture'],
        ['Exam/interview assistance', 'Manipulation; rejected absolutely'],
        ['"Undetectable mode" / stealth framing', 'Side panel is transparent, not hidden'],
        ['Auto answer injection into calls', 'Suggestions display; the user speaks them'],
        ['Inferring commitments from ambiguous language', 'Only explicit commitments tracked'],
        ['Reading email/Slack/calendar content without consent', 'Per-channel consent, revocable'],
        ['Emotion analysis used to manipulate', 'For user awareness only, never to "win"'],
    ]
    story.append(make_table(forbidden, col_widths=[7*cm, 8.5*cm], font_size=8.5))
    story.append(PageBreak())

def build_ch_arch(story):
    story.append(heading('Chapter 2 — Architecture Overview', STYLES['h1'], level=0))
    story.append(p(
        'The Ambient Intelligence Layer sits above the Organizational Memory (SituationSnapshot 27 '
        'fields + OutcomeLedger + OEM signals) and below the user-facing surfaces (Today panel + '
        'Whisper push + Ask + cross-meeting threads). It fuses signals from Calendar, Email, '
        'Slack/Teams, CRM connectors, and the Live Copilot audio stream into a 24/7 background loop: '
        'ingest → classify → correlate → alert.'))
    story.append(p(
        'The fusion layer feeds four intelligence engines: Commitment Escalation, Deal Health, '
        'Relationship Dynamics, and Sentiment & Emotion. Each engine writes back to the '
        'Organizational Memory, so every interaction makes the system smarter. This is the moat: '
        'Cluely has GPT; Maestro has your organization\'s entire history, learning from every '
        'interaction, building institutional memory that compounds over time.'))
    story.append(callout(
        '<b>The design law (from the constitution):</b> every increase in internal intelligence must '
        'reduce external complexity. The ambient layer makes the user\'s day simpler (fewer forgotten '
        'commitments, fewer unprepared meetings, fewer repeated mistakes) even as the intelligence '
        'gets deeper. The UI stays at 4 sidebar items; the engines multiply invisibly behind them.'))
    story.append(PageBreak())

def build_ch_phases(story):
    story.append(heading('Chapter 3 — The 20-Phase Unified Plan', STYLES['h1'], level=0))
    story.append(p(
        'The Ambient Intelligence roadmap (12 phases) integrates with the Live Copilot roadmap '
        '(8 phases). The Live Copilot phases (1-8) deliver the meeting-time layer. The Ambient '
        'phases (9-20) deliver the always-on layer. Together: 20 phases, 153 days, ~612 hours.'))
    story.append(heading('3.1 Live Copilot Phases (Days 1-33)', STYLES['h2'], level=1))
    lc = [
        ['Phase', 'Days', 'Hours', 'Deliverable'],
        ['1: Extension scaffold', '1-3', '12', 'manifest.json, consent-manager, panel shell'],
        ['2: Audio + transcription', '4-7', '16', 'offscreen audio capture, Whisper STT'],
        ['3: Scene 1 pre-call', '8-11', '16', 'lobby detection, attendee intelligence'],
        ['4: Scene 2 live', '12-18', '28', '4 card types (objection/commitment/whisper/pattern)'],
        ['5: Scene 3 post-call', '19-23', '20', 'summary, draft email, "What Maestro learned"'],
        ['6: Evidence + confidence', '24-27', '16', 'evidence-chain links, P25 confidence gate'],
        ['7: Accessibility + polish', '28-30', '12', 'keyboard nav, aria-live, contrast'],
        ['8: Integration + audit', '31-33', '12', 'E2E test, cross-surface coherence'],
    ]
    story.append(make_table(lc, col_widths=[3.5*cm, 1.5*cm, 1.5*cm, 9*cm], font_size=8.5))
    story.append(spacer(10))

    story.append(heading('3.2 Ambient Intelligence Phases (Days 34-153)', STYLES['h2'], level=1))
    amb = [
        ['Phase', 'Days', 'Hrs', 'Deliverable', 'Key File'],
        ['9: Ambient signal fusion', '34-43', '40', 'Calendar awareness + commitment escalation',
         'calendar_awareness.py, commitment_escalation.py'],
        ['10: Sentiment & emotion', '44-53', '40', 'Voice tone analysis, emotion detection',
         'sentiment_engine.py'],
        ['11: Deal health score', '54-63', '40', 'Live scoring, risk factors, momentum',
         'deal_health.py'],
        ['12: Negotiation strategy', '64-73', '40', 'BATNA, anchoring, concessions',
         'negotiation_strategy.py'],
        ['13: Relationship dynamics', '74-83', '40', 'Influence networks, power, coalitions',
         'relationship_dynamics.py'],
        ['14: Cross-meeting threads', '84-93', '40', 'Continuity, topic evolution, decisions',
         'cross_meeting_threads.py'],
        ['15: Talk ratio + coach', '94-103', '40', 'Speaking time, interruptions, clarity',
         'talk_ratio_coach.py'],
        ['16: Meeting grade + analytics', '104-113', '40', 'Effectiveness score, action items',
         'meeting_grader.py'],
        ['17: Email/Slack signals', '114-123', '40', 'Written comms monitoring, response time',
         'written_signal_fusion.py'],
        ['18: Multi-language', '124-133', '40', 'Accent-aware STT, cultural context, translation',
         'multilang_support.py'],
        ['19: Ambient notifications', '134-143', '40', 'Smart nudges, context timing, DND',
         'ambient_notifications.py'],
        ['20: Advanced analytics', '144-153', '40', 'Trends, team performance, org learning',
         'advanced_analytics.py'],
    ]
    story.append(make_table(amb, col_widths=[3.2*cm, 1.2*cm, 0.8*cm, 4.8*cm, 4.5*cm], font_size=7.5))
    story.append(spacer(10))
    story.append(p(
        '<b>Totals:</b> 20 phases, 153 days, ~612 hours, $480K-720K (4 engineers × 6 months).'))
    story.append(PageBreak())

def build_ch_policy(story):
    story.append(heading('Chapter 4 — The Coding Execution Policy', STYLES['h1'], level=0))
    story.append(p(
        'This is the governed coding policy. Every phase MUST follow it. The auditor verifies '
        'compliance by execution (P31). The policy has 3 stages: pre-phase (blocking), during-phase '
        '(per commit), and post-phase (blocking).'))

    story.append(heading('4.1 Pre-Phase (BLOCKING — before any code)', STYLES['h2'], level=1))
    pre = [
        ['Step', 'Action', 'Principle'],
        ['1', 'Paste complete 8-field read receipt', 'Gate (CEO rejects without it)'],
        ['2', 'Verify prior phase gate passes by execution', 'P1, P31'],
        ['3', 'List files + grep call sites for parameter changes', 'P20'],
        ['4', 'Audit every capture path for consent gating', 'Ethical line'],
    ]
    story.append(make_table(pre, col_widths=[1*cm, 9*cm, 5.5*cm], font_size=8.5))
    story.append(spacer(8))

    story.append(heading('4.2 During-Phase (per commit)', STYLES['h2'], level=1))
    during = [
        ['Step', 'Action', 'Principle'],
        ['1', 'Commit includes VERIFICATION section with pasted output', 'P23'],
        ['2', 'grep call sites; M of N = (M/N)% done', 'P20, Gate 15'],
        ['3', 'Write 2 tests: unit + integration (production path)', 'P22'],
        ['4', 'Re-run SSO scenario after shared-component changes', 'P24, P29'],
        ['5', 'Gate every confidence value on denominator (< 10 = "insufficient")', 'P25'],
        ['6', 'Execute consent-denied path; confirm zero capture', 'Ethical line'],
    ]
    story.append(make_table(during, col_widths=[1*cm, 9*cm, 5.5*cm], font_size=8.5))
    story.append(spacer(8))

    story.append(heading('4.3 Post-Phase (BLOCKING — before next phase)', STYLES['h2'], level=1))
    post = [
        ['Step', 'Action', 'Principle'],
        ['1', 'Run phase gate commands; paste output', 'P1'],
        ['2', 'Run L0 gate; verify no regression', 'P29, P30'],
        ['3', 'Push to origin/main; paste HEAD + origin/main (must match)', 'Gate 11'],
        ['4', 'Auditor independently verifies by execution', 'P31'],
        ['5', 'Only "Phase N PASS" allows next phase', 'The loop'],
    ]
    story.append(make_table(post, col_widths=[1*cm, 9*cm, 5.5*cm], font_size=8.5))
    story.append(spacer(10))

    story.append(heading('4.4 Forbidden Anti-Patterns (auditor rejects on sight)', STYLES['h2'], level=1))
    anti = [
        ['Anti-pattern', 'Principle violated'],
        ['Theater tests (assert True, weak isinstance)', 'P27'],
        ['Self-certification (✓ VERIFIED without output)', 'P5, P23'],
        ['Wiring gaps (0 of N callers pass new param)', 'P20, Gate 15'],
        ['Stale-clone auditing (HEAD != origin/main)', 'Gate 11'],
        ['Single-input testing (only the golden case)', 'P28'],
        ['Confidence without denominator', 'P25'],
        ['Stealth framing (hide from meeting software)', 'Ethical line'],
    ]
    story.append(make_table(anti, col_widths=[9*cm, 6.5*cm], font_size=8.5))
    story.append(PageBreak())

def build_ch_phase_details(story):
    story.append(heading('Chapter 5 — Ambient Phase Details (9-20)', STYLES['h1'], level=0))
    story.append(p(
        'Each ambient phase has deliverables, an ethical guard, and a gate. The gates are verified '
        'by execution (P31). The ethical guards extend the Live Copilot bright line to the always-on '
        'layer: consent for every capture, no manipulation, no surveillance, no inference without '
        'confirmation.'))

    details = [
        ['Phase', 'Deliverable', 'Ethical Guard', 'Gate'],
        ['9', 'Calendar awareness + commitment escalation',
         'Calendar metadata only; no content without consent; explicit commitments only',
         'test_calendar_awareness.py + test_commitment_escalation.py'],
        ['10', 'Sentiment & emotion tracking',
         'For user awareness only; never shown to other party; never to "win"',
         'test_sentiment_engine.py (emotion never shown to other party)'],
        ['11', 'Deal health score',
         'Score with denominator (P25); < 10 deals = "insufficient calibration"',
         'test_deal_health.py (confidence has denominator)'],
        ['12', 'Negotiation strategy',
         'Preparation only; no manipulative tactics; cites validated runtimes',
         'test_negotiation_strategy.py (evidence chain required)'],
        ['13', 'Relationship dynamics',
         'Derived from org signals; no personal profile scraping',
         'test_relationship_dynamics.py'],
        ['14', 'Cross-meeting threads',
         'Threads by entity + topic; decisions traced',
         'test_cross_meeting_threads.py'],
        ['15', 'Talk ratio + comms coach',
         'Capability-building, not dominance-building',
         'test_talk_ratio_coach.py (no dominance suggestions)'],
        ['16', 'Meeting grade + analytics',
         'Grade with denominator; follow-up tracked across meetings',
         'test_meeting_grader.py'],
        ['17', 'Email/Slack signal fusion',
         'Per-channel consent, revocable; consent-denied = 0 signals',
         'test_written_signal_fusion.py (consent-denied path = 0)'],
        ['18', 'Multi-language support',
         'Translation for user understanding; auto-translate to other party requires consent',
         'test_multilang_support.py (auto-translate gated)'],
        ['19', 'Ambient notifications',
         'Respects DND + focus + off-hours; max 5/hour',
         'test_ambient_notifications.py'],
        ['20', 'Advanced analytics',
         'Team-level aggregate; no individual surveillance',
         'test_advanced_analytics.py (no individual PII)'],
    ]
    story.append(make_table(details, col_widths=[0.8*cm, 3.8*cm, 5.2*cm, 5.7*cm], font_size=7.5))
    story.append(PageBreak())

def build_ch_loop(story):
    story.append(heading('Chapter 6 — The Loop + Honest Disclosure', STYLES['h1'], level=0))
    story.append(p(
        'The governance loop is the enforcement mechanism. It is the reason the 9 code-quality '
        'findings from Audit 1 are actually fixed (verified by the auditor at HEAD 09b2b87), not '
        'just claimed fixed. The loop applies equally to all 20 phases:'))
    loop = [
        ['Step', 'Action', 'Who'],
        ['1. Before each phase', 'Read governance modules from disk; paste 8-field receipt', 'Coder'],
        ['2. During each phase', 'Cite P-numbers (P20, P22, P23, P24, P25) per commit', 'Coder'],
        ['3. After each phase', 'Run gate + L0; push; paste HEAD + origin/main', 'Coder'],
        ['4. Auditor verifies', 'Fetch → checkout → run gate independently (P31) → SSO scenario (P29)', 'Auditor'],
        ['5. Next phase', 'Only after "Phase N PASS"', 'Both'],
    ]
    story.append(make_table(loop, col_widths=[2.5*cm, 9.5*cm, 3*cm], font_size=8.5))
    story.append(spacer(10))

    story.append(heading('6.1 Honest Disclosure', STYLES['h2'], level=1))
    story.append(callout(
        '<b>This is a 153-day, 612-hour, $480K-720K build.</b> The coder can execute every CODE '
        'phase (1-20). The CEO must resource the GTM milestones (design partners, ARR, SOC2/HIPAA/'
        'GDPR) in parallel. The 20 phases deliver the product the CEO promised investors: an ambient '
        'organizational intelligence layer that works 24/7, learns from every interaction, and '
        'compounds institutional memory over time. This is not a feature. This is a category.'))

    story.append(heading('6.2 Read Receipt', STYLES['h2'], level=1))
    story.append(p(
        '<b>GOVERNANCE LOOP READ RECEIPT (Coder):</b><br/>'
        '- GOVERNANCE_LOOP.md read at 2026-07-07T05:50:00Z. Key line: "THE LOOP CANNOT BE BROKEN."<br/>'
        '- ENTROPY_RECOVERY.md Part Four (P20-P26) read. P20: "If M of N call sites pass it, the '
        'fix is (M/N)% done." P26: "Principles don\'t enforce themselves. Re-application does."<br/>'
        '- ENTROPY_RECOVERY.md Part Five (P27-P34) read. P27: "Read at least the key assertions." '
        'P34: "The auditor\'s method is not a memory — it\'s a checklist."<br/>'
        '- AUDITOR_GOVERNANCE.md Gates 15-20 read. Gate 15: "A function signature with a new '
        'parameter proves nothing." Gate 17: "Reading the dedup logic proves nothing; executing it does."<br/>'
        '- audit_scripts/audit_gates.sh read — enforces Gate 11 + full suite + all verify scripts.<br/>'
        '<br/>'
        '<b>Auditor: Read GOVERNANCE_LOOP.md, AUDITOR_GOVERNANCE.md, and ENTROPY_RECOVERY.md Part '
        'Four + Part Five from disk before auditing. Do not audit from memory. The loop cannot be broken.</b>'))

def main():
    doc = TocDocTemplate(
        OUTPUT, pagesize=A4, leftMargin=2.2*cm, rightMargin=2.2*cm,
        topMargin=2*cm, bottomMargin=1.8*cm,
        title='Maestro Ambient Intelligence — Governed Execution Policy',
        author='MaestroAgent Coder',
        subject='20-phase plan: ambient organizational intelligence, done right',
        creator='ReportLab',
    )
    story = []
    build_cover(story)
    story.append(heading('Table of Contents', STYLES['h1'], level=0))
    story.append(spacer(8))
    toc = TableOfContents()
    toc.levelStyles = [STYLES['toc_l0'], STYLES['toc_l1']]
    story.append(toc)
    story.append(PageBreak())
    build_ch_ethics(story)
    build_ch_arch(story)
    build_ch_phases(story)
    build_ch_policy(story)
    build_ch_phase_details(story)
    build_ch_loop(story)
    doc.multiBuild(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"PDF generated: {OUTPUT}")
    print(f"Size: {os.path.getsize(OUTPUT):,} bytes")

if __name__ == '__main__':
    main()
