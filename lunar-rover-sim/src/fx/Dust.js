import * as THREE from 'three';
import { LUNAR_G } from '../terrain/constants.js';

/**
 * Regolith kicked up by the wheels. In vacuum there is no drag, so grains
 * fly on clean parabolic arcs and fall back — no billowing clouds.
 * Positions are evaluated analytically on the GPU from the launch state.
 */
export class Dust {
  constructor(count = 6000) {
    this.count = count;
    this.cursor = 0;
    const geo = new THREE.BufferGeometry();
    this.p0 = new THREE.BufferAttribute(new Float32Array(count * 3), 3);
    this.v0 = new THREE.BufferAttribute(new Float32Array(count * 3), 3);
    this.meta = new THREE.BufferAttribute(new Float32Array(count * 4), 4); // birth, life, size, ground y
    for (const a of [this.p0, this.v0, this.meta]) a.setUsage(THREE.DynamicDrawUsage);
    for (let i = 0; i < count; i++) this.meta.setXYZW(i, -1000, 0.01, 0, 0);
    geo.setAttribute('position', this.p0);
    geo.setAttribute('aVel', this.v0);
    geo.setAttribute('aMeta', this.meta);
    geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e6);

    this.uniforms = {
      uTime: { value: 0 },
      uG: { value: LUNAR_G },
      uScale: { value: 600 },
      uColor: { value: new THREE.Color(0.5, 0.47, 0.43) },
      uSunDir: { value: new THREE.Vector3(0, 1, 0) },
    };
    const material = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      transparent: true,
      depthWrite: false,
      vertexShader: /* glsl */ `
        attribute vec3 aVel;
        attribute vec4 aMeta;
        uniform float uTime, uG, uScale;
        varying float vAlpha;
        void main() {
          float t = uTime - aMeta.x;
          vec3 p = position + aVel * t + vec3(0.0, -0.5 * uG * t * t, 0.0);
          float alive = step(0.0, t) * step(t, aMeta.y) * step(aMeta.w, p.y);
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = alive * aMeta.z * uScale / max(-mv.z, 0.1);
          vAlpha = alive * (1.0 - smoothstep(aMeta.y * 0.6, aMeta.y, t)) * clamp(gl_PointSize * 0.6, 0.0, 1.0);
          gl_PointSize = max(gl_PointSize, alive * 1.5);
          if (alive < 0.5) gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        }`,
      fragmentShader: /* glsl */ `
        uniform vec3 uColor;
        varying float vAlpha;
        void main() {
          vec2 d = gl_PointCoord * 2.0 - 1.0;
          float r = dot(d, d);
          if (r > 1.0) discard;
          float a = (1.0 - r) * vAlpha * 0.8;
          gl_FragColor = vec4(uColor, a);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
    });
    this.points = new THREE.Points(geo, material);
    this.points.frustumCulled = false;
    this.points.renderOrder = 10;
    this.time = 0;
    this._dirty = false;
    this.enabled = true;
  }

  emit(x, y, z, vx, vy, vz, size, life, groundY) {
    const i = this.cursor;
    this.cursor = (this.cursor + 1) % this.count;
    this.p0.setXYZ(i, x, y, z);
    this.v0.setXYZ(i, vx, vy, vz);
    this.meta.setXYZW(i, this.time, life, size, groundY);
    if (this._min === undefined || i < this._min) this._min = i;
    if (this._max === undefined || i > this._max) this._max = i;
    this._dirty = true;
  }

  /**
   * Spray from a wheel contact. dir: wheel heading (unit xz), speed: m/s.
   */
  spray(contact, dirX, dirZ, speed, dt, groundY, sunlit = 1) {
    if (!this.enabled) return;
    const rate = Math.min(700, Math.abs(speed) * 260) * dt;
    let n = Math.floor(rate);
    if (Math.random() < rate - n) n++;
    const back = speed >= 0 ? -1 : 1;
    for (let k = 0; k < n; k++) {
      const s = Math.abs(speed) * (0.25 + Math.random() * 0.9);
      const up = 0.4 + Math.random() * 1.1;
      const side = (Math.random() - 0.5) * 0.9;
      const vx = (dirX * back + -dirZ * side) * s * 0.8;
      const vz = (dirZ * back + dirX * side) * s * 0.8;
      const vy = s * up;
      this.emit(
        contact.x + (Math.random() - 0.5) * 0.3, contact.y + 0.02, contact.z + (Math.random() - 0.5) * 0.3,
        vx, vy, vz,
        0.012 + Math.random() * Math.random() * 0.035,
        0.7 + Math.random() * 1.5,
        groundY - 0.05,
      );
    }
  }

  update(dt) {
    this.time += dt;
    this.uniforms.uTime.value = this.time;
    if (this._dirty) {
      for (const a of [this.p0, this.v0, this.meta]) {
        a.clearUpdateRanges();
        a.addUpdateRange(this._min * a.itemSize, (this._max - this._min + 1) * a.itemSize);
        a.needsUpdate = true;
      }
      this._dirty = false;
      this._min = this._max = undefined;
    }
  }
}
