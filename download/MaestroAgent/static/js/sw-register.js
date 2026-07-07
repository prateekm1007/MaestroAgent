// PWA service worker registration with update detection
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    navigator.serviceWorker.register('/static/sw.js').then(function(reg) {
      // Check for updates every 60 minutes
      setInterval(function() {
        reg.update();
      }, 60 * 60 * 1000);

      // Notify on new version
      reg.addEventListener('updatefound', function() {
        var newWorker = reg.installing;
        newWorker.addEventListener('statechange', function() {
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            // New version available — show toast
            var toast = document.createElement('div');
            toast.className = 'toast info';
            toast.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9999;padding:12px 20px;border-radius:8px;background:#3b82f6;color:white;font-size:13px;cursor:pointer;';
            toast.textContent = 'New version available. Click to update.';
            toast.onclick = function() {
              newWorker.postMessage({ action: 'skipWaiting' });
              toast.remove();
            };
            document.body.appendChild(toast);
          }
        });
      });
    }).catch(function(e) {
      console.log('SW registration failed:', e);
    });

    // Reload when the new SW takes over
    var refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', function() {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });
  });
}
