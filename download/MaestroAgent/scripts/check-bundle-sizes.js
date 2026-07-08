const fs = require('fs');
const path = require('path');

const budgets = JSON.parse(fs.readFileSync('performance-budgets.json', 'utf8'));

// Check bundle size
const bundlePath = 'static/js/bundle.min.js';
if (!fs.existsSync(bundlePath)) {
  console.error('FAIL: bundle.min.js not found. Run: node build.cjs');
  process.exit(1);
}

const bundleSize = fs.statSync(bundlePath).size;
const bundleKb = bundleSize / 1024;

// Also check separate JS files loaded
const extraJs = ['static/js/utils.js', 'static/js/state.js', 'static/js/components/card.js'];
let extraSize = 0;
extraJs.forEach(f => {
  if (fs.existsSync(f)) extraSize += fs.statSync(f).size;
});
const extraKb = extraSize / 1024;
const totalJsKb = bundleKb + extraKb;

// Check CSS
const cssFiles = ['static/css/design-system.css', 'static/css/invisible-maestro.css', 'static/css/maestro-bumble.css'];
let cssSize = 0;
cssFiles.forEach(f => {
  if (fs.existsSync(f)) cssSize += fs.statSync(f).size;
});
const cssKb = cssSize / 1024;

let passed = true;

console.log('=== Bundle Size Check ===');
console.log(`Bundle:     ${bundleKb.toFixed(1)}KB (budget: ${budgets['initial-js']['max-kb']}KB)`);
if (bundleKb > budgets['initial-js']['max-kb']) {
  console.error(`FAIL: Bundle exceeds initial-js budget`);
  passed = false;
} else {
  console.log('  ✓ Within budget');
}

console.log(`Extra JS:   ${extraKb.toFixed(1)}KB (utils + state + card)`);
console.log(`Total JS:   ${totalJsKb.toFixed(1)}KB (budget: ${budgets['total-js']['max-kb']}KB)`);
if (totalJsKb > budgets['total-js']['max-kb']) {
  console.error(`FAIL: Total JS exceeds budget`);
  passed = false;
} else {
  console.log('  ✓ Within budget');
}

console.log(`Total CSS:  ${cssKb.toFixed(1)}KB (budget: ${budgets['total-css']['max-kb']}KB)`);
if (cssKb > budgets['total-css']['max-kb']) {
  console.error(`FAIL: Total CSS exceeds budget`);
  passed = false;
} else {
  console.log('  ✓ Within budget');
}

if (passed) {
  console.log('\nPASS: All sizes within budget');
} else {
  console.log('\nFAIL: Budget exceeded');
  process.exit(1);
}
