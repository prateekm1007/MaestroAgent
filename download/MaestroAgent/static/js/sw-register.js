// PWA service worker registration
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js').catch(function(e) {
    console.log('SW registration failed:', e);
  });
}
