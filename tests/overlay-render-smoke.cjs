// Runs overlay.js against a minimal fake DOM: the companion must never stay blank.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const js = fs.readFileSync(path.resolve(__dirname, '..', 'web', 'overlay.js'), 'utf8');
const element = () => ({textContent: '', innerHTML: '', hidden: true, dataset: {}, style: {setProperty() {}, removeProperty() {}},
  classList: {toggle() {}, add() {}, remove() {}}, setAttribute() {}, scrollIntoView() {}, focus() {}});
const nodes = {};
const listeners = {};
const signedOut = () => { throw new Error('Sign in to use live controls.'); };
const document = {
  body: element(), documentElement: element(), activeElement: null,
  querySelector: selector => (nodes[selector] ??= element()),
  querySelectorAll: () => [],
  addEventListener: () => {},
};
const window = {
  addEventListener: (name, fn) => { listeners[name] = fn; },
  pywebview: {},
};
const bridgeApi = {
    preferences: async () => ({hotkey: 'TAB', accent: 'violet', opacity: 94, reduced_motion: false, size: 'wide', position: 'center'}),
    snapshot: async () => ({signed_in: false, username: '', tier: '', license: null, permissions: {}}),
    macro_profiles: async () => ({available: false, profiles: []}),
    macro_status: async () => signedOut(),
    loadouts: async () => signedOut(),
    app_theme: async () => ({accent: '#22D3EE', surface: '#0B1719', text_color: '#E8FAFB', muted_color: '#9DBDC0', glass: true}),
};
vm.runInNewContext(js, {window, document, setTimeout, clearTimeout, console, setInterval: (fn, ms) => setInterval(fn, ms).unref()});

(async () => {
  assert.match(nodes['#content'].innerHTML, /class="board"/, 'content must render before the bridge is ready');
  window.pywebview.api = bridgeApi;
  await listeners.pywebviewready();
  assert.match(nodes['#content'].innerHTML, /class="board"/, 'signed-out companion rendered a blank page');
  assert.match(nodes['#content'].innerHTML, /Sign in needed/);
  assert.equal(nodes['#toast']?.textContent ?? '', '', 'signed-out state is expected, not an error toast');
  console.log('Overlay render smoke checks passed.');
})().catch(error => { console.error(error); process.exit(1); });
