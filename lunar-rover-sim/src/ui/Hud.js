import { MACRO_MIN, MACRO_SIZE } from '../terrain/constants.js';

const $ = (id) => document.getElementById(id);
const deg = (r) => (r * 180) / Math.PI;

export class Hud {
  constructor({ data, physics, rig, sunState }) {
    this.data = data;
    this.physics = physics;
    this.rig = rig;
    this.sunState = sunState;
    this.el = {
      speed: $('h-speed'), heading: $('h-heading'), pitch: $('h-pitch'), roll: $('h-roll'),
      odo: $('h-odo'), alt: $('h-alt'), sun: $('h-sun'), status: $('h-status'),
      warning: $('warning'), camMode: $('cam-mode'), fps: $('fps'), hint: $('hint'),
    };
    this.minimap = $('minimap');
    this.mctx = this.minimap.getContext('2d');
    this._buildHillshade();
    this._t = 0;
    this._hintHidden = false;
    this._modeTimer = null;

    for (const btn of document.querySelectorAll('[data-close]')) {
      btn.onclick = () => $(btn.dataset.close).classList.add('hidden');
    }
    $('b-gfx').onclick = () => this.toggle('settings');
    $('b-help').onclick = () => this.toggle('help');
  }

  toggle(id) {
    const other = id === 'settings' ? 'help' : 'settings';
    $(other).classList.add('hidden');
    $(id).classList.toggle('hidden');
  }

  flashMode(text) {
    const e = this.el.camMode;
    e.textContent = text;
    e.style.opacity = '1';
    clearTimeout(this._modeTimer);
    this._modeTimer = setTimeout(() => { e.style.opacity = '0'; }, 2200);
  }

  setFps(fps, tstats, rocks) {
    this.el.fps.textContent = `${fps.toFixed(0)} FPS · рельеф ${tstats.nodes} · камни ${rocks}`;
  }

  // hillshade of the drivable area for the minimap
  _buildHillshade() {
    const d = this.data;
    const N = 1024;
    const c = document.createElement('canvas');
    c.width = c.height = N;
    const ctx = c.getContext('2d');
    const img = ctx.createImageData(N, N);
    const res = d.macroRes;
    const step = res / N;
    const H = d.macroH;
    const at = (x, y) => H[Math.min(res - 1, Math.max(0, Math.round(y))) * res + Math.min(res - 1, Math.max(0, Math.round(x)))];
    const lx = -0.6, ly = -0.55, lz = 0.58;
    for (let y = 0; y < N; y++) {
      for (let x = 0; x < N; x++) {
        const sx = x * step, sy = y * step;
        const gx = (at(sx + step, sy) - at(sx - step, sy)) / (2 * step * d.macroTexel);
        const gy = (at(sx, sy + step) - at(sx, sy - step)) / (2 * step * d.macroTexel);
        const nx = -gx, ny = -gy, nz = 1;
        const l = Math.max(0, (nx * lx + ny * ly + nz * lz) / Math.hypot(nx, ny, nz));
        const v = Math.round(40 + l * 170);
        const i = (y * N + x) * 4;
        img.data[i] = v; img.data[i + 1] = v * 0.97; img.data[i + 2] = v * 0.92; img.data[i + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    this.hill = c;
    this.hillScale = N / MACRO_SIZE;
  }

  _drawMinimap() {
    const ctx = this.mctx;
    const W = this.minimap.width;
    const p = this.physics;
    const span = 700; // metres across
    const px = (p.pos.x - MACRO_MIN) * this.hillScale, pz = (p.pos.z - MACRO_MIN) * this.hillScale;
    const s = span * this.hillScale;
    ctx.save();
    ctx.clearRect(0, 0, W, W);
    ctx.beginPath();
    ctx.arc(W / 2, W / 2, W / 2, 0, Math.PI * 2);
    ctx.clip();
    ctx.translate(W / 2, W / 2);
    // heading up: rotate so that the rover points to the top
    ctx.rotate(Math.PI + p.yaw);
    ctx.drawImage(this.hill, px - s / 2, pz - s / 2, s, s, -W / 2, -W / 2, W, W);
    ctx.restore();
    // rover marker
    ctx.save();
    ctx.translate(W / 2, W / 2);
    ctx.fillStyle = '#f2b45a';
    ctx.beginPath();
    ctx.moveTo(0, -9); ctx.lineTo(6, 7); ctx.lineTo(0, 3); ctx.lineTo(-6, 7);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
    // north indicator
    ctx.fillStyle = 'rgba(255,255,255,.7)';
    ctx.font = '600 11px system-ui';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('N', W / 2 - Math.sin(p.yaw) * (W / 2 - 12), W / 2 + Math.cos(p.yaw) * (W / 2 - 12));
  }

  update(dt, now) {
    const p = this.physics;
    this._t += dt;
    if (this._t < 0.1) return;
    this._t = 0;
    const e = this.el;
    e.speed.textContent = (Math.abs(p.v) * 3.6).toFixed(p.maxSpeed < 0.1 ? 2 : 1);
    let hd = (360 - deg(p.yaw) + 180) % 360;
    if (hd < 0) hd += 360;
    e.heading.textContent = `${hd.toFixed(0).padStart(3, '0')}°`;
    e.pitch.textContent = `${deg(p.pitch).toFixed(1)}°`;
    e.roll.textContent = `${deg(p.roll).toFixed(1)}°`;
    e.odo.textContent = p.odometer < 1000 ? `${p.odometer.toFixed(0)} м` : `${(p.odometer / 1000).toFixed(2)} км`;
    e.alt.textContent = `${p.pos.y.toFixed(1)} м`;
    e.sun.textContent = `${this.sunState.el.toFixed(0)}°`;

    let warn = '';
    const tilt = Math.max(Math.abs(deg(p.pitch)), Math.abs(deg(p.roll)));
    if (p.airborne && p.airTime > 0.25) warn = 'ОТРЫВ ОТ ГРУНТА';
    else if (p.collided > 0) warn = 'ПРЕПЯТСТВИЕ';
    else if (tilt > 22) warn = 'КРУТОЙ СКЛОН';
    e.warning.textContent = warn;
    e.warning.classList.toggle('hidden', !warn);
    e.status.textContent = warn ? 'ВНИМАНИЕ' : 'СВЯЗЬ УСТАНОВЛЕНА';
    e.status.classList.toggle('warn', !!warn);

    if (!this._hintHidden && p.odometer > 30) {
      this._hintHidden = true;
      e.hint.style.opacity = '0';
    }
    if (!this.minimap.classList.contains('hidden')) this._drawMinimap();
  }

  bindSettings(o) {
    const q = $('s-quality');
    q.value = o.quality;
    q.onchange = () => o.onQuality(q.value);
    const az = $('s-az'), el = $('s-el'), vaz = $('v-az'), vel = $('v-el');
    az.value = this.sunState.az;
    el.value = this.sunState.el;
    const showSun = () => { vaz.textContent = `${Math.round(az.value)}°`; vel.textContent = `${(+el.value).toFixed(1)}°`; };
    showSun();
    const sunInput = (final) => () => { showSun(); o.onSun(+az.value, +el.value, final); };
    az.oninput = sunInput(false); el.oninput = sunInput(false);
    az.onchange = sunInput(true); el.onchange = sunInput(true);
    const ex = $('s-exp'), vex = $('v-exp');
    ex.value = o.exposure;
    vex.textContent = (+ex.value).toFixed(2);
    ex.oninput = () => { vex.textContent = (+ex.value).toFixed(2); o.onExposure(+ex.value); };
    const sp = $('s-speed');
    sp.value = String(o.speed);
    sp.onchange = () => o.onSpeed(+sp.value);
    const toggles = { 't-ao': 'ao', 't-bloom': 'bloom', 't-film': 'film', 't-stars': 'stars', 't-dust': 'dust', 't-tracks': 'tracks', 't-hud': 'minimap' };
    for (const [id, key] of Object.entries(toggles)) {
      const box = $(id);
      const def = key === 'stars' ? false : true;
      box.checked = o.prefs[key] === undefined ? def : !!o.prefs[key];
      box.onchange = () => o.onToggle(key, box.checked);
    }
  }

  syncSun() {
    $('s-az').value = this.sunState.az;
    $('s-el').value = this.sunState.el;
  }

  setupTouch(input, enabled) {
    if (!enabled) return;
    const wrap = $('touch'), stick = $('stick'), knob = $('knob');
    wrap.classList.remove('hidden');
    let id = null;
    const set = (e) => {
      const r = stick.getBoundingClientRect();
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      let dx = (e.clientX - cx) / (r.width / 2), dy = (e.clientY - cy) / (r.height / 2);
      const m = Math.hypot(dx, dy);
      if (m > 1) { dx /= m; dy /= m; }
      knob.style.transform = `translate(${dx * 38}px, ${dy * 38}px)`;
      input.touch.throttle = Math.abs(dy) > 0.15 ? -dy : 0;
      input.touch.steer = Math.abs(dx) > 0.15 ? -dx : 0;
    };
    stick.addEventListener('pointerdown', (e) => { id = e.pointerId; stick.setPointerCapture(id); set(e); e.stopPropagation(); });
    stick.addEventListener('pointermove', (e) => { if (e.pointerId === id) set(e); });
    const end = (e) => {
      if (e.pointerId !== id) return;
      id = null;
      knob.style.transform = '';
      input.touch.throttle = 0;
      input.touch.steer = 0;
    };
    stick.addEventListener('pointerup', end);
    stick.addEventListener('pointercancel', end);
  }
}
