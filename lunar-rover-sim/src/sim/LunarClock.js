import * as THREE from 'three';

// Synodic month: one lunar day-night cycle, in Earth seconds.
export const SYNODIC_SECONDS = 29.530589 * 86400;

const DEG = Math.PI / 180;

// Planets on the ecliptic (≈ the Sun's path in the sky), placed by
// elongation from the Sun. Brightness is linear HDR radiance of the point.
const PLANETS = [
  { name: 'Венера', elong: 41, lat: 1.2, color: [1.0, 0.97, 0.88], power: 26 },
  { name: 'Юпитер', elong: 108, lat: -0.8, color: [1.0, 0.94, 0.82], power: 11 },
  { name: 'Марс', elong: 152, lat: 1.5, color: [1.0, 0.55, 0.32], power: 5 },
  { name: 'Сатурн', elong: -128, lat: 2.0, color: [1.0, 0.9, 0.7], power: 3.5 },
  { name: 'Меркурий', elong: -19, lat: -1.5, color: [0.95, 0.9, 0.85], power: 2.5 },
];

/**
 * Local lunar time at the landing site. World axes: +X east, +Y up, -Z north.
 * The Sun (and the star field) turn about the lunar pole once per synodic
 * month; the Earth stays almost fixed in the sky (tidal locking).
 */
export class LunarClock {
  constructor({ latitude = 26, dayFraction = 0.317, timeScale = 1000 } = {}) {
    this.lat = latitude * DEG;
    this.t = dayFraction; // 0 = midnight, 0.5 = noon
    this.day = 1;
    this.timeScale = timeScale;
    this.earthSeconds = 0;
    this.pole = new THREE.Vector3(0, Math.sin(this.lat), -Math.cos(this.lat));
    // direction of the celestial equator's meridian point (Sun at local noon)
    this.noon = new THREE.Vector3(0, Math.cos(this.lat), Math.sin(this.lat));
    this.sunDir = new THREE.Vector3();
    this.skyRot = new THREE.Matrix3(); // world -> celestial frame
    this.planets = PLANETS.map((p) => ({ ...p, dir: new THREE.Vector3() }));
    this.earthDir = new THREE.Vector3(-0.72, Math.sin(13 * DEG), -0.62).normalize();
    this._m4 = new THREE.Matrix4();
    this._v = new THREE.Vector3();
    this.update(0);
  }

  _onEquator(angle, out, latDeg = 0) {
    this._m4.makeRotationAxis(this.pole, angle);
    out.copy(this.noon).applyMatrix4(this._m4);
    if (latDeg) out.addScaledVector(this.pole, Math.sin(latDeg * DEG)).normalize();
    return out;
  }

  get hourAngle() {
    return 2 * Math.PI * (this.t - 0.5);
  }

  /** Advance by real seconds (scaled by timeScale). */
  update(dt) {
    const earthDt = dt * this.timeScale;
    this.earthSeconds += earthDt;
    this.t += earthDt / SYNODIC_SECONDS;
    while (this.t >= 1) { this.t -= 1; this.day++; }
    while (this.t < 0) { this.t += 1; this.day = Math.max(1, this.day - 1); }
    // rotating about the pole by -H moves the Sun east -> west
    const H = this.hourAngle;
    this._onEquator(-H, this.sunDir);
    for (const p of this.planets) this._onEquator(-H - p.elong * DEG, p.dir, p.lat);
    this._m4.makeRotationAxis(this.pole, H);
    this.skyRot.setFromMatrix4(this._m4);
  }

  setDayFraction(t) {
    this.t = ((t % 1) + 1) % 1;
    this.update(0);
  }

  get sunElevation() {
    return Math.asin(THREE.MathUtils.clamp(this.sunDir.y, -1, 1));
  }

  /** Fraction of the Earth's disk that is sunlit, as seen from the Moon. */
  get earthPhase() {
    return 0.5 * (1 - this.earthDir.dot(this.sunDir));
  }

  /** Local lunar clock: 24 "lunar hours" per synodic day. */
  clockString() {
    const h = this.t * 24;
    const hh = Math.floor(h), mm = Math.floor((h - hh) * 60);
    return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
  }

  /** Earth hours until the next sunset (if day) or sunrise (if night). */
  hoursToTerminator() {
    const isDay = this.sunDir.y > 0;
    // search forward along the day fraction
    const step = 1 / 2000;
    const save = this.t;
    let f = 0;
    for (let i = 1; i <= 2000; i++) {
      this._onEquator(-2 * Math.PI * (save + i * step - 0.5), this._v);
      if ((this._v.y > 0) !== isDay) { f = i * step; break; }
    }
    return { isDay, hours: (f * SYNODIC_SECONDS) / 3600 };
  }
}
