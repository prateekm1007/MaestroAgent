// Round 47 — Block 1.1: Canvas — Visual Decision Mapping.
// A thinking aid: the decision node, linked laws, experts, bottlenecks,
// connected by labeled edges. Bumble-styled cards, not a complex diagram.
// Accessed via the command palette (Ctrl+K), NOT a new sidebar item.

async function loadCanvas(decisionId) {
  const el = document.getElementById('canvas-content') || document.getElementById('main-content');
  if (!el) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Mapping the decision…</div>';

  try {
    // If no decision ID, get the top recommendation
    if (!decisionId) {
      const briefing = await api.getOEM('/ceo-briefing');
      const ot = briefing.one_thing || {};
      if (ot.rec_id) {
        decisionId = ot.rec_id;
      } else {
        el.innerHTML = `<div class="calm-empty" class="auto-text-center-p4820">
          <div class="auto-fs18-fw800-text-primary-mb8">No active decisions to map.</div>
          <div class="auto-fs14-text-muted">Connect more signal sources and Maestro will map your decisions here.</div>
        </div>`;
        return;
      }
    }

    const data = await api.getOEM(`/canvas/${encodeURIComponent(decisionId)}`);
    renderCanvas(el, data);
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed to load canvas: ${escapeHtml(e.message)}</div>`;
  }
}

function renderCanvas(el, data) {
  const nodes = data.nodes || [];
  const edges = data.edges || [];
  const assessment = data.assessment || '';

  let html = `<div class="auto-mw800-m0auto">`;

  // Header
  html += `
    <div class="auto-mb20">
      <div class="auto-fs18-fw800-text-primary">Decision Canvas</div>
      <div class="auto-fs13-text-muted-mt4">${escapeHtml(humanize(assessment))}</div>
    </div>
  `;

  if (nodes.length === 0) {
    html += `<div class="calm-empty" class="auto-text-center-p4820">
      <div class="auto-fs16-fw700-text-primary">This decision has no dependencies mapped yet.</div>
    </div>`;
    html += `</div>`;
    el.innerHTML = html;
    return;
  }

  // Canvas area — relative positioned for node placement
  html += `<div class="auto-pos-relative-w-full-h600-bg-muted">`;

  // Render edges first (SVG lines behind nodes)
  html += `<svg class="auto-pos-absolute-u-e89d-u-27fc-w-full">`;
  edges.forEach(edge => {
    const fromNode = nodes.find(n => n.id === edge.from);
    const toNode = nodes.find(n => n.id === edge.to);
    if (!fromNode || !toNode) return;
    const x1 = fromNode.position.x;
    const y1 = fromNode.position.y;
    const x2 = toNode.position.x;
    const y2 = toNode.position.y;
    html += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#D0D0D0" stroke-width="2" stroke-dasharray="4,4" />`;
    // Edge label
    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;
    html += `<text x="${midX}" y="${midY}" fill="#999" font-size="10" font-family="Montserrat,sans-serif" font-weight="600" text-anchor="middle">${escapeHtml(edge.label)}</text>`;
  });
  html += `</svg>`;

  // Render nodes — Bumble-styled cards
  nodes.forEach(node => {
    const pos = node.position || { x: 100, y: 100 };
    const typeColors = {
      decision: { bg: 'var(--maestro-yellow,#FFC629)', text: 'var(--maestro-black,#1A1A1A)' },
      law: { bg: 'var(--maestro-yellow-light,#FFF4D1)', text: 'var(--maestro-yellow-dark,#F0B500)' },
      expert: { bg: 'rgba(0,200,83,0.1)', text: 'var(--maestro-success,#00C853)' },
      bottleneck: { bg: 'rgba(255,152,0,0.15)', text: 'var(--maestro-warning,#FF9800)' },
    };
    const colors = typeColors[node.type] || typeColors.law;
    const size = node.type === 'decision' ? 180 : 140;

    html += `
      <div class="maestro-card canvas-node" data-node-id="${escapeHtml(node.id)}"
           class="auto-pos-absolute-u-1abd-u-02bd-wsize">
        <div class="auto-inline-block-p28-rad999-bg-c178">${escapeHtml(node.type)}</div>
        <div class="auto-fs12-fw700-text-primary-lh13">${escapeHtml(humanize(node.label))}</div>
        ${node.detail ? `<div class="auto-fs10-text-muted-mt2-lh13">${escapeHtml(humanize(node.detail))}</div>` : ''}
        ${node.confidence != null ? `<div class="auto-fs10-fw700-clr-c159-mt4">${Math.round(node.confidence * 100)}%</div>` : ''}
        ${node.verified ? `<div class="auto-fs9-text-positive-fw700-mt2">✓ VERIFIED</div>` : ''}
      </div>
    `;
  });

  html += `</div>`;

  // Withdrawal path note
  html += `
    <div class="auto-mt16-p1216-bg-muted-rad8">
      <strong>Withdrawal path:</strong> You can map decisions on a whiteboard. This canvas saves time; without it, you are slower but functional.
    </div>
  `;

  html += `</div>`;
  el.innerHTML = html;

  // Make nodes draggable
  _initCanvasDrag();
}

// Round 69 RESIDUAL-7: Central drag manager — single listener pair, not per-node.
// Old code added 2 document listeners per node per render — memory leak.
let _canvasDragState = null;

function _initCanvasDrag() {
  // Remove old listeners if they exist (prevents accumulation on re-render)
  _destroyCanvasDrag();

  _canvasDragState = { dragging: null, startX: 0, startY: 0, startLeft: 0, startTop: 0 };

  _canvasDragState.onMouseMove = (e) => {
    if (!_canvasDragState || !_canvasDragState.dragging) return;
    const dx = e.clientX - _canvasDragState.startX;
    const dy = e.clientY - _canvasDragState.startY;
    _canvasDragState.dragging.style.left = (_canvasDragState.startLeft + dx) + 'px';
    _canvasDragState.dragging.style.top = (_canvasDragState.startTop + dy) + 'px';
  };

  _canvasDragState.onMouseUp = () => {
    if (_canvasDragState && _canvasDragState.dragging) {
      _canvasDragState.dragging.style.cursor = 'move';
      _canvasDragState.dragging = null;
    }
  };

  document.addEventListener('mousemove', _canvasDragState.onMouseMove);
  document.addEventListener('mouseup', _canvasDragState.onMouseUp);

  // Per-node: only mousedown (not document listeners)
  document.querySelectorAll('.canvas-node').forEach(node => {
    node.addEventListener('mousedown', (e) => {
      if (!_canvasDragState) return;
      _canvasDragState.dragging = node;
      _canvasDragState.startX = e.clientX;
      _canvasDragState.startY = e.clientY;
      _canvasDragState.startLeft = parseInt(node.style.left);
      _canvasDragState.startTop = parseInt(node.style.top);
      node.style.cursor = 'grabbing';
      e.preventDefault();
    });
  });
}

function _destroyCanvasDrag() {
  if (_canvasDragState) {
    document.removeEventListener('mousemove', _canvasDragState.onMouseMove);
    document.removeEventListener('mouseup', _canvasDragState.onMouseUp);
    _canvasDragState = null;
  }
}
