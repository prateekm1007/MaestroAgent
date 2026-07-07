// perf-monitor.js — Web Vitals collection (non-blocking)
// Loaded after bundle, captures performance metrics
(function() {
  if (!('PerformanceObserver' in window)) return;

  // LCP
  new PerformanceObserver(function(list) {
    var entries = list.getEntries();
    var lcp = entries[entries.length - 1];
    if (lcp) {
      console.debug('[Perf] LCP:', Math.round(lcp.startTime) + 'ms');
      if (window.appStore) {
        window.appStore.set('lcp', lcp.startTime);
      }
    }
  }).observe({ type: 'largest-contentful-paint', buffered: true });

  // FID
  new PerformanceObserver(function(list) {
    list.getEntries().forEach(function(entry) {
      var fid = entry.processingStart - entry.startTime;
      console.debug('[Perf] FID:', Math.round(fid) + 'ms');
      if (window.appStore) {
        window.appStore.set('fid', fid);
      }
    });
  }).observe({ type: 'first-input', buffered: true });

  // CLS
  var clsValue = 0;
  new PerformanceObserver(function(list) {
    list.getEntries().forEach(function(entry) {
      if (!entry.hadRecentInput) clsValue += entry.value;
    });
    console.debug('[Perf] CLS:', clsValue.toFixed(3));
    if (window.appStore) {
      window.appStore.set('cls', clsValue);
    }
  }).observe({ type: 'layout-shift', buffered: true });

  // Long tasks (>50ms)
  new PerformanceObserver(function(list) {
    list.getEntries().forEach(function(entry) {
      if (entry.duration > 50) {
        console.debug('[Perf] Long task:', Math.round(entry.duration) + 'ms');
      }
    });
  }).observe({ type: 'longtask', buffered: true });
})();
