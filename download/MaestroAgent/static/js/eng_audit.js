// ENG: AUDIT — structured signals (NO JSON.stringify)
// ═══════════════════════════════════════════════════════════════════════════

async function loadEngAudit() {
  const el = document.getElementById('eng-audit-list');
  loadingHTML(el, 'Loading signal history…');
  try {
    const data = await api.getOEM('/signals?limit=100');
    if (data.signals.length === 0) {
      emptyHTML(el, 'No signal history yet. Events appear as signals flow into Maestro.');
      return;
    }
    el.innerHTML = `
      <div class="text-[10px] text-fg-500 mb-3">${data.total} signals · showing latest ${data.signals.length}</div>
      <div class="space-y-1">
        ${data.signals.map(r => `
          <div class="text-[11px] p-2 rounded bg-white/[0.02] border border-white/[0.04] grid grid-cols-12 gap-2 items-center hover:bg-white/[0.04] cursor-pointer" onclick="openDrilldown('signal', '${escapeJs(r.receipt_id)}')">
            <span class="mono text-brand-purple col-span-2" title="${escapeHtml(r.receipt_id)}">${escapeHtml(r.receipt_id.substring(0, 8))}</span>
            <span class="text-fg-500 col-span-2">${formatTimestamp(r.timestamp)}</span>
            <span class="tag tag-gray col-span-1">${escapeHtml(r.provider)}</span>
            <span class="text-fg-300 col-span-2">${escapeHtml(r.signal_type)}</span>
            <span class="text-fg-200 col-span-2 truncate" title="${escapeHtml(r.actor)}">${escapeHtml(r.actor)}</span>
            <span class="text-fg-400 col-span-2 truncate" title="${escapeHtml(r.artifact)}">${escapeHtml(r.artifact)}</span>
            <span class="text-fg-500 col-span-1">${r.law_code ? `<span class="source-cite">${escapeHtml(r.law_code)}</span>` : ''}</span>
          </div>
        `).join('')}
      </div>
    `;
  } catch (e) {
    errorHTML(el, e.message, 'loadEngAudit()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ENG: SETTINGS
// ═══════════════════════════════════════════════════════════════════════════

async function loadEngSettings() {
  document.getElementById('settings-api-url').value = MAESTRO_API || '(same origin)';
  const statusEl = document.getElementById('settings-oem-status');
  try {
    const data = await api.getOEM('/state');
    statusEl.innerHTML = `<span class="text-brand-cyan">●</span> Connected — ${data.summary.signals_processed} signals, ${data.summary.laws_inferred} laws`;
  } catch (e) {
    statusEl.innerHTML = `<span class="text-brand-rose">●</span> Unreachable: ${escapeHtml(e.message)}`;
  }
  await loadProviderStatus();
  await loadImportJobs();
  loadOAuthAdminConfigs();
}

// ─── Enterprise OAuth Self-Service ────────────────────────────────────────

let _editingOAuthProvider = '';

async function loadOAuthAdminConfigs() {
  const el = document.getElementById('oauth-admin-list');
  if (!el) return;
  try {
    const resp = await fetch((MAESTRO_API || '') + '/api/oauth/admin/providers');
    const data = await resp.json();
    el.innerHTML = data.providers.map(p => {
      const statusBadge = p.configured
        ? `<span class="tag ${p.configured_via === 'database' ? 'tag-green' : 'tag-yellow'}">${p.configured_via}</span>`
        : '<span class="tag tag-gray">not configured</span>';
      return `
        <div class="border border-white/[0.05] rounded-lg p-3">
          <div class="flex items-center justify-between mb-1">
            <div class="font-semibold text-white text-sm">${escapeHtml(humanize(p.label))}</div>
            ${statusBadge}
          </div>
          <div class="text-[10px] text-fg-400">
            ${p.client_id ? `Client ID: <code>${escapeHtml(p.client_id)}</code>` : 'No Client ID set'}
            ${p.has_secret ? ' · <span class="b-clr-1d11">Secret: encrypted</span>' : ''}
          </div>
          <div class="flex gap-1.5 mt-2">
            <button class="tag tag-gray cursor-pointer text-[10px] hover:bg-white/[0.05]" onclick="openOAuthConfigForm('${escapeJs(p.provider)}', '${escapeJs(p.label)}', '${escapeJs(p.client_id)}')" aria-label="Configure ${escapeHtml(humanize(p.label))}">Configure</button>
            ${p.configured_via === 'database' ? `<button class="tag tag-gray cursor-pointer text-[10px] hover:bg-red-500/10" onclick="deleteOAuthProvider('${escapeJs(p.provider)}')" aria-label="Remove ${escapeHtml(humanize(p.label))} config">Remove</button>` : ''}
            ${p.configured ? `<button class="tag tag-cyan cursor-pointer text-[10px]" onclick="window.open('${(MAESTRO_API || '') + '/api/oauth/' + p.provider + '/start'}')" aria-label="Connect ${escapeHtml(humanize(p.label))}">Connect</button>` : ''}
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Failed to load OAuth configs: ${escapeHtml(e.message)}</div>`;
  }
}

function openOAuthConfigForm(provider, label, existingClientId) {
  _editingOAuthProvider = provider;
  document.getElementById('oauth-form-title').textContent = `Configure ${label}`;
  document.getElementById('oauth-client-id').value = existingClientId || '';
  document.getElementById('oauth-client-secret').value = '';
  document.getElementById('oauth-redirect-uri').value = '';
  document.getElementById('oauth-config-form').style.display = '';
  document.getElementById('oauth-client-id').focus();
}

async function saveOAuthProvider() {
  const provider = _editingOAuthProvider;
  if (!provider) return;
  const clientId = document.getElementById('oauth-client-id').value.trim();
  const clientSecret = document.getElementById('oauth-client-secret').value.trim();
  const redirectUri = document.getElementById('oauth-redirect-uri').value.trim();

  if (!clientId || !clientSecret) {
    alert('Client ID and Client Secret are required.');
    return;
  }

  try {
    const resp = await fetch((MAESTRO_API || '') + `/api/oauth/admin/providers/${provider}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret, redirect_uri: redirectUri }),
    });
    const data = await resp.json();
    if (data.ok) {
      document.getElementById('oauth-config-form').style.display = 'none';
      loadOAuthAdminConfigs();
    } else {
      alert(data.detail || 'Failed to save OAuth config');
    }
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function deleteOAuthProvider(provider) {
  if (!confirm(`Remove ${provider} configuration? Environment variable fallback will remain if set.`)) return;
  try {
    const resp = await fetch((MAESTRO_API || '') + `/api/oauth/admin/providers/${provider}`, { method: 'DELETE' });
    const data = await resp.json();
    if (data.ok) {
      loadOAuthAdminConfigs();
    } else {
      alert(data.detail || 'Failed to remove');
    }
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

// ─── Signal provider connection UI ─────────────────────────────────────────

const PROVIDER_META = {
  github:     { name: 'GitHub',     icon: 'G', description: 'Code execution, PR reviews, and repository management' },
  jira:       { name: 'Jira',       icon: 'J', description: 'Issue tracking, sprint velocity, approval bottlenecks' },
  slack:      { name: 'Slack',      icon: 'S', description: 'Messages, threads, hidden experts, departure signals' },
  confluence: { name: 'Confluence', icon: 'C', description: 'Knowledge pages, version history, expertise graph' },
  gmail:      { name: 'Gmail',      icon: 'M', description: 'Email patterns, decision trails, cross-team signals' },
};

async function loadProviderStatus() {
  const listEl = document.getElementById('signal-providers-list');
  if (!listEl) return;
  try {
    const data = await api.getOAuthStatus();
    listEl.innerHTML = data.providers.map(p => {
      const meta = PROVIDER_META[p.provider] || { name: p.provider, icon: 'O', description: '' };
      const statusBadge = p.connected
        ? `<span class="tag tag-cyan">Connected</span>`
        : p.configured
          ? `<span class="tag tag-gray">Not connected</span>`
          : `<span class="tag tag-amber" title="Set MAESTRO_OAUTH_${p.provider.toUpperCase()}_CLIENT_ID and _SECRET env vars">Not configured</span>`;
      const actionButton = p.connected
        ? `<button class="btn btn-ghost text-[11px]" onclick="disconnectProvider('${escapeJs(p.provider)}')">Disconnect</button>`
        : `<button class="btn btn-primary text-[11px]" ${p.configured ? '' : 'disabled'} onclick="connectProvider('${escapeJs(p.provider)}')">Connect</button>`;
      return `
        <div class="flex items-center justify-between p-3 rounded-lg bg-ink-800/60 border border-ink-700">
          <div class="flex items-center gap-3">
            <div class="text-xl">${meta.icon}</div>
            <div>
              <div class="text-sm font-semibold text-white">${meta.name}</div>
              <div class="text-[10px] text-fg-500">${escapeHtml(humanize(meta.description))}</div>
            </div>
          </div>
          <div class="flex items-center gap-3">
            ${statusBadge}
            ${actionButton}
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    listEl.innerHTML = `<div class="text-xs text-brand-rose">Failed to load provider status: ${escapeHtml(e.message)}</div>`;
  }
}

async function connectProvider(provider) {
  try {
    const resp = await fetch(`${MAESTRO_API}/api/oauth/${provider}/start`);
    if (!resp.ok) {
      const err = await resp.json();
      showError(`Failed to start OAuth: ${err.detail || 'Unknown error'}`);
      return;
    }
    const { auth_url } = await resp.json();
    window.location.href = auth_url;
  } catch (e) {
    showError(`Connection failed: ${e.message}`);
  }
}

async function disconnectProvider(provider) {
  if (!confirm(`Disconnect ${provider}? Already-ingested history is preserved.`)) return;
  try {
    await fetch(`${MAESTRO_API}/api/oauth/${provider}/disconnect`, { method: 'POST' });
    SWR.invalidate('oauth:status');
    await loadProviderStatus();
  } catch (e) {
    showError(`Disconnect failed: ${e.message}`);
  }
}

async function loadImportJobs() {
  const listEl = document.getElementById('import-jobs-list');
  if (!listEl) return;
  try {
    const data = await api.getImports();
    if (!data.jobs || data.jobs.length === 0) {
      listEl.innerHTML = '<div class="text-xs text-fg-500">No import jobs yet. Connect a provider to start.</div>';
      return;
    }
    listEl.innerHTML = data.jobs.slice(0, 10).map(job => {
      const statusColor = job.status === 'completed' ? 'cyan' : job.status === 'failed' ? 'rose' : job.status === 'running' ? 'violet' : 'gray';
      return `
        <div class="flex items-center justify-between p-2 rounded-lg bg-ink-800/60 border border-ink-700 text-xs">
          <div>
            <div class="font-semibold text-white">${job.providers.join(', ')}</div>
            <div class="text-fg-500">${job.total_signals || 0} signals · ${job.started_at ? new Date(job.started_at).toLocaleString() : ''}</div>
          </div>
          <div class="flex items-center gap-2">
            <span class="tag tag-${statusColor}">${job.status}</span>
            ${job.status === 'running' ? `<button class="btn btn-ghost text-[10px]" onclick="cancelImport('${escapeJs(job.job_id)}')">Cancel</button>` : ''}
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    listEl.innerHTML = `<div class="text-xs text-brand-rose">Failed to load jobs: ${escapeHtml(e.message)}</div>`;
  }
}

async function cancelImport(jobId) {
  if (!jobId) {
    const banner = document.getElementById('import-banner');
    jobId = banner.dataset.jobId;
  }
  if (!jobId) return;
  try {
    await fetch(`${MAESTRO_API}/api/imports/${jobId}/cancel`, { method: 'POST' });
  } catch (e) {
    console.warn('Cancel failed:', e);
  }
}

// ─── Live import progress banner (WebSocket) ────────────────────────────────

let importWs = null;
let importPollInterval = null;

async function checkForRunningImports() {
  try {
    const data = await api.getImports();
    const running = (data.jobs || []).find(j => j.status === 'running');
    if (running) {
      subscribeToImport(running.job_id);
    }
  } catch (e) {
    // Silently fail — banner is non-critical
  }
}

function subscribeToImport(jobId) {
  if (importWs) {
    try { importWs.close(); } catch (e) {}
  }
  const wsBase = MAESTRO_API.replace(/^http/, 'ws') || (window.location.origin.replace(/^http/, 'ws'));
  importWs = new WebSocket(`${wsBase}/api/imports/${jobId}/stream`);
  importWs.onmessage = (e) => {
    try {
      const snap = JSON.parse(e.data);
      if (snap.type === 'ping') return;
      updateImportBanner(jobId, snap);
    } catch (err) {}
  };
  importWs.onerror = (e) => {
    console.warn('Import WS error:', e);
    // Don't silently fall back to polling — surface the error
    showError('Import monitoring connection lost. Will retry.');
  };
  importWs.onclose = () => {
    if (importPollInterval) clearInterval(importPollInterval);
    let pollStartedAt = Date.now(), pollErrors = 0;
    importPollInterval = setInterval(async () => {
      // Max poll duration: 1 hour
      if (Date.now() - pollStartedAt > 60 * 60 * 1000) {
        clearInterval(importPollInterval);
        importPollInterval = null;
        showError('Import monitoring timed out after 1 hour.');
        hideImportBanner();
        return;
      }
      try {
        const resp = await fetch(`${MAESTRO_API}/api/imports/${jobId}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const job = await resp.json();
        pollErrors = 0;
        if (job.status === 'running' || (job.providers_progress && Object.values(job.providers_progress).some(p => p.status === 'running'))) {
          updateImportBanner(jobId, job);
        } else {
          hideImportBanner();
          clearInterval(importPollInterval);
          importPollInterval = null;
        }
      } catch (e) {
        if (++pollErrors > 5) {
          clearInterval(importPollInterval);
          importPollInterval = null;
          hideImportBanner();
          showError('Import monitoring lost after 5 consecutive errors.');
        }
      }
    }, 5000);
  };
}

function updateImportBanner(jobId, snap) {
  const banner = document.getElementById('import-banner');
  banner.classList.remove('hidden');
  banner.dataset.jobId = jobId;

  const providers = snap.providers_progress || {};
  const providerNames = Object.keys(providers);
  const totalEvents = snap.total_events || 0;
  const runningProvider = providerNames.find(p => providers[p].status === 'running');
  const totalEstimated = runningProvider ? providers[runningProvider].total_estimated : 0;
  const etaSeconds = runningProvider ? providers[runningProvider].eta_seconds : 0;

  const titleEl = document.getElementById('import-banner-title');
  const subtitleEl = document.getElementById('import-banner-subtitle');
  if (runningProvider) {
    const meta = PROVIDER_META[runningProvider] || { name: runningProvider };
    titleEl.textContent = `Importing ${meta.name}…`;
    const etaMin = Math.ceil(etaSeconds / 60);
    subtitleEl.textContent = `${totalEvents.toLocaleString()} events processed · ETA ${etaMin}m`;
  } else if (snap.status === 'completed') {
    titleEl.textContent = `Import complete`;
    subtitleEl.textContent = `${totalEvents.toLocaleString()} events imported`;
    setTimeout(hideImportBanner, 5000);
  } else if (snap.status === 'failed') {
    titleEl.textContent = `Import failed`;
    subtitleEl.textContent = snap.error || 'Unknown error';
    setTimeout(hideImportBanner, 10000);
  }

  const oem = snap.oem || {};
  document.getElementById('import-banner-patterns').textContent = oem.patterns_detected || 0;
  document.getElementById('import-banner-laws').textContent = oem.laws_inferred || 0;
  document.getElementById('import-banner-recs').textContent = oem.recommendations || 0;

  const progressPct = totalEstimated > 0 ? Math.min(100, (totalEvents / totalEstimated) * 100) : 0;
  document.getElementById('import-banner-progress').style.width = `${progressPct}%`;

  // Only refresh dashboard on completion (not on every progress tick).
  // The old code re-fetched /ceo-briefing + /dashboard every 2s during
  // imports — hundreds of unnecessary backend inference calls.
  if (snap.phase === 'completed' && window._currentSurface === 'home') {
    SWR.invalidatePrefix('oem:');  // Invalidate cache; next render fetches fresh
    loadDashboard();
  }
}

function hideImportBanner() {
  document.getElementById('import-banner').classList.add('hidden');
  // Full teardown: close WS and clear polling interval
  if (importWs) { try { importWs.close(); } catch (e) {} importWs = null; }
  if (importPollInterval) { clearInterval(importPollInterval); importPollInterval = null; }
}

// Page lifecycle: clean up all resources on page hide
window.addEventListener('pagehide', () => {
  teardownLive();
  if (importWs) { try { importWs.close(); } catch (e) {} importWs = null; }
  if (importPollInterval) { clearInterval(importPollInterval); importPollInterval = null; }
});

// Visibility change: pause SWR revalidation when tab is backgrounded
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    // Tab backgrounded — SWR will stop revalidating naturally
    // (no active timers to pause since SWR is event-driven)
  } else {
    // Tab foregrounded — revalidate stale cache
    SWR.revalidateAll();
  }
});

// ═══════════════════════════════════════════════════════════════════════════