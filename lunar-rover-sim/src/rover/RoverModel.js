import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

// Model space: +Z forward, +Y up, +X = rover's left, origin on the ground
// below the centre of the chassis. Units: metres (1:1 NASA/JPL model).
export const RIG = {
  wheelRadius: 0.263,
  rockerPivot: new THREE.Vector3(0, 0.94, 0.21),
  bogiePivot: new THREE.Vector3(0, 0.70, -0.53),
  // nominal wheel centres, refined from the geometry at load time
  wheels: [
    { id: 'FL', side: 1, pos: 'F', c: new THREE.Vector3(1.06, 0.263, 1.10), steer: true },
    { id: 'ML', side: 1, pos: 'M', c: new THREE.Vector3(1.18, 0.263, -0.08), steer: false },
    { id: 'RL', side: 1, pos: 'R', c: new THREE.Vector3(1.06, 0.263, -1.16), steer: true },
    { id: 'FR', side: -1, pos: 'F', c: new THREE.Vector3(-1.06, 0.263, 1.10), steer: true },
    { id: 'MR', side: -1, pos: 'M', c: new THREE.Vector3(-1.18, 0.263, -0.08), steer: false },
    { id: 'RR', side: -1, pos: 'R', c: new THREE.Vector3(-1.06, 0.263, -1.16), steer: true },
  ],
  mastHeadLocal: new THREE.Vector3(-0.63, 2.05, 0.73),
};

function rotateAboutWorldAxis(node, axis, angle) {
  const pq = new THREE.Quaternion();
  node.parent.getWorldQuaternion(pq);
  const qw = new THREE.Quaternion().setFromAxisAngle(axis.clone().normalize(), angle);
  node.quaternion.premultiply(pq.clone().invert().multiply(qw).multiply(pq));
  node.updateMatrixWorld(true);
}

function distSegment2(pz, py, az, ay, bz, by) {
  const vz = bz - az, vy = by - ay;
  const t = Math.max(0, Math.min(1, ((pz - az) * vz + (py - ay) * vy) / (vz * vz + vy * vy)));
  const dz = pz - (az + vz * t), dy = py - (ay + vy * t);
  return dz * dz + dy * dy;
}

/**
 * Splits the triangles of a mesh into parts. Geometry is baked into model
 * space; each returned part shares the vertex buffers of the source.
 */
function splitMesh(mesh, toModel, classify) {
  const geo = mesh.geometry.clone();
  geo.applyMatrix4(toModel);
  const pos = geo.attributes.position;
  const index = geo.index ? geo.index.array : null;
  const triCount = index ? index.length / 3 : pos.count / 3;
  const parts = new Map();
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  for (let t = 0; t < triCount; t++) {
    const i0 = index ? index[t * 3] : t * 3;
    const i1 = index ? index[t * 3 + 1] : t * 3 + 1;
    const i2 = index ? index[t * 3 + 2] : t * 3 + 2;
    a.fromBufferAttribute(pos, i0); b.fromBufferAttribute(pos, i1); c.fromBufferAttribute(pos, i2);
    const cx = (a.x + b.x + c.x) / 3, cy = (a.y + b.y + c.y) / 3, cz = (a.z + b.z + c.z) / 3;
    const key = classify(cx, cy, cz);
    if (!parts.has(key)) parts.set(key, []);
    parts.get(key).push(i0, i1, i2);
  }
  const out = new Map();
  for (const [key, idx] of parts) {
    const g = new THREE.BufferGeometry();
    for (const name in geo.attributes) g.setAttribute(name, geo.attributes[name]);
    g.setIndex(idx);
    // bounds of the referenced vertices only (the buffers are shared)
    const box = new THREE.Box3();
    const v = new THREE.Vector3();
    for (let i = 0; i < idx.length; i++) box.expandByPoint(v.fromBufferAttribute(pos, idx[i]));
    g.boundingBox = box;
    g.boundingSphere = box.getBoundingSphere(new THREE.Sphere());
    out.set(key, g);
  }
  return out;
}

export class RoverModel {
  static async load(url, onProgress) {
    const gltf = await new GLTFLoader().loadAsync(url, (e) => {
      if (onProgress && e.total) onProgress(e.loaded / e.total);
    });
    return new RoverModel(gltf.scene);
  }

  constructor(scene) {
    this.root = new THREE.Group();
    this.root.name = 'rover';
    this.materials = new Set();
    scene.updateMatrixWorld(true);

    // Deploy the Remote Sensing Mast (the model ships stowed).
    const mastBase = scene.getObjectByName('bottom');
    const mastTop = scene.getObjectByName('top');
    if (mastBase && mastTop) {
      rotateAboutWorldAxis(mastBase, new THREE.Vector3(0.425, 0, 0.905), Math.PI / 2);
      rotateAboutWorldAxis(mastTop, new THREE.Vector3(0, 1, 0), -Math.PI / 2);
      this.mastHead = scene.getObjectByName('head');
    }
    scene.updateMatrixWorld(true);
    if (this.mastHead) {
      // camera eye just in front of the Mastcam-Z head
      const hb = new THREE.Box3().setFromObject(this.mastHead);
      RIG.mastHeadLocal.set((hb.min.x + hb.max.x) / 2, hb.max.y - 0.04, hb.max.z + 0.08);
    }

    const wheelsNode = scene.getObjectByName('Wheels_objs');
    const suspNode = scene.getObjectByName('suspension');
    const toModel = new THREE.Matrix4();

    // --- wheels: cluster triangles by nearest nominal wheel centre --------
    const wheelMeshes = [];
    wheelsNode?.traverse((o) => o.isMesh && wheelMeshes.push(o));
    const wheelParts = RIG.wheels.map(() => []);
    for (const m of wheelMeshes) {
      toModel.copy(m.matrixWorld);
      const parts = splitMesh(m, toModel, (x, y, z) => {
        let best = 0, bd = Infinity;
        RIG.wheels.forEach((w, i) => {
          const d = (x - w.c.x) ** 2 + (z - w.c.z) ** 2;
          if (d < bd) { bd = d; best = i; }
        });
        return best;
      });
      for (const [k, g] of parts) wheelParts[k].push({ geometry: g, material: m.material });
    }
    // refine wheel centres from geometry bounds
    wheelParts.forEach((list, i) => {
      if (!list.length) return;
      const box = new THREE.Box3();
      list.forEach((p) => box.union(p.geometry.boundingBox));
      const c = box.getCenter(new THREE.Vector3());
      RIG.wheels[i].c.set(c.x, (box.max.y - box.min.y) / 2 + box.min.y, c.z);
      RIG.wheels[i].radius = (box.max.y - box.min.y) / 2;
    });
    RIG.wheelRadius = RIG.wheels.reduce((s, w) => s + (w.radius || RIG.wheelRadius), 0) / RIG.wheels.length;

    // --- suspension: rocker / bogie / steering assemblies ----------------
    const suspMeshes = [];
    suspNode?.traverse((o) => o.isMesh && suspMeshes.push(o));
    const rp = RIG.rockerPivot, bp = RIG.bogiePivot;
    const classifySusp = (x, y, z) => {
      if (Math.abs(x) < 0.6) return 'body';
      const side = x > 0 ? 'L' : 'R';
      const s = x > 0 ? 1 : -1;
      const wf = RIG.wheels.find((w) => w.side === s && w.pos === 'F').c;
      const wm = RIG.wheels.find((w) => w.side === s && w.pos === 'M').c;
      const wr = RIG.wheels.find((w) => w.side === s && w.pos === 'R').c;
      const dF = Math.hypot(x - wf.x, z - wf.z), dR = Math.hypot(x - wr.x, z - wr.z);
      if (dF < 0.21 && y < 1.02) return 'steerF' + side;
      if (dR < 0.21 && y < 1.02) return 'steerR' + side;
      if (Math.hypot(x - wm.x, z - wm.z) < 0.27 && y < 0.62) return 'bogie' + side;
      if (z < bp.z - 0.06) return 'bogie' + side;
      if (z < rp.z - 0.08 && z > bp.z - 0.06) {
        const dRock = distSegment2(z, y, rp.z, rp.y, bp.z, bp.y);
        const dBog = distSegment2(z, y, bp.z, bp.y, wm.z + 0.06, 0.42);
        return dBog < dRock ? 'bogie' + side : 'rocker' + side;
      }
      return 'rocker' + side;
    };
    const suspParts = new Map();
    for (const m of suspMeshes) {
      toModel.copy(m.matrixWorld);
      for (const [k, g] of splitMesh(m, toModel, classifySusp)) {
        if (!suspParts.has(k)) suspParts.set(k, []);
        suspParts.get(k).push({ geometry: g, material: m.material });
      }
    }

    // --- body: everything else keeps its hierarchy -------------------------
    wheelsNode?.parent?.remove(wheelsNode);
    suspNode?.parent?.remove(suspNode);
    this.body = new THREE.Group();
    this.body.name = 'body';
    this.body.add(scene);
    this.root.add(this.body);

    const addParts = (parent, list, pivot) => {
      for (const p of list || []) {
        const mesh = new THREE.Mesh(p.geometry, p.material);
        mesh.position.copy(pivot).negate();
        parent.add(mesh);
      }
    };
    addParts(this.body, suspParts.get('body'), new THREE.Vector3());

    // articulated chain per side
    this.rockers = {};
    this.bogies = {};
    this.wheelNodes = [];
    this.steerNodes = [];
    for (const side of ['L', 'R']) {
      const s = side === 'L' ? 1 : -1;
      const rocker = new THREE.Group();
      rocker.position.copy(rp);
      this.body.add(rocker);
      addParts(rocker, suspParts.get('rocker' + side), rp);
      const bogie = new THREE.Group();
      bogie.position.copy(bp).sub(rp);
      rocker.add(bogie);
      addParts(bogie, suspParts.get('bogie' + side), bp);
      this.rockers[side] = rocker;
      this.bogies[side] = bogie;

      RIG.wheels.forEach((w, i) => {
        if (w.side !== s) return;
        const parent = w.pos === 'F' ? rocker : bogie;
        const parentPivot = w.pos === 'F' ? rp : bp;
        const steer = new THREE.Group();
        steer.position.copy(w.c).sub(parentPivot);
        parent.add(steer);
        if (w.steer) addParts(steer, suspParts.get((w.pos === 'F' ? 'steerF' : 'steerR') + side), w.c);
        const spin = new THREE.Group();
        steer.add(spin);
        addParts(spin, wheelParts[i], w.c);
        this.wheelNodes[i] = spin;
        this.steerNodes[i] = steer;
      });
    }

    // --- materials & shadows ----------------------------------------------
    this.root.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = true;
      o.receiveShadow = true;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of mats) {
        if ('transmission' in m && m.transmission > 0) {
          m.transmission = 0;
          m.opacity = 1;
        }
        m.envMapIntensity = 1.0;
        this.materials.add(m);
      }
    });

    this._tmp = new THREE.Vector3();
  }

  /** Apply articulation. state: rocker{L,R}, bogie{L,R}, steer[6], spin[6] (radians). */
  applyPose(state) {
    this.rockers.L.rotation.x = -state.rocker.L;
    this.rockers.R.rotation.x = -state.rocker.R;
    this.bogies.L.rotation.x = -state.bogie.L;
    this.bogies.R.rotation.x = -state.bogie.R;
    for (let i = 0; i < 6; i++) {
      this.steerNodes[i].rotation.y = state.steer[i];
      this.wheelNodes[i].rotation.x = state.spin[i];
    }
  }

  mastHeadWorld(out) {
    this.root.updateWorldMatrix(true, false);
    return out.copy(RIG.mastHeadLocal).applyMatrix4(this.root.matrixWorld);
  }
}
