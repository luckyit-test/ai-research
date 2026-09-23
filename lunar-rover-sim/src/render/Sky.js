import * as THREE from 'three';

/** Black lunar sky: HDR sun disk with lens glare and an optional star field. */
export class Sky {
  constructor() {
    this.uniforms = {
      uSunDir: { value: new THREE.Vector3(0, 1, 0) },
      uStars: { value: 0.35 },
      uPixelAngle: { value: 0.0015 },
      uGlare: { value: 1 },
    };
    const material = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      side: THREE.BackSide,
      depthWrite: false,
      depthTest: false,
      vertexShader: /* glsl */ `
        varying vec3 vDir;
        void main() {
          vDir = position;
          vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          gl_Position = p.xyww;
        }`,
      fragmentShader: /* glsl */ `
        uniform vec3 uSunDir;
        uniform float uStars;
        uniform float uPixelAngle;
        uniform float uGlare;
        varying vec3 vDir;

        uint lowbias32(uint x) {
          x ^= x >> 16u; x *= 0x7feb352du; x ^= x >> 15u; x *= 0x846ca68bu; x ^= x >> 16u; return x;
        }
        float u01(uint h) { return float(h >> 8u) * (1.0 / 16777216.0); }

        vec2 octEncode(vec3 n) {
          n /= (abs(n.x) + abs(n.y) + abs(n.z));
          vec2 p = n.xz;
          if (n.y < 0.0) p = (1.0 - abs(p.yx)) * vec2(p.x >= 0.0 ? 1.0 : -1.0, p.y >= 0.0 ? 1.0 : -1.0);
          return p;
        }

        vec3 starLayer(vec3 d, float grid, uint seed, float density) {
          vec2 uv = octEncode(d) * grid;
          vec2 cell = floor(uv);
          vec3 acc = vec3(0.0);
          for (int j = -1; j <= 1; j++) for (int i = -1; i <= 1; i++) {
            vec2 c = cell + vec2(float(i), float(j));
            uint h = lowbias32(uint(int(c.x) + 4096) * 0x9e3779b1u ^ lowbias32(uint(int(c.y) + 4096) + seed));
            if (u01(h) > density) continue;
            h = lowbias32(h);
            vec2 sp = c + vec2(u01(h), u01(lowbias32(h + 1u)));
            float dist = length(uv - sp) / grid * 2.2; // ~ angular distance
            float mag = pow(u01(lowbias32(h + 2u)), 7.0);
            float temp = u01(lowbias32(h + 3u));
            vec3 tint = mix(vec3(1.0, 0.78, 0.6), vec3(0.72, 0.82, 1.0), temp);
            float sigma = uPixelAngle * 0.75;
            acc += tint * mag * exp(-dist * dist / (sigma * sigma));
          }
          return acc;
        }

        void main() {
          vec3 d = normalize(vDir);
          vec3 col = vec3(0.0);
          if (uStars > 0.0) {
            col += starLayer(d, 900.0, 7u, 0.22) * 2.5;
            col += starLayer(d, 350.0, 13u, 0.35) * 5.0;
            col *= uStars;
          }
          float cosA = clamp(dot(d, uSunDir), -1.0, 1.0);
          float ang = acos(cosA);
          float disk = 1.0 - smoothstep(0.0044, 0.0048, ang);
          // slight limb darkening
          float limb = sqrt(max(0.0, 1.0 - pow(ang / 0.0046, 2.0)));
          col += vec3(1.0, 0.975, 0.94) * disk * (0.55 + 0.45 * limb) * 900.0;
          col += vec3(1.0, 0.96, 0.9) * uGlare * (exp(-ang * 55.0) * 1.2 + exp(-ang * 9.0) * 0.06 + 0.02 / (1.0 + ang * 400.0));
          gl_FragColor = vec4(col, 1.0);
        }`,
    });
    this.mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 4), material);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = -1000;
    this.mesh.name = 'sky';
  }

  update(camera, renderer) {
    this.mesh.position.copy(camera.position);
    this.mesh.scale.setScalar(camera.far * 0.5);
    const h = renderer.getDrawingBufferSize(new THREE.Vector2()).y;
    this.uniforms.uPixelAngle.value = THREE.MathUtils.degToRad(camera.fov) / Math.max(1, h);
  }
}
