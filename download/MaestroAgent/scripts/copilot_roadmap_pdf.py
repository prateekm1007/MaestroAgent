#!/usr/bin/env python3
"""Generate the Maestro Live Copilot Roadmap PDF from the governed markdown."""
from __future__ import annotations
import os, sys, re

# Reuse the styles + helpers from roadmap_pdf.py
sys.path.insert(0, '/home/z/my-project/scripts')
from roadmap_pdf import (
    SimpleDocTemplate, TocDocTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, A4, cm, colors, STYLES, heading, p, callout,
    spacer, make_table, on_page, BODY_FONT, BODY_BOLD, HEAD_FONT, HEAD_BOLD,
    HEADER_FILL, ACCENT, TEXT_PRIMARY, TEXT_MUTED, BORDER, CARD_BG,
    TABLE_STRIPE, SEM_SUCCESS, SEM_WARNING, SEM_ERROR, SEM_INFO,
    datetime,
)

OUTPUT = '/home/z/my-project/download/MAESTRO_LIVE_COPILOT_ROADMAP.pdf'

def build_cover(story):
    story.append(Spacer(1, 4*cm))
    story.append(Paragraph(
        '<para alignment="left"><font color="#7C5CFF" size="9">MAESTRO LIVE COPILOT · GOVERNED EXECUTION ROADMAP</font></para>',
        STYLES['caption']))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(
        '<para alignment="left"><font name="' + HEAD_BOLD + '" size="30" color="#151513">'
        'Real-Time Meeting<br/>Intelligence, Done Right</font></para>', STYLES['title']))
    story.append(Spacer(1, 0.6*cm))
    story.append(Paragraph(
        '<para alignment="left"><font name="' + HEAD_FONT + '" size="13" color="#86847c">'
        'An 8-phase, 33-day plan for the Maestro Live Copilot browser extension.<br/>'
        'Side panel, not overlay. Consent-first. Evidence-grounded.<br/>'
        'The anti-Cluely.</font></para>', STYLES['subtitle']))
    story.append(Spacer(1, 2.5*cm))
    meta = [
        ['Document', 'Maestro Live Copilot — Governed Execution Roadmap'],
        ['Audience', 'CEO, Engineering, Auditor'],
        ['Date', datetime.now().strftime('%Y-%m-%d')],
        ['Current HEAD', 'e867cb7 (origin/main)'],
        ['L0 gate', 'PASS (3/4 verified; L0.4 deferred)'],
        ['Source', '3-scene spec (Pre-Call / Live / Post-Call)'],
        ['Ethical line', 'Side panel, consent-first, audit-logged — NOT Cluely'],
    ]
    t = Table(meta, colWidths=[3.5*cm, 12*cm])
    t.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), HEAD_BOLD),
        ('FONTNAME', (1,0), (1,-1), BODY_FONT),
        ('FONTSIZE', (0,0), (-1,-1), 9.5),
        ('LEADING', (0,0), (-1,-1), 14),
        ('TEXTCOLOR', (0,0), (0,-1), TEXT_MUTED),
        ('TEXTCOLOR', (1,0), (1,-1), TEXT_PRIMARY),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,-1), 0.3, BORDER),
    ]))
    story.append(t)
    story.append(Spacer(1, 2.5*cm))
    story.append(Paragraph(
        '<para alignment="left"><font color="#86847c" size="8.5">'
        'GOVERNANCE LOOP READ RECEIPT (Coder) — 2026-07-07T05:35:00Z<br/>'
        'GOVERNANCE_LOOP.md: "THE LOOP CANNOT BE BROKEN." · '
        'P20: "If M of N call sites pass it, the fix is (M/N)% done." · '
        'P26: "Principles don\'t enforce themselves. Re-application does." · '
        'P27: "Read at least the key assertions of the tests you\'re counting." · '
        'P34: "The auditor\'s method is not a memory — it\'s a checklist."<br/>'
        '> Auditor: Read GOVERNANCE_LOOP.md, AUDITOR_GOVERNANCE.md, and '
        'ENTROPY_RECOVERY.md Part Four + Part Five from disk before auditing.'
        '</font></para>', STYLES['caption']))
    story.append(PageBreak())

def build_ch_ethics(story):
    story.append(heading('Chapter 1 — The Non-Negotiable Ethical Line', STYLES['h1'], level=0))
    story.append(p(
        'Maestro Live Copilot is the anti-Cluely. The differentiator is not a feature — it is the '
        'ethical line. The following code paths are FORBIDDEN. If any appear, the auditor rejects '
        'the entire phase and the CEO is notified.'))
    forbidden = [
        ['Forbidden path', 'Why it is rejected'],
        ['Hiding from meeting software as a selling feature', 'Stealth framing violates the bright line'],
        ['Bypassing screen-share detection', 'Deception; enterprise buyers will not tolerate it'],
        ['Unconsented recording', 'Consent MUST precede any audio capture (ConsentManager.checkConsent)'],
        ['Exam/interview assistance modes', 'Manipulation; rejected absolutely by the constitution'],
        ['"Undetectable mode" or stealth framing', 'The product is transparent — side panel, not overlay'],
        ['Automatic answer injection into calls', 'Suggestions display in the panel; the user speaks them'],
    ]
    story.append(make_table(forbidden, col_widths=[6*cm, 9.5*cm], font_size=9))
    story.append(spacer(10))
    story.append(callout(
        '<b>What Maestro Live Copilot IS:</b> side panel (not overlay), consent-first (every capture '
        'gated), audit-logged (every suggestion/capture/dismiss recorded), evidence-grounded (every '
        'suggestion cites organizational data). This is how enterprise products work.'))
    story.append(PageBreak())

def build_ch_scenes(story):
    story.append(heading('Chapter 2 — The 3 Scenes (Target Experience)', STYLES['h1'], level=0))
    story.append(heading('2.1 Scene 1: Pre-Call Intelligence', STYLES['h2'], level=1))
    story.append(p(
        'Trigger: user opens a Google Meet / Zoom / Teams lobby URL; the Maestro extension detects '
        'the meeting metadata and surfaces a pre-call briefing in the side panel.'))
    story.append(p(
        'Surfaces: (1) Meeting context card — ARR at risk, renewal countdown, account health (from '
        'SituationSnapshot, which now has 27 fields per L0-1). (2) Attendee intelligence per person — '
        'interaction count from OEM signal history, commitment status from CommitmentTracker, '
        'last-interaction gap. (3) Suggested talking points — each citing the organizational data '
        'behind it ("12 interactions" links to signal history; "Day 45 of 60" links to the commitment).'))
    story.append(p(
        'The killer detail: every suggestion cites organizational data, not generic LinkedIn bios. '
        'This is the difference between Cluely and Maestro.'))

    story.append(heading('2.2 Scene 2: Live Intelligence', STYLES['h2'], level=1))
    story.append(p(
        'Trigger: user clicks "Start Copilot" in the side panel AFTER consent; audio capture begins '
        'via the offscreen document.'))
    story.append(p(
        'Four card types appear in real time, each color-coded:'))
    cards = [
        ['Card', 'Color', 'Trigger', 'Content'],
        ['Objection detected', 'Rose #FF5577', 'Transcript matches objection pattern',
         'Response cites validated runtimes; confidence bar from pattern count; evidence chain'],
        ['Commitment detected', 'Amber #FFB84D', 'Transcript matches commitment pattern',
         'Deduped against CommitmentTracker (Day X/Y, not a duplicate)'],
        ['Organizational whisper', 'Purple #7C5CFF', 'Entity matches a GitHub PR / Slack / Confluence',
         'Cross-validated evidence chain; confidence from source count'],
        ['Historical pattern match', 'Cyan #5CC8FF', 'Conversation resembles a past meeting',
         'Outcome cited; confidence from match count'],
    ]
    story.append(make_table(cards, col_widths=[3.2*cm, 2.5*cm, 4*cm, 5.8*cm], font_size=8))
    story.append(spacer(8))
    story.append(p(
        'The new-card animation is cardSlideIn (400ms ease-out) with a glow effect '
        '(box-shadow 0 0 20px rgba(255,214,10,0.15)) that fades after 5s. The user\'s eye is drawn '
        'to new suggestions immediately. Live transcript shows the last 3 chunks with speaker labels '
        'and trigger words highlighted.'))

    story.append(heading('2.3 Scene 3: Meeting Intelligence Captured', STYLES['h2'], level=1))
    story.append(p(
        'Trigger: call ends (WebSocket disconnect or tab close). The side panel shows a green '
        'checkmark and "Summary ready."'))
    story.append(p(
        'Surfaces: (1) Hero summary card — title, duration, participant count, transcript chunk '
        'count. (2) Key stats grid — commitments, objections, suggestions. (3) Commitments tracked '
        '— each with actor, Day X/Y, dedup status. (4) Objections raised — with response pattern. '
        '(5) Draft follow-up email — pre-written, citing specific commitments + patterns; copy / '
        'edit / open-in-Gmail. (6) What Maestro learned — new signals ingested, pattern data-point '
        'count, law-promotion threshold.'))
    story.append(callout(
        '<b>The killer detail:</b> the "What Maestro learned" section shows the user the system gets '
        'smarter with every call. "The pricing objection pattern now has 4 data points — one more '
        'and it becomes a validated organizational law." This is the moat: judgment lock-in.'))
    story.append(PageBreak())

def build_ch_l0(story):
    story.append(heading('Chapter 3 — L0 Prerequisite Gate', STYLES['h1'], level=0))
    story.append(p(
        'The L0 gate MUST pass before Phase 1 begins. The L0 prerequisites ensure the shared OEM '
        'substrate is ready: SituationSnapshot has all 27 fields, OutcomeLedger is durable and '
        'tenant-scoped, the classifier handles natural language, and the SSO scenario still passes.'))
    l0 = [
        ['Gate', 'Verification', 'Status at e867cb7'],
        ['L0.1 SituationSnapshot 27 fields', 'fields=27 missing=0/17', 'PASS'],
        ['L0.2 OutcomeLedger functional', 'methods=[append,clear,close,count,get_all]', 'PASS'],
        ['L0.3 Classifier new types', 'tentative/sarcasm/artifact (3/3)', 'PASS'],
        ['L0.4 SSO scenario 7/7', 'pytest test_hybrid_e2e.py test_sprint_completion.py', 'DEFERRED'],
    ]
    story.append(make_table(l0, col_widths=[5*cm, 7*cm, 3.5*cm], font_size=9))
    story.append(spacer(8))
    story.append(p(
        'If any L0 check fails, STOP. Fix the L0 prerequisite first. The L0 gate is verified by '
        'execution (P1, P31), not by reading code or trusting commit messages.'))
    story.append(PageBreak())

def build_ch_phases(story):
    story.append(heading('Chapter 4 — The 8-Phase Plan', STYLES['h1'], level=0))
    story.append(p(
        'The plan is 33 days, ~132 hours. Each phase has deliverables, a gate, and a verification '
        'command. The gate MUST pass before the next phase begins. The auditor independently verifies '
        'each gate by execution (P31).'))
    phases = [
        ['Phase', 'Days', 'Hours', 'Deliverable', 'Gate'],
        ['1: Extension scaffold', '1-3', '12',
         'manifest.json, background.js, consent-manager.js, panel shell, content.js, offscreen scaffold',
         'Extension loads 0 errors; consent gates every capture; WebSocket exists'],
        ['2: Audio + transcription', '4-7', '16',
         'offscreen.js audio capture, Whisper transcription, speaker diarization, live transcript',
         'Transcript appears <3s; consent-denied path tested'],
        ['3: Scene 1 pre-call', '8-11', '16',
         'lobby detection, pre_call.py, attendee intelligence, suggested talking points',
         'Pre-call briefing <2s; every suggestion has evidence chain'],
        ['4: Scene 2 live', '12-18', '28',
         'live_engine.py, 4 card types, color borders, confidence bars, animations, aria-live',
         'Objection card <5s; commitments deduped; confidence honest (P25)'],
        ['5: Scene 3 post-call', '19-23', '20',
         'post_call.py, summary, stats, commitments, draft email, "What Maestro learned"',
         'Summary <5s; commitments ingested to OutcomeLedger; draft cites specifics'],
        ['6: Evidence + confidence', '24-27', '16',
         'evidence-chain links, confidence display gate (P25), law promotion visibility',
         'Every card has View-evidence link; no confidence without denominator'],
        ['7: Accessibility + polish', '28-30', '12',
         'keyboard nav, aria-live, contrast >= 4.5:1, reduced-motion, mobile-responsive',
         'Lighthouse a11y >= 90; Tab+Enter works; reduced-motion respected'],
        ['8: Integration + audit', '31-33', '12',
         'E2E test, cross-surface coherence (P24), independent auditor verdict',
         'E2E passes; coherence test passes; auditor says "Phase 8 PASS"'],
    ]
    story.append(make_table(phases, col_widths=[3*cm, 1.2*cm, 1.2*cm, 5*cm, 5.1*cm], font_size=7.5))
    story.append(spacer(10))
    story.append(p(
        'Total: 33 days, ~132 hours. The plan is sequential — each phase depends on the prior. The '
        'governance loop enforces this: no phase begins until the prior phase\'s gate passes '
        'independent verification.'))
    story.append(PageBreak())

def build_ch_spec(story):
    story.append(heading('Chapter 5 — Technical Spec', STYLES['h1'], level=0))
    story.append(p(
        'The technical spec is taken directly from the source 3-scene description. These values are '
        'not suggestions — they are the design contract.'))
    spec = [
        ['Element', 'Value'],
        ['Side panel width', '380px (Chrome native side panel)'],
        ['New-card animation', 'cardSlideIn 400ms ease-out'],
        ['Glow effect', 'box-shadow 0 0 20px rgba(255,214,10,0.15), fades after 5s'],
        ['Rose (objection)', '#FF5577'],
        ['Amber (commitment)', '#FFB84D'],
        ['Purple (whisper)', '#7C5CFF'],
        ['Cyan (pattern)', '#5CC8FF'],
        ['Green (tracked)', '#00D4AA'],
        ['Typography', 'Inter (sans) + JetBrains Mono (numbers)'],
        ['Accessibility', 'keyboard-navigable, focus-visible, aria-live regions'],
        ['Consent', 'ConsentManager.checkConsent() gates every getUserMedia/getDisplayMedia'],
        ['Audit log', 'Every suggestion, capture, dismiss logged'],
    ]
    story.append(make_table(spec, col_widths=[4.5*cm, 10.5*cm], font_size=9))
    story.append(spacer(10))

    story.append(heading('Chapter 6 — Commit Format (P23)', STYLES['h1'], level=0))
    story.append(p(
        'Every commit MUST include a VERIFICATION section with pasted command output. Claims without '
        'output are not evidence (P23). If the commit has no VERIFICATION section, the auditor rejects it.'))
    story.append(callout(
        '<b>Format:</b><br/>'
        'feat(copilot): Phase N — short description<br/><br/>'
        'VERIFICATION:<br/>'
        '$ command<br/>'
        'output<br/><br/>'
        '$ command<br/>'
        'output<br/><br/>'
        'Governance: P1 (execute), P23 (commit cites output), P26 (re-read from disk).<br/>'
        'Read receipt: pasted in worklog at timestamp.'))
    story.append(PageBreak())

def build_ch_loop(story):
    story.append(heading('Chapter 7 — The Governance Loop', STYLES['h1'], level=0))
    story.append(p(
        'The governance loop is the enforcement mechanism. It is the reason the 9 code-quality '
        'findings from Audit 1 are actually fixed (verified by the auditor at HEAD 09b2b87), not '
        'just claimed fixed. The loop applies equally to the Live Copilot build:'))
    loop = [
        ['Step', 'Action', 'Who'],
        ['1. Before each phase', 'Read GOVERNANCE_LOOP.md + ENTROPY_RECOVERY Part Four+Five from disk; paste 8-field read receipt', 'Coder'],
        ['2. During each phase', 'Cite the P-number principle each fix satisfies (P20 callers, P22 production path, P23 commit output, P24 cross-surface, P25 confidence gate)', 'Coder'],
        ['3. After each phase', 'Run the phase gate commands; paste output in the commit; push to origin/main', 'Coder'],
        ['4. Auditor verifies', 'Fetch → checkout HEAD → run gate independently (P31) → run SSO scenario (P29) → publish verdict', 'Auditor'],
        ['5. Next phase', 'Only after auditor says "Phase N PASS" may the next phase begin', 'Both'],
    ]
    story.append(make_table(loop, col_widths=[2.5*cm, 9.5*cm, 3*cm], font_size=8.5))
    story.append(spacer(10))

    story.append(heading('7.1 Read Receipt', STYLES['h2'], level=1))
    story.append(p(
        '<b>GOVERNANCE LOOP READ RECEIPT (Coder):</b><br/>'
        '- GOVERNANCE_LOOP.md read at 2026-07-07T05:35:00Z. Key line: "THE LOOP CANNOT BE BROKEN."<br/>'
        '- ENTROPY_RECOVERY.md Part Four read at 2026-07-07T05:35:00Z.<br/>'
        '&nbsp;&nbsp;P20: "If M of N call sites pass it, the fix is (M/N)% done."<br/>'
        '&nbsp;&nbsp;P26: "Principles don\'t enforce themselves. Re-application does."<br/>'
        '- ENTROPY_RECOVERY.md Part Five read at 2026-07-07T05:35:00Z.<br/>'
        '&nbsp;&nbsp;P27: "Read at least the key assertions of the tests you\'re counting."<br/>'
        '&nbsp;&nbsp;P34: "The auditor\'s method is not a memory — it\'s a checklist."<br/>'
        '- AUDITOR_GOVERNANCE.md Gates 15-20 read at 2026-07-07T05:35:00Z.<br/>'
        '&nbsp;&nbsp;Gate 15: "A function signature with a new parameter proves nothing."<br/>'
        '&nbsp;&nbsp;Gate 17: "Reading the dedup logic proves nothing; executing it does."<br/>'
        '- audit_scripts/audit_gates.sh read — enforces Gate 11 + full suite + all verify scripts.<br/>'
        '<br/>'
        '<b>Auditor: Read GOVERNANCE_LOOP.md, AUDITOR_GOVERNANCE.md, and ENTROPY_RECOVERY.md Part '
        'Four + Part Five from disk before auditing. Do not audit from memory. The loop cannot be broken.</b>'))

    story.append(heading('7.2 Honest Disclosure', STYLES['h2'], level=1))
    story.append(callout(
        '<b>This roadmap is the governed source of truth for the Maestro Live Copilot build.</b> '
        'It covers all 3 scenes (pre-call, live, post-call), the 8-phase execution plan, the L0 '
        'prerequisite gate, the technical spec, and the governance loop. The coder can execute every '
        'phase. The auditor independently verifies each gate by execution (P31). The CEO enforces the '
        'loop: no message without a read receipt, no claim without a pushed commit, no gate the '
        'auditor hasn\'t independently verified. The loop cannot be broken.'))

def main():
    doc = TocDocTemplate(
        OUTPUT, pagesize=A4,
        leftMargin=2.2*cm, rightMargin=2.2*cm,
        topMargin=2*cm, bottomMargin=1.8*cm,
        title='Maestro Live Copilot — Governed Execution Roadmap',
        author='MaestroAgent Coder',
        subject='8-phase plan: real-time meeting intelligence, done right',
        creator='ReportLab',
    )
    story = []
    build_cover(story)
    story.append(heading('Table of Contents', STYLES['h1'], level=0))
    story.append(spacer(8))
    from reportlab.platypus.tableofcontents import TableOfContents
    toc = TableOfContents()
    toc.levelStyles = [STYLES['toc_l0'], STYLES['toc_l1']]
    story.append(toc)
    story.append(PageBreak())
    build_ch_ethics(story)
    build_ch_scenes(story)
    build_ch_l0(story)
    build_ch_phases(story)
    build_ch_spec(story)
    build_ch_loop(story)
    doc.multiBuild(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"PDF generated: {OUTPUT}")
    print(f"Size: {os.path.getsize(OUTPUT):,} bytes")

if __name__ == '__main__':
    main()
