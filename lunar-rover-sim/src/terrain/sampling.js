import {
  MACRO_MIN, MACRO_SIZE, FAR_MIN, FAR_SIZE, BLEND_START, BLEND_END,
  DETAIL_TILE, DETAIL_B_SCALE, DETAIL_B_AMP, DETAIL_B_ROT, DETAIL_B_OFFSET,
  MICRO_TILE, DETAIL_A_FADE, DETAIL_B_FADE,
} from './constants.js';

const f = (v) => (Number.isInteger(v) ? v.toFixed(1) : String(v));

// GLSL used by every shader that needs terrain heights / gradients at runtime.
// The CPU implementation in TerrainData mirrors these formulas exactly.
export function terrainSamplingGLSL(macroRes, farRes) {
  const c = Math.cos(DETAIL_B_ROT), s = Math.sin(DETAIL_B_ROT);
  return /* glsl */ `
uniform highp sampler2D uMacroH;
uniform highp sampler2D uFarH;
uniform sampler2D uMacroInfo;
uniform sampler2D uFarInfo;
uniform sampler2D uDetail;
uniform sampler2D uMicro;

#define MACRO_MIN ${f(MACRO_MIN)}
#define MACRO_TEXEL ${f(MACRO_SIZE / macroRes)}
#define MACRO_RES ${macroRes}
#define FAR_MIN ${f(FAR_MIN)}
#define FAR_TEXEL ${f(FAR_SIZE / farRes)}
#define FAR_RES ${farRes}
#define BLEND_START ${f(BLEND_START)}
#define BLEND_END ${f(BLEND_END)}
#define DETAIL_TILE ${f(DETAIL_TILE)}
#define DB_SCALE ${f(DETAIL_B_SCALE)}
#define DB_AMP ${f(DETAIL_B_AMP)}
#define MICRO_TILE ${f(MICRO_TILE)}
const mat2 DB_ROT = mat2(${f(c)}, ${f(s)}, ${f(-s)}, ${f(c)});
const vec2 DB_OFF = vec2(${f(DETAIL_B_OFFSET[0])}, ${f(DETAIL_B_OFFSET[1])});

float terrainBlendW(vec2 p) {
  return smoothstep(BLEND_START, BLEND_END, max(abs(p.x), abs(p.y)));
}

float catmullRomH(highp sampler2D t, vec2 pTex, int res) {
  vec2 st = pTex - 0.5;
  vec2 fi = floor(st);
  vec2 fr = st - fi;
  vec2 w0 = fr * (-0.5 + fr * (1.0 - 0.5 * fr));
  vec2 w1 = 1.0 + fr * fr * (-2.5 + 1.5 * fr);
  vec2 w2 = fr * (0.5 + fr * (2.0 - 1.5 * fr));
  vec2 w3 = fr * fr * (-0.5 + 0.5 * fr);
  ivec2 b = ivec2(fi) - 1;
  ivec2 hi = ivec2(res - 1);
  vec4 wx = vec4(w0.x, w1.x, w2.x, w3.x);
  vec4 wy = vec4(w0.y, w1.y, w2.y, w3.y);
  float r = 0.0;
  for (int y = 0; y < 4; y++) {
    vec4 row;
    for (int x = 0; x < 4; x++) {
      row[x] = texelFetch(t, clamp(b + ivec2(x, y), ivec2(0), hi), 0).r;
    }
    r += wy[y] * dot(wx, row);
  }
  return r;
}

float baseHeight(vec2 p) {
  float w = terrainBlendW(p);
  float hf = catmullRomH(uFarH, (p - FAR_MIN) / FAR_TEXEL, FAR_RES);
  if (w >= 1.0) return hf;
  float hm = catmullRomH(uMacroH, (p - MACRO_MIN) / MACRO_TEXEL, MACRO_RES);
  return mix(hm, hf, w);
}

vec2 detailUvA(vec2 p) { return p / DETAIL_TILE; }
vec2 detailUvB(vec2 p) { return (DB_ROT * (p + DB_OFF)) / (DETAIL_TILE * DB_SCALE); }

// geometric detail with distance fade (vertex shader)
float detailHeightV(vec2 p, float camDist) {
  float wa = 1.0 - smoothstep(${f(DETAIL_A_FADE[0])}, ${f(DETAIL_A_FADE[1])}, camDist);
  float wb = 1.0 - smoothstep(${f(DETAIL_B_FADE[0])}, ${f(DETAIL_B_FADE[1])}, camDist);
  float h = 0.0;
  if (wa > 0.0) h += textureLod(uDetail, detailUvA(p), 0.0).r * wa;
  if (wb > 0.0) h += textureLod(uDetail, detailUvB(p), 0.0).r * (DB_SCALE * DB_AMP) * wb;
  return h * (1.0 - terrainBlendW(p));
}

vec4 macroInfo(vec2 p) {
  float w = terrainBlendW(p);
  vec4 fi = texture(uFarInfo, (p - FAR_MIN) / ${f(FAR_SIZE)});
  if (w >= 1.0) return fi;
  vec4 mi = texture(uMacroInfo, (p - MACRO_MIN) / ${f(MACRO_SIZE)});
  return mix(mi, fi, w);
}
`;
}
