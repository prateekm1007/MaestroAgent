const fs = require('fs');
const path = require('path');
const esbuild = require('esbuild');

const jsFiles = [
    'static/js/utils.js',
    'static/js/csp-shim.js',
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
    'static/js/sw-register.js',
    'static/js/app_init.js',
];

console.log(`Building ${jsFiles.length} JS files...`);

let combined = '// MaestroAgent frontend bundle\n\n';
jsFiles.forEach(f => {
    if (fs.existsSync(f)) {
        combined += `// === ${path.basename(f)} ===\n`;
        combined += fs.readFileSync(f, 'utf8');
        combined += '\n\n';
    }
});

fs.writeFileSync('static/js/bundle.dev.js', combined);

const originalSize = jsFiles.reduce((t, f) => t + (fs.existsSync(f) ? fs.statSync(f).size : 0), 0);

esbuild.transform(combined, {
    minify: true,
    target: ['es2020'],
}).then(result => {
    fs.writeFileSync('static/js/bundle.min.js', result.code);
    console.log(`Original:  ${(originalSize / 1024).toFixed(1)}KB across ${jsFiles.length} files`);
    console.log(`Minified:  ${(result.code.length / 1024).toFixed(1)}KB in 1 file`);
    console.log(`Reduction: ${((1 - result.code.length / originalSize) * 100).toFixed(1)}% smaller`);
}).catch(err => {
    console.error('Minify failed:', err.message);
    fs.copyFileSync('static/js/bundle.dev.js', 'static/js/bundle.min.js');
    console.log('Fallback: using unminified bundle');
});
