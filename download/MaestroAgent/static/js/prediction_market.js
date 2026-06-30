// PREDICTION MARKET — calibrate individual prediction accuracy
// ═══════════════════════════════════════════════════════════════════════════
// Surface 5 of the cognitive model UI. Shows the calibration ranking
// (Brier-score-based, not hierarchy) and lets anyone submit a prediction.
//
// Calls:
//   GET  /api/oem/predictions/market/calibration   (ranked predictors)
//   GET  /api/oem/predictions/market               (list all predictions)
//   POST /api/oem/predictions/market               (submit new prediction)
//   POST /api/oem/predictions/market/{id}/resolve  (resolve with outcome)
//
// Product law: eliminates THINKING about "whose estimate should I trust?"
// by surfacing each predictor's Brier-scored calibration profile.
// ═══════════════════════════════════════════════════════════════════════════

let _predictionMarketView = 'ranking'; // 'ranking' | 'all' | 'submit'

async function loadPredictionMarket() {
  const rankingEl = document.getElementById('prediction-market-ranking');
  if (!rankingEl) return;

  // Always load the ranking first (the killer view)
  rankingEl.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Computing calibration…</div>';

  try {
    const data = await api.getOEM('/predictions/market/calibration');
    renderCalibrationRanking(rankingEl, data.predictors || []);
  } catch (e) {
    rankingEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)} <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadPredictionMarket()">Retry</button></div>`;
  }
}

function renderCalibrationRanking(container, predictors) {
  if (!predictors.length) {
    container.innerHTML = `<div class="ds-empty">
      <div style="font-size:14px;color:var(--ds-text-primary);margin-bottom:6px;">No resolved predictions yet.</div>
      <div>Once predictions are submitted and resolved, each predictor gets a Brier score. The ranking below sorts by accuracy — not hierarchy.</div>
      <button class="ds-btn ds-btn-primary" style="margin-top:16px;" onclick="setPredictionMarketView('submit')">Submit first prediction</button>
    </div>`;
    return;
  }

  const html = `
    <div class="ds-row-between" style="margin-bottom:14px;">
      <div class="ds-meta">Ranked by Brier score · lower is better · 0 = perfect · 0.25 = random</div>
      <div class="ds-row" style="gap:6px;">
        <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="setPredictionMarketView('all')">All predictions</button>
        <button class="ds-btn ds-btn-primary ds-btn-small" onclick="setPredictionMarketView('submit')">Submit prediction</button>
      </div>
    </div>
    <div class="ds-card" style="padding:0;">
      ${predictors.map((p, i) => {
        const brier = p.avg_brier_score;
        const brierClass = brier == null ? 'ds-brier-poor' :
          brier < 0.1 ? 'ds-brier-excellent' :
          brier < 0.2 ? 'ds-brier-well' :
          brier < 0.3 ? 'ds-brier-moderate' :
          'ds-brier-poor';
        const label = p.calibration_quality || 'untested';
        return `
          <div class="ds-rank-row">
            <div class="ds-rank-num">${i + 1}</div>
            <div>
              <div class="ds-rank-email">${escapeHtml(p.email)}</div>
              <div class="ds-meta">${p.resolved_predictions} resolved · ${p.total_predictions} total · ${escapeHtml(label)}</div>
            </div>
            <div class="ds-sparkline ds-sparkline-empty" title="Calibration trend will populate as predictions accumulate during the pilot"></div>
            <div class="ds-brier-badge ${brierClass}">Brier ${brier == null ? '—' : brier.toFixed(3)}</div>
          </div>
        `;
      }).join('')}
    </div>
  `;
  container.innerHTML = html;
}

function setPredictionMarketView(view) {
  _predictionMarketView = view;
  const rankingEl = document.getElementById('prediction-market-ranking');
  const allEl = document.getElementById('prediction-market-all');
  const submitEl = document.getElementById('prediction-market-submit');
  if (rankingEl) rankingEl.style.display = view === 'ranking' ? 'block' : 'none';
  if (allEl) allEl.style.display = view === 'all' ? 'block' : 'none';
  if (submitEl) submitEl.style.display = view === 'submit' ? 'block' : 'none';

  if (view === 'all' && allEl) loadAllMarketPredictions();
  if (view === 'submit' && submitEl) renderPredictionSubmitForm(submitEl);
}

async function loadAllMarketPredictions() {
  const allEl = document.getElementById('prediction-market-all');
  if (!allEl) return;
  allEl.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Loading predictions…</div>';

  try {
    const data = await api.getOEM('/predictions/market');
    renderAllMarketPredictions(allEl, data.predictions || []);
  } catch (e) {
    allEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function renderAllMarketPredictions(container, predictions) {
  if (!predictions.length) {
    container.innerHTML = `<div class="ds-empty">No predictions submitted yet. Use "Submit prediction" to add one.</div>`;
    return;
  }

  container.innerHTML = `
    <div class="ds-row-between" style="margin-bottom:14px;">
      <div class="ds-meta">${predictions.length} prediction${predictions.length === 1 ? '' : 's'}</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="setPredictionMarketView('ranking')">Back to ranking</button>
    </div>
    <div class="ds-stack">
      ${predictions.map(p => {
        const status = p.status || 'open';
        const statusClass = status === 'resolved' ? (p.actual_outcome ? 'validated' : 'rejected') : 'pending';
        return `
          <div class="ds-card" style="padding:14px 16px;">
            <div class="ds-row-between" style="margin-bottom:6px;">
              <span class="ds-tag ds-tag-${statusClass}">${escapeHtml(status)}</span>
              <span class="ds-meta">${formatTimestamp(p.made_at)}</span>
            </div>
            <div style="font-size:13.5px;color:var(--ds-text-primary);margin-bottom:6px;">${escapeHtml(p.event)}</div>
            <div class="ds-row" style="gap:14px;">
              <span class="ds-meta">predictor <span class="ds-meta-strong">${escapeHtml(p.predictor)}</span></span>
              <span class="ds-meta">prob <span class="ds-meta-strong">${(p.probability * 100).toFixed(0)}%</span></span>
              ${p.brier_score != null ? `<span class="ds-meta">brier <span class="ds-meta-strong">${p.brier_score.toFixed(3)}</span></span>` : ''}
              ${p.hypothesis_id ? `<span class="ds-meta">linked hypothesis</span>` : ''}
            </div>
            ${status === 'open' ? `
              <div class="ds-row" style="gap:6px;margin-top:10px;">
                <button class="ds-btn ds-btn-positive ds-btn-small" onclick="resolveMarketPrediction('${escapeJs(p.prediction_id)}', true)">Resolve: happened</button>
                <button class="ds-btn ds-btn-risk ds-btn-small" onclick="resolveMarketPrediction('${escapeJs(p.prediction_id)}', false)">Resolve: didn't</button>
              </div>
            ` : ''}
          </div>
        `;
      }).join('')}
    </div>
  `;
}

function renderPredictionSubmitForm(container) {
  container.innerHTML = `
    <div class="ds-card">
      <div class="ds-row-between" style="margin-bottom:14px;">
        <div style="font-size:14px;font-weight:500;color:var(--ds-text-primary);">Submit a prediction</div>
        <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="setPredictionMarketView('ranking')">Cancel</button>
      </div>
      <div class="ds-stack" style="gap:12px;">
        <div>
          <label class="ds-cascade-label" for="pm-predictor">Predictor (email)</label>
          <input id="pm-predictor" class="ask-input" style="font-size:13px;" placeholder="you@acme.com" value="ceo@acme.com">
        </div>
        <div>
          <label class="ds-cascade-label" for="pm-event">Event (what will happen?)</label>
          <input id="pm-event" class="ask-input" style="font-size:13px;" placeholder="e.g. Q4 launch ships on time">
        </div>
        <div>
          <label class="ds-cascade-label" for="pm-probability">Probability: <span id="pm-prob-val" class="ds-meta-strong">70%</span></label>
          <input id="pm-probability" type="range" min="0" max="100" value="70" style="width:100%;" oninput="document.getElementById('pm-prob-val').textContent=this.value+'%'">
        </div>
        <div>
          <label class="ds-cascade-label" for="pm-window">Resolution window (optional)</label>
          <input id="pm-window" class="ask-input" style="font-size:13px;" placeholder="e.g. Q4 2025">
        </div>
        <button class="ds-btn ds-btn-primary" onclick="submitMarketPrediction()">Submit</button>
        <div id="pm-submit-result" style="display:none;"></div>
      </div>
    </div>
  `;
}

async function submitMarketPrediction() {
  const predictor = document.getElementById('pm-predictor').value.trim();
  const event = document.getElementById('pm-event').value.trim();
  const probability = parseInt(document.getElementById('pm-probability').value, 10) / 100;
  const resolutionWindow = document.getElementById('pm-window').value.trim();
  const resultEl = document.getElementById('pm-submit-result');

  if (!predictor || !event) {
    resultEl.style.display = 'block';
    resultEl.innerHTML = `<div class="ds-error">Predictor and event are required.</div>`;
    return;
  }

  resultEl.style.display = 'block';
  resultEl.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Submitting…</div>';

  try {
    const resp = await api.postOEM('/predictions/market', {
      predictor, event, probability, resolution_window: resolutionWindow,
    });
    resultEl.innerHTML = `<div class="ds-card" style="background:rgba(34,197,94,0.05);border-color:rgba(34,197,94,0.25);">
      <div style="font-size:13px;color:var(--ds-positive);font-weight:500;margin-bottom:4px;">Prediction submitted</div>
      <div class="ds-meta">ID: ${escapeHtml(resp.prediction_id || '')}</div>
      <div class="ds-meta">Probability: ${(probability * 100).toFixed(0)}%</div>
      ${resp.prediction && resp.prediction.brier_score != null ? `<div class="ds-meta">Brier score: ${resp.prediction.brier_score.toFixed(3)}</div>` : ''}
      <button class="ds-btn ds-btn-ghost ds-btn-small" style="margin-top:8px;" onclick="setPredictionMarketView('all')">View all predictions</button>
    </div>`;
    document.getElementById('pm-event').value = '';
  } catch (e) {
    resultEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function resolveMarketPrediction(predictionId, actualOutcome) {
  try {
    await api.postOEM(`/predictions/market/${predictionId}/resolve`, { actual_outcome: actualOutcome });
    loadAllMarketPredictions();
  } catch (e) {
    showError(`Failed to resolve: ${e.message}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
