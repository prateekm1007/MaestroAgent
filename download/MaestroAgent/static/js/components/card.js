// card.js — reusable card components. Used by 15+ surfaces.
// Each component is a PURE FUNCTION: (data) => HTML string.
// No DOM access. No side effects. Testable in isolation.
// Depends on: escapeHtml, humanize (from utils.js + humanize.js)

function RecommendationCard(r, opts) {
  opts = opts || {};
  var urgencyTag = r.urgency === 'urgent' ? 'tag-rose' : r.urgency === 'normal' ? 'tag-amber' : 'tag-gray';
  var compact = opts.compact;
  var title = escapeHtml(humanize ? humanize(r.title || '') : (r.title || ''));
  var desc = escapeHtml(humanize ? humanize(r.description || '') : (r.description || ''));
  
  return '<div class="card ' + (r.urgency === 'urgent' ? 'urgent' : '') + ' mb-3"' +
    ' data-action="openDrilldown" data-type="recommendation" data-id="' + escapeHtml(r.title || '') + '">' +
    '<div class="flex items-start justify-between mb-2">' +
      '<div class="flex-1">' +
        '<div class="text-sm font-semibold">' + title + '</div>' +
        (compact ? '' : '<div class="text-[11px] text-fg-400 mt-1">' + desc + '</div>') +
      '</div>' +
      '<span class="tag ' + urgencyTag + '">' + escapeHtml(r.urgency || 'normal') + '</span>' +
    '</div>' +
    '<div class="flex items-center gap-3 text-[10px] text-fg-500 mt-2">' +
      '<span>' + (r.evidence_count || 0) + ' signals</span>' +
      (r.linked_laws && r.linked_laws.length ? '<span>· ' + r.linked_laws.length + ' patterns</span>' : '') +
    '</div>' +
  '</div>';
}

function MetricTile(label, value, drilldownId) {
  return '<div class="metric metric-clickable"' +
    ' data-action="openDrilldown" data-type="metric" data-id="' + escapeHtml(drilldownId || '') + '">' +
    '<div class="metric-value">' + escapeHtml(String(value)) + '</div>' +
    '<div class="metric-label">' + escapeHtml(label) + '</div>' +
  '</div>';
}

function ErrorState(message, retryAction) {
  return '<div class="error-state" role="alert">' +
    '<span class="text-brand-rose">' + escapeHtml(message) + '</span>' +
    (retryAction ? '<button class="btn btn-ghost text-xs ml-2" data-action="' + escapeHtml(retryAction) + '">Retry</button>' : '') +
  '</div>';
}

function LoadingState(text) {
  return '<div class="loading-state"><span class="spinner"></span> ' + escapeHtml(text || 'Loading…') + '</div>';
}

function EmptyState(text, icon) {
  return '<div class="empty-state">' +
    '<span class="fs-24">' + (icon || '📭') + '</span>' +
    '<div class="text-sm text-fg-500 mt-2">' + escapeHtml(text || 'No data') + '</div>' +
  '</div>';
}

function LawCard(law) {
  var conf = formatConfidence(law.confidence);
  var status = law.status || 'validated';
  var statusTag = status === 'validated' ? 'tag-green' : status === 'draft' ? 'tag-amber' : 'tag-gray';
  return '<div class="card mb-2" data-action="openDrilldown" data-type="law" data-id="' + escapeHtml(law.code || '') + '">' +
    '<div class="flex items-start justify-between mb-1">' +
      '<div class="text-sm font-semibold">' + escapeHtml(law.statement || law.code || '') + '</div>' +
      '<span class="tag ' + statusTag + '">' + escapeHtml(status) + '</span>' +
    '</div>' +
    '<div class="flex items-center gap-3 text-[10px] text-fg-500 mt-1">' +
      '<span>conf: ' + conf + '</span>' +
      '<span>' + (law.evidence_count || 0) + ' evidence</span>' +
      '<span>' + (law.validated_runtimes || 0) + ' runtimes</span>' +
    '</div>' +
  '</div>';
}

function WhisperCard(w) {
  var priority = w.priority || 'normal';
  var priorityTag = priority === 'urgent' ? 'tag-rose' : priority === 'high' ? 'tag-amber' : 'tag-gray';
  return '<div class="card mb-3">' +
    '<div class="flex items-start justify-between mb-2">' +
      '<div class="flex-1">' +
        '<div class="text-sm font-semibold">' + escapeHtml(w.insight || w.title || '') + '</div>' +
        (w.situation ? '<div class="text-[11px] text-fg-400 mt-1">' + escapeHtml(w.situation) + '</div>' : '') +
      '</div>' +
      '<span class="tag ' + priorityTag + '">' + escapeHtml(priority) + '</span>' +
    '</div>' +
    (w.evidence && w.evidence.length ?
      '<div class="text-[10px] text-fg-500 mt-2">' + w.evidence.length + ' evidence signals</div>' : '') +
    (w.action ? '<div class="text-xs text-brand-blue mt-2">' + escapeHtml(w.action) + '</div>' : '') +
  '</div>';
}
