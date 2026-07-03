// app_init.js — extracted from inline scripts (CSP compliance)

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/static/sw.js').catch(() => {
        // Non-fatal — the app works without the service worker
      });
    });
  }

// Initialize Lucide icons after DOM loads
  document.addEventListener('DOMContentLoaded', function() {
    if (typeof lucide !== 'undefined') lucide.createIcons();
  });

  // Surface → Lucide icon mapping (CEO's world-class spec: every surface has an icon)
  const SURFACE_ICONS = {
    today: 'sunrise', memory: 'brain', 'ask-v2': 'help-circle', home: 'layout-dashboard',
    inbox: 'inbox', simulator: 'sliders-horizontal', hayek: 'network', flow: 'git-branch',
    physics: 'atom', debate: 'swords', customer: 'users', intents: 'arrow-down-right',
    contradictions: 'alert-octagon', predictions: 'trending-up', assumptions: 'alert-triangle',
    'eng-signals': 'radio', 'eng-oem': 'settings-2', 'eng-audit': 'scroll-text',
    'eng-settings': 'settings', canvas: 'pen-tool', personal: 'lock', work: 'briefcase',
    learn: 'graduation-cap', evolution: 'trending-up', cognition: 'cpu',
    autobiography: 'book-open', playbook: 'clipboard-list', live: 'mic',
    coordination: 'git-merge', more: 'grid-horizontal', ask: 'help-circle',
  };

  // Re-run after surface changes + inject surface icon into breadcrumb
  const _origNavTo = window.navTo;
  if (_origNavTo) {
    window.navTo = function(surface) {
      _origNavTo(surface);
      // Inject Lucide icon into the breadcrumb page title
      const bcPage = document.getElementById('bc-page');
      if (bcPage) {
        const iconName = SURFACE_ICONS[surface] || 'circle';
        // Remove any existing icon
        const existingIcon = bcPage.querySelector('.bc-surface-icon');
        if (existingIcon) existingIcon.remove();
        // Insert new icon before the text
        const iconEl = document.createElement('i');
        iconEl.setAttribute('data-lucide', iconName);
        iconEl.className = 'bc-surface-icon';
        bcPage.insertBefore(iconEl, bcPage.firstChild);
      }
      setTimeout(function() { if (typeof lucide !== 'undefined') lucide.createIcons(); }, 50);
    };
  }

// Round 78: onclick → addEventListener (CSP compliance)
document.addEventListener('DOMContentLoaded', function() {
  var el_oc_0 = document.querySelector('[data-oc="oc-0"]');
  if (el_oc_0) el_oc_0.addEventListener('click', function() { closeDrilldown() });
  var el_oc_1 = document.querySelector('[data-oc="oc-1"]');
  if (el_oc_1) el_oc_1.addEventListener('click', function() { closeDrilldown() });
  var el_oc_2 = document.querySelector('[data-oc="oc-2"]');
  if (el_oc_2) el_oc_2.addEventListener('click', function() { switchDrilldownTab('why') });
  var el_oc_3 = document.querySelector('[data-oc="oc-3"]');
  if (el_oc_3) el_oc_3.addEventListener('click', function() { switchDrilldownTab('where') });
  var el_oc_4 = document.querySelector('[data-oc="oc-4"]');
  if (el_oc_4) el_oc_4.addEventListener('click', function() { switchDrilldownTab('evidence') });
  var el_oc_5 = document.querySelector('[data-oc="oc-5"]');
  if (el_oc_5) el_oc_5.addEventListener('click', function() { switchDrilldownTab('timeline') });
  var el_oc_6 = document.querySelector('[data-oc="oc-6"]');
  if (el_oc_6) el_oc_6.addEventListener('click', function() { switchDrilldownTab('people') });
  var el_oc_7 = document.querySelector('[data-oc="oc-7"]');
  if (el_oc_7) el_oc_7.addEventListener('click', function() { switchDrilldownTab('prediction') });
  var el_oc_8 = document.querySelector('[data-oc="oc-8"]');
  if (el_oc_8) el_oc_8.addEventListener('click', function() { switchDrilldownTab('simulation') });
  var el_oc_9 = document.querySelector('[data-oc="oc-9"]');
  if (el_oc_9) el_oc_9.addEventListener('click', function() { switchDrilldownTab('recommendation') });
  var el_oc_10 = document.querySelector('[data-oc="oc-10"]');
  if (el_oc_10) el_oc_10.addEventListener('click', function() { switchDrilldownTab('perspectives') });
  var el_oc_11 = document.querySelector('[data-oc="oc-11"]');
  if (el_oc_11) el_oc_11.addEventListener('click', function() { switchDrilldownTab('sowhat') });
  var el_oc_12 = document.querySelector('[data-oc="oc-12"]');
  if (el_oc_12) el_oc_12.addEventListener('click', function() { openMoreMenu(); return false; });
  var el_oc_13 = document.querySelector('[data-oc="oc-13"]');
  if (el_oc_13) el_oc_13.addEventListener('click', function() { openCommandPalette() });
  var el_oc_14 = document.querySelector('[data-oc="oc-14"]');
  if (el_oc_14) el_oc_14.addEventListener('click', function() { toggleTheme() });
  var el_oc_15 = document.querySelector('[data-oc="oc-15"]');
  if (el_oc_15) el_oc_15.addEventListener('click', function() { toggleMobileSidebar() });
  var el_oc_16 = document.querySelector('[data-oc="oc-16"]');
  if (el_oc_16) el_oc_16.addEventListener('click', function() { runSimulator() });
  var el_oc_17 = document.querySelector('[data-oc="oc-17"]');
  if (el_oc_17) el_oc_17.addEventListener('click', function() { document.getElementById('ask-input').value='who is the bottleneck?'; submitAsk('who is the bottleneck?') });
  var el_oc_18 = document.querySelector('[data-oc="oc-18"]');
  if (el_oc_18) el_oc_18.addEventListener('click', function() { document.getElementById('ask-input').value='what laws have been discovered?'; submitAsk('what laws have been discovered?') });
  var el_oc_19 = document.querySelector('[data-oc="oc-19"]');
  if (el_oc_19) el_oc_19.addEventListener('click', function() { document.getElementById('ask-input').value='what is the P1 cluster risk?'; submitAsk('what is the P1 cluster risk?') });
  var el_oc_20 = document.querySelector('[data-oc="oc-20"]');
  if (el_oc_20) el_oc_20.addEventListener('click', function() { document.getElementById('customer-ask-input').value='Why is Initech slowing down?'; submitCustomerAsk('Why is Initech slowing down?') });
  var el_oc_21 = document.querySelector('[data-oc="oc-21"]');
  if (el_oc_21) el_oc_21.addEventListener('click', function() { document.getElementById('customer-ask-input').value='Who actually influences Globex?'; submitCustomerAsk('Who actually influences Globex?') });
  var el_oc_22 = document.querySelector('[data-oc="oc-22"]');
  if (el_oc_22) el_oc_22.addEventListener('click', function() { document.getElementById('customer-ask-input').value='Why did we lose Hooli?'; submitCustomerAsk('Why did we lose Hooli?') });
  var el_oc_23 = document.querySelector('[data-oc="oc-23"]');
  if (el_oc_23) el_oc_23.addEventListener('click', function() { document.getElementById('customer-ask-input').value='What promises have we made?'; submitCustomerAsk('What promises have we made?') });
  var el_oc_24 = document.querySelector('[data-oc="oc-24"]');
  if (el_oc_24) el_oc_24.addEventListener('click', function() { document.getElementById('customer-ask-input').value='Which engineering work unlocks the most ARR?'; submitCustomerAsk('Which engineering work unlocks the most ARR?') });
  var el_oc_25 = document.querySelector('[data-oc="oc-25"]');
  if (el_oc_25) el_oc_25.addEventListener('click', function() { setAssumptionsView('dangerous') });
  var el_oc_26 = document.querySelector('[data-oc="oc-26"]');
  if (el_oc_26) el_oc_26.addEventListener('click', function() { setAssumptionsView('accuracy') });
  var el_oc_27 = document.querySelector('[data-oc="oc-27"]');
  if (el_oc_27) el_oc_27.addEventListener('click', function() { startLiveMeeting() });
  var el_oc_28 = document.querySelector('[data-oc="oc-28"]');
  if (el_oc_28) el_oc_28.addEventListener('click', function() { analyzeTranscript() });
  var el_oc_29 = document.querySelector('[data-oc="oc-29"]');
  if (el_oc_29) el_oc_29.addEventListener('click', function() { document.getElementById('oauth-config-form').style.display='none' });
  var el_oc_30 = document.querySelector('[data-oc="oc-30"]');
  if (el_oc_30) el_oc_30.addEventListener('click', function() { saveOAuthProvider() });
  var el_oc_31 = document.querySelector('[data-oc="oc-31"]');
  if (el_oc_31) el_oc_31.addEventListener('click', function() { cancelImport() });
  var el_oc_ask_box = document.querySelector('[data-oc="oc-ask-box"]');
  if (el_oc_ask_box) el_oc_ask_box.addEventListener('click', function() { navTo('ask-v2'); });
});

// Mobile nav: wire up click handlers + sync active state with navTo
document.addEventListener('DOMContentLoaded', function() {
  var mobileNavItems = document.querySelectorAll('.mobile-nav-item');
  mobileNavItems.forEach(function(item) {
    item.addEventListener('click', function() {
      var surface = this.getAttribute('data-surface');
      if (surface && typeof navTo === 'function') navTo(surface);
    });
  });

  // Sync mobile nav active state when navTo is called
  var _origNavTo2 = window.navTo;
  if (_origNavTo2) {
    window.navTo = function(surface) {
      _origNavTo2(surface);
      mobileNavItems.forEach(function(item) {
        var itemSurface = item.getAttribute('data-surface');
        if (itemSurface === surface) {
          item.classList.add('active');
        } else {
          item.classList.remove('active');
        }
      });
    };
  }
});

