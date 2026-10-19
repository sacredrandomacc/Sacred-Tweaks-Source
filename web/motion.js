'use strict';
// Shared pointer effects for the main app and the companion: a cursor spotlight
// on surfaces and a press ripple on buttons. Pure decoration; never blocks input.
(() => {
  const SURFACES = '.panel,.card,.macro-card,.profile-card,.preset-choice,.btn,.button';
  const PRESSABLE = '.btn,.button,.nav button,button.nav,.macro-card,.account-button,.account';
  const still = () => {
    const b = document.body;
    return !b || b.classList.contains('no-motion') || b.classList.contains('lightweight') ||
      b.classList.contains('effects-paused') || b.dataset.reduced === 'true' ||
      matchMedia('(prefers-reduced-motion: reduce)').matches;
  };
  // Gentle 3D tilt toward the cursor for cards that invite it.
  const TILT = '.tool-card,.metric,.theme-swatch,.mech-col,.macro-card,.preview-swatch,.profile-card';
  let tilted = null;
  const untilt = () => { if (tilted) { tilted.style.removeProperty('--tilt-x'); tilted.style.removeProperty('--tilt-y'); tilted = null; } };
  let frame = 0, last = null;
  document.addEventListener('pointermove', event => {
    last = event;
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      const card = last.target.closest?.(TILT);
      if (card !== tilted) untilt();
      if (card && !still()) {
        const b = card.getBoundingClientRect(), max = card.matches('.mech-col,.preview-swatch') ? 3 : 6;
        card.classList.add('tilt');
        card.style.setProperty('--tilt-x', `${((last.clientX - b.left) / b.width - .5) * max}deg`);
        card.style.setProperty('--tilt-y', `${-((last.clientY - b.top) / b.height - .5) * max}deg`);
        tilted = card;
      }
      const surface = last.target.closest?.(SURFACES);
      if (!surface || still()) return;
      const r = surface.getBoundingClientRect();
      surface.style.setProperty('--mx', `${last.clientX - r.left}px`);
      surface.style.setProperty('--my', `${last.clientY - r.top}px`);
    });
  }, {passive: true});
  document.addEventListener('pointerleave', untilt);
  document.addEventListener('pointerdown', event => {
    const target = event.target.closest?.(PRESSABLE);
    if (!target || target.disabled || still()) return;
    const r = target.getBoundingClientRect(), size = Math.max(r.width, r.height) * 2.2;
    const ripple = document.createElement('span');
    ripple.className = 'ripple';
    ripple.setAttribute('aria-hidden', 'true');
    ripple.style.cssText = `width:${size}px;height:${size}px;left:${event.clientX - r.left - size / 2}px;top:${event.clientY - r.top - size / 2}px`;
    target.appendChild(ripple);
    ripple.addEventListener('animationend', () => ripple.remove());
    setTimeout(() => ripple.remove(), 900);
  }, {passive: true});
})();
