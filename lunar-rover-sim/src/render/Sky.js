import * as THREE from 'three';

/** Black lunar sky: HDR sun disk with lens glare and an optional star field. */
export class Sky {
  constructor() {
    this.uniforms = {
      uSunDir: { value: new THREE.Vector3(0, 1, 0) },
      uStars: { value: 0.35 },
      uPixelAngle: { value: 0.0015 },
      uGlare: { value: 1 },
      uEarthDir: { value: new THREE.Vector3(0.3, 0.2, 0.93).normalize() },
      uEarth: { value: 1 },
      uEarthRot: { value: 0.8 },
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
        uniform vec3 uEarthDir;
        uniform float uEarth;
        uniform float uEarthRot;
        varying vec3 vDir;

        float hash3(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
        float vnoise(vec3 x) {
          vec3 i = floor(x), f = fract(x);
          f = f * f * (3.0 - 2.0 * f);
          return mix(mix(mix(hash3(i), hash3(i + vec3(1, 0, 0)), f.x), mix(hash3(i + vec3(0, 1, 0)), hash3(i + vec3(1, 1, 0)), f.x), f.y),
                     mix(mix(hash3(i + vec3(0, 0, 1)), hash3(i + vec3(1, 0, 1)), f.x), mix(hash3(i + vec3(0, 1, 1)), hash3(i + vec3(1, 1, 1)), f.x), f.y), f.z);
        }
        float fbm3(vec3 p) { float s = 0.0, a = 0.5; for (int i = 0; i < 6; i++) { s += a * vnoise(p); p = p * 2.03 + 17.1; a *= 0.5; } return s; }

        // Earth as seen from the Moon: ~1.9° across, phase set by the Sun direction.
        vec3 earth(vec3 d) {
          float R = 0.0166;
          vec3 E = uEarthDir;
          float c = dot(d, E);
          if (c < cos(R * 1.25)) return vec3(0.0);
          vec3 T = normalize(cross(vec3(0.0, 1.0, 0.0), E));
          vec3 B = cross(E, T);
          vec2 q = vec2(dot(d, T), dot(d, B)) / R;
          float r2 = dot(q, q);
          vec3 col = vec3(0.0);
          if (r2 < 1.0) {
            vec3 n = q.x * T + q.y * B - sqrt(1.0 - r2) * E;
            // body-fixed coordinates (rotating Earth, axis roughly "up")
            float ca = cos(uEarthRot), sa = sin(uEarthRot);
            vec3 b = vec3(dot(n, T) * ca - dot(n, -E) * sa, dot(n, B), dot(n, T) * sa + dot(n, -E) * ca);
            float lat = abs(b.y);
            float land = smoothstep(0.53, 0.56, fbm3(b * 2.1 + 3.0));
            float ice = smoothstep(0.78, 0.9, lat + fbm3(b * 5.0) * 0.1);
            vec3 cw = b * 3.2 + vec3(fbm3(b * 6.0) * 1.2, 0.0, 0.0);
            float cloud = smoothstep(0.5, 0.82, fbm3(cw + vec3(uEarthRot * 0.3, 0.0, 0.0)) + 0.06 * sin(b.y * 16.0 + fbm3(b * 3.0) * 4.0));
            vec3 ocean = vec3(0.012, 0.03, 0.085);
            vec3 ground = mix(vec3(0.15, 0.12, 0.08), vec3(0.07, 0.09, 0.045), fbm3(b * 7.0));
            col = mix(ocean, ground, land);
            col = mix(col, vec3(0.8), ice);
            col = mix(col, vec3(0.92), cloud * 0.85);
            float ndl = dot(n, uSunDir);
            float lit = smoothstep(-0.06, 0.12, ndl) * (0.25 + 0.75 * max(ndl, 0.0));
            float rim = pow(1.0 - sqrt(1.0 - r2), 3.0);
            col = col * lit * 2.0 + vec3(0.3, 0.5, 1.0) * rim * smoothstep(-0.2, 0.3, ndl) * 0.55;
            // faint earthshine-free night side
            col *= smoothstep(1.0, 0.985, r2) * 0.6 + 0.4;
          }
          // thin atmosphere halo just outside the limb
          float halo = exp(-max(0.0, sqrt(r2) - 1.0) * 30.0) * step(1.0, r2);
          col += vec3(0.2, 0.4, 1.0) * halo * 0.25 * smoothstep(-0.3, 0.4, dot(normalize(-E + uSunDir), uSunDir));
          return col * uEarth;
        }

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
          if (uEarth > 0.0) col += earth(d);
          float cosA = clamp(dot(d, uSunDir), -1.0, 1.0);
          float ang = acos(cosA);
          float disk = 1.0 - smoothstep(0.0044, 0.0048, ang);
          // slight limb darkening
          float limb = sqrt(max(0.0, 1.0 - pow(ang / 0.0046, 2.0)));
          col += vec3(1.0, 0.975, 0.94) * disk * (0.55 + 0.45 * limb) * 160.0;
          col += vec3(1.0, 0.96, 0.9) * uGlare * (exp(-ang * 160.0) * 0.8 + exp(-ang * 30.0) * 0.05 + 0.006 / (1.0 + ang * 300.0));
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
