// Lucide icon helper — consistent iconography system
// Usage: icon('plus', 16) returns <i data-lucide="plus" data-size="16"></i>
// After rendering HTML, call lucide.createIcons() to convert <i> tags to SVGs.
function icon(name, size = 20, color = 'currentColor') {
  return '<i data-lucide="' + name + '" data-size="' + size + '" data-color="' + color + '" class="lucide-icon"></i>';
}
