const esbuild = require('esbuild');
const fs = require('fs');
const path = require('path');

// The original 39 JS files in load order (from the pre-bundle app.html)
const jsFiles = [
    'static/js/core.js',
    'static/js/maestro.js',
    'static/js/swr_cache.js',
    'static/js/virtualization.js',
    'static/js/ambient_organizational_judgment.js',
    'static/js/home_core.js',
    'static/js/home_renderers.js',
    'static/js/ask.js',
    'static/js/physics_laws.js',
    'static/js/live_meeting.js',
    'static/js/eng_audit.js',
    'static/js/drill_down_modal.js',
    'static/js/digital_twin.js',
    'static/js/customer_judgment_engine.js',
    'static/js/prepared_decisions.js',
    'static/js/intent_cascade.js',
    'static/js/contradictions.js',
    'static/js/prediction_market.js',
    'static/js/assumptions.js',
    'static/js/humanize.js',
    'static/js/org_dot.js',
    'static/js/trajectory_panel.js',
    'static/js/today.js',
    'static/js/work.js',
    'static/js/ask_v2.js',
    'static/js/learn.js',
    'static/js/evolution.js',
    'static/js/cognition.js',
    'static/js/autobiography.js',
    'static/js/playbook.js',
    'static/js/personal.js',
    'static/js/swipe-cards.js',
    'static/js/mode-tabs.js',
    'static/js/onboarding.js',
    'static/js/canvas.js',
    'static/js/teammate.js',
    'static/js/coordination.js',
    'static/js/icons.js',
    'static/js/app_init.js',
];

console.log(`Bundling ${jsFiles.length} JS files...`);

// Create the entry file
const entryPoint = 'static/js/bundle-entry.js';
let entryContent = '// Auto-generated bundle entry — do not edit\n\n';
jsFiles.forEach(f => {
    const relPath = path.relative('static/js', f);
    entryContent += `require('./${relPath}');\n`;
});
fs.writeFileSync(entryPoint, entryContent);

// Bundle with esbuild
esbuild.build({
    entryPoints: [entryPoint],
    bundle: true,
    minify: true,
    sourcemap: true,
    outfile: 'static/js/bundle.min.js',
    allowOverwrite: true,
    target: ['es2020'],
    format: 'iife',
    logLevel: 'info',
}).then(result => {
    console.log('Bundle created: static/js/bundle.min.js');
    const originalSize = jsFiles.reduce((total, f) => total + fs.statSync(f).size, 0);
    const bundledSize = fs.statSync('static/js/bundle.min.js').size;
    console.log(`Original: ${(originalSize / 1024).toFixed(1)}KB across ${jsFiles.length} files`);
    console.log(`Bundled:  ${(bundledSize / 1024).toFixed(1)}KB in 1 file`);
    console.log(`Reduction: ${((1 - bundledSize / originalSize) * 100).toFixed(1)}% smaller`);
}).catch(() => process.exit(1));
