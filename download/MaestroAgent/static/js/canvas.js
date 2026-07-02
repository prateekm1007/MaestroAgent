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
        el.innerHTML = `<div class="calm-empty" style="text-align:center;padding:48px 20px;">
          <div style="font-size:18px;font-weight:800;color:var(--maestro-black,var(--text-primary));margin-bottom:8px;font-family:var(--font-sans,inherit);">No active decisions to map.</div>
          <div style="font-size:14px;color:var(--maestro-gray-mid,var(--text-muted));">Connect more signal sources and Maestro will map your decisions here.</div>
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

  let html = `<div style="max-width:800px;margin:0 auto;font-family:var(--font-sans,inherit);">`;

  // Header
  html += `
    <div style="margin-bottom:20px;">
      <div style="font-size:18px;font-weight:800;color:var(--maestro-black,var(--text-primary));">Decision Canvas</div>
      <div style="font-size:13px;color:var(--maestro-gray-mid,var(--text-muted));margin-top:4px;">${escapeHtml(humanize(assessment))}</div>
    </div>
  `;

  if (nodes.length === 0) {
    html += `<div class="calm-empty" style="text-align:center;padding:48px 20px;">
      <div style="font-size:16px;font-weight:700;color:var(--maestro-black,var(--text-primary));">This decision has no dependencies mapped yet.</div>
    </div>`;
    html += `</div>`;
    el.innerHTML = html;
    return;
  }

  // Canvas area — relative positioned for node placement
  html += `<div style="position:relative;width:100%;height:600px;background:var(--maestro-gray-light,#F9F9F9);border-radius:16px;overflow:hidden;border:1px solid var(--divider,#E5E5E5);">`;

  // Render edges first (SVG lines behind nodes)
  html += `<svg style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:1;">`;
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
    html += `<text x="${midX}" y="${midY}" fill="#999" font-size="10" font-family="var(--font-sans,inherit)" font-weight="600" text-anchor="middle">${escapeHtml(edge.label)}</text>`;
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
           style="position:absolute;left:${pos.x - size/2}px;top:${pos.y - 35}px;width:${size}px;min-height:70px;z-index:2;cursor:move;background:white;border:2px solid ${colors.bg};padding:10px 12px;">
        <div style="display:inline-block;padding:2px 8px;border-radius:999px;background:${colors.bg};color:${colors.text};font-size:9px;font-weight:800;margin-bottom:4px;text-transform:uppercase;">${escapeHtml(node.type)}</div>
        <div style="font-size:12px;font-weight:700;color:var(--maestro-black,var(--text-primary));line-height:1.3;">${escapeHtml(humanize(node.label))}</div>
        ${node.detail ? `<div style="font-size:10px;color:var(--maestro-gray-mid,var(--text-muted));margin-top:2px;line-height:1.3;">${escapeHtml(humanize(node.detail))}</div>` : ''}
        ${node.confidence != null ? `<div style="font-size:10px;font-weight:700;color:${colors.text};margin-top:4px;">${Math.round(node.confidence * 100)}%</div>` : ''}
        ${node.verified ? `<div style="font-size:9px;color:var(--maestro-success,#00C853);font-weight:700;margin-top:2px;">✓ VERIFIED</div>` : ''}
      </div>
    `;
  });

  html += `</div>`;

  // Withdrawal path note
  html += `
    <div style="margin-top:16px;padding:12px 16px;background:var(--maestro-gray-light,#F5F5F5);border-radius:8px;font-size:12px;color:var(--maestro-gray-dark,var(--text-secondary));line-height:1.5;">
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
