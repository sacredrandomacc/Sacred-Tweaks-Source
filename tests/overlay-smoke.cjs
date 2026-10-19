const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..', 'web');
const html = fs.readFileSync(path.join(root, 'overlay.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'overlay.js'), 'utf8');
new vm.Script(js, {filename: 'overlay.js'});

for (const page of ['home', 'macros', 'windows', 'appearance']) {
  assert.match(html, new RegExp(`data-page="${page}"`), `${page} page is missing`);
}
for (const page of ['performance', 'measurements', 'backups']) {
  assert.doesNotMatch(html, new RegExp(`data-page="${page}"`));
  assert.doesNotMatch(js, new RegExp(`const ${page}\\s*=`));
}
assert.match(js, /macro_profiles/);
assert.match(js, /Open Macro Studio/);
assert.match(js, /save_macro_profile/);
assert.match(js, /View & edit/);
assert.match(html, /id="reset-layout"/);
assert.match(js, /size:'wide',position:'center'/);
assert.doesNotMatch(js, /<select id="size">/);
assert.doesNotMatch(js, /preview_performance|macro_configure|macro_enable/);
console.log('Overlay source smoke checks passed.');
