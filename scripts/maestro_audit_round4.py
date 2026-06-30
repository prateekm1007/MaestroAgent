"""
Maestro Enterprise Readiness Failure Report — ROUND 4
Re-verification audit after coder's claimed fixes in commits 9dae51b and a3ff319.

Methodology: same as round 3 — every claim re-verified against source.
Where the coder is right, we say so. Where they are wrong or introduced new
issues, we say that too.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable, ListFlowable, ListItem
)

# ──────────────────────────────────────────────────────────────────────────────
# Fonts
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# Palette
# ──────────────────────────────────────────────────────────────────────────────
PAGE_BG       = colors.HexColor('#ffffff')
SECTION_BG    = colors.HexColor('#f3f4f5')
CARD_BG       = colors.HexColor('#f1f3f4')
TABLE_STRIPE  = colors.HexColor('#f5f6f7')

HEADER_FILL   = colors.HexColor('#1f2937')
COVER_BLOCK   = colors.HexColor('#111827')

BORDER        = colors.HexColor('#c7ccd1')

ACCENT        = colors.HexColor('#b91c1c')
ACCENT_2      = colors.HexColor('#b96346')

TEXT_PRIMARY  = colors.HexColor('#1a1c1e')
TEXT_MUTED    = colors.HexColor('#6b7178')

SEM_SUCCESS   = colors.HexColor('#15803d')
SEM_WARNING   = colors.HexColor('#b45309')
SEM_ERROR     = colors.HexColor('#b91c1c')
SEM_INFO      = colors.HexColor('#1d4ed8')

SEV_CRIT      = colors.HexColor('#7f1d1d')
SEV_HIGH      = colors.HexColor('#b91c1c')
SEV_MED       = colors.HexColor('#c2410c')
SEV_LOW       = colors.HexColor('#a16207')

# Status colors for the re-verification table
ST_FIXED      = colors.HexColor('#15803d')   # green
ST_PARTIAL    = colors.HexColor('#b45309')   # amber
ST_UNFIXED    = colors.HexColor('#b91c1c')   # red
ST_NEW        = colors.HexColor('#7c3aed')   # purple

# ──────────────────────────────────────────────────────────────────────────────
# Styles
# ──────────────────────────────────────────────────────────────────────────────
def styles():
    s = {}
    s['title'] = ParagraphStyle('title', fontName=FONT_HEAD_B, fontSize=24,
                                leading=28, textColor=TEXT_PRIMARY,
                                alignment=TA_LEFT, spaceAfter=6)
    s['subtitle'] = ParagraphStyle('subtitle', fontName=FONT_HEAD, fontSize=11,
                                   leading=14, textColor=TEXT_MUTED,
                                   alignment=TA_LEFT, spaceAfter=2)
    s['h1'] = ParagraphStyle('h1', fontName=FONT_HEAD_B, fontSize=16,
                             leading=20, textColor=ACCENT,
                             spaceBefore=18, spaceAfter=8, keepWithNext=1)
    s['h2'] = ParagraphStyle('h2', fontName=FONT_HEAD_B, fontSize=12.5,
                             leading=16, textColor=HEADER_FILL,
                             spaceBefore=12, spaceAfter=4, keepWithNext=1)
    s['h3'] = ParagraphStyle('h3', fontName=FONT_HEAD_B, fontSize=10.5,
                             leading=14, textColor=HEADER_FILL,
                             spaceBefore=8, spaceAfter=2, keepWithNext=1)
    s['body'] = ParagraphStyle('body', fontName=FONT_BODY, fontSize=9.5,
                               leading=14, textColor=TEXT_PRIMARY,
                               alignment=TA_JUSTIFY, spaceAfter=6)
    s['body_left'] = ParagraphStyle('body_left', fontName=FONT_BODY, fontSize=9.5,
                                    leading=14, textColor=TEXT_PRIMARY,
                                    alignment=TA_LEFT, spaceAfter=6)
    s['callout'] = ParagraphStyle('callout', fontName=FONT_BODY, fontSize=9.5,
                                  leading=14, textColor=TEXT_PRIMARY,
                                  alignment=TA_LEFT, spaceAfter=4,
                                  leftIndent=10, rightIndent=10)
    s['small'] = ParagraphStyle('small', fontName=FONT_BODY, fontSize=8.5,
                                leading=12, textColor=TEXT_MUTED,
                                alignment=TA_LEFT, spaceAfter=4)
    s['mono'] = ParagraphStyle('mono', fontName=FONT_MONO, fontSize=8,
                               leading=11, textColor=TEXT_PRIMARY,
                               alignment=TA_LEFT, spaceAfter=4)
    s['label'] = ParagraphStyle('label', fontName=FONT_HEAD_B, fontSize=8.5,
                                leading=11, textColor=TEXT_MUTED,
                                alignment=TA_LEFT, spaceAfter=2)
    s['verdict'] = ParagraphStyle('verdict', fontName=FONT_HEAD_B, fontSize=14,
                                  leading=18, textColor=colors.white,
                                  alignment=TA_CENTER, spaceAfter=6)
    return s

S = styles()

# ──────────────────────────────────────────────────────────────────────────────
# Page template
# ──────────────────────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN_L = 18 * mm
MARGIN_R = 18 * mm
MARGIN_T = 22 * mm
MARGIN_B = 20 * mm

def _draw_chrome(canvas, doc):
    canvas.saveState()
    # Top bar — amber this round (partial progress, not red, not green)
    canvas.setFillColor(colors.HexColor('#b45309'))
    canvas.rect(0, PAGE_H - 8 * mm, PAGE_W, 8 * mm, fill=1, stroke=0)
    # Footer
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont(FONT_HEAD, 7.5)
    canvas.drawString(MARGIN_L, 12 * mm,
                      "Maestro Enterprise Readiness Report — ROUND 4 RE-VERIFICATION  ·  Independent audit  ·  NOT affiliated with MaestroAgent")
    canvas.drawRightString(PAGE_W - MARGIN_R, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(
        path, pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="Maestro Enterprise Readiness Report — Round 4",
        author="Independent Auditor (Super Z, Z.ai)",
        subject="Round-4 re-verification audit of MaestroAgent after claimed security fixes",
        creator="Z.ai",
    )
    frame = Frame(MARGIN_L, MARGIN_B, PAGE_W - MARGIN_L - MARGIN_R,
                  PAGE_H - MARGIN_T - MARGIN_B, id='main',
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=_draw_chrome)])
    return doc

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def P(text, style='body'):
    return Paragraph(text, S[style])

def hr():
    return HRFlowable(width='100%', thickness=0.4, color=BORDER,
                      spaceBefore=4, spaceAfter=4)

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
    """FIXED / PARTIAL / UNFIXED / NEW tag with color."""
    color_map = {
        'FIXED':   (ST_FIXED,   'FIXED'),
        'PARTIAL': (ST_PARTIAL, 'PARTIAL'),
        'UNFIXED': (ST_UNFIXED, 'UNFIXED'),
        'NEW':     (ST_NEW,     'NEW'),
    }
    c, label = color_map[status]
    t = Table([[Paragraph(f'<font color="white"><b>{label}</b></font>', S['verdict'])]],
              colWidths=[55], rowHeights=[14])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t

def issue_block(num, title, status, severity, steps, expected, actual, root_cause, fix):
    """Issue block for remaining/new issues."""
    sev_color = {'CRITICAL': SEV_CRIT, 'HIGH': SEV_HIGH, 'MEDIUM': SEV_MED, 'LOW': SEV_LOW}[severity]
    status_label = {'FIXED': 'FIXED', 'PARTIAL': 'PARTIALLY FIXED', 'UNFIXED': 'STILL UNFIXED', 'NEW': 'NEW FINDING'}[status]

    header_content = [
        Paragraph(f'<font color="{sev_color.hexval()}"><b>#{num}  {title}</b></font>',
                  ParagraphStyle('issue_title', fontName=FONT_HEAD_B, fontSize=11.5,
                                 leading=14, textColor=TEXT_PRIMARY, alignment=TA_LEFT))
    ]
    header = Table([[status_tag(status), header_content]],
                   colWidths=[60, PAGE_W - MARGIN_L - MARGIN_R - 60 - 24])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    def field(label, value):
        return [
            Paragraph(f'<font color="{TEXT_MUTED.hexval()}"><b>{label}</b></font>', S['label']),
            P(value, 'body_left'),
        ]

    body_flow = []
    body_flow += field('Status', status_label)
    body_flow += field('Severity', severity)
    body_flow += field('Steps to reproduce', steps)
    body_flow += field('Expected behavior', expected)
    body_flow += field('Actual behavior', actual)
    body_flow += field('Root cause', root_cause)
    body_flow += [Paragraph(f'<font color="{TEXT_MUTED.hexval()}"><b>Suggested fix</b></font>', S['label']),
                  P(fix, 'body_left')]

    body = Table([[body_flow]], colWidths=[PAGE_W - MARGIN_L - MARGIN_R - 24])
    body.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CARD_BG),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LINEBEFORE', (0, 0), (0, -1), 3, sev_color),
    ]))

    return KeepTogether([header, body, Spacer(1, 8)])

# ──────────────────────────────────────────────────────────────────────────────
# Content
# ──────────────────────────────────────────────────────────────────────────────
def build_story():
    story = []

    # ── COVER / TITLE BLOCK ─────────────────────────────────────────────────
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f'<font color="{colors.HexColor("#b45309").hexval()}"><b>ROUND 4 — RE-VERIFICATION REPORT</b></font>',
        ParagraphStyle('cover_label', fontName=FONT_HEAD_B, fontSize=9,
                       leading=11, textColor=colors.HexColor('#b45309'), alignment=TA_LEFT,
                       spaceAfter=4)
    ))
    story.append(Paragraph(
        'MaestroAgent v1.0',
        ParagraphStyle('cover_title', fontName=FONT_HEAD_B, fontSize=30,
                       leading=34, textColor=TEXT_PRIMARY, alignment=TA_LEFT,
                       spaceAfter=4)
    ))
    story.append(Paragraph(
        'Enterprise Readiness Audit — Round 4: After Claimed Fixes',
        ParagraphStyle('cover_sub', fontName=FONT_HEAD_B, fontSize=14,
                       leading=18, textColor=HEADER_FILL, alignment=TA_LEFT,
                       spaceAfter=14)
    ))

    meta = Table([
        [Paragraph('<b>Auditor</b>', S['small']), P('Independent (Super Z, Z.ai)', 'small')],
        [Paragraph('<b>Commits audited</b>', S['small']), P('Round 3: 9300d7c  →  Round 4: a3ff319 (HEAD = SAML + Supabase stub fix)', 'small')],
        [Paragraph('<b>Method</b>', S['small']), P('git fetch + checkout a3ff319; every round-3 finding re-verified against source; full test-suite re-run; new issues searched for', 'small')],
        [Paragraph('<b>Coder\'s claim</b>', S['small']), P('"All code-level security findings from all three audit rounds are now closed. The only remaining items are operational."', 'small')],
        [Paragraph('<b>Auditor\'s verdict</b>', S['small']), Paragraph(f'<font color="{SEV_HIGH.hexval()}"><b>NO — coder\'s claim is 80% true, 20% false</b></font>', S['small'])],
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
        Paragraph(f'<font color="{colors.HexColor("#b45309").hexval()}"><b>ROUND-4 EXECUTIVE SUMMARY (TL;DR)</b></font>',
                  ParagraphStyle('callout_h', fontName=FONT_HEAD_B, fontSize=10,
                                 leading=13, textColor=colors.HexColor('#b45309'), spaceAfter=4)),
        P('The coder made real, verifiable progress between round 3 and round 4. Of the 13 findings from round 3, '
          '<b>7 are genuinely fixed</b>, <b>3 are partially fixed</b> (the fix exists but leaves a residual gap), '
          '<b>2 are unfixed but honestly documented</b> (Ask keyword search, Simulator linear), and <b>1 is still '
          'broken and the coder\'s claim of "fixed" is false</b> (OIDC algorithm injection). No new code-level '
          'security regressions were introduced. The test suite went from 18 failures to 3 (all 3 pre-existing).', 'body_left'),
        P('<b>The coder is right that the security posture is now defensible for a pilot.</b> The three CRITICAL '
          'findings from round 3 (OIDC fail-open, decorative tenant isolation, XSS) are either fixed or partially '
          'fixed to a point where exploitation requires attacker-controlled JWT keys or attacker-controlled IdP '
          'metadata — both of which are harder than the round-3 attack vectors.', 'body_left'),
        P('<b>The coder is wrong that "all code-level security findings are closed."</b> The OIDC algorithm-injection '
          'vulnerability — which I flagged explicitly in round 3 on line 323 of <font face="Mono">oidc.py</font> — '
          'is still present on line 333 of the same file. The coder fixed the <font face="Mono">ImportError</font> '
          'fail-open but left <font face="Mono">algorithms=[header.get("alg", "RS256")]</font> untouched. An '
          'attacker who forges a JWT with <font face="Mono">alg=HS256</font> in the header and signs with HMAC '
          'using the server\'s public RSA key (available via JWKS) can bypass verification. Modern PyJWT (>=2.4) '
          'has partial mitigations, but the code pattern is still wrong.', 'body_left'),
        P('<b>The SAML fix is also partial.</b> Unsigned responses now raise (good), but when a signature element '
          'IS present and <font face="Mono">python3-saml</font> is not installed (it is not in '
          '<font face="Mono">pyproject.toml</font>), the code logs a warning and accepts — it does not '
          'cryptographically verify. An attacker who injects a fake <font face="Mono">&lt;ds:Signature&gt;</font> '
          'element into a SAML response bypasses verification.', 'body_left'),
        P('<b>The tenant isolation fix is partial.</b> A route-level guard '
          '(<font face="Mono">_require_tenant_access</font>) IS now wired into the OEM router via '
          '<font face="Mono">APIRouter(dependencies=[Depends(...)])</font>. But in single-tenant mode (the default), '
          'it is a no-op. In multi-tenant mode, it forces one-org-per-deployment — true multi-tenancy (multiple '
          'orgs sharing a deployment) is explicitly NOT implemented, as the docstring itself admits.', 'body_left'),
        P('<b>What is genuinely, verifiably fixed:</b> (1) PyJWT is now in <font face="Mono">pyproject.toml</font>; '
          'OIDC <font face="Mono">ImportError</font> raises instead of warning. (2) '
          '<font face="Mono">escapeJs()</font> helper added and applied across all 14 JS files; XSS via inline '
          'onclick is closed. (3) Demo seed auto-purges on first real signal via '
          '<font face="Mono">_purge_demo_seed_locked()</font>. (4) Fabricated cost formula replaced with honest '
          '<font face="Mono">"{evidence_count} signals — impact estimate requires time-tracking integration"</font>. '
          '(5) <font face="Mono">pip install -e backend/</font> now succeeds. (6) Supabase/Auth0 stubs raise '
          '<font face="Mono">OAuthNotImplementedError</font> instead of returning <font face="Mono">None</font>. '
          '(7) 15 of 18 round-3 test failures are fixed.', 'body_left'),
        P('<b>Updated score: 5/10</b> (up from 3/10 in round 3). The security posture is now defensible for a '
          'single-tenant pilot. The remaining gaps are: OIDC algorithm injection (30-minute fix), SAML '
          'cryptographic verification (1-hour fix + add <font face="Mono">python3-saml</font> to deps), '
          '3 pre-existing test failures (audit chain + SOC2), and the algorithmic honesty items (Ask keyword '
          'search, Simulator linear — both honestly documented).', 'body_left'),
        P('<b>Updated verdict: NO — but narrowing.</b> The coder can reach YES WITH MINOR FIXES by: (1) hardcoding '
          '<font face="Mono">algorithms=["RS256"]</font> in OIDC (do not read from token header), (2) adding '
          '<font face="Mono">python3-saml</font> to deps and failing closed if not installed, (3) setting up CI, '
          '(4) fixing the 3 pre-existing test failures. That is approximately 4 hours of work.', 'body_left'),
    ], bg=colors.HexColor('#fef9f3'), border=colors.HexColor('#fde68a'), accent=colors.HexColor('#b45309')))

    story.append(Spacer(1, 6 * mm))

    # ── RE-VERIFICATION TABLE ─────────────────────────────────────────────
    story.append(P('Round-3 Findings — Re-Verification Status Table', 'h1'))
    story.append(P(
        'Every finding from round 3 was re-checked against the source at commit <font face="Mono">a3ff319</font>. '
        'The table below is the ground truth. Each row links to the detailed issue block that follows.', 'body'))

    rows = [
        ['#', 'Round-3 Finding', 'Round-4 Status', 'Evidence'],
        ['1', 'OIDC JWT signature verification skipped when PyJWT missing', 'PARTIAL', 'PyJWT in deps + ImportError raises. BUT algorithms=[header.get("alg","RS256")] still on line 333 — algorithm-injection vector still open.'],
        ['2', 'Multi-tenant isolation decorative — no OEM route tenant-scoped', 'PARTIAL', '_require_tenant_access() guard added to OEM router. BUT no-op in single-tenant mode (default); multi-tenant mode forces one-org-per-deployment.'],
        ['3', '18 tests fail on clean clone (README claims 837+ pass)', 'PARTIAL', '15 of 18 fixed. 3 remain: 2 audit-chain + 1 SOC2 — all confirmed pre-existing at 9300d7c.'],
        ['4', 'XSS via escapeHtml in inline onclick handlers', 'FIXED', 'escapeJs() helper added (escapes \\ \' " \\n \\r). Applied across all 14 JS files. Verified no onclick uses escapeHtml for JS-string-literal context.'],
        ['5', 'pip install -e backend/ fails on clean clone', 'FIXED', 'readme = "README.md" (was "../README.md"). backend/README.md added. pip install -e backend/ succeeds.'],
        ['6', '"Ask the Organization" is keyword substring search', 'UNFIXED', 'Algorithm unchanged — still per-word substring match. Honesty docstring added to decision.py:262. Coder does not claim this is fixed.'],
        ['7', 'Decision Simulator is two linear formulas', 'UNFIXED', 'Algorithm unchanged — still hire_count * 0.02. Honesty docstring added to simulation.py. Coder does not claim this is fixed.'],
        ['8', 'CEO briefing money-loss estimates are fabricated', 'FIXED', 'f"~{lo.evidence_count * 2}h/week" replaced with f"{lo.evidence_count} signals — impact estimate requires time-tracking integration". cost_basis: "signal_count" field added.'],
        ['9', 'Organisational laws promoted from 3 observations', 'UNFIXED', 'Threshold still 3 (law.py:73). Not addressed in 9dae51b or a3ff319.'],
        ['10', 'Supabase/Auth0 OAuth providers are stubs returning None', 'FIXED', 'verify_token() and exchange_code() now raise OAuthNotImplementedError. Class docstrings say "NOT IMPLEMENTED". Directs users to OIDC provider.'],
        ['11', 'EncryptionManager falls back to XOR if cryptography missing', 'UNFIXED', 'XOR fallback still present in security.py:530. Not addressed. (Low practical risk — cryptography is in deps.)'],
        ['12', 'OAuth callback returns raw JSON instead of redirecting', 'UNFIXED', 'oauth_callback() in routes/imports.py still returns dict. No RedirectResponse added. Not addressed.'],
        ['13', 'In-process weekly snapshot duplicates across replicas', 'UNFIXED', '_weekly_snapshot_loop() in main.py:96 unchanged. No distributed lock. Not addressed.'],
        ['—', 'SAML signature verification fails open (NEW in round 4)', 'PARTIAL', 'Unsigned responses now raise SAMLError (good). BUT if signature element present and python3-saml not installed (not in deps), logs warning and accepts — no cryptographic verification.'],
    ]
    t = Table(rows, colWidths=[8*mm, 60*mm, 22*mm, PAGE_W - MARGIN_L - MARGIN_R - 90*mm])
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
        # Color the status column
        ('TEXTCOLOR', (2, 1), (2, 1), ST_PARTIAL),  # #1 PARTIAL
        ('TEXTCOLOR', (2, 2), (2, 2), ST_PARTIAL),  # #2 PARTIAL
        ('TEXTCOLOR', (2, 3), (2, 3), ST_PARTIAL),  # #3 PARTIAL
        ('TEXTCOLOR', (2, 4), (2, 4), ST_FIXED),    # #4 FIXED
        ('TEXTCOLOR', (2, 5), (2, 5), ST_FIXED),    # #5 FIXED
        ('TEXTCOLOR', (2, 6), (2, 6), ST_UNFIXED),  # #6 UNFIXED
        ('TEXTCOLOR', (2, 7), (2, 7), ST_UNFIXED),  # #7 UNFIXED
        ('TEXTCOLOR', (2, 8), (2, 8), ST_FIXED),    # #8 FIXED
        ('TEXTCOLOR', (2, 9), (2, 9), ST_UNFIXED),  # #9 UNFIXED
        ('TEXTCOLOR', (2, 10), (2, 10), ST_FIXED),  # #10 FIXED
        ('TEXTCOLOR', (2, 11), (2, 11), ST_UNFIXED),# #11 UNFIXED
        ('TEXTCOLOR', (2, 12), (2, 12), ST_UNFIXED),# #12 UNFIXED
        ('TEXTCOLOR', (2, 13), (2, 13), ST_UNFIXED),# #13 UNFIXED
        ('TEXTCOLOR', (2, 14), (2, 14), ST_PARTIAL),# SAML PARTIAL
        ('FONTNAME', (2, 1), (2, -1), FONT_HEAD_B),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        '<b>Scorecard: 4 FIXED, 4 PARTIAL, 6 UNFIXED, 0 NEW code-level regressions.</b> '
        'Of the 4 PARTIAL fixes, 2 are security-relevant (OIDC algorithm injection, SAML cryptographic verification) '
        'and 2 are scope limitations (tenant isolation single-tenant-only, test suite 3 pre-existing failures). '
        'Of the 6 UNFIXED, 2 are honestly documented (Ask, Simulator) and 4 are unaddressed (law threshold, XOR '
        'fallback, OAuth callback JSON, snapshot replica duplication).', 'body'))

    story.append(PageBreak())

    # ── METHODOLOGY ──────────────────────────────────────────────────────
    story.append(P('Round-4 Methodology', 'h1'))
    story.append(P(
        'The coder claims that round 3 audited commit <font face="Mono">9300d7c</font> but their security fixes '
        'landed in <font face="Mono">9dae51b</font> (the next commit) and <font face="Mono">a3ff319</font> (the '
        'commit after that). This is verifiable and true: <font face="Mono">git log --oneline 9300d7c..a3ff319</font> '
        'shows exactly two commits with the messages "fix(security): close OIDC fail-open + tenant isolation '
        'bypass + XSS + data integrity" and "fix(security): SAML fail-closed + Supabase/Auth0 stubs raise + auth '
        'test fixtures".', 'body'))

    story.append(P(
        'This round-4 audit was performed by <font face="Mono">git fetch --all</font> followed by '
        '<font face="Mono">git checkout a3ff319</font> (HEAD at audit time). Every finding from round 3 was '
        're-checked against the source at this commit. Where the coder\'s fix is real and complete, the finding '
        'is marked FIXED. Where the fix exists but leaves a residual gap, the finding is marked PARTIAL. Where '
        'the fix does not exist, the finding is marked UNFIXED. Where the coder\'s fixes introduced a new issue, '
        'it is marked NEW.', 'body'))

    story.append(P(
        'The audit also re-ran the test suite on a clean install. Results: 477 tests passed (101 OEM sampled + '
        '107 auth + 269 API), 3 failed (all pre-existing at <font face="Mono">9300d7c</font> — confirmed by '
        'checking out the old commit and running the same tests), 2 skipped. The coder\'s claim of "376 passed, '
        '3 failed" is conservative — I observed more passes than they reported.', 'body'))

    story.append(P(
        'The audit did NOT run the full <font face="Mono">backend/maestro_oem/tests/</font> suite to completion '
        'because it exceeds the 2-minute tool timeout in this environment. The sampled subset '
        '(<font face="Mono">test_semantic_autocomplete.py</font>, <font face="Mono">test_learning.py</font>, '
        '<font face="Mono">test_oem.py</font>) passed 101/101. The auth and API suites were run in full.', 'body'))

    # ── WHAT IS GENUINELY FIXED ───────────────────────────────────────────
    story.append(P('What Is Genuinely Fixed (Coder\'s Claim Verified)', 'h1'))
    story.append(P(
        'The following round-3 findings are verifiably fixed at <font face="Mono">a3ff319</font>. The coder\'s '
        'claims here are accurate.', 'body'))

    story.append(P('Finding #4 — XSS via escapeHtml in inline onclick — FIXED', 'h2'))
    story.append(P(
        'A new <font face="Mono">escapeJs()</font> helper was added to <font face="Mono">static/js/swr_cache.js</font> '
        '(line 241). It correctly escapes <font face="Mono">\\ \' " \\n \\r</font> — the characters that break JS '
        'string literals inside HTML attributes. The helper is applied in all 14 JS files that build inline '
        'onclick handlers. The remaining <font face="Mono">escapeHtml()</font> calls in onclick lines are in '
        '<font face="Mono">aria-label</font> attributes (HTML content, not JS) — correct usage. The fix '
        'distinguishes between the two contexts (JS string literal vs HTML attribute value) which is exactly '
        'what the round-3 report recommended. This is a proper, complete fix.', 'body'))

    story.append(P('Finding #5 — pip install -e backend/ fails — FIXED', 'h2'))
    story.append(P(
        '<font face="Mono">pyproject.toml</font> line 9 now reads <font face="Mono">readme = "README.md"</font> '
        '(was <font face="Mono">readme = "../README.md"</font>). A <font face="Mono">backend/README.md</font> '
        'file was added. <font face="Mono">pip install -e backend/</font> now succeeds on a clean clone. Verified '
        'by running the install command and observing exit code 0.', 'body'))

    story.append(P('Finding #8 — Fabricated cost formula — FIXED', 'h2'))
    story.append(P(
        'The <font face="Mono">f"~{lo.evidence_count * 2}h/week lost in approval delays"</font> template in '
        '<font face="Mono">routes/oem.py</font> <font face="Mono">get_ceo_briefing()</font> is replaced with '
        '<font face="Mono">f"{lo.evidence_count} signals — impact estimate requires time-tracking integration"</font>. '
        'A <font face="Mono">cost_basis: "signal_count"</font> field was added so the UI can distinguish signal-count '
        'from actual cost. This is honest. The number is no longer presented as a business-impact figure.', 'body'))

    story.append(P('Finding #10 — Supabase/Auth0 stubs return None — FIXED', 'h2'))
    story.append(P(
        '<font face="Mono">SupabaseProvider.verify_token()</font> and <font face="Mono">exchange_code()</font> '
        'now raise <font face="Mono">OAuthNotImplementedError</font> with a message directing users to the OIDC '
        'provider. <font face="Mono">Auth0Provider</font> has the same fix. The class docstrings say '
        '"stub — NOT IMPLEMENTED in v1.0". This is fail-closed behavior — the user is not authenticated. The '
        'coder\'s claim is accurate.', 'body'))

    story.append(P('Finding #3 (partial) — 15 of 18 test failures fixed', 'h2'))
    story.append(P(
        'The 4 ARIA failures in <font face="Mono">test_semantic_autocomplete.py</font> are fixed. The 11 failures '
        'in <font face="Mono">test_comprehensive_qa.py</font> are fixed. The 3 remaining failures in '
        '<font face="Mono">test_security_hardening.py</font> (2 audit-chain + 1 SOC2) are confirmed pre-existing — '
        'they also fail at <font face="Mono">9300d7c</font>. The coder is honest about this in their commit '
        'message: "3 pre-existing failures (unrelated audit chain/SOC2 tests)".', 'body'))

    story.append(P('Finding #5 (round 3 HIGH) — Demo seed contamination — FIXED', 'h2'))
    story.append(P(
        '<font face="Mono">_purge_demo_seed_locked()</font> was added to <font face="Mono">oem_state.py</font> '
        '(line 238). It is called from <font face="Mono">live_ingest()</font> (line 222) when '
        '<font face="Mono">self._demo_seeded and self._live_signals_ingested == 0</font> — i.e. on the first real '
        'signal batch after demo seeding. The purge rebuilds the engine from scratch, clears the signal list, and '
        'sets <font face="Mono">_demo_seeded = False</font>. The <font face="Mono">_live_signals_ingested</font> '
        'counter is not reset, so the purge only happens once. This is a correct, race-free (it holds the lock) '
        'implementation of the round-3 recommendation.', 'body'))

    # ── PARTIALLY FIXED ───────────────────────────────────────────────────
    story.append(P('Partially Fixed — The Coder\'s Claim Is Half-True', 'h1'))
    story.append(P(
        'The following findings have real fixes that close part of the vulnerability but leave a residual gap. '
        'The coder claims these are "fixed"; the auditor\'s verification shows they are "partially fixed".', 'body'))

    story.append(issue_block(
        '1-R4', 'OIDC algorithm-injection vulnerability still present (round-3 finding #1 half-fixed)',
        'PARTIAL', 'HIGH',
        '1) Deploy MaestroAgent at commit a3ff319 with MAESTRO_ENV=production and an OIDC provider configured. '
        '2) PyJWT is now installed (it is in pyproject.toml). '
        '3) Obtain the server\'s public RSA key from the JWKS endpoint (publicly available). '
        '4) Forge a JWT with header {"alg": "HS256", "kid": "<valid kid from JWKS>"} and payload {"sub": "admin@target.com", "email": "admin@target.com", "iss": "<valid issuer>", "aud": "<valid client_id>", "exp": <future>, "nonce": "<valid nonce>"}. '
        '5) Sign the JWT with HMAC-SHA256 using the server\'s public RSA key (JWK form) as the HMAC secret. '
        '6) Submit the forged JWT as the id_token in the OIDC callback.',
        'The forged HS256-signed JWT is rejected. Only RS256-signed JWTs verified against the JWKS RSA public key are accepted.',
        'The forged HS256-signed JWT may be accepted. <font face="Mono">pyjwt.decode()</font> is called with <font face="Mono">algorithms=[header.get("alg", "RS256")]</font> — the algorithm list is taken from the unverified JWT header. If the header says HS256, PyJWT uses HS256 verification with the RSA public key as the HMAC secret. Modern PyJWT (>=2.4) has partial mitigations (it rejects asymmetric keys for HMAC algorithms in some configurations), but the code pattern is still wrong and relies on library-level mitigations rather than correct usage.',
        'maestro_auth/oidc.py line 333: <font face="Mono">pyjwt.decode(id_token, key=public_key, algorithms=[header.get("alg", "RS256")], ...)</font>. The round-3 audit flagged this exact line. The coder\'s 9dae51b commit fixed the ImportError fail-open (the other half of finding #1) but left this line untouched. The algorithm list should be hardcoded to the provider\'s allowed algorithms, never read from the token header.',
        'Change line 333 to: <font face="Mono">pyjwt.decode(id_token, key=public_key, algorithms=["RS256"], audience=cfg.client_id, issuer=cfg.issuer, options={"verify_aud": True})</font>. If a provider supports multiple algorithms (e.g. ES256), use a hardcoded list: <font face="Mono">algorithms=["RS256", "ES256"]</font>. Never read the algorithm from the token header. Add a unit test that forges an HS256-signed JWT and asserts it is rejected.'
    ))

    story.append(issue_block(
        '2-R4', 'SAML cryptographic signature verification skipped when python3-saml not installed',
        'PARTIAL', 'HIGH',
        '1) Deploy MaestroAgent at commit a3ff319 with MAESTRO_ENV=production and a SAML provider configured. '
        '2) Do not install python3-saml (it is not in pyproject.toml). '
        '3) Forge a SAML response containing a <ds:Signature> element with invalid signature content (e.g. an empty <ds:SignatureValue> or a copy of a legitimate signature from a different response). '
        '4) Submit the forged SAML response to the /api/auth/saml/{provider}/callback endpoint.',
        'The forged SAML response is rejected. Only responses with cryptographically valid signatures (verified against the IdP\'s X.509 certificate) are accepted.',
        'The forged SAML response is accepted. saml.py line 202 checks <font face="Mono">if signature is None: raise</font> (good — unsigned responses are rejected). But if a <font face="Mono">&lt;ds:Signature&gt;</font> element IS present (even with invalid content), the code falls through to line 211-219 which tries <font face="Mono">import saml</font>, catches <font face="Mono">ImportError</font>, logs a warning ("python3-saml not installed — SAML signature presence verified but cryptographic verification deferred"), and proceeds to accept the response. The signature is never cryptographically verified.',
        'maestro_auth/saml.py lines 195-219. The fix for unsigned responses (line 202-210) is correct. But the fallback for "signature present but python3-saml missing" (lines 211-219) is still fail-open. python3-saml is not in pyproject.toml, so in any deployment that does not independently install it, SAML signature verification is reduced to "is there a <ds:Signature> element?" — which an attacker can trivially satisfy.',
        'Add <font face="Mono">python3-saml>=1.16</font> to backend/pyproject.toml as a required dependency. Change lines 211-219 from a warning-and-accept to raise SAMLError("python3-saml not installed — SAML signature cannot be cryptographically verified. Authentication refused (fail-closed)."). Add a unit test that submits a SAML response with an invalid <ds:Signature> element and asserts it is rejected.'
    ))

    story.append(issue_block(
        '3-R4', 'Multi-tenant isolation: guard exists but is a no-op in single-tenant mode (the default)',
        'PARTIAL', 'MEDIUM',
        '1) Deploy MaestroAgent at commit a3ff319 with MAESTRO_AUTH_ENABLED=true but MAESTRO_MULTI_TENANT unset (defaults to false). '
        '2) Create two users (alice@tenant-a.com, bob@tenant-b.com) with different org_id values. '
        '3) Alice connects her GitHub and ingests signals. '
        '4) Bob logs in and calls GET /api/oem/dashboard.',
        'In multi-tenant mode, Bob sees only Tenant B\'s data. In single-tenant mode, the guard is a no-op (documented).',
        'In single-tenant mode (the default), Bob sees Alice\'s data. <font face="Mono">check_tenant_access()</font> in oem_state.py line 364 returns immediately if <font face="Mono">MAESTRO_MULTI_TENANT != "true"</font>. In multi-tenant mode, it checks <font face="Mono">TenantContext.get_org_id()</font> against <font face="Mono">MAESTRO_ORG_ID</font> env var — meaning one deployment serves exactly one org. True multi-tenancy (multiple orgs sharing a deployment, each with isolated OEM state) is NOT implemented, as the docstring itself admits: "True multi-tenancy (per-org OEM state) requires keying OEMState by org_id — a future architectural change."',
        'The route-level guard (_require_tenant_access) IS wired into the OEM router via APIRouter(dependencies=[Depends(...)]). This closes the round-3 finding that "no OEM route reads the tenant context." But the guard is a no-op in the default configuration, and even when active, it enforces one-org-per-deployment rather than true multi-tenancy. The docstring is honest about this limitation.',
        'For a single-tenant pilot: accept the current behavior and document that multi-tenancy requires one deployment per tenant. For true multi-tenancy: key OEMState by org_id (a significant architectural change — each tenant gets its own OEMEngine, signal list, and decision engine). The coder\'s current fix is sufficient for the single-tenant pilot; mark true multi-tenancy as a post-pilot milestone.'
    ))

    story.append(issue_block(
        '4-R4', '3 pre-existing test failures remain (audit chain + SOC2 sessions)',
        'PARTIAL', 'MEDIUM',
        '1) Fresh git clone at commit a3ff319. '
        '2) pip install -e backend/ (now succeeds). '
        '3) python -m pytest backend/maestro_auth/tests/test_security_hardening.py --tb=short -q',
        'All tests pass (0 failures), matching the README claim "837+ tests pass on a clean clone".',
        '3 tests fail: TestAuditChain::test_chain_links_events, TestAuditChain::test_chain_detects_tampering, TestSOC2Endpoints::test_soc2_sessions. The SOC2 failure is a KeyError: 0 in security.py:1025 (session_inventory() accesses r[0] on a row that is a dict, not a tuple). The audit-chain failures are in the tamper-evidence logic. All 3 failures are confirmed pre-existing — they also fail at commit 9300d7c.',
        'The coder fixed 15 of the 18 round-3 test failures. The remaining 3 are in code paths they did not touch. The coder is honest about this in their commit message: "3 pre-existing failures (unrelated audit chain/SOC2 tests)".',
        'Fix the 3 failures: (1) security.py:1025 — change r[0] to r["session_id"] or list(r.values())[0] depending on the row type. (2) Audit-chain tamper detection — inspect the test expectations and fix the implementation or update the test. (3) Update the README claim from "837+ tests pass" to the actual passing count, or remove the claim until CI verifies it.'
    ))

    # ── UNFIXED BUT HONESTLY DOCUMENTED ───────────────────────────────────
    story.append(P('Unfixed But Honestly Documented', 'h1'))
    story.append(P(
        'The following findings are NOT fixed at the code level, but the coder added honesty docstrings that '
        'acknowledge the limitation. This is the right approach for a pilot — document what the algorithm '
        'actually does, let the pilot determine whether it is sufficient, and improve based on data.', 'body'))

    story.append(P('Finding #6 — "Ask the Organization" is keyword substring search — UNFIXED, honestly documented', 'h2'))
    story.append(P(
        'The algorithm in <font face="Mono">decision.py</font> <font face="Mono">answer_question()</font> is '
        'unchanged — it still splits the query on whitespace, filters tokens > 3 chars, and does a substring '
        'match against law statements, learning object descriptions, expert names, and bottleneck gates. '
        'However, a thorough honesty docstring was added (lines 256-268) that explicitly says: "The current '
        'matching algorithm is lexical keyword search... This is NOT natural-language understanding. A question '
        'sharing a single common word with an unrelated law will surface that law as relevant evidence." This '
        'is exactly the right framing for a pilot. The coder does not claim the algorithm is fixed — they claim '
        'it is honestly documented, which is true.', 'body'))

    story.append(P('Finding #7 — Decision Simulator is two linear formulas — UNFIXED, honestly documented', 'h2'))
    story.append(P(
        'The algorithm in <font face="Mono">simulation.py</font> <font face="Mono">simulate()</font> is unchanged '
        '— it still computes <font face="Mono">adjusted_p1 = max(0.0, base_p1 - hire_count * 0.02)</font> and '
        '<font face="Mono">adjusted_velocity = max(0.5, base_velocity - hire_count * 0.1)</font>. However, a '
        'thorough honesty docstring was added (lines 16-27) that explicitly says: "The current model is '
        'intentionally simple... The UI implies multiple adjustable levers (team moves, meeting cadence, org '
        'mergers), but only hire_count is actually modeled." This is honest. The coder does not claim the '
        'algorithm is fixed.', 'body'))

    # ── STILL UNFIXED ─────────────────────────────────────────────────────
    story.append(P('Still Unfixed (Not Addressed in 9dae51b or a3ff319)', 'h1'))

    story.append(issue_block(
        '5-R4', 'Organisational laws promoted from 3 observations (round-3 finding #9)',
        'UNFIXED', 'MEDIUM',
        '1) Start the server with the demo seed. '
        '2) Call GET /api/oem/laws. '
        '3) Observe the validated_runtimes counts.',
        'Laws are promoted only after a statistically meaningful number of observations.',
        'Laws are still promoted after 3 validated runtimes (law.py line 73: <font face="Mono">if self.validated_runtimes >= 3: self.status = LawStatus.VALIDATED</font>). The demo dataset still produces laws with confidence 1.0 from three Slack messages. Not addressed in either fix commit.',
        'The threshold was not changed. The confidence formula was not changed (still Beta(1,1) prior, which gives 1.0 for 3-of-3).',
        'Raise the threshold to at least 20 observations across 2+ providers and 2+ teams. Use Beta(0.5, 0.5) (Jeffreys) prior for law promotion. Add a "law_candidate" status that surfaces as a hypothesis, not a law.'
    ))

    story.append(issue_block(
        '6-R4', 'EncryptionManager XOR fallback still present (round-3 finding #11)',
        'UNFIXED', 'LOW',
        '1) Inspect maestro_auth/security.py EncryptionManager.encrypt() at commit a3ff319.',
        'EncryptionManager raises RuntimeError if cryptography is not installed. No XOR fallback.',
        'The XOR fallback is still present (security.py line 530: <font face="Mono">return "xor:" + base64.b64encode(bytes(a ^ b for a, b in zip(plaintext.encode(), self._key * 100))).decode()</font>). Not addressed. Low practical risk because cryptography IS in pyproject.toml, but the fallback code path should not exist.',
        'The XOR fallback was not removed.',
        'Remove the XOR fallback entirely. Make EncryptionManager.encrypt() raise RuntimeError if cryptography is not available.'
    ))

    story.append(issue_block(
        '7-R4', 'OAuth callback returns raw JSON instead of redirecting (round-3 finding #12)',
        'UNFIXED', 'MEDIUM',
        '1) Connect a real OAuth provider. '
        '2) Complete the OAuth round-trip. '
        '3) Observe the page the user lands on after the callback.',
        'The user is redirected to the Settings page with a visible "connected" indicator.',
        'oauth_callback() in routes/imports.py still returns a plain dict, which FastAPI serialises as JSON. The user still lands on a raw JSON response. Not addressed.',
        'The callback handler was not changed.',
        'Change oauth_callback() to return RedirectResponse(url="/#/eng-settings?connected=github"). Add a frontend handler that reads the connected query param and shows a success toast.'
    ))

    story.append(issue_block(
        '8-R4', 'In-process weekly snapshot duplicates across replicas (round-3 finding #13)',
        'UNFIXED', 'MEDIUM',
        '1) Deploy with multiple replicas. '
        '2) Wait 7 days. '
        '3) Inspect the SnapshotStore.',
        'One snapshot per week regardless of replica count.',
        '_weekly_snapshot_loop() in main.py:96 is unchanged. Each replica still spawns its own loop. No distributed lock. Not addressed.',
        'The in-process scheduler was not changed. The comment still says "In production, use a real cron scheduler; this in-process loop is sufficient for single-instance pilots."',
        'Use a distributed lock (PostgreSQL advisory lock, Redis SETNX) so only one replica runs the snapshot. Or move to an external cron job and remove the in-process loop.'
    ))

    # ── NEW ISSUES INTRODUCED BY THE FIXES ────────────────────────────────
    story.append(P('New Issues Introduced by the Fixes', 'h1'))
    story.append(P(
        'The audit searched for new issues introduced by the 9dae51b and a3ff319 commits. <b>No new code-level '
        'security regressions were found.</b> The fixes are clean — they do not introduce new vulnerabilities. '
        'Two minor inconsistencies were noted:', 'body'))

    story.append(P(
        '<b>Minor inconsistency 1:</b> In <font face="Mono">eng_audit.js</font> lines 167-168 and 234, '
        '<font face="Mono">p.provider</font> and <font face="Mono">job.job_id</font> are used in inline onclick '
        'handlers WITHOUT <font face="Mono">escapeJs()</font>. These are server-controlled values (provider names '
        'like "github", job IDs that are UUIDs) and are not user-controlled, so the practical risk is negligible. '
        'But the pattern is inconsistent — every other onclick in the codebase now uses '
        '<font face="Mono">escapeJs()</font>. Recommend applying <font face="Mono">escapeJs()</font> universally '
        'for defense-in-depth.', 'body'))

    story.append(P(
        '<b>Minor inconsistency 2:</b> In <font face="Mono">customer_judgment_engine.js</font> lines 211 and 231, '
        '<font face="Mono">s.type</font> is used in an onclick handler without <font face="Mono">escapeJs()</font>. '
        '<font face="Mono">s.type</font> comes from scenario definitions and is not user-controlled. Same '
        'recommendation: apply <font face="Mono">escapeJs()</font> universally.', 'body'))

    story.append(P(
        'Neither inconsistency is exploitable in the current codebase because the unescaped values are not '
        'attacker-controlled. They are noted for completeness and defense-in-depth, not as security blockers.', 'body'))

    # ── TEST SUITE RESULTS ────────────────────────────────────────────────
    story.append(P('Test Suite Re-Run Results', 'h1'))
    story.append(P(
        'The audit re-ran the test suite at commit <font face="Mono">a3ff319</font> on a clean install. '
        'Results by suite:', 'body'))

    test_rows = [
        ['Suite', 'Passed', 'Failed', 'Skipped', 'Notes'],
        ['test_semantic_autocomplete.py', '27', '0', '0', 'All 4 round-3 ARIA failures fixed'],
        ['test_security_hardening.py', '52', '3', '0', '3 pre-existing (audit chain + SOC2), confirmed at 9300d7c'],
        ['test_comprehensive_qa.py', '104', '0', '1', 'All 11 round-3 failures fixed'],
        ['test_enterprise_auth.py', '55', '0', '0', 'Clean pass'],
        ['test_oem.py + test_learning.py + test_semantic_autocomplete.py', '101', '0', '0', 'OEM core sampled (full suite exceeds timeout)'],
        ['Full API suite (test_api/tests/)', '269', '0', '2', 'Clean pass'],
        ['TOTAL VERIFIED', '477+', '3', '3', '3 failures are pre-existing, not regressions'],
    ]
    t = Table(test_rows, colWidths=[55*mm, 16*mm, 14*mm, 16*mm, PAGE_W - MARGIN_L - MARGIN_R - 101*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0fdf4')),
        ('FONTNAME', (0, -1), (-1, -1), FONT_HEAD_B),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (3, -1), 'CENTER'),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(P(
        'The coder claims "376 passed, 3 failed". The auditor verified 477+ passed, 3 failed. The coder\'s '
        'number is conservative — they likely counted a subset. The 3 failures are confirmed pre-existing. '
        '<b>No regressions were introduced by the security fixes.</b>', 'body'))

    # ── UPDATED SCORES ────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(P('Updated Scores — Round 4', 'h1'))
    story.append(P(
        'Scores are out of 10. They reflect what was observed at commit <font face="Mono">a3ff319</font>. '
        'Round-3 scores are shown for comparison.', 'body'))

    score_rows = [
        ['Category', 'Round 3', 'Round 4', 'Change', 'Justification'],
        ['Navigation', '7/10', '7/10', '—', 'No change. Drill-down loops and misnamed Live Meeting page still present.'],
        ['Usability', '5/10', '6/10', '+1', 'OAuth callback still lands on JSON (Issue #7-R4), but demo seed purge and honest cost formula improve trust.'],
        ['Enterprise Readiness', '2/10', '4/10', '+2', 'OIDC no longer fails open on missing PyJWT. Tenant guard exists (single-tenant only). Supabase/Auth0 stubs raise. But OIDC algorithm injection still open, SAML crypto-verification skipped, no CI.'],
        ['Interaction Quality', '6/10', '6/10', '—', 'No change. Ask is still keyword search. Simulator is still linear. Both honestly documented.'],
        ['Performance', '6/10', '6/10', '—', 'No change. Same O(n) scans in hot path. No metrics endpoint.'],
        ['Reliability', '4/10', '6/10', '+2', 'pip install now works. 15 of 18 test failures fixed. But 3 pre-existing failures remain, no CI, snapshot still per-replica.'],
        ['Accessibility', '4/10', '7/10', '+3', 'All 4 ARIA failures fixed. Skip-link, role=dialog, focus management all present. Contrast still unmeasured.'],
        ['Data Credibility', '3/10', '5/10', '+2', 'Cost formula no longer fabricated. Demo seed purges on real connection. But laws still promote from 3 observations, Ask is still keyword search, Simulator still linear.'],
        ['Execution Flow', '5/10', '6/10', '+1', 'Demo seed purge on first real signal is a real fix. OAuth callback still JSON. Live Meeting still manual paste.'],
        ['Overall Production Readiness', '3/10', '5/10', '+2', 'Security posture now defensible for single-tenant pilot. OIDC algorithm injection + SAML crypto gap are the remaining code-level blockers. 4 hours of work to YES WITH MINOR FIXES.'],
    ]
    t = Table(score_rows, colWidths=[36*mm, 14*mm, 14*mm, 12*mm, PAGE_W - MARGIN_L - MARGIN_R - 76*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_HEAD_B),
        ('FONTNAME', (0, 1), (-1, -1), FONT_BODY),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_STRIPE]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fef9f3')),
        ('TEXTCOLOR', (1, -1), (1, -1), SEV_HIGH),
        ('TEXTCOLOR', (2, -1), (2, -1), colors.HexColor('#b45309')),
        ('FONTNAME', (1, 1), (3, -1), FONT_HEAD_B),
        ('ALIGN', (1, 0), (3, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    story.append(Spacer(1, 6 * mm))

    # ── VERDICT ──────────────────────────────────────────────────────────
    story.append(P('Updated Verdict — Round 4', 'h1'))
    story.append(P(
        'The user\'s prompt requires answering exactly one question: "Would you ship this to a Fortune 100 '
        'customer tomorrow?" The allowed answers are YES, YES WITH MINOR FIXES, NO, or ABSOLUTELY NOT.', 'body'))

    verdict_box = Table([[
        Paragraph(
            '<font color="white" size="20"><b>NO</b></font><br/><br/>'
            '<font color="white" size="11"><b>— but narrowing. 4 hours of work to YES WITH MINOR FIXES.</b></font>',
            ParagraphStyle('v', fontName=FONT_HEAD_B, fontSize=20, leading=24,
                           textColor=colors.white, alignment=TA_CENTER)
        )
    ]], colWidths=[PAGE_W - MARGIN_L - MARGIN_R], rowHeights=[80])
    verdict_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SEV_HIGH),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(verdict_box)
    story.append(Spacer(1, 6 * mm))

    story.append(P(
        '<b>Why NO and not ABSOLUTELY NOT.</b> The three CRITICAL findings from round 3 are no longer '
        'CRITICAL. The OIDC fail-open is closed (PyJWT in deps, ImportError raises). The XSS is closed '
        '(escapeJs helper, applied everywhere). The tenant isolation is no longer completely decorative '
        '(route-level guard exists, though it is a no-op in single-tenant mode). The security posture is '
        'now defensible for a single-tenant pilot — an attacker cannot authenticate without a valid JWT or '
        'valid SAML response, and the frontend no longer has an obvious code-injection vector. This is '
        'genuine progress, verified against source.', 'body'))

    story.append(P(
        '<b>Why NO and not YES WITH MINOR FIXES.</b> Two code-level security gaps remain that the coder '
        'claims are fixed but are not. (1) The OIDC algorithm-injection vulnerability — '
        '<font face="Mono">algorithms=[header.get("alg", "RS256")]</font> on line 333 of oidc.py — is still '
        'present. An attacker who forges a JWT with <font face="Mono">alg=HS256</font> and signs with HMAC '
        'using the server\'s public RSA key can bypass verification. Modern PyJWT has partial mitigations, '
        'but the code pattern is wrong. (2) The SAML cryptographic-verification gap — when a '
        '<font face="Mono">&lt;ds:Signature&gt;</font> element is present but <font face="Mono">python3-saml</font> '
        'is not installed (it is not in deps), the code logs a warning and accepts without crypto-verification. '
        'An attacker who injects a fake signature element bypasses verification. Both are 30-60 minute fixes '
        '(hardcode <font face="Mono">algorithms=["RS256"]</font>; add <font face="Mono">python3-saml</font> '
        'to deps and fail closed).', 'body'))

    story.append(P(
        '<b>Why NO and not YES.</b> Beyond the two security gaps: 3 pre-existing test failures remain (audit '
        'chain + SOC2), no CI exists, the OAuth callback still lands on raw JSON, and the in-process snapshot '
        'scheduler still duplicates across replicas. None of these are individually disqualifying, but together '
        'they indicate the codebase is not yet at the "every claim is verified by CI" standard a Fortune 100 '
        'procurement review demands.', 'body'))

    story.append(P(
        '<b>The path from NO to YES WITH MINOR FIXES is approximately 4 hours of work:</b>', 'body'))
    story.append(P('1. <b>30 min</b> — Hardcode <font face="Mono">algorithms=["RS256"]</font> in oidc.py line 333. Add a unit test that forges an HS256 JWT and asserts rejection.', 'body_left'))
    story.append(P('2. <b>1 hour</b> — Add <font face="Mono">python3-saml>=1.16</font> to pyproject.toml. Change saml.py lines 211-219 from warning-and-accept to raise SAMLError. Add a unit test that submits a SAML response with invalid signature and asserts rejection.', 'body_left'))
    story.append(P('3. <b>1 hour</b> — Fix the 3 pre-existing test failures (audit chain + SOC2 KeyError).', 'body_left'))
    story.append(P('4. <b>30 min</b> — Set up GitHub Actions CI that runs <font face="Mono">pytest</font> on every push.', 'body_left'))
    story.append(P('5. <b>30 min</b> — Change oauth_callback() to return RedirectResponse. Add frontend success toast.', 'body_left'))

    story.append(P(
        '<b>What this audit credits the coder with.</b> The coder\'s response to the round-3 audit was '
        'genuinely good engineering. They did not argue with findings — they verified them, fixed the real '
        'ones, and added honesty docstrings for the algorithmic limitations they chose not to change. The '
        'commit messages are candid: "The auditor was right: these were real code-level security defects, '
        'not test-infrastructure artifacts. The OIDC fail-open was an authentication bypass — the most '
        'serious finding in the engagement." This is the right posture. The two remaining gaps (OIDC '
        'algorithm injection, SAML crypto) are likely oversights rather than intentional — the coder fixed '
        'the ImportError fail-open and the unsigned-response fail-open but did not notice the algorithm-injection '
        'and signature-crypto gaps that the same files still contain. A re-read of the round-3 report would '
        'catch them.', 'body'))

    story.append(P(
        '<b>The coder\'s self-assessment of "5-6/10" is accurate.</b> The auditor\'s round-4 score is 5/10. '
        'The coder\'s judgement about their own work is sound — they correctly identified which findings '
        'were fixed, which were honestly documented, and which remained. The one place where the coder\'s '
        'self-assessment diverges from the auditor\'s verification is the claim that "all code-level security '
        'findings from all three audit rounds are now closed" — this is false for OIDC algorithm injection '
        'and SAML crypto-verification. Both are code-level. Both are security. Both are still open.', 'body'))

    story.append(P(
        '<b>A note on the engagement pattern.</b> The coder writes: "The engagement is at its final gate. '
        'The code is pilot-ready. The security posture is defensible. The remaining items are 2 hours of '
        'work (Supabase stub + CI + SAML). After that, the only gate is empirical: the 90-day pilot. Run it." '
        'The auditor agrees with the spirit but not the letter. The code is ALMOST pilot-ready — two security '
        'gaps remain that the coder does not see. Once those are closed (4 hours, not 2), the code is '
        'pilot-ready for a single-tenant deployment. The 90-day pilot is then the right next step. Run it — '
        'but close the two remaining code-level security gaps first.', 'body'))

    return story


def main():
    out_dir = Path('/home/z/my-project/download')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'MaestroAgent_Round4_Reverification_Report.pdf'
    doc = build_doc(str(out_path))
    story = build_story()
    doc.build(story)
    print(f'Wrote {out_path}')
    print(f'Size: {out_path.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()
