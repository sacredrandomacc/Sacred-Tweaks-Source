'use strict';
// Interface sounds synthesized with Web Audio: no audio files, nothing loaded
// from disk or network. Quiet by design; window.SacredSound.enabled turns them off.
(() => {
  let ctx = null, master = null, lastTick = 0;
  const audio = () => {
    if (!ctx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return null;
      ctx = new Ctx();
      master = ctx.createGain();
      master.gain.value = .32;
      master.connect(ctx.destination);
    }
    if (ctx.state === 'suspended') ctx.resume().catch(() => {});
    return ctx;
  };
  // One short voice: oscillator sweep through a soft envelope.
  function voice(type, from, to, duration, gain, delay = 0) {
    const t = ctx.currentTime + delay, osc = ctx.createOscillator(), amp = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(from, t);
    osc.frequency.exponentialRampToValueAtTime(to, t + duration);
    amp.gain.setValueAtTime(0, t);
    amp.gain.linearRampToValueAtTime(gain, t + .006);
    amp.gain.exponentialRampToValueAtTime(.0001, t + duration);
    osc.connect(amp).connect(master);
    osc.start(t);
    osc.stop(t + duration + .02);
  }
  function noise(duration, gain, freq) {
    const t = ctx.currentTime, buffer = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * duration), ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / data.length);
    const src = ctx.createBufferSource(), filter = ctx.createBiquadFilter(), amp = ctx.createGain();
    src.buffer = buffer;
    filter.type = 'bandpass';
    filter.frequency.setValueAtTime(freq, t);
    filter.frequency.exponentialRampToValueAtTime(freq * 3, t + duration);
    amp.gain.value = gain;
    src.connect(filter).connect(amp).connect(master);
    src.start(t);
  }
  // Each pack reshapes the same cues: soft (default), mechanical keyboard, sci-fi.
  const packs = {
    mechanical: {
      tap: () => { noise(.035, .28, 2600); voice('square', 190, 120, .03, .05); },
      tick: () => noise(.015, .08, 4200),
      on: () => { noise(.03, .25, 2200); noise(.03, .2, 3000); },
      off: () => { noise(.04, .22, 1500); },
      select: () => { noise(.03, .25, 3200); }
    },
    scifi: {
      tap: () => { voice('sine', 1400, 2200, .06, .12); voice('triangle', 700, 1400, .08, .06); },
      tick: () => voice('sine', 3200, 3600, .02, .03),
      on: () => { voice('sawtooth', 300, 1200, .14, .05); voice('sine', 900, 1800, .16, .12, .04); },
      off: () => { voice('sawtooth', 1200, 300, .14, .05); voice('sine', 1000, 400, .14, .1); },
      open: () => { voice('sine', 200, 1600, .35, .1); noise(.3, .06, 1200); },
      select: () => voice('sine', 1800, 2600, .07, .12)
    }
  };
  const sounds = {
    tap: () => { voice('sine', 820, 520, .07, .22); voice('triangle', 1640, 1200, .03, .05); },
    tick: () => voice('sine', 2400, 2000, .025, .035),
    on: () => { voice('sine', 520, 880, .09, .2); voice('sine', 880, 1320, .12, .14, .06); },
    off: () => { voice('sine', 760, 420, .1, .18); voice('sine', 420, 300, .09, .08, .05); },
    open: () => { noise(.28, .12, 600); voice('sine', 330, 660, .3, .12); voice('sine', 660, 990, .25, .07, .08); },
    close: () => { noise(.18, .08, 900); voice('sine', 600, 300, .18, .1); },
    success: () => { [660, 830, 990].forEach((f, i) => voice('sine', f, f * 1.01, .18, .13, i * .07)); },
    error: () => { voice('square', 220, 160, .14, .06); voice('square', 196, 140, .16, .05, .1); },
    select: () => { voice('triangle', 990, 1480, .08, .14); }
  };
  const api = window.SacredSound = {
    enabled: true, pack: 'soft',
    set volume(v) { api._volume = Math.max(0, Math.min(1, v)); if (master) master.gain.value = .45 * api._volume; },
    _volume: .7,
    _custom: {},
    async setCustom(name, dataUrl) {
      if (!dataUrl) { delete api._custom[name]; return; }
      try {
        const bytes = Uint8Array.from(atob(dataUrl.split(',')[1]), c => c.charCodeAt(0)).buffer;
        const ctx = audio();
        if (ctx) api._custom[name] = await ctx.decodeAudioData(bytes);
      } catch (_) { delete api._custom[name]; }
    },
    play(name) {
      if (api._custom[name] && api.enabled && api._volume > 0 && audio()) {
        const src = ctx.createBufferSource(); src.buffer = api._custom[name]; src.connect(master); master.gain.value = .45 * api._volume; src.start(); return;
      }
      const cue = packs[api.pack]?.[name] || sounds[name];
      if (!api.enabled || !cue || api._volume <= 0) return;
      try { if (audio()) { master.gain.value = .45 * api._volume; cue(); } } catch (_) { /* audio is optional */ }
    }
  };
  // Delegated cues so every page gets them without per-button wiring.
  document.addEventListener('pointerdown', event => {
    const target = event.target.closest?.('button,.theme-swatch,.choice');
    if (!target || target.disabled) return;
    if (target.classList.contains('danger') || target.dataset.action === 'stop-macros' || target.dataset.action === 'emergency-stop') api.play('off');
    else api.play(target.matches('.theme-swatch,.choice') ? 'select' : 'tap');
  }, {passive: true});
  document.addEventListener('change', event => {
    if (event.target.matches?.('input[type=checkbox]')) api.play(event.target.checked ? 'on' : 'off');
  });
  document.addEventListener('pointerover', event => {
    const target = event.target.closest?.('.nav button,button.nav,.mech-row,.theme-swatch,.macro-card');
    if (!target || target.contains(event.relatedTarget)) return;
    const now = performance.now();
    if (now - lastTick > 70) { lastTick = now; api.play('tick'); }
  }, {passive: true});
})();
