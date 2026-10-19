'use strict';
// Ambient background particles + click bursts on one full-window canvas.
// Paused while hidden, minimized, in Fortnite (body.effects-paused), lightweight,
// reduced motion, or when the style is "none".
(() => {
  const STYLES = {
    none: 'None', stardust: 'Stardust', fireflies: 'Fireflies', snow: 'Snowfall', embers: 'Embers',
    bubbles: 'Bubbles', constellation: 'Constellation', sakura: 'Sakura petals', rain: 'Neon rain', bats: 'Bats',
    waves: 'Wallpaper: Gradient waves', starfield: 'Wallpaper: Warp starfield', aurora: 'Wallpaper: Aurora curtains', grid: 'Wallpaper: Synth grid'
  };
  const canvas = document.createElement('canvas');
  canvas.className = 'particle-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  const ctx = canvas.getContext('2d');
  let style = 'none', density = 50, items = [], sparks = [], frame = 0, last = 0, w = 0, h = 0, dpr = 1;
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#9A82F7';
  const still = () => {
    const b = document.body;
    return document.hidden || b.classList.contains('lightweight') || b.classList.contains('no-motion') ||
      b.classList.contains('effects-paused') || b.dataset.reduced === 'true' || matchMedia('(prefers-reduced-motion: reduce)').matches;
  };
  const rand = (a, b) => a + Math.random() * (b - a);
  function spawn(initial) {
    const p = {x: rand(0, w), y: initial ? rand(0, h) : -20, r: rand(1, 2.6), vx: rand(-.15, .15), vy: rand(.1, .5), a: rand(.3, .9), t: rand(0, 6.28), s: rand(.6, 1.4)};
    if (style === 'embers' || style === 'bubbles') { p.y = initial ? rand(0, h) : h + 20; p.vy = -rand(.25, .9); }
    if (style === 'bubbles') p.r = rand(4, 14);
    if (style === 'snow') { p.r = rand(1.2, 3.6); p.vy = rand(.3, 1.1); }
    if (style === 'sakura') { p.r = rand(4, 8); p.vy = rand(.4, 1); p.vx = rand(.2, .7); }
    if (style === 'rain') { p.r = rand(8, 22); p.vy = rand(4, 9); p.vx = 0; }
    if (style === 'bats') { p.r = rand(7, 14); p.y = initial ? rand(0, h * .7) : rand(0, h * .6); p.x = initial ? rand(0, w) : -30; p.vx = rand(.6, 1.6); p.vy = 0; }
    if (style === 'fireflies' || style === 'constellation' || style === 'stardust') { p.vx = rand(-.25, .25); p.vy = rand(-.25, .25); }
    if (style === 'starfield') { p.x = rand(-1, 1); p.y = rand(-1, 1); p.z = initial ? rand(.05, 1) : 1; }
    return p;
  }
  const WALLPAPERS = new Set(['waves', 'aurora', 'grid']);
  function count() { if (WALLPAPERS.has(style)) return 0; if (style === 'starfield') return Math.round(220 * density / 50); return style === 'none' ? 0 : Math.round((w * h) / 26000 * (density / 50) * (style === 'bubbles' || style === 'bats' ? .35 : style === 'constellation' ? .8 : 1)); }
  function resize() {
    dpr = Math.min(2, window.devicePixelRatio || 1); w = innerWidth; h = innerHeight;
    canvas.width = w * dpr; canvas.height = h * dpr; canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = count(); items = Array.from({length: n}, () => spawn(true));
  }
  function bat(p, color) {
    const flap = Math.sin(p.t * 8) * .5 + .5, s = p.r;
    ctx.fillStyle = color; ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    ctx.quadraticCurveTo(p.x - s * .6, p.y - s * (.3 + flap * .6), p.x - s * 1.4, p.y - s * .1);
    ctx.quadraticCurveTo(p.x - s * .8, p.y + s * .1, p.x - s * .5, p.y + s * .35);
    ctx.quadraticCurveTo(p.x, p.y + s * .15, p.x + s * .5, p.y + s * .35);
    ctx.quadraticCurveTo(p.x + s * .8, p.y + s * .1, p.x + s * 1.4, p.y - s * .1);
    ctx.quadraticCurveTo(p.x + s * .6, p.y - s * (.3 + flap * .6), p.x, p.y);
    ctx.fill();
  }
  function draw(now) {
    frame = requestAnimationFrame(draw);
    if (now - last < 15) return; // ~60 fps ceiling
    const dt = Math.min(3, (now - last) / 16.7); last = now;
    ctx.clearRect(0, 0, w, h);
    const accent = css('--accent'), accent2 = css('--accent-2'), text = css('--text') || css('--ink');
    const px = parseFloat(css('--parallax-x')) || 0, py = parseFloat(css('--parallax-y')) || 0;
    if (!still() && WALLPAPERS.has(style)) wallpaper(now / 1000, accent, accent2);
    if (!still() && style === 'starfield') {
      const cx = w / 2 + px * 4, cy = h / 2 + py * 4;
      for (const p of items) {
        const pz = p.z; p.z -= .006 * dt * (density / 50 + .5);
        if (p.z <= .02) { Object.assign(p, spawn(false)); continue; }
        const sx = cx + p.x / p.z * w * .5, sy = cy + p.y / p.z * h * .5, ox = cx + p.x / pz * w * .5, oy = cy + p.y / pz * h * .5;
        ctx.globalAlpha = Math.min(1, (1 - p.z) * 1.4); ctx.strokeStyle = p.s > 1 ? accent2 : text; ctx.lineWidth = (1 - p.z) * 2.2;
        ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(sx, sy); ctx.stroke();
      }
    }
    if (!still() && style !== 'none' && style !== 'starfield' && !WALLPAPERS.has(style)) {
      for (const p of items) {
        p.t += .016 * dt; p.x += (p.vx + (style === 'snow' || style === 'sakura' ? Math.sin(p.t) * .3 : 0)) * dt; p.y += p.vy * dt;
        if (style === 'fireflies') { p.vx += rand(-.02, .02); p.vy += rand(-.02, .02); p.vx *= .99; p.vy *= .99; }
        if (p.y > h + 30 || p.y < -40 || p.x > w + 40 || p.x < -40) {
          if (style === 'fireflies' || style === 'constellation' || style === 'stardust') { p.x = (p.x + w) % w; p.y = (p.y + h) % h; }
          else Object.assign(p, spawn(false));
        }
        const x = p.x + px * p.s * 1.5, y = p.y + py * p.s * 1.5;
        ctx.globalAlpha = p.a * (style === 'fireflies' || style === 'stardust' ? .55 + .45 * Math.sin(p.t * 3) : 1);
        if (style === 'bats') bat({...p, x, y}, '#0b0710'), ctx.globalAlpha = .25, bat({...p, x: x + 1, y: y + 1}, accent2);
        else if (style === 'rain') { ctx.strokeStyle = accent; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + p.r); ctx.stroke(); }
        else if (style === 'bubbles') { ctx.strokeStyle = accent2; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(x, y, p.r, 0, 6.28); ctx.stroke(); }
        else if (style === 'sakura') { ctx.fillStyle = '#F9A8D4'; ctx.save(); ctx.translate(x, y); ctx.rotate(p.t * 2); ctx.beginPath(); ctx.ellipse(0, 0, p.r, p.r * .55, 0, 0, 6.28); ctx.fill(); ctx.restore(); }
        else {
          ctx.fillStyle = style === 'snow' ? text : style === 'embers' ? (p.s > 1 ? '#FFB347' : accent) : (p.s > 1 ? accent2 : accent);
          if (style === 'fireflies' || style === 'embers') { ctx.shadowBlur = 12; ctx.shadowColor = ctx.fillStyle; }
          ctx.beginPath(); ctx.arc(x, y, p.r, 0, 6.28); ctx.fill(); ctx.shadowBlur = 0;
        }
      }
      if (style === 'constellation') {
        ctx.strokeStyle = accent; ctx.lineWidth = .6;
        for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) { // ponytail: O(n²), n stays under ~120
          const a = items[i], b = items[j], d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < 130) { ctx.globalAlpha = (1 - d / 130) * .35; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
        }
      }
    }
    for (const s of sparks) {
      s.x += s.vx * dt; s.y += s.vy * dt; s.vy += .12 * dt; s.life -= .03 * dt;
      ctx.globalAlpha = Math.max(0, s.life); ctx.fillStyle = s.c; ctx.shadowBlur = 8; ctx.shadowColor = s.c;
      ctx.beginPath(); ctx.arc(s.x, s.y, s.r * s.life + .3, 0, 6.28); ctx.fill(); ctx.shadowBlur = 0;
    }
    sparks = sparks.filter(s => s.life > 0);
    ctx.globalAlpha = 1;
    if (style === 'none' && !sparks.length) { cancelAnimationFrame(frame); frame = 0; ctx.clearRect(0, 0, w, h); }
  }
  function wallpaper(t, accent, accent2) {
    if (style === 'waves') {
      for (let k = 0; k < 4; k++) {
        const g = ctx.createLinearGradient(0, 0, w, 0);
        g.addColorStop(0, accent); g.addColorStop(1, accent2);
        ctx.globalAlpha = .07 + k * .025; ctx.fillStyle = g; ctx.beginPath(); ctx.moveTo(0, h);
        for (let x = 0; x <= w; x += 16) ctx.lineTo(x, h * (.55 + k * .09) + Math.sin(x / (180 + k * 60) + t * (.4 + k * .15)) * (40 + k * 12));
        ctx.lineTo(w, h); ctx.fill();
      }
    } else if (style === 'aurora') {
      ctx.globalCompositeOperation = 'lighter';
      for (let k = 0; k < 3; k++) {
        const x = w * (.25 + .25 * k) + Math.sin(t * .2 + k * 2) * w * .15, y = h * (.25 + .1 * Math.sin(t * .3 + k));
        const g = ctx.createRadialGradient(x, y, 0, x, y, w * .45);
        g.addColorStop(0, k % 2 ? accent2 : accent); g.addColorStop(1, 'transparent');
        ctx.globalAlpha = .1 * (density / 50); ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
      }
      ctx.globalCompositeOperation = 'source-over';
    } else if (style === 'grid') {
      const horizon = h * .55, speed = (t * 40 * (density / 50 + .4)) % 40;
      ctx.strokeStyle = accent; ctx.lineWidth = 1;
      for (let i = 0; i < 24; i++) {
        const y = horizon + Math.pow((i * 40 + speed) / 960, 2) * (h - horizon);
        ctx.globalAlpha = .08 + .3 * (y - horizon) / (h - horizon); ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
      }
      for (let i = -12; i <= 12; i++) { ctx.globalAlpha = .18; ctx.beginPath(); ctx.moveTo(w / 2 + i * 30, horizon); ctx.lineTo(w / 2 + i * 160, h); ctx.stroke(); }
      const sun = ctx.createRadialGradient(w / 2, horizon, 0, w / 2, horizon, h * .35);
      sun.addColorStop(0, accent2); sun.addColorStop(1, 'transparent');
      ctx.globalAlpha = .18; ctx.fillStyle = sun; ctx.fillRect(0, 0, w, horizon);
    }
    ctx.globalAlpha = 1;
  }
  const start = () => { if (!frame) { last = performance.now(); frame = requestAnimationFrame(draw); } };
  const api = window.SacredParticles = {
    styles: STYLES,
    set(next = {}) {
      style = STYLES[next.style] ? next.style : 'none';
      density = Math.max(10, Math.min(100, Number(next.density) || 50));
      if (!canvas.isConnected && document.body) document.body.prepend(canvas);
      resize(); start();
    },
    burst(x, y) {
      if (still()) return;
      const colors = [css('--accent'), css('--accent-2'), '#ffffff'];
      for (let i = 0; i < 14; i++) {
        const angle = rand(0, 6.28), speed = rand(1.2, 4);
        sparks.push({x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed - 1, r: rand(1.2, 2.6), life: 1, c: colors[i % 3]});
      }
      if (!canvas.isConnected && document.body) { document.body.prepend(canvas); resize(); }
      start();
    }
  };
  addEventListener('resize', () => { if (canvas.isConnected) resize(); });
  document.addEventListener('pointerdown', event => {
    if (event.target.closest?.('button,.theme-swatch,.mech-switch,.switch,.macro-card')) api.burst(event.clientX, event.clientY);
  }, {passive: true});
})();
