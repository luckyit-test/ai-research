import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

const DEG = Math.PI / 180;

// Array layout (model space of the rover: +Z forward, +Y up, +X left).
export const ARRAY = {
  mount: new THREE.Vector3(0.15, 1.28, -0.8), // pylon foot on the rear deck
  height: 1.2, // pylon length
  wing: { w: 1.3, d: 0.92, gap: 0.14 }, // each wing (along X × along Z)
  maxTilt: 70 * DEG,
  area: 2 * 1.3 * 0.92 * 0.94, // active cell area, m²
};

function roundedRect(w, h, r) {
  const s = new THREE.Shape();
  const x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y);
  s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r);
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h);
  s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r);
  s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

/** Aluminium frame ring of a wing, lying in the XZ plane. */
function frameGeometry(w, d, bar) {
  const outer = roundedRect(w, d, 0.02);
  const inner = roundedRect(w - 2 * bar, d - 2 * bar, 0.012);
  outer.holes.push(inner);
  const g = new THREE.ExtrudeGeometry(outer, { depth: 0.022, bevelEnabled: true, bevelThickness: 0.003, bevelSize: 0.003, bevelSegments: 2, curveSegments: 4 });
  g.rotateX(-Math.PI / 2);
  g.translate(0, -0.011, 0);
  // cross ribs under the cells
  const ribs = [];
  for (let i = 1; i < 4; i++) {
    const rib = new THREE.ExtrudeGeometry(roundedRect(0.018, d - 2 * bar, 0.004), { depth: 0.014, bevelEnabled: false });
    rib.rotateX(-Math.PI / 2);
    rib.translate(-w / 2 + (i * w) / 4, -0.016, 0);
    ribs.push(rib);
  }
  return mergeGeometries([g, ...ribs]);
}

function cellSheet(w, d) {
  const g = new THREE.ShapeGeometry(roundedRect(w, d, 0.006), 2);
  g.rotateX(-Math.PI / 2);
  return g;
}

function tubeBetween(a, b, r, seg = 10) {
  const curve = new THREE.LineCurve3(a, b);
  return new THREE.TubeGeometry(curve, 1, r, seg, false);
}

/** Lathe profile for the pylon: flange, tapered tube, collar. */
function pylonGeometry(h) {
  const pts = [
    [0.0, 0], [0.11, 0], [0.11, 0.018], [0.06, 0.03], [0.045, 0.06],
    [0.038, h * 0.5], [0.032, h - 0.12], [0.05, h - 0.1], [0.05, h - 0.04], [0.035, h - 0.03], [0.035, h], [0, h],
  ].map(([x, y]) => new THREE.Vector2(x, y));
  return new THREE.LatheGeometry(pts, 28);
}

function hubGeometry(len) {
  const pts = [[0, -len / 2], [0.04, -len / 2], [0.055, -len / 2 + 0.02], [0.055, len / 2 - 0.02], [0.04, len / 2], [0, len / 2]]
    .map(([x, y]) => new THREE.Vector2(x, y));
  const g = new THREE.LatheGeometry(pts, 24);
  g.rotateZ(Math.PI / 2);
  return g;
}

const CELL_FRAGMENT = /* glsl */ `
#include <map_fragment>
{
  // 156 mm cells with 4 mm gaps and silver busbars, under cover glass
  vec2 p = vCellP;
  vec2 cell = vec2(0.158, 0.158);
  vec2 f = fract(p / cell);
  vec2 id = floor(p / cell);
  // pixel-footprint aware (anti-aliased) lines: no moire or shimmer at distance
  vec2 fw = fwidth(p / cell);
  float lod = clamp(1.0 - max(fw.x, fw.y) * 6.0, 0.0, 1.0);
  vec2 g2 = smoothstep(vec2(0.025) + fw, vec2(0.025) - fw, f);
  float gap = mix(0.3, max(g2.x, g2.y), clamp(1.0 - max(fw.x, fw.y) * 3.0, 0.0, 1.0));
  float bw = fwidth(f.x * 3.0);
  float bus = (1.0 - smoothstep(0.012, 0.012 + bw, abs(fract(f.x * 3.0) - 0.5))) * (1.0 - gap) * lod + 0.04 * (1.0 - lod);
  float fwf = fwidth(f.y * 38.0);
  float fingers = (1.0 - smoothstep(0.05, 0.05 + fwf, abs(fract(f.y * 38.0) - 0.5))) * 0.25 * clamp(1.0 - fwf * 2.0, 0.0, 1.0);
  float v = fract(sin(dot(id, vec2(12.9898, 78.233))) * 43758.5453);
  vec3 si = mix(vec3(0.018, 0.03, 0.075), vec3(0.03, 0.045, 0.1), v);
  vec3 col = mix(si, vec3(0.62, 0.64, 0.66), clamp(bus + fingers * (1.0 - gap), 0.0, 1.0));
  col = mix(col, vec3(0.75, 0.73, 0.7), clamp(gap, 0.0, 1.0));
  diffuseColor.rgb = col;
  cellMetal = clamp(bus + gap, 0.0, 1.0);
}
`;

export class SolarArray {
  constructor() {
    this.root = new THREE.Group();
    this.root.name = 'solar-array';
    this.root.position.copy(ARRAY.mount);

    const white = new THREE.MeshStandardMaterial({ color: 0xe9e6de, roughness: 0.55, metalness: 0.05 });
    const alu = new THREE.MeshStandardMaterial({ color: 0xb9bcc0, roughness: 0.32, metalness: 0.9 });
    const dark = new THREE.MeshStandardMaterial({ color: 0x2a2a2c, roughness: 0.45, metalness: 0.6 });
    const kapton = new THREE.MeshStandardMaterial({ color: 0xc9a25a, roughness: 0.38, metalness: 0.75, side: THREE.FrontSide });
    const cells = new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.3, metalness: 0.2, clearcoat: 1, clearcoatRoughness: 0.2 });
    cells.onBeforeCompile = (shader) => {
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec2 vCellP;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvCellP = position.xz + vec2(0.5);');
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\nvarying vec2 vCellP;')
        .replace('#include <map_fragment>', 'float cellMetal = 0.0;\n' + CELL_FRAGMENT)
        .replace('#include <metalnessmap_fragment>', '#include <metalnessmap_fragment>\nmetalnessFactor = mix(0.15, 0.95, cellMetal);');
    };
    cells.customProgramCacheKey = () => 'solar-cells';
    this.materials = [white, alu, dark, kapton, cells];

    const add = (parent, geo, mat) => {
      const m = new THREE.Mesh(geo, mat);
      m.castShadow = true;
      m.receiveShadow = true;
      parent.add(m);
      return m;
    };

    // pylon & yaw bearing
    add(this.root, pylonGeometry(ARRAY.height), white);
    const bearing = new THREE.LatheGeometry([[0, 0], [0.075, 0], [0.075, 0.05], [0.06, 0.07], [0, 0.07]].map(([x, y]) => new THREE.Vector2(x, y)), 24);
    bearing.translate(0, ARRAY.height - 0.02, 0);
    add(this.root, bearing, dark);
    // diagonal braces to the deck
    for (const s of [-1, 1]) {
      add(this.root, tubeBetween(new THREE.Vector3(s * 0.28, 0.02, 0.18), new THREE.Vector3(0, 0.55, 0), 0.012), alu);
    }

    this.yaw = new THREE.Group();
    this.yaw.position.y = ARRAY.height + 0.05;
    this.root.add(this.yaw);
    // yoke carrying the tilt axis
    const yokeH = 0.14;
    for (const s of [-1, 1]) {
      add(this.yaw, tubeBetween(new THREE.Vector3(0, 0, 0), new THREE.Vector3(s * 0.16, yokeH, 0), 0.016), white);
    }
    this.tilt = new THREE.Group();
    this.tilt.position.y = yokeH;
    this.yaw.add(this.tilt);
    add(this.tilt, hubGeometry(0.36), dark);

    const { w, d, gap } = ARRAY.wing;
    const frame = frameGeometry(w, d, 0.03);
    const sheet = cellSheet(w - 0.05, d - 0.05);
    const back = cellSheet(w - 0.05, d - 0.05);
    back.rotateX(Math.PI);
    for (const s of [-1, 1]) {
      const wing = new THREE.Group();
      wing.position.x = s * (0.18 + gap + w / 2);
      this.tilt.add(wing);
      add(wing, frame, alu);
      const c = add(wing, sheet, cells);
      c.position.y = 0.0125;
      const b = add(wing, back, kapton);
      b.position.y = -0.019;
      // spar from the hub to the wing
      add(this.tilt, tubeBetween(new THREE.Vector3(s * 0.17, 0, 0), new THREE.Vector3(s * (0.18 + gap + 0.04), 0, 0), 0.018), alu);
      for (const z of [-0.3, 0.3]) {
        add(this.tilt, tubeBetween(new THREE.Vector3(s * 0.12, 0, 0), new THREE.Vector3(s * (0.18 + gap + 0.03), -0.01, z), 0.008), alu);
      }
    }

    this.yawAngle = 0;
    this.tiltAngle = 0;
    this.normal = new THREE.Vector3(0, 1, 0);
    this.center = new THREE.Vector3();
    this._q = new THREE.Quaternion();
    this._v = new THREE.Vector3();
  }

  /**
   * Two-axis sun tracking. sunDir is in world space; parentQuat is the
   * rover body's world orientation.
   */
  update(dt, sunDir, parentQuat, sunUp) {
    this._q.copy(parentQuat).invert();
    const s = this._v.copy(sunDir).applyQuaternion(this._q);
    let targetYaw = this.yawAngle, targetTilt = 0;
    if (sunUp && s.y > -0.05) {
      targetYaw = Math.atan2(s.x, s.z);
      const elev = Math.asin(THREE.MathUtils.clamp(s.y, -1, 1));
      targetTilt = THREE.MathUtils.clamp(Math.PI / 2 - elev, 0, ARRAY.maxTilt);
    }
    let dy = targetYaw - this.yawAngle;
    dy = Math.atan2(Math.sin(dy), Math.cos(dy));
    this.yawAngle += THREE.MathUtils.clamp(dy, -0.45 * dt, 0.45 * dt);
    this.tiltAngle += THREE.MathUtils.clamp(targetTilt - this.tiltAngle, -0.3 * dt, 0.3 * dt);
    this.yaw.rotation.y = this.yawAngle;
    this.tilt.rotation.x = this.tiltAngle;
    this.tilt.updateWorldMatrix(true, false);
    this.tilt.getWorldQuaternion(this._q);
    this.normal.set(0, 1, 0).applyQuaternion(this._q);
    this.tilt.getWorldPosition(this.center);
  }
}
