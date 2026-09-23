import * as THREE from 'three';

/**
 * Wheel tracks rendered into a toroidal world-space texture that follows the
 * rover. R = rut depth, G = grouser (tread) imprint. The terrain shader turns
 * it into micro-relief and darker, disturbed regolith.
 */
export class Tracks {
  constructor(renderer, { size = 128, res = 4096 } = {}) {
    this.renderer = renderer;
    this.size = size;
    this.res = res;
    this.rt = new THREE.WebGLRenderTarget(res, res, {
      type: THREE.UnsignedByteType,
      format: THREE.RGFormat,
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      wrapS: THREE.RepeatWrapping,
      wrapT: THREE.RepeatWrapping,
      depthBuffer: false,
      generateMipmaps: false,
    });
    this.rt.texture.wrapS = this.rt.texture.wrapT = THREE.RepeatWrapping;
    this.center = new THREE.Vector2(0, 0);
    this.snap = 16;
    this.maxQuads = 256;

    const geo = new THREE.BufferGeometry();
    this.posAttr = new THREE.BufferAttribute(new Float32Array(this.maxQuads * 4 * 2), 2);
    this.dataAttr = new THREE.BufferAttribute(new Float32Array(this.maxQuads * 4 * 3), 3);
    this.posAttr.setUsage(THREE.DynamicDrawUsage);
    this.dataAttr.setUsage(THREE.DynamicDrawUsage);
    geo.setAttribute('position', this.posAttr);
    geo.setAttribute('aData', this.dataAttr);
    const idx = [];
    for (let q = 0; q < this.maxQuads; q++) {
      const b = q * 4;
      idx.push(b, b + 1, b + 2, b + 2, b + 1, b + 3);
    }
    geo.setIndex(idx);
    geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e9);
    this.geo = geo;

    this.paintMat = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: /* glsl */ `
        in vec2 position; // already in unwrapped UV space
        in vec3 aData;    // across (-1..1), along distance (m), strength
        uniform vec2 uOffset;
        out vec3 vData;
        void main() {
          vData = aData;
          gl_Position = vec4((position + uOffset) * 2.0 - 1.0, 0.0, 1.0);
        }`,
      fragmentShader: /* glsl */ `
        precision highp float;
        in vec3 vData;
        out vec4 outColor;
        void main() {
          float a = abs(vData.x);
          float rut = smoothstep(1.0, 0.72, a) * vData.z;
          // chevron grousers (Perseverance wheels have curved treads)
          float ph = fract((vData.y + a * 0.045) / 0.075);
          float tread = smoothstep(0.02, 0.12, ph) * smoothstep(0.52, 0.38, ph);
          outColor = vec4(rut, rut * tread, 0.0, 1.0);
        }`,
      uniforms: { uOffset: { value: new THREE.Vector2() } },
      blending: THREE.CustomBlending,
      blendEquation: THREE.MaxEquation,
      blendSrc: THREE.OneFactor,
      blendDst: THREE.OneFactor,
      depthTest: false,
      depthWrite: false,
    });
    this.mesh = new THREE.Mesh(geo, this.paintMat);
    this.mesh.frustumCulled = false;

    this.clearMat = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: /* glsl */ `
        in vec2 position;
        uniform vec2 uOffset;
        void main() { gl_Position = vec4((position + uOffset) * 2.0 - 1.0, 0.0, 1.0); }`,
      fragmentShader: /* glsl */ `
        precision highp float;
        out vec4 outColor;
        void main() { outColor = vec4(0.0); }`,
      uniforms: { uOffset: { value: new THREE.Vector2() } },
      depthTest: false,
      depthWrite: false,
    });
    this.clearGeo = new THREE.BufferGeometry();
    this.clearGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(8), 2));
    this.clearGeo.setIndex([0, 1, 2, 2, 1, 3]);
    this.clearGeo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e9);
    this.clearMesh = new THREE.Mesh(this.clearGeo, this.clearMat);
    this.clearMesh.frustumCulled = false;

    this.camera = new THREE.Camera();
    this.quads = 0;
    this.prev = [];
    this.enabled = true;

    const clr = new THREE.Color();
    renderer.getClearColor(clr);
    const a = renderer.getClearAlpha();
    renderer.setRenderTarget(this.rt);
    renderer.setClearColor(0x000000, 0);
    renderer.clear(true, false, false);
    renderer.setRenderTarget(null);
    renderer.setClearColor(clr, a);
  }

  uniforms() {
    return {
      uTracks: { value: this.rt.texture },
      uTrackWin: { value: new THREE.Vector4(0, 0, this.size, this.size / this.res) },
    };
  }

  _drawWrapped(mesh, uMin, vMin, uMax, vMax, uniform) {
    const r = this.renderer;
    const ox = -Math.floor(uMin), oz = -Math.floor(vMin);
    const nx = Math.floor(uMax) - Math.floor(uMin), nz = Math.floor(vMax) - Math.floor(vMin);
    for (let j = 0; j <= nz; j++) {
      for (let i = 0; i <= nx; i++) {
        uniform.value.set(ox - i, oz - j);
        r.render(mesh, this.camera);
      }
    }
  }

  _clearWorldRect(x0, z0, x1, z1) {
    const s = this.size;
    const p = this.clearGeo.attributes.position;
    p.setXY(0, x0 / s, z0 / s); p.setXY(1, x1 / s, z0 / s);
    p.setXY(2, x0 / s, z1 / s); p.setXY(3, x1 / s, z1 / s);
    p.needsUpdate = true;
    this._drawWrapped(this.clearMesh, x0 / s, z0 / s, x1 / s, z1 / s, this.clearMat.uniforms.uOffset);
  }

  /** Move the window with the rover, clearing strips that wrap around. */
  follow(x, z, uniforms) {
    const s = this.snap;
    const nx = Math.round(x / s) * s, nz = Math.round(z / s) * s;
    const ox = this.center.x, oz = this.center.y;
    if (nx === ox && nz === oz) return;
    const r = this.renderer;
    const prev = r.getRenderTarget();
    const autoClear = r.autoClear;
    r.autoClear = false;
    r.setRenderTarget(this.rt);
    const h = this.size / 2;
    if (Math.abs(nx - ox) >= this.size || Math.abs(nz - oz) >= this.size) {
      this._clearWorldRect(nx - h, nz - h, nx + h, nz + h);
    } else {
      if (nx > ox) this._clearWorldRect(ox + h, nz - h, nx + h, nz + h);
      if (nx < ox) this._clearWorldRect(nx - h, nz - h, ox - h, nz + h);
      if (nz > oz) this._clearWorldRect(nx - h, oz + h, nx + h, nz + h);
      if (nz < oz) this._clearWorldRect(nx - h, nz - h, nx + h, oz - h);
    }
    r.setRenderTarget(prev);
    r.autoClear = autoClear;
    this.center.set(nx, nz);
    if (uniforms) uniforms.uTrackWin.value.set(nx, nz, this.size, this.size / this.res);
  }

  /**
   * Stamp a wheel segment. a,b: world xz of the contact point at the previous
   * and current frame; heading vector; width in metres; s0/s1 along-track
   * distances for the tread pattern.
   */
  addSegment(ax, az, bx, bz, width, s0, s1, strength = 1) {
    if (this.quads >= this.maxQuads) return;
    const dx = bx - ax, dz = bz - az;
    const len = Math.hypot(dx, dz);
    if (len < 1e-4) return;
    const tx = dx / len, tz = dz / len;
    const nx = -tz * width * 0.5, nz = tx * width * 0.5;
    // extend slightly to avoid gaps between segments
    const ex = tx * 0.01, ez = tz * 0.01;
    const s = this.size;
    const q = this.quads++;
    const P = this.posAttr, D = this.dataAttr;
    P.setXY(q * 4 + 0, (ax - ex + nx) / s, (az - ez + nz) / s);
    P.setXY(q * 4 + 1, (ax - ex - nx) / s, (az - ez - nz) / s);
    P.setXY(q * 4 + 2, (bx + ex + nx) / s, (bz + ez + nz) / s);
    P.setXY(q * 4 + 3, (bx + ex - nx) / s, (bz + ez - nz) / s);
    D.setXYZ(q * 4 + 0, 1, s0, strength);
    D.setXYZ(q * 4 + 1, -1, s0, strength);
    D.setXYZ(q * 4 + 2, 1, s1, strength);
    D.setXYZ(q * 4 + 3, -1, s1, strength);
    const u0 = Math.min(ax, bx) - width, u1 = Math.max(ax, bx) + width;
    const v0 = Math.min(az, bz) - width, v1 = Math.max(az, bz) + width;
    this._bounds = this._bounds || [Infinity, Infinity, -Infinity, -Infinity];
    this._bounds[0] = Math.min(this._bounds[0], u0 / s);
    this._bounds[1] = Math.min(this._bounds[1], v0 / s);
    this._bounds[2] = Math.max(this._bounds[2], u1 / s);
    this._bounds[3] = Math.max(this._bounds[3], v1 / s);
  }

  flush() {
    if (!this.quads) return;
    const r = this.renderer;
    const prev = r.getRenderTarget();
    const autoClear = r.autoClear;
    r.autoClear = false;
    this.posAttr.needsUpdate = true;
    this.dataAttr.needsUpdate = true;
    this.geo.setDrawRange(0, this.quads * 6);
    r.setRenderTarget(this.rt);
    const b = this._bounds;
    this._drawWrapped(this.mesh, b[0], b[1], b[2], b[3], this.paintMat.uniforms.uOffset);
    r.setRenderTarget(prev);
    r.autoClear = autoClear;
    this.quads = 0;
    this._bounds = null;
  }
}
