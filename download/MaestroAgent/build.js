const esbuild = require('esbuild');
const fs = require('fs');
const path = require('path');

// Read app.html to extract script load order
const appHtml = fs.readFileSync('app.html', 'utf8');
const scriptMatches = appHtml.matchAll(/<script(?:\s+[^>]*?)?\s+src="([^"]+)"[^>]*>/g);

// Collect JS files in order, skipping vendor files and csp-shim
const jsFiles = [];
for (const match of scriptMatches) {
    const src = match[1];
    if (src.includes('csp-shim') || src.includes('vendor/')) continue;
    if (src.startsWith('/static/js/')) {
        const filePath = src.replace('/static/js/', 'static/js/');
        if (fs.existsSync(filePath)) {
            jsFiles.push(filePath);
        }
    }
}

console.log(`Bundling ${jsFiles.length} JS files...`);

// Create the entry file with correct paths
const entryPoint = 'static/js/bundle-entry.js';
let entryContent = '// Auto-generated bundle entry — do not edit\n';
entryContent += '// This file imports all JS modules in the correct load order.\n\n';
// Use path relative to the entry file location (static/js/)
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
