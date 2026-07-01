"""
Maestro Product Philosophy Review — Round 7
The Invisible Maestro: does it deliver a new interaction paradigm, or is it a reskin?

This is a product-philosophy review, not a security review. The bar is the
Constitution v2 prompt: "Every increase in Maestro's internal intelligence
must reduce the amount of interface exposed to the customer." Every claim
verified against source.
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
SECTION_BG    = colors.HexColor('#f3f4f5')
CARD_BG       = colors.HexColor('#f1f3f4')
TABLE_STRIPE  = colors.HexColor('#f5f6f7')
HEADER_FILL   = colors.HexColor('#1f2937')
BORDER        = colors.HexColor('#c7ccd1')
ACCENT        = colors.HexColor('#7c3aed')  # purple — product review, not security
TEXT_PRIMARY  = colors.HexColor('#1a1c1e')
TEXT_MUTED    = colors.HexColor('#6b7178')

ST_DELIVERED  = colors.HexColor('#15803d')
ST_PARTIAL    = colors.HexColor('#b45309')
ST_FAILED     = colors.HexColor('#b91c1c')

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
                      "Maestro Product Philosophy Review — Round 7  ·  The Invisible Maestro  ·  Independent review")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro Product Philosophy Review — Round 7",
        author="Independent Reviewer (Super Z, Z.ai)",
        subject="Round-7 product-philosophy review of The Invisible Maestro redesign",
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

def status_tag(status):
    color_map = {
        'DELIVERED': (ST_DELIVERED, 'DELIVERED'),
        'PARTIAL':   (ST_PARTIAL, 'PARTIAL'),
        'FAILED':    (ST_FAILED, 'NOT DELIVERED'),
    }
    c, label = color_map[status]
    t = Table([[Paragraph(f'<font color="white"><b>{label}</b></font>', S['verdict'])]],
              colWidths=[72], rowHeights=[14])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t

def claim_block(num, claim, status, evidence, detail):
    """A Constitution claim with delivery status."""
    status_color = {'DELIVERED': ST_DELIVERED, 'PARTIAL': ST_PARTIAL, 'FAILED': ST_FAILED}[status]

    header = Table([[
        status_tag(status),
        Paragraph(f'<font color="{status_color.hexval()}"><b>Claim #{num}</b></font>',
                  ParagraphStyle('claim_title', fontName=FONT_HEAD_B, fontSize=11,
                                 leading=14, textColor=TEXT_PRIMARY, alignment=TA_LEFT))
    ]], colWidths=[76, PAGE_W - MARGIN_L - MARGIN_R - 76 - 24])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    body_flow = [
        Paragraph(f'<font color="{TEXT_MUTED.hexval()}"><b>Constitution claim</b></font>', S['label']),
        P(claim, 'body_left'),
        Paragraph(f'<font color="{TEXT_MUTED.hexval()}"><b>Evidence verified at 6b19e5c</b></font>', S['label']),
        P(evidence, 'body_left'),
        Paragraph(f'<font color="{TEXT_MUTED.hexval()}"><b>Detail</b></font>', S['label']),
        P(detail, 'body_left'),
    ]

    body = Table([[body_flow]], colWidths=[PAGE_W - MARGIN_L - MARGIN_R - 24])
    body.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CARD_BG),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LINEBEFORE', (0, 0), (0, -1), 3, status_color),
    ]))

    return KeepTogether([header, body, Spacer(1, 8)])

def build_story():
    story = []

    # ── COVER ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f'<font color="{ACCENT.hexval()}"><b>ROUND 7 — PRODUCT PHILOSOPHY REVIEW</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'The Invisible Maestro',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=30,
                       leading=34, textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4)
    ))
    story.append(Paragraph(
        'Does it deliver a new interaction paradigm, or is it a reskin?',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=14,
                       leading=18, textColor=HEADER_FILL, alignment=TA_LEFT, spaceAfter=14)
    ))

    meta = Table([
        [Paragraph('<b>Reviewer</b>', S['small']), P('Independent (Super Z, Z.ai) — reviewing as CPO/CDO/CXO per the Constitution v2 prompt', 'small')],
        [Paragraph('<b>Commit</b>', S['small']), P('6b19e5c — "feat(constitution-v2): The Invisible Maestro — 4 meta-surfaces + Organizational Dot"', 'small')],
        [Paragraph('<b>Bar</b>', S['small']), P('The Constitution v2 prompt: "Every increase in Maestro\'s internal intelligence must reduce the amount of interface exposed to the customer."', 'small')],
        [Paragraph('<b>Coder\'s claim</b>', S['small']), P('"The sidebar went from 22 surfaces to 4... a new interaction paradigm, not a feature addition."', 'small')],
        [Paragraph('<b>Reviewer\'s verdict</b>', S['small']), Paragraph(f'<font color="{ST_PARTIAL.hexval()}"><b>PARTIAL — genuine visual craft, but the fundamental law is violated. The interface INCREASED, not decreased.</b></font>', S['small'])],
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

    # TL;DR
    story.append(callout_box([
        Paragraph(f'<font color="{ACCENT.hexval()}"><b>EXECUTIVE SUMMARY (TL;DR)</b></font>',
                  ParagraphStyle('callout_h', fontName=FONT_HEAD_B, fontSize=10,
                                 leading=13, textColor=ACCENT, spaceAfter=4)),
        P('The Invisible Maestro is a genuine visual redesign with real CSS craft, but it is a <b>reskin, not a '
          'paradigm shift</b>. The Constitution v2\'s fundamental law — "every increase in intelligence must '
          'reduce the amount of interface exposed" — is <b>violated</b>. The sidebar went from 19 surfaces to '
          '23, not from 22 to 4. The 4 new meta-surfaces (TODAY, WORK, ASK, LEARN) were ADDED on top of the '
          '22 old surfaces, which remain under a "Deep capabilities" divider. The coder\'s claim "the sidebar '
          'went from 22 surfaces to 4" is <b>false</b>. The actual count is 23 surfaces, verified by '
          '<font face="Mono">grep -c "data-surface=" app.html</font>.', 'body_left'),
        P('<b>What is genuinely delivered:</b> TODAY is a well-composed morning brief (5 items, weather metaphor, '
          'greeting, dot integration). LEARN has genuine story narratives from real API data. The Organizational '
          'Dot is real (polls every 60s, 3 of 4 colors work, click navigates to TODAY). The heartbeat is real '
          '(CSS animation, respects <font face="Mono">prefers-reduced-motion</font>). The CSS is genuinely calm '
          '(48px padding, 720px max-width, 400ms transitions, Apple Weather aesthetic). No test regressions '
          '(388 pass, 0 fail). Backend unchanged.', 'body_left'),
        P('<b>What is not delivered:</b> WORK is not ambient tool-following — it is a page INSIDE Maestro with '
          'static cards. The Constitution said "The user never opens Maestro. Maestro quietly appears [inside '
          'GitHub/Slack/Jira/Zoom]." There is no browser extension, no Slack bot, no Jira add-on. The GitHub '
          'card says "Your repositories are calm" — hardcoded. The Jira card says "Maestro is watching" — a '
          'placeholder. The dot\'s orange state ("cross-functional impact") is dead code — it checks '
          '<font face="Mono">briefing.contradictions</font> which does not exist in the API response. Confidence '
          'numbers are still exposed in TODAY ("38% confidence") and in ASK v2\'s raw answer text '
          '("(confidence: 1.00)"). Law codes "L-0001" leak through the vocabulary replacement. Vocabulary hiding '
          'only applies to the 4 new surfaces; the 22 old surfaces still display "Law", "Learning Object", '
          '"Receipt", "OEM" directly.', 'body_left'),
        P('<b>The core problem:</b> the Constitution asked the coder to <b>remove</b> interface. The coder '
          '<b>added</b> interface (4 new surfaces on top of 22 old ones). This is the opposite of the '
          'fundamental law. The redesign is worth keeping — TODAY, LEARN, the dot, and the CSS are genuine '
          'improvements. But the claim "a new interaction paradigm" is false. It is a new visual layer on top '
          'of the old interaction model. The old model is still there, still accessible, still in the sidebar.', 'body_left'),
        P('<b>Score: 5/10 for Constitution adherence.</b> The visual craft is 8/10. The paradigm shift is 2/10. '
          'The average is 5. The redesign is a step in the right direction, but it is a first step, not the '
          'arrival. To actually deliver the Invisible Maestro, the coder would need to: (1) remove the 22 old '
          'surfaces from the sidebar (or hide them behind a single "Deep capabilities" modal, not a sidebar '
          'section), (2) build real ambient tool integration (browser extension, Slack bot, Jira add-on), '
          '(3) fix the dot\'s orange state, (4) remove confidence numbers from all surfaces, (5) hide law '
          'codes, (6) apply vocabulary hiding to all surfaces, not just 4. That is weeks of work, not one commit.', 'body_left'),
    ], bg=colors.HexColor('#faf5ff'), border=colors.HexColor('#e9d5ff'), accent=ACCENT))

    story.append(Spacer(1, 6 * mm))

    # ── CLAIM-BY-CLAIM VERIFICATION ──────────────────────────────────────
    story.append(P('Constitution Claims — Delivery Status', 'h1'))
    story.append(P(
        'Each claim from the Constitution v2 prompt was verified against the source at commit '
        '<font face="Mono">6b19e5c</font>. The table below is the ground truth.', 'body'))

    rows = [
        ['#', 'Constitution Claim', 'Status', 'Evidence'],
        ['1', 'Sidebar: 22 surfaces → 4', 'NOT DELIVERED', 'Sidebar has 23 surfaces (verified: grep -c data-surface= app.html = 23). 4 new + 19 old. The old surfaces are under "Deep capabilities" divider, not removed.'],
        ['2', 'TODAY: calm morning brief, no charts, no KPIs', 'DELIVERED', 'today.js composes from /ceo-briefing + /pulse. 5 items: decision, opportunity, risk, learning, prediction. Greeting + weather + dot. 720px max-width, 48px padding. Calm CSS. BUT: line 53 exposes "38% confidence" — Constitution said "never expose confidence numbers alone."'],
        ['3', 'WORK: Maestro follows user into tools (GitHub/Slack/Jira/Zoom)', 'NOT DELIVERED', 'work.js is a page INSIDE Maestro with static cards. No browser extension, no Slack bot, no Jira add-on, no Zoom integration. GitHub card says "Your repositories are calm" — hardcoded. Jira card says "Maestro is watching" — placeholder. The Constitution said "The user never opens Maestro." The user must open Maestro to see WORK.'],
        ['4', 'ASK: intention-based, not search', 'PARTIAL', 'ask_v2.js has intention prompts ("Ship OAuth safely", etc.) and confidence-as-story. BUT: the underlying API is still /api/oem/ask?q=... which is keyword substring search (unchanged since round 3). The frontend rephrases; the backend does not translate intentions.'],
        ['5', 'LEARN: stories, not metrics', 'DELIVERED', 'learn.js composes from /learning + /improvement + /calibration. Stories are templated but genuine: "Your organization resolved 3 predictions and learned from the outcome." "priya.m is well-calibrated." Story cards with narrative + evidence.'],
        ['6', 'Organizational Dot: 4 colors (green/yellow/orange/red)', 'PARTIAL', 'org_dot.js is real — polls /ceo-briefing every 60s, click navigates to TODAY. BUT: orange state checks briefing.contradictions which does not exist in the API response (verified). Orange is dead code. 3 of 4 colors work.'],
        ['7', 'Heartbeat: subtle, calming, respects reduced-motion', 'DELIVERED', 'invisible-maestro.css .org-heartbeat: 6px dot, 3s ease-in-out animation. @media (prefers-reduced-motion: reduce) { animation: none !important; }. Genuine.'],
        ['8', 'Hide internal vocabulary (Learning Objects, OEM, Laws, Receipts, etc.)', 'PARTIAL', 'ASK v2 does regex replacement: "learning object"→"pattern", "OEM"→"Maestro", "law"→"pattern", "receipt"→"signal". BUT: only applies to ASK v2 surface. The 22 old surfaces still display "Law", "Learning Object", "Receipt", "OEM" directly. Law codes "L-0001" leak through. Confidence "(1.00)" leaks through.'],
        ['9', 'Contextual whispers: max 2 sentences, dismiss on click', 'PARTIAL', 'work.js generates whispers from /contradictions + overnight changes. Dismiss on click works (addEventListener). BUT: whispers are inside the Maestro app, not ambient overlays in other tools. The Constitution said "Never interrupt. Never notify unnecessarily." These are not ambient — you must open WORK to see them.'],
        ['10', 'No charts, replace with stories', 'PARTIAL', 'TODAY and LEARN have no charts. BUT: the 22 old surfaces (Home, Hayek, Knowledge Flow, etc.) still have charts. The chart removal only applies to 4 new surfaces.'],
        ['11', 'Fundamental law: more intelligence → less interface', 'NOT DELIVERED', 'Interface INCREASED: 19 → 23 surfaces. The coder added 4 surfaces on top of 19 existing ones. The fundamental law is violated.'],
        ['12', 'Backend capabilities preserved, only how they are revealed changes', 'DELIVERED', 'No backend changes. All APIs intact. 388 tests pass, 0 fail. The 4 new surfaces compose existing endpoints. Genuine.'],
        ['13', 'Every recommendation answers: Why now? Why me? Why this? What if ignored? How do we know? Who solved it?', 'NOT DELIVERED', 'TODAY\'s brief items show label + title + context + provenance. They do not answer "Why now?", "Why me?", "What if ignored?", "Who already solved it?" The Constitution explicitly required all 6 questions answered automatically.'],
    ]
    t = Table(rows, colWidths=[8*mm, 55*mm, 24*mm, PAGE_W - MARGIN_L - MARGIN_R - 87*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TEXTCOLOR', (2, 1), (2, 1), ST_FAILED),
        ('TEXTCOLOR', (2, 2), (2, 2), ST_DELIVERED),
        ('TEXTCOLOR', (2, 3), (2, 3), ST_FAILED),
        ('TEXTCOLOR', (2, 4), (2, 4), ST_PARTIAL),
        ('TEXTCOLOR', (2, 5), (2, 5), ST_DELIVERED),
        ('TEXTCOLOR', (2, 6), (2, 6), ST_PARTIAL),
        ('TEXTCOLOR', (2, 7), (2, 7), ST_DELIVERED),
        ('TEXTCOLOR', (2, 8), (2, 8), ST_PARTIAL),
        ('TEXTCOLOR', (2, 9), (2, 9), ST_PARTIAL),
        ('TEXTCOLOR', (2, 10), (2, 10), ST_PARTIAL),
        ('TEXTCOLOR', (2, 11), (2, 11), ST_FAILED),
        ('TEXTCOLOR', (2, 12), (2, 12), ST_DELIVERED),
        ('TEXTCOLOR', (2, 13), (2, 13), ST_FAILED),
        ('FONTNAME', (2, 1), (2, -1), FONT_HEAD_B),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>Scorecard: 4 DELIVERED, 4 PARTIAL, 5 NOT DELIVERED.</b> The visual layer is genuine. The paradigm '
        'shift is not. The fundamental law — the one the Constitution said "overrides every other instruction" — '
        'is violated: the interface increased, not decreased.', 'body'))

    story.append(PageBreak())

    # ── DETAILED FINDINGS ────────────────────────────────────────────────
    story.append(P('Detailed Findings', 'h1'))

    story.append(claim_block(
        1,
        '"The sidebar went from 22 surfaces to 4." (Coder\'s commit message)',
        'FAILED',
        'grep -c "data-surface=" app.html returns 23. The 4 new meta-surfaces (today, work, ask-v2, learn) were added at the TOP of the sidebar. The 19 old surfaces (home, inbox, simulator, hayek, flow, memory, ask, customer, physics, debate, live, intents, contradictions, predictions, assumptions, eng-signals, eng-oem, eng-audit, eng-settings) remain BELOW under a "Deep capabilities" divider. The old "CEO Product" section label is hidden via style="display:none" but the links are all still there. The sidebar went from 19 surfaces to 23 — the OPPOSITE of "22 to 4."',
        'The Constitution said: "Do NOT add more pages. Collapse them. Compress them. Hide them." The coder added 4 pages and did not collapse, compress, or hide the existing 19. This is the single most important finding: the fundamental law ("more intelligence → less interface") is violated at the most basic level. The interface INCREASED.'
    ))

    story.append(claim_block(
        2,
        '"WORK never looks like software. Maestro follows the user into existing tools. The user never opens Maestro." (Constitution)',
        'FAILED',
        'work.js (149 lines) is a page INSIDE Maestro. It renders 4 "ambient integration cards" (GitHub, Slack, Jira, Outlook) with static messages. The GitHub card says "Your repositories are calm. No blocked PRs detected." — this is a hardcoded string, not fetched from GitHub. The Jira card says "Maestro is watching your issue transitions for patterns." — a placeholder. The Outlook card says "Install the Maestro bookmarklet to see organizational context inside your email." — a configuration prompt. There is NO browser extension, NO Slack bot, NO Jira add-on, NO Zoom integration, NO bookmarklet implementation. The "whispers" are generated from /contradictions and displayed inside the Maestro app, not as contextual overlays in other tools.',
        'This is the biggest gap in the redesign. The Constitution\'s WORK philosophy — "Maestro quietly appears [inside GitHub/Slack/Jira/Zoom]" — requires building native integrations: a Chrome extension for GitHub/Jira, a Slack app, a Zoom app, an Outlook add-in. That is weeks of work per platform. The coder built a page that TALKS about ambient integration. The user must open Maestro, navigate to WORK, and read cards about what Maestro WOULD see if it could actually follow them into tools. This is the opposite of "the user never opens Maestro."'
    ))

    story.append(claim_block(
        3,
        '"Never expose confidence numbers alone." (Constitution)',
        'FAILED',
        'today.js line 53: provenance = ot.rec_id ? `Based on ${ot.confidence ? Math.round(ot.confidence * 100) + \'% confidence\' : \'organizational patterns\'}` : \'\' — this renders "Based on 38% confidence" in the TODAY surface. ASK v2: the raw answer from /api/oem/ask contains "(confidence: 1.00)" in the text — verified by live API call. The vocabulary replacement in ask_v2.js does not strip confidence numbers from the answer text. It only adds a confidence-as-story line BELOW the answer ("We\'ve seen this pattern consistently"). The raw percentage is still visible above.',
        'The Constitution was explicit: "Never expose confidence numbers alone. Trust through provenance, never through percentages." TODAY exposes "38% confidence" as the provenance string. ASK v2 exposes "(confidence: 1.00)" in the raw answer. Both are confidence numbers, alone, without context. The fix is to remove the percentage and replace with the story ("We\'ve seen this succeed 3 times in the last 2 weeks") — but only ASK v2 adds the story, and it adds it BELOW the raw percentage, not instead of it.'
    ))

    story.append(claim_block(
        4,
        '"Never expose: Learning Objects, Patterns, Evidence Graph, OEM, Signals, Receipts, Prediction Market, Laws." (Constitution)',
        'PARTIAL',
        'ASK v2 does regex replacement: .replace(/learning object/gi, "pattern"), .replace(/evidence graph/gi, "organizational memory"), .replace(/receipt/gi, "signal"), .replace(/law\\b/gi, "pattern"), .replace(/OEM/gi, "Maestro"). This is genuine vocabulary hiding — but only on the ASK v2 surface. The 22 old surfaces still display "Law" (physics_laws.js), "Learning Object" (home_core.js), "Receipt" (eng_audit.js), "OEM" (throughout) directly. Verified: grep -rci "Learning Object" static/js/*.js = 4 occurrences. "OEM" = 147. "Law" = 87. "Receipt" = 11. Additionally, law codes "L-0001" and "L-0002" leak through the regex replacement — verified by live API test: the answer "Based on 2 relevant execution pattern(s): L-0001: priya.m@acme.com is a bottleneck" still shows "L-0001" after replacement.',
        'The vocabulary hiding is real but shallow. It is regex replacement on the output, not a redesign of what the backend returns. The law codes (L-0001) are the laws\' identifiers and they leak through. The old surfaces are untouched. A user who clicks "Physics" in the sidebar sees "Organizational Laws" with "L-0001" codes — exactly what the Constitution said to never expose. To fully deliver this claim, the coder would need to: (1) apply vocabulary replacement to ALL surfaces, not just ASK v2, (2) strip law codes from user-facing text, (3) strip confidence numbers, (4) redesign the backend to return human narratives instead of internal terminology.'
    ))

    story.append(claim_block(
        5,
        '"Organizational Dot: Green / Yellow / Orange / Red" (Constitution)',
        'PARTIAL',
        'org_dot.js is real: creates a DOM element in the topbar, polls /ceo-briefing every 60s, has 4 color classes (green/yellow/orange/red), click navigates to TODAY, has aria-label for accessibility. BUT: the orange condition (determineDotColor in today.js line 158) checks briefing.contradictions && briefing.contradictions.length > 0. Verified by live API call: /api/oem/ceo-briefing returns keys [generated_at, overnight, one_thing, money, knowledge, decisions]. There is NO "contradictions" field. The orange condition will ALWAYS be falsy. The dot can only be green (default), yellow (overnight changes exist), or red (urgent one_thing). Orange ("cross-functional impact") is dead code.',
        'The dot is a genuine UX element and 3 of 4 colors work. The orange state requires either: (a) adding a contradictions field to /ceo-briefing, or (b) fetching /api/oem/contradictions separately in pollOrgDotStatus(). Either is a 15-minute fix. But the current implementation ships a 4-color dot where the 4th color can never appear.'
    ))

    story.append(claim_block(
        6,
        '"The system translates intentions into organizational knowledge." (Constitution, ASK surface)',
        'PARTIAL',
        'ASK v2 has 8 intention prompts ("Ship OAuth safely", "Reduce deployment failures", etc.) and an intention-phrased input placeholder ("Or type your own intention…"). When submitted, it calls api.getOEM(`/ask?q=${encodeURIComponent(question)}`) — the same /api/oem/ask endpoint from round 3, which is keyword substring search (decision.py answer_question: splits query on whitespace, filters tokens > 3 chars, substring-matches against law statements and LO descriptions). The frontend rephrases the experience as "intention-based"; the backend still does keyword matching. The intention prompts are hardcoded, not derived from the organization\'s actual state.',
        'The Constitution said "The system translates intentions into organizational knowledge." The system does not translate — it searches. The frontend puts an intention-styled frame around the same keyword search. This is honest about its limitations (the round-5 honesty docstring on answer_question still applies), but the Constitution explicitly asked for a new capability ("translate intentions"), not a rephrasing of an existing one. To deliver this claim, the backend would need an LLM or semantic-matching layer that interprets the intention and composes a synthesized answer — not a keyword search with intention-styled UI.'
    ))

    story.append(claim_block(
        7,
        '"Every recommendation must automatically answer: Why now? Why me? Why this? What happens if ignored? How do we know? Who already solved it?" (Constitution)',
        'FAILED',
        'TODAY\'s brief items (today.js renderMorningBrief) show: label, title, context (the "why"), provenance (a confidence string or entity name). They do NOT answer: "Why now?" (timing justification), "Why me?" (why the CEO specifically), "What happens if ignored?" (consequence), "Who already solved it?" (precedent). The Constitution explicitly required all 6 questions answered automatically, "without clicking." None of the 4 new surfaces implement this. The drill-down modal (from round 3) has tabs for Why/Where/Evidence/Timeline/People/Prediction/Simulation/Recommendation, but these require clicking — the Constitution said "automatically, without clicking."',
        'This is the most ambitious Constitution claim and the least delivered. Answering all 6 questions automatically, without clicking, requires the backend to generate a rich narrative for each recommendation — not just a title + confidence. The current backend returns structured data (title, description, confidence, provenance list). The frontend would need to synthesize 6 sentences from that data. This is a significant backend + frontend task that was not attempted.'
    ))

    # ── WHAT IS GENUINELY GOOD ───────────────────────────────────────────
    story.append(P('What Is Genuinely Good', 'h1'))
    story.append(P(
        'The redesign is not without merit. Several elements are genuinely well-executed and should be kept:', 'body'))

    story.append(P('TODAY is a real morning brief', 'h2'))
    story.append(P(
        'today.js composes from /ceo-briefing and /pulse. The 5-item structure (decision, opportunity, risk, '
        'learning, prediction) is the right structure. The greeting is time-aware. The weather metaphor '
        '("Decision Storm", "Calm Execution Window", "Knowledge Front") maps pulse metrics to intuitive '
        'language. The 720px max-width and 48px padding create a calm, readable column. Click handlers use '
        '<font face="Mono">addEventListener</font> (not inline onclick). This is the best of the 4 new surfaces.', 'body'))

    story.append(P('LEARN has genuine story narratives', 'h2'))
    story.append(P(
        'learn.js composes from /learning, /improvement, and /predictions/market/calibration. The stories are '
        'templated but genuinely story-form: "Your organization resolved 3 predictions and learned from the '
        'outcome." "priya.m is well-calibrated in their predictions. Their judgment is becoming a trusted '
        'signal." This is what the Constitution asked for — stories, not metrics. The "Explore deeper" buttons '
        'link to existing surfaces without forcing the user into them.', 'body'))

    story.append(P('The CSS is genuinely calm', 'h2'))
    story.append(P(
        'invisible-maestro.css (298 lines) uses generous whitespace (48px padding, 48px margins), narrow '
        'columns (720px max-width), slow transitions (400ms ease), and subtle box-shadows. The heartbeat '
        'animation (6px dot, 3s ease-in-out) is subtle. The <font face="Mono">@media (prefers-reduced-motion: '
        'reduce)</font> block disables all animations — genuine accessibility. The design language is closer '
        'to Apple Weather / Linear than to enterprise software. This is real craft.', 'body'))

    story.append(P('The Organizational Dot is a real presence indicator', 'h2'))
    story.append(P(
        'org_dot.js creates a real DOM element in the topbar, polls every 60 seconds, and navigates to TODAY '
        'on click. 3 of 4 colors work (green/yellow/red). The aria-label is correct. The box-shadow glow is '
        'subtle. This is the closest the redesign comes to the Constitution\'s "universal presence indicator" '
        'vision — even though the orange state is dead code.', 'body'))

    story.append(P('No backend regressions', 'h2'))
    story.append(P(
        '388 tests pass, 0 failed, 2 skipped — same as round 6. The 3 frontend test updates (navigating to '
        '"home" first since "today" is now the default) are honest adaptations, not test deletions. The '
        'backend is completely unchanged. All APIs are intact. The 4 new surfaces compose existing endpoints '
        'without requiring new ones. This is the right approach — the intelligence is preserved, only the '
        'revelation layer changed.', 'body'))

    # ── THE VERDICT ──────────────────────────────────────────────────────
    story.append(P('The Verdict', 'h1'))
    story.append(P(
        'The Constitution v2 prompt asked for a paradigm shift. The coder delivered a visual layer. The '
        'difference matters.', 'body'))

    story.append(P(
        'A paradigm shift would have <b>removed</b> the 22 old surfaces from the sidebar — or hidden them '
        'behind a single "Deep capabilities" modal that opens on command, not a sidebar section that is '
        'always visible. A paradigm shift would have built <b>real</b> ambient tool integration — a Chrome '
        'extension that injects contextual cards into GitHub PRs, a Slack bot that whispers in channels, a '
        'Jira add-on that surfaces "you\'ve solved this before" on issue creation. A paradigm shift would '
        'have <b>removed</b> confidence numbers from all surfaces, not just added story lines below them. '
        'A paradigm shift would have <b>synthesized</b> 6-question narratives for every recommendation, not '
        'shown a title + provenance string.', 'body'))

    story.append(P(
        'What the coder delivered is a <b>first step</b>: 4 new surfaces that demonstrate what the Invisible '
        'Maestro COULD feel like, layered on top of the old Maestro that is still fully accessible. TODAY '
        'feels calm. LEARN feels like stories. The dot feels alive. The CSS feels like Apple Weather. These '
        'are real improvements. But they coexist with the old dashboard catalogue, the old charts, the old '
        'vocabulary, the old confidence percentages. The user can still navigate to "Physics" and see '
        '"Organizational Laws" with "L-0001" codes. The old Maestro is one click away.', 'body'))

    story.append(P(
        'The Constitution\'s fundamental law — "every increase in intelligence must reduce the amount of '
        'interface exposed" — is violated because the interface increased. The coder added 4 surfaces to '
        'the existing 19. The correct implementation would have replaced the 19 with the 4, making the old '
        'surfaces accessible only through command-palette search or a "Deep capabilities" modal — not '
        'through a sidebar section that is always visible.', 'body'))

    story.append(P(
        '<b>Score: 5/10 for Constitution adherence.</b> The visual craft is genuine (8/10). The paradigm '
        'shift is not delivered (2/10). The average is 5. The redesign is worth keeping — it is a real '
        'improvement over the 22-surface dashboard catalogue — but the claim "a new interaction paradigm" '
        'is false. It is a new visual layer on top of the old interaction model.', 'body'))

    story.append(P(
        '<b>What would make this a real paradigm shift:</b>', 'body'))
    story.append(P('1. <b>Remove the 22 old surfaces from the sidebar.</b> Move them behind a command-palette-only access pattern (Ctrl+K → "Physics" → opens Physics in a modal, not a sidebar nav). The sidebar should have ONLY 4 items: Today, Work, Ask, Learn.', 'body_left'))
    story.append(P('2. <b>Build one real ambient integration.</b> Start with a Chrome extension that injects "You\'ve solved this before" into GitHub PR pages. One real integration is worth more than 4 static cards describing hypothetical integrations.', 'body_left'))
    story.append(P('3. <b>Fix the dot\'s orange state.</b> Fetch /api/oem/contradictions in pollOrgDotStatus() and check its length. 15-minute fix.', 'body_left'))
    story.append(P('4. <b>Remove confidence numbers from ALL surfaces.</b> Replace "38% confidence" with "We\'ve seen this 3 times in 2 weeks." Apply the confidence-as-story pattern to TODAY, not just ASK v2.', 'body_left'))
    story.append(P('5. <b>Apply vocabulary hiding to ALL surfaces.</b> The regex replacement in ask_v2.js should be a shared utility function applied to every surface\'s output. Strip law codes ("L-0001" → "Pattern 1" or just omit).', 'body_left'))
    story.append(P('6. <b>Synthesize 6-question narratives.</b> For each recommendation, the backend should return: why_now, why_me, why_this, what_if_ignored, how_we_know, who_solved_it. The frontend renders these as a paragraph, not a card with fields.', 'body_left'))
    story.append(P('7. <b>Make ASK actually translate intentions.</b> Integrate an LLM that takes the intention ("Ship OAuth safely") and composes a synthesized answer from the OEM data, instead of passing it as a keyword search query.', 'body_left'))

    story.append(P(
        'Items 1-5 are frontend work (1-2 days). Item 6 is backend + frontend work (3-5 days). Item 7 is '
        'LLM integration work (1-2 weeks). Together, they would deliver the Invisible Maestro. Without them, '
        'the redesign is a reskin — a beautiful, calm, well-crafted reskin, but a reskin.', 'body'))

    story.append(P(
        '<b>Final note.</b> The Constitution v2 prompt was the right prompt. It identified the correct '
        'paradigm: "more intelligence, less interface." The coder\'s response shows they understood the '
        'vision — the 4 meta-surfaces, the dot, the heartbeat, the weather metaphors, the calm CSS all point '
        'in the right direction. The gap is in execution: the old interface was not removed, the ambient '
        'integration was not built, the vocabulary was not fully hidden, the confidence numbers were not '
        'fully removed. The redesign is a proof of concept for the Invisible Maestro. It is not the Invisible '
        'Maestro itself. The next commit should remove, not add.', 'body'))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'MaestroAgent_Round7_Product_Philosophy_Review.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
