/** Keyboard + on-screen touch controls → throttle / steer. */
export class Input {
  constructor() {
    this.keys = new Set();
    this.handlers = new Map();
    this.touch = { throttle: 0, steer: 0 };
    window.addEventListener('keydown', (e) => {
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT')) return;
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'].includes(e.code)) e.preventDefault();
      if (!this.keys.has(e.code)) {
        const h = this.handlers.get(e.code);
        if (h) h(e);
      }
      this.keys.add(e.code);
    });
    window.addEventListener('keyup', (e) => this.keys.delete(e.code));
    window.addEventListener('blur', () => this.keys.clear());
  }

  on(code, fn) {
    this.handlers.set(code, fn);
  }

  read(out) {
    const k = this.keys;
    let t = 0, s = 0;
    if (k.has('KeyW') || k.has('ArrowUp')) t += 1;
    if (k.has('KeyS') || k.has('ArrowDown')) t -= 1;
    if (k.has('KeyA') || k.has('ArrowLeft')) s += 1;
    if (k.has('KeyD') || k.has('ArrowRight')) s -= 1;
    out.throttle = Math.max(-1, Math.min(1, t + this.touch.throttle));
    out.steer = Math.max(-1, Math.min(1, s + this.touch.steer));
    out.brake = k.has('Space');
    out.boost = k.has('ShiftLeft') || k.has('ShiftRight');
    return out;
  }
}
