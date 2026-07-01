"""
Maestro Constitution V8 — Institutional Memory
The Final Constitution. V6 improved the organization. V7 revised Maestro's theory.
V8 unifies them into one thing the customer sees: "What we've learned."
19 engines become 1 product: Institutional Memory.

First: fix 2 V6 wiring gaps (1.5 hours). Then: 6 V8 specs (~12 days).
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
SECTION_BG    = colors.HexColor('#f0fdf4')
CARD_BG       = colors.HexColor('#dcfce7')
TABLE_STRIPE  = colors.HexColor('#f0fdf4')
HEADER_FILL   = colors.HexColor('#14532d')
BORDER        = colors.HexColor('#86efac')
ACCENT        = colors.HexColor('#15803d')
TEXT_PRIMARY  = colors.HexColor('#1a1c1e')
TEXT_MUTED    = colors.HexColor('#6b7178')

ST_DELIVERED  = colors.HexColor('#15803d')
ST_PARTIAL    = colors.HexColor('#b45309')
ST_FAILED     = colors.HexColor('#b91c1c')
ST_V8         = colors.HexColor('#15803d')

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
                      "Maestro Constitution V8 — Institutional Memory  ·  The Final Constitution")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro Constitution V8 — Institutional Memory",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="V8 final constitution — from 19 engines to 1 product: Institutional Memory",
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

def spec_block(num, name, principle, gap, files, api, acceptance, effort, deps):
    flowables = []
    header = Table([[
        Paragraph(f'<font color="white"><b>SPEC #{num}</b></font>',
                  ParagraphStyle('sh', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=colors.white, alignment=TA_CENTER)),
        Paragraph(f'<font color="white"><b>{name}</b></font>',
                  ParagraphStyle('st', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=colors.white, alignment=TA_LEFT))
    ]], colWidths=[28*mm, PAGE_W - MARGIN_L - MARGIN_R - 28*mm - 24])
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ST_V8),
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

    flowables += field('V8 Principle', principle)
    flowables += field('Current codebase gap', gap)
    flowables += field('Files to create/modify', files)
    flowables += field('API contract', api)
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
        f'<font color="{ACCENT.hexval()}"><b>CONSTITUTION V8 — INSTITUTIONAL MEMORY</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Institutional Memory',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=34,
                       leading=38, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        '19 engines become 1 product. The customer never sees versions. They ask "What have we learned?"',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=12,
                       leading=16, textColor=HEADER_FILL, alignment=TA_LEFT, spaceAfter=14)
    ))

    meta = Table([
        [Paragraph('<b>Baseline</b>', S['small']), P('Commit ad00d31. V5 complete (8 specs). V6 complete (6 specs, 2 wiring gaps). 74 backend modules, 28 frontend files. 19 cognitive engines. 423 tests pass.', 'small')],
        [Paragraph('<b>V8 shift</b>', S['small']), P('V6 improved the organization. V7 revised Maestro\'s theory. V8 unifies them: 19 engines become 1 product — Institutional Memory. The customer never sees "DNA" or "Institution Model" or "Trajectory Intervention." They see "What we\'ve learned."', 'small')],
        [Paragraph('<b>Constitutional law</b>', S['small']), P('"Maestro should become the living institutional memory of an organization — continuously observing, questioning, revising, and deepening its understanding until it becomes the most accurate model of how that organization thinks, decides, and learns."', 'small')],
        [Paragraph('<b>Deliverable</b>', S['small']), P('Step 0: fix 2 V6 wiring gaps (1.5 hours). Then 6 V8 specs (~12 days): Institutional Memory Timeline, Institutional Confidence, Unknown Unknowns, Organizational Curiosity, Understanding Map, Unified Surface.', 'small')],
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

    # ── PREAMBLE ─────────────────────────────────────────────────────────
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>WHY V8 EXISTS</b></font>',
                  ParagraphStyle('callout_h', fontName=FONT_HEAD_B, fontSize=10,
                                 leading=13, textColor=ACCENT, spaceAfter=4)),
        P('V3 observed. V4 judged. V5 disappeared. V6 adapted. V7 revised its theory. Each version added '
          'engines. 19 cognitive engines across 6 constitutions. All invisible. All enhancing existing '
          'surfaces. That is a significant engineering achievement.', 'body_left'),
        P('<b>V8 is different.</b> V8 says: stop producing engines. Produce Institutional Memory. The '
          'customer should never see "DNA," "Institution Model," "Trajectory Intervention," "Compounding '
          'Judgment," or "Closed Learning Loop." They should ask "Tell me what we\'ve learned" and hear: '
          '"Over the last six months your organization quietly stopped depending on one engineer, reduced '
          'approval latency by 31%, shifted from reactive reviews to planned reviews, and now predicts '
          'delivery with 18% higher accuracy." That is infinitely more valuable than 19 engine names.', 'body_left'),
        P('<b>The 19 engines remain internally.</b> V8 does not delete them. It changes how they are '
          'EXPOSED. Internally: 19 modules doing their work. Externally: 1 product called Institutional '
          'Memory that answers "What has this organization learned?"', 'body_left'),
        P('<b>Same discipline.</b> Every spec has: principle, codebase gap, files, API, acceptance test, '
          'effort, dependencies. The V5 litmus test (UI simpler) and V6 litmus test (permanently improves) '
          'are retained. A new V8 litmus test is added: "Does this make the customer say \'Maestro knows '
          'how our company works\'?" If yes, it is V8.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── STEP 0: FIX V6 WIRING GAPS ──────────────────────────────────────
    story.append(P('Step 0 — Fix 2 V6 Wiring Gaps (MUST DO FIRST, 1.5 hours)', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ST_FAILED.hexval()}"><b>2 GAPS FROM ROUND 24 — FIX BEFORE V8</b></font>',
                  ParagraphStyle('gap_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ST_FAILED, spaceAfter=4)),
        P('<b>Gap 1: Background loop NOT hooked into live_ingest() (30 min).</b> '
          'Background adaptation only runs when TODAY fetches the API — not on signal ingest. V6 Law 2 '
          'violated. Fix: add <font face="Mono">BackgroundLoop.check()</font> call at end of '
          '<font face="Mono">oem_state.py live_ingest()</font>.', 'body_left'),
        P('<b>Gap 2: DNA NOT referenced in wisdom.py (1 hour).</b> '
          'DNA produces 7 chromosomes but does not filter recommendations. Fix: modify '
          '<font face="Mono">wisdom.py</font> to import <font face="Mono">organizational_dna.py</font>, '
          'compute alignment_score per recommendation.', 'body_left'),
        P('<b>These are 1.5 hours total. Do them first. Then build V8.</b>', 'body_left'),
    ], bg=colors.HexColor('#fef3f2'), border=colors.HexColor('#fecaca'), accent=ST_FAILED))

    # ── SPEC SUMMARY ─────────────────────────────────────────────────────
    story.append(P('The 6 V8 Specifications', 'h1'))

    rows = [
        ['#', 'Specification', 'Effort', 'What It Replaces/Creates'],
        ['1', 'Institutional Memory Timeline', '2 days', 'Replaces Evolution Narrative (autobiography). Experiential moments, not literary chapters.'],
        ['2', 'Institutional Confidence', '1.5 days', 'NEW. "How well do we understand Finance? 96%. Sales? 18%." Coverage map per domain.'],
        ['3', 'Unknown Unknowns', '1.5 days', 'NEW. "We have insufficient evidence for Executive hiring, Compensation, Board decisions." Honest gaps.'],
        ['4', 'Organizational Curiosity', '2 days', 'Maestro asks the org questions. "Was Alice\'s departure planned?" Feedback partnership.'],
        ['5', 'Understanding Map', '2 days', 'NEW. Visual coverage that grows with each recommendation. Customers see the product compound.'],
        ['6', 'Unified "Your Organization" Surface', '3 days', 'Merges V6+V7 into one screen. One page. Everything else command palette.'],
        ['', '', '', ''],
        ['TOTAL', '6 V8 specs', '~12 days', 'V8: from 19 engines to 1 product — Institutional Memory'],
    ]
    t = Table(rows, colWidths=[8*mm, 42*mm, 18*mm, PAGE_W - MARGIN_L - MARGIN_R - 68*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, 6), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, 8), (-1, 8), colors.HexColor('#dcfce7')),
        ('FONTNAME', (0, 8), (-1, 8), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(PageBreak())

    # ── SPEC 1: INSTITUTIONAL MEMORY TIMELINE ────────────────────────────
    story.extend(spec_block(
        1, 'Institutional Memory Timeline — experiential moments, not literary chapters',
        'V8: "Organizations don\'t read autobiographies. They revisit moments. Memory should feel experiential, not literary." Instead of "2025 Q1: Your organization became cautious," show a moment card: "March 14: Deployment failure. Maestro predicted 62%. Reality: failure occurred. Learning: review order mattered more than deployment size. Institution changed. Every deployment recommendation since then uses this rule."',
        'evolution_narrative.py (162 lines) produces 5 literary chapters ("Who you are," "What you\'ve learned"). The autobiography surface (autobiography.js, 41 lines) renders them as a narrative. The gap: the narrative is literary, not experiential. Organizations do not read autobiographies. They revisit moments — specific predictions, specific outcomes, specific learnings, specific institutional changes.',
        'CREATE <font face="Mono">backend/maestro_oem/memory_timeline.py</font> — the MemoryTimelineEngine. Produces TIMELINE MOMENTS, not chapters. Each moment is a card: {date, event, prediction (what Maestro predicted), reality (what happened), learning (what the org learned), institution_change (how the org changed), evidence_count}. Sources: prediction_lifecycle.py (resolved predictions — each is a moment), evolution_tracker.py (eliminated failure modes — each is a moment), model_revision.py (V7.1, when built — each revision is a moment). REPLACE <font face="Mono">static/js/autobiography.js</font> with <font face="Mono">static/js/memory_timeline.js</font> — renders moments as a vertical timeline of cards (not paragraphs). Each card is self-contained: date + event + prediction + reality + learning + change. Modify the command-palette entry from "Your Organization\'s Story" to "What we\'ve learned."',
        'GET /api/oem/memory-timeline returns: { "moments": [ {"date": "2024-11-12", "event": "payments-edge circuit breaker PR", "prediction": "Maestro predicted 62% success", "reality": "Failure occurred — circuit breaker did not trigger in time", "learning": "Review order mattered more than deployment size. The PR was reviewed after merge, not before.", "institution_change": "Every deployment recommendation since Nov 12 now requires pre-merge review for circuit-breaker changes.", "evidence_count": 3} ], "summary": "Your organization has 12 learning moments. The most recent: a deployment failure that changed how circuit-breaker reviews work." }. Must have at least 3 moments with all 6 fields (or honest "insufficient history").',
        '1) GET /api/oem/memory-timeline returns moments array (3+ or honest). 2) Each moment has date, event, prediction, reality, learning, institution_change. 3) Moments reference real prediction_lifecycle / evolution_tracker data. 4) The "What we\'ve learned" surface renders moments as cards (not paragraphs). 5) V5 litmus: no new sidebar item (command-palette only). 6) V8 litmus: does this make the customer say "Maestro knows how our company works"? YES — it shows specific moments where Maestro learned.',
        '2 days (1.5 days engine + 0.5 day frontend)',
        'prediction_lifecycle.py (for resolved predictions). evolution_tracker.py (for eliminated failure modes). Replaces evolution_narrative.py + autobiography.js.'
    ))

    # ── SPEC 2: INSTITUTIONAL CONFIDENCE ────────────────────────────────
    story.extend(spec_block(
        2, 'Institutional Confidence — "How well do we understand Finance? 96%"',
        'V8: "Not prediction confidence. Institutional confidence. Imagine the CEO asks \'Should I trust Maestro about Marketing?\' Maestro answers: \'No. We\'ve only observed 14 campaigns. Our understanding is still immature.\' That honesty becomes an enormous trust builder."',
        'No module tracks per-domain understanding coverage. confidence.py tracks per-LAW confidence (how sure am I about this pattern?). But there is no per-DOMAIN confidence (how well do I understand the Finance domain? The Engineering domain? The Sales domain?). The gap: Maestro cannot say "I understand Engineering at 91% but Sales at 18%" — it has no domain-level coverage metric.',
        'CREATE <font face="Mono">backend/maestro_oem/institutional_confidence.py</font> — the InstitutionalConfidenceEngine. For each organizational domain (from signal metadata — payments, auth, platform, deployment, legal, etc.): compute coverage_score (0-100) based on: (1) signal_count in that domain, (2) learning_objects in that domain, (3) validated laws in that domain, (4) resolved predictions about that domain, (5) causal chains involving that domain. Also compute maturity_label (nascent/developing/mature/deep). CREATE GET /api/oem/confidence endpoint. MODIFY static/js/today.js — add an "Understanding" section: a calm coverage display per domain (not a chart — a sentence: "We understand Engineering deeply (91%). We\'re still learning about Sales (18%).")',
        'GET /api/oem/confidence returns: { "domains": [ {"domain": "payments", "confidence": 0.91, "maturity": "deep", "signal_count": 12, "laws": 3, "resolved_predictions": 5, "narrative": "We understand payments deeply. 12 signals, 3 validated patterns, 5 resolved predictions."}, {"domain": "sales", "confidence": 0.18, "maturity": "nascent", "signal_count": 2, "laws": 0, "resolved_predictions": 0, "narrative": "We\'re just starting to understand sales. 2 signals, no patterns yet. Trust our recommendations here with caution."} ], "overall_confidence": 0.62, "narrative": "We understand payments and auth deeply. We\'re still learning about sales and legal. Trust our recommendations accordingly." }. Must have at least 3 domains with confidence + maturity + narrative.',
        '1) GET /api/oem/confidence returns domains array (3+) each with confidence (0-1), maturity, signal_count, narrative. 2) Low-confidence domains have honest narrative ("Trust with caution"). 3) TODAY shows "Understanding" section with per-domain confidence. 4) V5 litmus: no new panel — enhances TODAY. 5) V8 litmus: does this make the customer trust Maestro MORE? YES — honesty about gaps builds trust.',
        '1.5 days (1 day coverage-scoring engine + 0.5 day API + frontend)',
        'All existing modules (signal counts per domain, learning objects, laws, predictions, causal chains). No new dependencies.'
    ))

    story.append(PageBreak())

    # ── SPEC 3: UNKNOWN UNKNOWNS ─────────────────────────────────────────
    story.extend(spec_block(
        3, 'Unknown Unknowns — "We have insufficient evidence for Executive hiring"',
        'V8: "Today Maestro reports known patterns. I want areas we do not understand. \'We have insufficient evidence for Executive hiring, Compensation, Board decisions, Vendor negotiations, International expansion.\' That is scientifically honest. And it naturally drives adoption."',
        'curiosity.py (184 lines) identifies untested assumptions and unmeasured domains. But it frames them as QUESTIONS ("Nobody has tested whether..."). V8 reframes them as GAPS: areas where Maestro has NO understanding. The gap: no module explicitly lists what Maestro does NOT know — the blind spots, the coverage holes, the domains with zero signals.',
        'CREATE <font face="Mono">backend/maestro_oem/unknown_unknowns.py</font> — the UnknownUnknownsEngine. Produces a list of organizational domains/activities where Maestro has insufficient evidence (< 3 signals or < 1 learning object). Sources: scan all signal types in signal_classes.py, identify which organizational activities (hiring, compensation, board decisions, vendor negotiations, international expansion, M&A, budgeting, performance reviews, etc.) have ZERO or near-zero signal coverage. CREATE GET /api/oem/unknowns endpoint. MODIFY static/js/today.js — add an "What Maestro doesn\'t know yet" section: "We don\'t understand: Executive hiring (0 signals), Compensation (0 signals), Board decisions (0 signals). Connect more signal sources to learn about these areas."',
        'GET /api/oem/unknowns returns: { "blind_spots": [ {"area": "Executive hiring", "signal_count": 0, "reason": "No HR or recruiting signals ingested. Connect an HR system to learn about hiring decisions.", "impact": "Maestro cannot advise on hiring patterns or departure risks at the executive level."}, {"area": "Compensation", "signal_count": 0, "reason": "No compensation or payroll signals. Compensation decisions are invisible to Maestro.", "impact": "Maestro cannot detect compensation-related retention risks."} ], "coverage_gaps": [ {"area": "Sales", "signal_count": 2, "reason": "Only 2 signals from sales. Insufficient for pattern detection.", "impact": "Sales recommendations are low-confidence."} ], "narrative": "Maestro has 5 complete blind spots and 2 coverage gaps. Connecting HR, compensation, and sales systems would significantly improve understanding." }. Must have at least 3 blind_spots with area + reason + impact.',
        '1) GET /api/oem/unknowns returns blind_spots (3+) + coverage_gaps. 2) Each blind_spot has area, signal_count (0 or near-0), reason, impact. 3) TODAY shows "What Maestro doesn\'t know yet" section. 4) V5 litmus: no new panel — enhances TODAY. 5) V8 litmus: does this build trust? YES — honesty about gaps is the strongest trust signal.',
        '1.5 days (1 day gap-detection engine + 0.5 day API + frontend)',
        'signal_classes.py (to enumerate signal types). institutional_confidence.py (V8 #2, for coverage thresholds). curiosity.py (for existing untested-assumption logic).'
    ))

    # ── SPEC 4: ORGANIZATIONAL CURIOSITY ─────────────────────────────────
    story.extend(spec_block(
        4, 'Organizational Curiosity — Maestro asks the org questions',
        'V8: "Instead of waiting for signals, Maestro starts asking: \'We don\'t understand why approvals doubled this week. Can you tell us?\' or \'Was Alice\'s departure planned?\' or \'Did Legal change policy?\' The organization teaches Maestro. Maestro teaches the organization. That\'s a genuine feedback partnership."',
        'curiosity.py (184 lines) generates questions for the user ("Nobody has tested whether..."). But these are passive — they appear in TODAY and wait for the user to act. V8 makes curiosity ACTIVE: Maestro detects anomalies (approval rate doubled, signal pattern changed, a key person disappeared from signals) and ASKS the organization directly. The gap: no mechanism for Maestro to ask a question, receive an answer, and incorporate the answer into its model.',
        'CREATE <font face="Mono">backend/maestro_oem/organizational_curiosity.py</font> — the OrganizationalCuriosityEngine. Detects anomalies (from signal history: "approval count doubled this week vs 4-week average"), generates specific questions ("We noticed approval volume doubled this week. Was this intentional?"), and provides a mechanism for the user to ANSWER (text input or multiple choice). Each answer is stored as a new signal (type: human_context) that feeds into the model. CREATE GET /api/oem/curiosity/questions endpoint (returns open questions). CREATE POST /api/oem/curiosity/answer endpoint (accepts answer, creates signal). MODIFY static/js/today.js — add a "Maestro has questions" card: "We noticed approval volume doubled this week. Was this intentional?" with a text input + submit button. When answered, the card disappears and the answer becomes a signal.',
        'GET /api/oem/curiosity/questions returns: { "questions": [ {"id": "q-001", "question": "We noticed approval volume doubled this week (from 3 to 7). Was this intentional?", "context": "4-week average was 3.2 approvals/week. This week: 7.", "type": "anomaly_explanation", "asked_at": "..."} ], "open_count": 1 }. POST /api/oem/curiosity/answer accepts: {"question_id": "q-001", "answer": "Yes, we\'re catching up after the holiday backlog."}. Returns: {"ok": true, "signal_created": true, "signal_id": "sig-xxx"}. The answer becomes a human_context signal that feeds into the model.',
        '1) GET /api/oem/curiosity/questions returns questions array (1+ or honest "no open questions"). 2) Each question has id, question, context, type. 3) POST /api/oem/curiosity/answer creates a signal (verified: signal appears in model after answering). 4) TODAY shows "Maestro has questions" card with input + submit. 5) After answering, card disappears. 6) V5 litmus: no new panel — enhances TODAY. 7) V8 litmus: does this make the customer say "Maestro knows how our company works"? YES — the org teaches Maestro directly.',
        '2 days (1.5 days anomaly detection + question generation + answer ingestion + 0.5 day API + frontend)',
        'signal history (for anomaly detection). signal.py (for creating human_context signals). curiosity.py (for existing question logic).'
    ))

    story.append(PageBreak())

    # ── SPEC 5: UNDERSTANDING MAP ────────────────────────────────────────
    story.extend(spec_block(
        5, 'Understanding Map — visual coverage that grows with each recommendation',
        'V8: "Imagine every recommendation literally coloring in a map of organizational understanding. Engineering: 91%. Sales: 18%. Customers would immediately understand why the product compounds." Every recommendation should grow the map. After each resolved prediction, the domain\'s coverage increases.',
        'institutional_confidence.py (V8 #2) computes per-domain confidence. But it is a number, not a visual. The gap: no visual representation of coverage that makes the compounding visible. A CEO should be able to SEE that Maestro understands Engineering deeply (green bar) but Sales poorly (red bar) — and that the green bars are growing over time.',
        'CREATE <font face="Mono">backend/maestro_oem/understanding_map.py</font> — the UnderstandingMapEngine. Produces a visual map: for each domain, a coverage bar (0-100%) with color (red < 30%, amber 30-60%, green 60-90%, deep green > 90%). Also produces a GROWTH RATE: "Engineering coverage grew 12% this month (from 79% to 91%)." The map updates after each resolved prediction (the domain\'s coverage increases). CREATE GET /api/oem/understanding-map endpoint. CREATE <font face="Mono">static/js/understanding_map.js</font> — renders the map as horizontal bars (one per domain) with color + percentage + growth indicator. MODIFY static/js/learn.js — add the Understanding Map as the TOP section (before everything else): the first thing the user sees in LEARN is "How well Maestro understands your organization."',
        'GET /api/oem/understanding-map returns: { "domains": [ {"domain": "payments", "coverage": 91, "color": "deep_green", "growth_this_month": "+3%", "narrative": "Payments: deeply understood (91%). Growing steadily."}, {"domain": "auth", "coverage": 78, "color": "green", "growth_this_month": "+5%", "narrative": "Auth: well understood (78%). Fast growth."}, {"domain": "sales", "coverage": 18, "color": "red", "growth_this_month": "0%", "narrative": "Sales: barely understood (18%). No growth. Connect sales signals."} ], "overall_coverage": 62, "overall_growth": "+4% this month", "narrative": "Maestro understands 62% of your organization. Coverage grew 4% this month, mostly from resolved predictions in auth and payments." }. Must have at least 3 domains with coverage + color + growth + narrative.',
        '1) GET /api/oem/understanding-map returns domains (3+) with coverage (0-100), color, growth_this_month, narrative. 2) LEARN surface shows Understanding Map as TOP section. 3) Map is visual (horizontal bars with colors). 4) growth_this_month is computed (not hardcoded). 5) V5 litmus: enhances LEARN (no new panel). 6) V8 litmus: does this make the customer say "Maestro knows how our company works"? YES — the map VISUALLY proves it.',
        '2 days (1 day map engine + growth tracking + 0.5 day API + 0.5 day frontend visualization)',
        'institutional_confidence.py (V8 #2). prediction_lifecycle.py (for growth tracking — each resolved prediction grows the domain).'
    ))

    # ── SPEC 6: UNIFIED SURFACE ──────────────────────────────────────────
    story.extend(spec_block(
        6, 'Unified "Your Organization" Surface — one page, everything else command palette',
        'V8: "Eventually the product becomes: Your Organization — Today / Needs attention / Learning / Recent changes / Understanding / Open questions / Prepared decisions. One page. Everything else Command Palette." The customer never sees 19 engines. They see one page that answers "What have we learned?"',
        'TODAY, LEARN, and Cognition are 3 separate surfaces with overlapping content. TODAY has the morning brief + nudges + curiosity + background loop + trajectory intervention. LEARN has DNA + evolution tracker + understanding map (V8 #5). Cognition has 10+ organ render sections. The gap: the customer must navigate between 3 surfaces to understand "what we\'ve learned." V8 unifies them into one "Your Organization" surface.',
        'RESTRUCTURE static/js/today.js — rename to "Your Organization" surface. Merge the key content from LEARN and Cognition into a SINGLE unified page with 7 sections: (1) Today (morning brief — current), (2) Needs attention (trajectory intervention + nudges — current), (3) Learning (curiosity questions + background notices — current), (4) Recent changes (evolution tracker + DNA evolution — from LEARN), (5) Understanding (understanding map + institutional confidence — from V8 #2/#5), (6) Open questions (curiosity questions — from V8 #4), (7) Prepared decisions (executive function plans — current). MOVE Cognition surface to command-palette only (it becomes a "deep view" for power users, not the default). Sidebar: "Today" becomes "Your Organization" (or just "Maestro"). LEARN and Cognition remain accessible via command palette but are NOT in the sidebar. Sidebar: "Your Organization" + "Work" + "Ask" + "More..." = 4 items (unchanged).',
        'No new API. This is a frontend restructure. The unified surface fetches from: /ceo-briefing, /nudges, /curiosity/questions, /background-loop, /trajectory-intervention, /evolution-tracker, /dna, /understanding-map, /confidence, /execute. All existing APIs. The restructure is in how the content is PRESENTED — one page, 7 sections, scrollable, calm.',
        '1) The "Your Organization" surface (renamed from TODAY) contains 7 sections. 2) Each section renders content from existing APIs (no new APIs). 3) LEARN and Cognition are command-palette only (not in sidebar). 4) Sidebar: 4 items ("Your Organization" + "Work" + "Ask" + "More..."). 5) V5 litmus: SIMPLER (3 surfaces merged into 1). 6) V8 litmus: does this make the customer say "Maestro knows how our company works"? YES — one page answers everything.',
        '3 days (2 days frontend restructure + 0.5 day API consolidation + 0.5 day testing)',
        'All V3-V6 APIs (existing). V8 #1-#5 (for timeline, confidence, unknowns, curiosity, map content).'
    ))

    # ── BUILD ORDER ──────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(P('Build Order', 'h1'))

    dep_rows = [
        ['Step', 'Spec', 'Effort', 'Dependency', 'Key Output'],
        ['0', 'Fix V6 wiring gaps', '1.5 hours', 'None', 'Background loop in live_ingest + DNA in wisdom.py'],
        ['1', '#1 Institutional Memory Timeline', '2 days', 'prediction_lifecycle.py + evolution_tracker.py', 'Experiential moments (not literary chapters)'],
        ['2', '#2 Institutional Confidence', '1.5 days', 'All existing modules', 'Per-domain coverage score ("Finance: 96%")'],
        ['3', '#3 Unknown Unknowns', '1.5 days', 'V8 #2 (for coverage thresholds)', 'Honest gaps ("We don\'t understand: hiring, compensation")'],
        ['4', '#4 Organizational Curiosity', '2 days', 'signal history + signal.py', 'Maestro asks the org questions + ingests answers'],
        ['5', '#5 Understanding Map', '2 days', 'V8 #2 (institutional confidence)', 'Visual coverage bars that grow over time'],
        ['6', '#6 Unified Surface', '3 days', 'V8 #1-#5 + all V3-V6 APIs', 'One page. Everything else command palette.'],
        ['', '', '', '', ''],
        ['TOTAL', '6 V8 specs + V6 fixes', '~12 days + 1.5 hours', 'V5+V6 complete', 'V8: from 19 engines to 1 product — Institutional Memory'],
    ]
    t = Table(dep_rows, colWidths=[10*mm, 38*mm, 16*mm, 45*mm, 55*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, 7), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, 9), (-1, 9), colors.HexColor('#dcfce7')),
        ('FONTNAME', (0, 9), (-1, 9), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]))
    story.append(t)

    # ── THE V8 LITMUS TEST ───────────────────────────────────────────────
    story.append(P('The V8 Litmus Test', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>DOES THIS MAKE THE CUSTOMER SAY "MAESTRO KNOWS HOW OUR COMPANY WORKS"?</b></font>',
                  ParagraphStyle('litmus_h', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=ACCENT, spaceAfter=4)),
        P('V5 litmus: "Is the UI simpler?" (retained).', 'body_left'),
        P('V6 litmus: "Does this permanently improve the organization?" (retained).', 'body_left'),
        P('V7 litmus: "Does this make Maestro\'s understanding more accurate?" (retained, when V7.1 is built).', 'body_left'),
        P('<b>V8 litmus (NEW): "Does this make the customer say \'Maestro knows how our company works\'?"</b>', 'body_left'),
        P('Every V8 spec must pass. The bar is not "does the engine work?" or "is the UI simpler?" or '
          '"does the org improve?" It is: does the CUSTOMER experience Maestro as something that knows '
          'their company? If the customer sees engine names, version numbers, or implementation details, '
          'it fails. If the customer sees "What we\'ve learned" and feels understood, it passes.', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ACCENT))

    # ── THE END STATE ────────────────────────────────────────────────────
    story.append(P('The End State', 'h1'))
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>"MAESTRO KNOWS HOW OUR COMPANY WORKS"</b></font>',
                  ParagraphStyle('end_h', fontName=FONT_HEAD_B, fontSize=12,
                                 leading=15, textColor=ACCENT, spaceAfter=4)),
        P('<b>One year later, the customer no longer says "We use Maestro." They say "Maestro knows how '
          'our company works." That sentence is worth more than any feature, any dashboard, any copilot. '
          'Because nobody else can say it.</b>', 'body_left'),
        P('The 19 engines remain internally. The customer sees one product: Institutional Memory. They '
          'open one page: "Your Organization." They see: what needs attention, what they\'ve learned, '
          'where they\'re drifting, what Maestro doesn\'t know yet, what questions Maestro has for them, '
          'and how well Maestro understands each part of the company. They never see "DNA" or "Institution '
          'Model" or "Trajectory Intervention." They see understanding.', 'body_left'),
        P('<b>The constitutional law:</b> "Maestro should become the living institutional memory of an '
          'organization — continuously observing, questioning, revising, and deepening its understanding '
          'until it becomes the most accurate model of how that organization thinks, decides, and learns."', 'body_left'),
        P('<b>Build order: Step 0 (fix V6 gaps, 1.5 hours) -> #1 Timeline (2 days) -> #2 Confidence '
          '(1.5 days) -> #3 Unknowns (1.5 days) -> #4 Curiosity (2 days) -> #5 Map (2 days) -> #6 '
          'Unified Surface (3 days). Total ~12 days + 1.5 hours. When complete, V8 is done. The product '
          'is Institutional Memory. Ship the 90-day pilot.</b>', 'body_left'),
    ], bg=SECTION_BG, border=BORDER, accent=ACCENT))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'MaestroAgent_Constitution_V8_Institutional_Memory.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
