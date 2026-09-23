import * as THREE from 'three';
import { mergeVertices } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Compact 3D gradient noise for shaping rocks (CPU side).
function makeNoise3(seed) {
  const rnd = mulberry32(seed);
  const perm = new Uint8Array(512);
  const p = Array.from({ length: 256 }, (_, i) => i);
  for (let i = 255; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [p[i], p[j]] = [p[j], p[i]];
  }
  for (let i = 0; i < 512; i++) perm[i] = p[i & 255];
  const G = [];
  for (let i = 0; i < 256; i++) {
    const z = rnd() * 2 - 1, a = rnd() * Math.PI * 2, r = Math.sqrt(1 - z * z);
    G.push([r * Math.cos(a), r * Math.sin(a), z]);
  }
  const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);
  return (x, y, z) => {
    const X = Math.floor(x), Y = Math.floor(y), Z = Math.floor(z);
    const fx = x - X, fy = y - Y, fz = z - Z;
    const u = fade(fx), v = fade(fy), w = fade(fz);
    let res = 0;
    for (let dz = 0; dz < 2; dz++) for (let dy = 0; dy < 2; dy++) for (let dx = 0; dx < 2; dx++) {
      const g = G[perm[perm[perm[(X + dx) & 255] + ((Y + dy) & 255)] + ((Z + dz) & 255)]];
      const d = g[0] * (fx - dx) + g[1] * (fy - dy) + g[2] * (fz - dz);
      res += d * (dx ? u : 1 - u) * (dy ? v : 1 - v) * (dz ? w : 1 - w);
    }
    return res * 1.6;
  };
}

/**
 * A rock shape description: a convex polyhedron from random cutting planes
 * with softened edges, then weathered with multi-octave noise, chips and a
 * flattened, partly buried base.
 */
export function makeRockShape(seed) {
  const rnd = mulberry32(seed * 7919 + 13);
  const noise = makeNoise3(seed * 31 + 7);
  const planes = [];
  const n = 7 + Math.floor(rnd() * 9);
  for (let i = 0; i < n; i++) {
    const z = rnd() * 2 - 1, a = rnd() * Math.PI * 2, r = Math.sqrt(1 - z * z);
    planes.push({ n: [r * Math.cos(a), r * Math.sin(a) * 0.9, z], d: 0.62 + rnd() * 0.36 });
  }
  const angular = 0.45 + rnd() * 0.55; // 0 = rounded, 1 = sharp facets
  const k = 0.07 - angular * 0.055;
  const scale = [1, 0.5 + rnd() * 0.45, 0.65 + rnd() * 0.4];
  const chips = [];
  for (let i = 0, c = Math.floor(rnd() * 4); i < c; i++) {
    const z = rnd() * 2 - 1, a = rnd() * Math.PI * 2, r = Math.sqrt(1 - z * z);
    chips.push({ n: [r * Math.cos(a), r * Math.sin(a), z], d: 0.75 + rnd() * 0.2 });
  }
  const pitScale = 5 + rnd() * 6;
  return (dx, dy, dz) => {
    // soft-min of the plane distances along this direction
    let sum = 0;
    for (const p of [...planes, ...chips]) {
      const c = dx * p.n[0] + dy * p.n[1] + dz * p.n[2];
      const r = c > 0.02 ? p.d / c : 50;
      sum += Math.exp(-r / k);
    }
    let r = -k * Math.log(sum + Math.exp(-1.25 / k));
    r *= 1 + 0.10 * noise(dx * 1.7, dy * 1.7, dz * 1.7) + 0.045 * noise(dx * 4.1 + 3, dy * 4.1, dz * 4.1) + 0.018 * noise(dx * 9 + 7, dy * 9, dz * 9);
    // small vesicles / pits
    const pit = noise(dx * pitScale + 11, dy * pitScale, dz * pitScale);
    if (pit > 0.35) r -= (pit - 0.35) * 0.05;
    let x = dx * r * scale[0], y = dy * r * scale[1], z = dz * r * scale[2];
    // flattened base
    const base = -0.28 * scale[1];
    if (y < base) y = base + (y - base) * 0.25;
    return [x, y, z];
  };
}

export function buildRockGeometry(shape, detail) {
  let geo = new THREE.IcosahedronGeometry(1, detail);
  geo.deleteAttribute('normal');
  geo.deleteAttribute('uv');
  geo = mergeVertices(geo, 1e-5);
  const pos = geo.attributes.position;
  const v = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i).normalize();
    const [x, y, z] = shape(v.x, v.y, v.z);
    pos.setXYZ(i, x, y, z);
  }
  geo.computeVertexNormals();
  geo.computeBoundingSphere();
  geo.computeBoundingBox();
  return geo;
}

/** Variants × LODs of rock geometry. */
export function buildRockLibrary(variants = 8, lods = [14, 6, 2]) {
  const lib = [];
  for (let s = 0; s < variants; s++) {
    const shape = makeRockShape(s + 1);
    const geos = lods.map((d) => buildRockGeometry(shape, d));
    const box = geos[0].boundingBox;
    lib.push({
      geos,
      // normalised extents so placement can compute height & footprint
      halfX: Math.max(-box.min.x, box.max.x),
      halfZ: Math.max(-box.min.z, box.max.z),
      top: box.max.y,
      bottom: box.min.y,
    });
  }
  return lib;
}
