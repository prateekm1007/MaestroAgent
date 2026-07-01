// V8 Personal Mode — SwipeCard class.
// Bumble's signature interaction adapted for insights: swipe right to act,
// swipe left to defer. One card at a time. Bold, focused, decisive.

class SwipeCard {
  constructor(element, onSwipeRight, onSwipeLeft) {
    this.el = element;
    this.startX = 0;
    this.currentX = 0;
    this.dragging = false;
    this.onSwipeRight = onSwipeRight || (() => {});
    this.onSwipeLeft = onSwipeLeft || (() => {});
    this.threshold = 120; // px to trigger swipe
    this.bind();
  }

  bind() {
    // Touch events
    this.el.addEventListener('touchstart', (e) => this._start(e), { passive: true });
    this.el.addEventListener('touchmove', (e) => this._move(e), { passive: true });
    this.el.addEventListener('touchend', (e) => this._end(e), { passive: true });
    // Mouse events
    this.el.addEventListener('mousedown', (e) => this._start(e));
    document.addEventListener('mousemove', (e) => this._move(e));
    document.addEventListener('mouseup', (e) => this._end(e));
  }

  _start(e) {
    this.dragging = true;
    this.startX = e.touches ? e.touches[0].clientX : e.clientX;
    this.el.classList.add('swiping');
  }

  _move(e) {
    if (!this.dragging) return;
    this.currentX = (e.touches ? e.touches[0].clientX : e.clientX) - this.startX;
    this.el.style.transform = `translateX(${this.currentX}px) rotate(${this.currentX * 0.05}deg)`;
    // Show action indicators
    const rightIndicator = this.el.querySelector('.swipe-action-right');
    const leftIndicator = this.el.querySelector('.swipe-action-left');
    if (rightIndicator) {
      rightIndicator.style.opacity = Math.min(Math.max(this.currentX / 150, 0), 1);
    }
    if (leftIndicator) {
      leftIndicator.style.opacity = Math.min(Math.max(-this.currentX / 150, 0), 1);
    }
  }

  _end() {
    if (!this.dragging) return;
    this.dragging = false;
    this.el.classList.remove('swiping');

    if (this.currentX > this.threshold) {
      this.el.classList.add('swipe-right');
      setTimeout(() => this.onSwipeRight(), 300);
    } else if (this.currentX < -this.threshold) {
      this.el.classList.add('swipe-left');
      setTimeout(() => this.onSwipeLeft(), 300);
    } else {
      // Snap back
      this.el.style.transform = '';
      const rightIndicator = this.el.querySelector('.swipe-action-right');
      const leftIndicator = this.el.querySelector('.swipe-action-left');
      if (rightIndicator) rightIndicator.style.opacity = 0;
      if (leftIndicator) leftIndicator.style.opacity = 0;
    }
    this.currentX = 0;
  }
}

// Helper: create a swipe card element from data
function createSwipeCard(data) {
  const card = document.createElement('div');
  card.className = 'swipe-card';

  const categoryClass = data.category_class || 'decision';
  const rightLabel = data.right_label || 'ACT NOW';
  const leftLabel = data.left_label || 'NOT NOW';

  card.innerHTML = `
    <div class="swipe-action-right">${escapeHtml(rightLabel)}</div>
    <div class="swipe-action-left">${escapeHtml(leftLabel)}</div>
    <div class="swipe-card-body">
      <div class="swipe-card-category ${categoryClass}">${escapeHtml(data.category || 'INSIGHT')}</div>
      <div class="swipe-card-judgment">${escapeHtml(humanize(data.judgment || data.title || ''))}</div>
      ${data.evidence ? `<div class="swipe-card-evidence">${escapeHtml(humanize(data.evidence))}</div>` : ''}
      ${data.why_link ? `<a class="why-link" style="font-size:13px;color:var(--maestro-yellow-dark);cursor:pointer;font-weight:700;margin-top:auto;" onclick="${data.why_callback || ''}">Why?</a>` : ''}
    </div>
    <div class="swipe-card-hint">
      <span class="left-hint">${escapeHtml(leftLabel)}</span>
      <span class="right-hint">${escapeHtml(rightLabel)}</span>
    </div>
  `;
  return card;
}

// Helper: open an action sheet (bottom sheet) with action buttons
function openActionSheet(title, actions) {
  // Create overlay
  let overlay = document.querySelector('.action-sheet-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.className = 'action-sheet-overlay';
    document.body.appendChild(overlay);
  }

  // Create or update sheet
  let sheet = document.querySelector('.action-sheet');
  if (!sheet) {
    sheet = document.createElement('div');
    sheet.className = 'action-sheet';
    document.body.appendChild(sheet);
  }

  sheet.innerHTML = `
    <div style="font-size:18px;font-weight:800;color:var(--maestro-black);margin-bottom:var(--space-4);font-family:'Montserrat',sans-serif;">${escapeHtml(title)}</div>
    ${actions.map(a => `
      <button class="maestro-btn ${a.style || ''}" style="width:100%;margin-bottom:var(--space-3);" onclick="${a.onclick}">
        ${escapeHtml(a.label)}
      </button>
    `).join('')}
    <button class="maestro-btn maestro-btn-ghost" style="width:100%;" onclick="closeActionSheet()">Cancel</button>
  `;

  overlay.classList.add('open');
  sheet.classList.add('open');

  overlay.onclick = closeActionSheet;
}

function closeActionSheet() {
  const overlay = document.querySelector('.action-sheet-overlay');
  const sheet = document.querySelector('.action-sheet');
  if (overlay) overlay.classList.remove('open');
  if (sheet) sheet.classList.remove('open');
}
