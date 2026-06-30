/**
 * Maestro Ambient Whisper — Browser Extension (Manifest V3)
 *
 * This is the delivery mechanism that makes Maestro ambient.
 *
 * The backend Whisper API exists (commit 3fe450c) but it requires the
 * user to open Maestro and call it. This extension surfaces the Whisper
 * WITHOUT the user opening Maestro — it detects when you're in Gmail,
 * Google Calendar, or GitHub, infers the context from the page, calls
 * the Whisper API, and shows a small non-intrusive panel.
 *
 * This is the "radio receiver" for Maestro's "radio station."
 *
 * INSTALLATION (Chrome/Edge):
 *   1. Open chrome://extensions
 *   2. Enable Developer mode
 *   3. Click "Load unpacked"
 *   4. Select this folder (maestro-ambient-extension/)
 *   5. Set MAESTRO_API_URL in the extension options
 *
 * PRIVACY BY DESIGN:
 *   - No keystroke logging
 *   - No content inspection of email bodies or documents
 *   - Uses only page URL + title to infer context
 *   - Calls the Maestro Whisper API with inferred context only
 *   - No data is stored or transmitted elsewhere
 *
 * The extension is deliberately lightweight — the intelligence lives in
 * Maestro's backend, not in the extension.
 */

(function() {
  'use strict';

  // Prevent double-injection
  if (window.__maestroAmbientInjected) return;
  window.__maestroAmbientInjected = true;

  let MAESTRO_API_URL = 'http://localhost:8000';
  let whisperEnabled = true;
  let lastWhisperTime = 0;
  const WHISPER_COOLDOWN_MS = 60000;

  chrome.storage?.local.get(['maestroApiUrl', 'whisperEnabled'], (result) => {
    if (result.maestroApiUrl) MAESTRO_API_URL = result.maestroApiUrl;
    if (result.whisperEnabled !== undefined) whisperEnabled = result.whisperEnabled;
  });

  // ─── Context Detection (URL + title only, NO content inspection) ─────────

  function detectContext() {
    const url = window.location.href;
    const title = document.title;

    if (url.includes('mail.google.com')) {
      return { context: 'email', entity: extractEntity(title), topic: inferTopic(title), app: 'gmail' };
    }
    if (url.includes('calendar.google.com')) {
      return { context: 'meeting', entity: extractEntity(title), topic: '', app: 'calendar' };
    }
    if (url.includes('github.com')) {
      const domain = inferDomain(url);
      return { context: 'review', entity: domain, topic: domain, app: 'github' };
    }
    if (url.includes('zoom.us')) {
      return { context: 'meeting', entity: extractEntity(title), topic: '', app: 'zoom' };
    }
    if (url.includes('slack.com')) {
      return { context: 'message', entity: '', topic: '', app: 'slack' };
    }
    return null;
  }

  function extractEntity(title) {
    const known = ['Globex', 'Initech', 'Hooli', 'Microsoft', 'Stripe', 'Snowflake', 'Amazon', 'Google', 'Acme'];
    for (const c of known) { if (title.includes(c)) return c; }
    const match = title.match(/\b([A-Z][a-z]+)\b/);
    return match ? match[1] : '';
  }

  function inferTopic(title) {
    const l = title.toLowerCase();
    if (l.includes('price') || l.includes('pricing') || l.includes('cost')) return 'pricing';
    if (l.includes('security') || l.includes('compliance') || l.includes('soc2')) return 'security';
    if (l.includes('timeline') || l.includes('deadline') || l.includes('due')) return 'timeline';
    if (l.includes('contract') || l.includes('renewal') || l.includes('legal')) return 'legal';
    if (l.includes('feature') || l.includes('roadmap')) return 'features';
    return '';
  }

  function inferDomain(url) {
    const l = url.toLowerCase();
    if (l.includes('auth') || l.includes('oauth') || l.includes('security')) return 'auth';
    if (l.includes('payment') || l.includes('billing')) return 'payments';
    if (l.includes('deploy') || l.includes('release')) return 'deployment';
    if (l.includes('platform') || l.includes('infra')) return 'platform';
    return '';
  }

  // ─── Whisper Panel ──────────────────────────────────────────────────────

  function createPanel(data) {
    const existing = document.getElementById('maestro-whisper-panel');
    if (existing) existing.remove();
    if (!data.whispers || data.whispers.length === 0) return;

    const panel = document.createElement('div');
    panel.id = 'maestro-whisper-panel';
    panel.style.cssText = `position:fixed;bottom:20px;right:20px;width:340px;max-height:400px;overflow-y:auto;background:#0a0a14;border:1px solid rgba(124,92,255,0.3);border-radius:12px;padding:14px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:12px;color:#eaeaef;z-index:999999;box-shadow:0 8px 32px rgba(0,0,0,0.4);transition:opacity 0.3s,transform 0.3s;opacity:0;transform:translateY(10px);`;

    panel.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid rgba(255,255,255,0.06);">
        <div style="width:20px;height:20px;border-radius:6px;background:rgba(124,92,255,0.15);display:flex;align-items:center;justify-content:center;color:#7c5cff;font-weight:bold;font-size:11px;">M</div>
        <div style="font-size:11px;font-weight:600;color:#7c5cff;letter-spacing:0.03em;">Maestro Whisper</div>
        <div style="margin-left:auto;cursor:pointer;color:#6b7280;font-size:14px;" id="maestro-w-close">×</div>
      </div>
      <div id="maestro-w-content"></div>
      ${data.narrative ? `<div style="margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.06);font-size:9px;color:#6b7280;">${esc(data.narrative)}</div>` : ''}
    `;

    const content = panel.querySelector('#maestro-w-content');
    data.whispers.slice(0, 4).forEach(w => {
      const item = document.createElement('div');
      item.style.cssText = 'margin-bottom:8px;padding:6px 8px;background:rgba(255,255,255,0.03);border-radius:6px;';
      item.innerHTML = `<div style="font-size:11px;color:#eaeaef;line-height:1.4;">${esc(w.text)}</div><div style="font-size:9px;color:#6b7280;margin-top:3px;">${esc(w.source||'')} · ${Math.round((w.confidence||0.5)*100)}% confidence</div>`;
      content.appendChild(item);
    });
    if (data.warnings) {
      data.warnings.slice(0, 2).forEach(w => {
        const item = document.createElement('div');
        item.style.cssText = 'margin-bottom:8px;padding:6px 8px;background:rgba(245,158,11,0.08);border-left:2px solid #f59e0b;border-radius:4px;';
        item.innerHTML = `<div style="font-size:11px;color:#fbbf24;line-height:1.4;">⚠ ${esc(w.text)}</div>`;
        content.appendChild(item);
      });
    }

    document.body.appendChild(panel);
    requestAnimationFrame(() => { panel.style.opacity = '1'; panel.style.transform = 'translateY(0)'; });
    panel.querySelector('#maestro-w-close').addEventListener('click', () => dismiss(panel));
    setTimeout(() => dismiss(panel), 30000);
  }

  function dismiss(panel) {
    if (!panel.parentNode) return;
    panel.style.opacity = '0';
    panel.style.transform = 'translateY(10px)';
    setTimeout(() => panel.remove(), 300);
  }

  function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

  // ─── API Call ───────────────────────────────────────────────────────────

  async function fetchWhisper(ctx) {
    try {
      const params = new URLSearchParams({ context: ctx.context, entity: ctx.entity, topic: ctx.topic });
      const resp = await fetch(`${MAESTRO_API_URL}/api/oem/whisper?${params}`, { credentials: 'include', headers: { 'Accept': 'application/json' } });
      if (!resp.ok) return null;
      return await resp.json();
    } catch { return null; }
  }

  // ─── Main ───────────────────────────────────────────────────────────────

  async function maybeWhisper() {
    if (!whisperEnabled) return;
    if (Date.now() - lastWhisperTime < WHISPER_COOLDOWN_MS) return;
    const ctx = detectContext();
    if (!ctx || (!ctx.entity && !ctx.topic)) return;
    lastWhisperTime = Date.now();
    const data = await fetchWhisper(ctx);
    if (data && data.whispers && data.whispers.length > 0) createPanel(data);
  }

  setTimeout(maybeWhisper, 3000);
  let lastUrl = location.href;
  setInterval(() => { if (location.href !== lastUrl) { lastUrl = location.href; setTimeout(maybeWhisper, 2000); } }, 2000);

  chrome.runtime?.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'toggleWhisper') { whisperEnabled = msg.enabled; if (!whisperEnabled) { const p = document.getElementById('maestro-whisper-panel'); if (p) p.remove(); } sendResponse({ ok: true }); }
    if (msg.type === 'triggerWhisper') { maybeWhisper(); sendResponse({ ok: true }); }
  });
})();
