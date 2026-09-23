// Shared GLSL used by the terrain bakers and the runtime terrain shaders.
// Everything is deterministic: the same world coordinate always produces the
// same height, so baked maps, CPU physics and the GPU mesh agree.

export const GLSL_NOISE = /* glsl */ `
uint lowbias32(uint x) {
  x ^= x >> 16u; x *= 0x7feb352du;
  x ^= x >> 15u; x *= 0x846ca68bu;
  x ^= x >> 16u;
  return x;
}
uint hash2i(ivec2 c, uint seed) {
  return lowbias32(uint(c.x) * 0x8da6b343u + lowbias32(uint(c.y) * 0xd8163841u + seed));
}
float u01(uint h) { return float(h >> 8u) * (1.0 / 16777216.0); }

int imodi(int a, int m) { return a - m * int(floor(float(a) / float(m))); }
ivec2 wrapCell(ivec2 c, int period) {
  return period > 0 ? ivec2(imodi(c.x, period), imodi(c.y, period)) : c;
}

vec2 hgrad(ivec2 c, uint seed) {
  float a = u01(hash2i(c, seed)) * 6.28318530718;
  return vec2(cos(a), sin(a));
}

// 2D gradient noise in [-1, 1]; period > 0 makes it tile every 'period' cells.
float gnoise(vec2 p, uint seed, int period) {
  vec2 fi = floor(p);
  ivec2 i = ivec2(fi);
  vec2 f = p - fi;
  vec2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  float a = dot(hgrad(wrapCell(i, period), seed), f);
  float b = dot(hgrad(wrapCell(i + ivec2(1, 0), period), seed), f - vec2(1.0, 0.0));
  float c = dot(hgrad(wrapCell(i + ivec2(0, 1), period), seed), f - vec2(0.0, 1.0));
  float d = dot(hgrad(wrapCell(i + ivec2(1, 1), period), seed), f - vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y) * 1.41421356;
}

const mat2 OCT_ROT = mat2(0.8, -0.6, 0.6, 0.8);

float fbm(vec2 p, int oct, uint seed) {
  float s = 0.0, a = 0.5, n = 0.0;
  for (int i = 0; i < 12; i++) {
    if (i >= oct) break;
    s += a * gnoise(p, seed + uint(i) * 131u, 0);
    n += a;
    p = OCT_ROT * p * 2.03;
    a *= 0.5;
  }
  return s / n;
}

// Tileable fbm: p in cell units, 'period' cells for the first octave.
float fbmP(vec2 p, int oct, uint seed, int period, float gain) {
  float s = 0.0, a = 0.5, n = 0.0;
  for (int i = 0; i < 8; i++) {
    if (i >= oct) break;
    s += a * gnoise(p, seed + uint(i) * 131u, period);
    n += a;
    p *= 2.0;
    period *= 2;
    a *= gain;
  }
  return s / n;
}

float smin(float a, float b, float k) {
  float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
  return mix(b, a, h) - k * h * (1.0 - h);
}
float smax(float a, float b, float k) { return -smin(-a, -b, k); }
`;

export const GLSL_CRATERS = /* glsl */ `
// Radial crater profile (r = distance / radius), result in units of radius.
// 'fresh' in [0,1]: 1 = young, deep, sharp raised rim; 0 = old, subdued.
float craterProfile(float r, float fresh) {
  float depth = mix(0.10, 0.40, fresh);
  float rimH  = mix(0.015, 0.075, fresh);
  float inner = depth * r * r - depth + rimH;
  float outer = rimH / max(r * r * r, 1e-3);
  float k = mix(0.16, 0.035, fresh);
  float h = smin(inner, outer, k);
  // degraded craters get a flatter floor
  h = smax(h, -depth * mix(0.55, 0.92, fresh) + rimH, k * 0.6);
  return h * (1.0 - smoothstep(1.7, 2.5, r));
}

struct CraterAcc { float h; float ejecta; float interior; };

// One layer of randomly placed craters on a jittered grid of 'cell' metres.
// period > 0 (in cells) makes the layer tileable.
void craterLayer(vec2 p, float cell, uint seed, float prob, float rMin, float rMax,
                 int period, inout CraterAcc acc) {
  vec2 g = p / cell;
  vec2 gi = floor(g);
  vec2 f = g - gi;
  ivec2 ci = ivec2(gi);
  for (int j = -1; j <= 1; j++) {
    for (int i = -1; i <= 1; i++) {
      ivec2 c = ci + ivec2(i, j);
      uint h = hash2i(wrapCell(c, period), seed);
      if (u01(h) > prob) continue;
      h = lowbias32(h);
      vec2 center = vec2(float(i), float(j)) + vec2(u01(h), u01(lowbias32(h ^ 0x9e3779b9u)));
      h = lowbias32(h + 0x632be5abu);
      float rad = mix(rMin, rMax, pow(u01(h), 1.8));
      h = lowbias32(h);
      float fresh = pow(u01(h), 2.2);
      h = lowbias32(h);
      vec2 d = f - center;
      float r = length(d) / rad;
      if (r > 2.5) continue;
      float ang = atan(d.y, d.x);
      float ph = u01(h) * 6.2831;
      r *= 1.0 + 0.05 * sin(ang * 3.0 + ph) + 0.03 * sin(ang * 5.0 + ph * 2.3) + 0.02 * sin(ang * 8.0 + ph * 4.1);
      acc.h += craterProfile(r, fresh) * rad * cell;
      float ej = fresh * (1.0 - smoothstep(1.0, 2.3, r)) * smoothstep(0.55, 0.95, r);
      acc.ejecta = max(acc.ejecta, ej);
      acc.interior = max(acc.interior, (1.0 - smoothstep(0.75, 1.0, r)) * (0.4 + 0.6 * fresh));
    }
  }
}
`;

// Large scale terrain: rolling plains, distant rounded massifs and a
// saturated population of craters. minCell drops layers too small to be
// represented at the resolution being baked.
export const GLSL_MACRO = /* glsl */ `
float macroHeight(vec2 p, float minCell, out vec3 extra) {
  float dist = length(p);
  float h = fbm(p / 1700.0, 6, 11u) * 26.0;
  h += fbm(p / 420.0 + 17.3, 5, 12u) * 6.0;
  h += fbm(p / 95.0 - 5.1, 4, 15u) * 2.2;
  h += fbm(p / 38.0 + 2.9, 3, 20u) * 0.9;

  // highland massifs rising towards the horizon
  float mask = smoothstep(1500.0, 5200.0, dist + fbm(p / 2900.0, 3, 13u) * 1100.0);
  float m = fbm(p / 3600.0 + 3.7, 7, 14u) * 0.5 + 0.5;
  float massif = pow(clamp(m * 1.25 - 0.18, 0.0, 1.5), 1.7) * 900.0;
  // softer "near hills" that already show on the local horizon
  float hillMask = smoothstep(450.0, 1900.0, dist + fbm(p / 1300.0 + 9.0, 3, 16u) * 500.0);
  float hills = pow(clamp(fbm(p / 900.0 - 7.7, 6, 17u) * 0.5 + 0.58, 0.0, 1.3), 2.0) * 170.0;
  h += massif * mask + hills * hillMask;

  CraterAcc acc = CraterAcc(0.0, 0.0, 0.0);
  if (minCell <= 1800.0) craterLayer(p, 1800.0, 101u, 0.30, 0.14, 0.36, 0, acc);
  if (minCell <= 800.0)  craterLayer(p, 800.0, 102u, 0.34, 0.12, 0.36, 0, acc);
  if (minCell <= 380.0)  craterLayer(p, 380.0, 103u, 0.40, 0.12, 0.36, 0, acc);
  if (minCell <= 180.0)  craterLayer(p, 180.0, 104u, 0.46, 0.12, 0.36, 0, acc);
  if (minCell <= 90.0)   craterLayer(p, 90.0, 105u, 0.50, 0.12, 0.36, 0, acc);
  if (minCell <= 46.0)   craterLayer(p, 46.0, 106u, 0.50, 0.12, 0.36, 0, acc);
  h += acc.h;

  // sink the world edge well below the curved horizon so it is never seen
  float edge = smoothstep(10500.0, 15800.0, max(abs(p.x), abs(p.y)));
  h = mix(h, -250.0, edge);

  float albedo = fbm(p / 2300.0 + 40.0, 4, 18u) * 0.6 + fbm(p / 260.0 - 13.0, 3, 19u) * 0.4;
  extra = vec3(acc.ejecta, albedo, acc.interior);
  return h;
}
`;

// Small scale relief stored in a 128 m tileable texture (sampled twice at
// different scales and rotations to hide the repetition).
export const GLSL_DETAIL = /* glsl */ `
const float DETAIL_TILE = 128.0;
float detailHeight(vec2 p, out vec2 extra) {
  float h = 0.0;
  h += fbmP(p / 16.0, 5, 21u, 8, 0.5) * 0.55;
  h += fbmP(p * (26.0 / 128.0) + 3.3, 3, 23u, 26, 0.5) * 0.12;
  h += fbmP(p / 2.0, 4, 22u, 64, 0.55) * 0.05;
  CraterAcc acc = CraterAcc(0.0, 0.0, 0.0);
  craterLayer(p, 16.0, 201u, 0.42, 0.12, 0.36, 8, acc);
  craterLayer(p, 8.0, 202u, 0.48, 0.12, 0.36, 16, acc);
  craterLayer(p, 4.0, 203u, 0.52, 0.12, 0.36, 32, acc);
  craterLayer(p, 2.0, 204u, 0.55, 0.13, 0.36, 64, acc);
  h += acc.h;
  extra = vec2(acc.ejecta, acc.interior);
  return h;
}
`;

// Micro regolith: granular soil with small clods and pebbles, 2 m tile.
export const GLSL_MICRO = /* glsl */ `
const float MICRO_TILE = 2.0;
float microHeight(vec2 p, out float alb) {
  // p in metres inside [0, MICRO_TILE)
  float h = fbmP(p / 0.4, 5, 31u, 5, 0.55) * 0.0035;
  h += fbmP(p / 0.05, 3, 32u, 40, 0.5) * 0.0009;
  alb = fbmP(p / 0.25, 3, 33u, 8, 0.5) * 0.35;
  // irregular clods and grit (tileable jittered grids)
  for (int layer = 0; layer < 2; layer++) {
    float cell = layer == 0 ? 0.1 : 0.04;
    int period = layer == 0 ? 20 : 50;
    vec2 g = p / cell;
    vec2 gi = floor(g);
    vec2 f = g - gi;
    for (int j = -1; j <= 1; j++) for (int i = -1; i <= 1; i++) {
      ivec2 c = ivec2(gi) + ivec2(i, j);
      uint hs = hash2i(wrapCell(c, period), 300u + uint(layer));
      if (u01(hs) > (layer == 0 ? 0.22 : 0.35)) continue;
      hs = lowbias32(hs);
      vec2 center = vec2(float(i), float(j)) + vec2(u01(hs), u01(lowbias32(hs + 11u)));
      hs = lowbias32(hs + 7u);
      float rad = mix(0.12, 0.38, u01(hs) * u01(lowbias32(hs + 17u)) * 1.6);
      vec2 d = f - center;
      float ang = atan(d.y, d.x);
      float ph = u01(lowbias32(hs + 3u)) * 6.283;
      float rr = rad * (1.0 + 0.25 * sin(ang * 2.0 + ph) + 0.15 * sin(ang * 3.0 + ph * 1.7) + 0.1 * sin(ang * 5.0 + ph * 2.9));
      float r = length(d) / rr;
      if (r < 1.0) {
        float bump = pow(1.0 - r * r, 0.7);
        float ht = bump * rad * cell * mix(0.25, 0.55, u01(lowbias32(hs + 9u)));
        h = max(h, h * 0.5 + ht);
        alb += smoothstep(1.0, 0.5, r) * (u01(lowbias32(hs + 13u)) - 0.45) * 0.8;
      }
    }
  }
  return h;
}
`;
