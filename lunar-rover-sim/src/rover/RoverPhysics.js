import * as THREE from 'three';
import { RIG } from './RoverModel.js';
import { LUNAR_G, BLEND_START } from '../terrain/constants.js';

const DEG = Math.PI / 180;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const wrapPi = (a) => Math.atan2(Math.sin(a), Math.cos(a));

// rotate (z, y) by angle (positive = +z end goes up)
function rot(z, y, a, out) {
  const c = Math.cos(a), s = Math.sin(a);
  out.z = z * c - y * s;
  out.y = z * s + y * c;
  return out;
}

/**
 * Rover dynamics.
 *
 * Horizontal motion is a drive model (speed + yaw rate with traction and
 * slope effects). The chassis attitude comes from a kinematic rocker-bogie
 * solve against the terrain + rocks under each wheel, followed by a
 * spring/ballistic filter in lunar gravity, so the rover rocks over boulders,
 * floats over crests and lands softly.
 */
export class RoverPhysics {
  constructor(ground) {
    this.ground = ground; // { heightAt(x,z), rockHeightAt(x,z,base) , blockers(x,z,r) }
    this.pos = new THREE.Vector3();
    this.yaw = 0;
    this.pitch = 0;
    this.roll = 0;
    this.v = 0; // forward speed m/s
    this.w = 0; // yaw rate rad/s
    this.vy = 0;
    this.pitchRate = 0;
    this.rollRate = 0;
    this.airborne = false;
    this.airTime = 0;
    this.odometer = 0;
    this.maxSpeed = 2.2;
    this.boost = 1;
    this.collided = 0;
    this.powerLimit = 1; // 0..1 from the power system

    this.controls = { throttle: 0, steer: 0, brake: false, boost: false };
    this.pose = {
      rocker: { L: 0, R: 0 },
      bogie: { L: 0, R: 0 },
      steer: [0, 0, 0, 0, 0, 0],
      spin: [0, 0, 0, 0, 0, 0],
    };
    this.wheelContact = new Array(6).fill(true);
    this.wheelWorld = RIG.wheels.map(() => new THREE.Vector3());
    this.wheelSpeed = new Array(6).fill(0);

    this.quaternion = new THREE.Quaternion();
    this._sol = { L: { a: 0, b: 0 }, R: { a: 0, b: 0 } };
    this._tmp = { z: 0, y: 0 };
    this._tmp2 = { z: 0, y: 0 };
    this._e = new THREE.Euler(0, 0, 0, 'YXZ');
    this._v = new THREE.Vector3();
    this._target = { y: 0, pitch: 0, roll: 0 };
    this._poseT = { rL: 0, rR: 0, bL: 0, bR: 0 };
  }

  reset(x, z, yaw = 0) {
    this.pos.set(x, 0, z);
    this.yaw = yaw;
    this.v = this.w = this.vy = this.pitchRate = this.rollRate = 0;
    this._sol.L.a = this._sol.L.b = this._sol.R.a = this._sol.R.b = 0;
    this._solve();
    this.pose.rocker.L = this._poseT.rL; this.pose.rocker.R = this._poseT.rR;
    this.pose.bogie.L = this._poseT.bL; this.pose.bogie.R = this._poseT.bR;
    this.pos.y = this._target.y;
    this.pitch = this._target.pitch;
    this.roll = this._target.roll;
    this.airborne = false;
    this._updateQuaternion();
  }

  /** Height of the wheel centre when resting at (x,z), wheel rolling along (fx,fz). */
  wheelCenterHeight(x, z, fx, fz) {
    const r = RIG.wheelRadius;
    let best = -Infinity;
    const lx = -fz, lz = fx; // lateral
    for (let i = -2; i <= 2; i++) {
      const t = i * 0.42 * r;
      const up = Math.sqrt(r * r - t * t);
      for (let j = -1; j <= 1; j += 2) {
        const px = x + fx * t + lx * j * 0.13;
        const pz = z + fz * t + lz * j * 0.13;
        const h = this.ground.surfaceAt(px, pz) + up;
        if (h > best) best = h;
      }
    }
    return best;
  }

  // 2D rocker-bogie solve for one side. Returns pivot height & angles.
  _solveSide(sideKey, s, yaw) {
    const fx = Math.sin(yaw), fz = Math.cos(yaw);
    const rx = Math.cos(yaw), rz = -Math.sin(yaw); // +X of model in world
    const P0 = RIG.rockerPivot, B0 = RIG.bogiePivot;
    const W = RIG.wheels.filter((w) => w.side === s);
    const F0 = W.find((w) => w.pos === 'F').c, M0 = W.find((w) => w.pos === 'M').c, R0 = W.find((w) => w.pos === 'R').c;
    const sol = this._sol[sideKey];
    let a = sol.a, b = sol.b;
    const t = this._tmp;
    let pivotY = 0;
    const px = this.pos.x, pz = this.pos.z;
    const cosP = Math.cos(this.pitch);
    const cF = [0, 0, 0];
    for (let it = 0; it < 3; it++) {
      // wheel z positions (body frame, along heading) from the current angles
      rot(B0.z - P0.z, B0.y - P0.y, a, t);
      const Bz = P0.z + t.z;
      rot(F0.z - P0.z, F0.y - P0.y, a, t);
      const Fz = P0.z + t.z;
      rot(M0.z - B0.z, M0.y - B0.y, b, t);
      const Mz = Bz + t.z;
      rot(R0.z - B0.z, R0.y - B0.y, b, t);
      const Rz = Bz + t.z;
      const zs = [Fz, Mz, Rz], xs = [F0.x, M0.x, R0.x];
      for (let k = 0; k < 3; k++) {
        const wx = px + fx * zs[k] * cosP + rx * xs[k];
        const wz = pz + fz * zs[k] * cosP + rz * xs[k];
        cF[k] = this.wheelCenterHeight(wx, wz, fx, fz);
      }
      const [yF, yM, yR] = cF;
      // bogie angle from middle & rear wheel centres
      const b0 = Math.atan2(M0.y - R0.y, M0.z - R0.z);
      b = Math.atan2(yM - yR, Math.max(0.3, Mz - Rz)) - b0;
      // bogie pivot (average of the two wheel constraints)
      rot(M0.z - B0.z, M0.y - B0.y, b, t);
      const bm = { z: Mz - t.z, y: yM - t.y };
      rot(R0.z - B0.z, R0.y - B0.y, b, t);
      const bpz = 0.5 * (bm.z + (Rz - t.z)), bpy = 0.5 * (bm.y + (yR - t.y));
      // rocker angle from bogie pivot to front wheel
      const a0 = Math.atan2(F0.y - B0.y, F0.z - B0.z);
      a = Math.atan2(yF - bpy, Math.max(0.3, Fz - bpz)) - a0;
      rot(P0.z - B0.z, P0.y - B0.y, a, t);
      pivotY = bpy + t.y;
      b = b; // bogie absolute angle
    }
    sol.a = a;
    sol.b = b;
    sol.pivotY = pivotY;
    sol.heights = cF.slice();
    return sol;
  }

  _solve() {
    const L = this._solveSide('L', 1, this.yaw);
    const R = this._solveSide('R', -1, this.yaw);
    const track = RIG.wheels[0].c.x - RIG.wheels[3].c.x; // ~2.1 m
    const pitch = 0.5 * (L.a + R.a);
    const roll = Math.atan2(L.pivotY - R.pivotY, track);
    const pivotY = 0.5 * (L.pivotY + R.pivotY);
    // body origin below the rocker pivot midpoint
    this._e.set(-pitch, this.yaw, roll, 'YXZ');
    this._v.copy(RIG.rockerPivot).applyEuler(this._e);
    this._target.y = pivotY - this._v.y;
    this._target.pitch = pitch;
    this._target.roll = roll;
    // articulation relative to the body (differential keeps them opposite)
    const pt = this._poseT;
    pt.rL = L.a - pitch;
    pt.rR = R.a - pitch;
    pt.bL = L.b - L.a;
    pt.bR = R.b - R.a;
    return this._target;
  }

  _updateQuaternion() {
    this._e.set(-this.pitch, this.yaw, this.roll, 'YXZ');
    this.quaternion.setFromEuler(this._e);
  }

  step(dt) {
    const c = this.controls;
    const g = LUNAR_G;
    const vmax = this.maxSpeed * (c.boost ? 2 : 1) * this.powerLimit;
    const grounded = !this.airborne;

    // --- drive ------------------------------------------------------------
    const pivotTurn = Math.abs(c.throttle) < 0.05 && Math.abs(c.steer) > 0.05 && Math.abs(this.v) < 0.25;
    let targetV = c.throttle * vmax;
    if (pivotTurn) targetV = 0;
    const slope = this.pitch;
    const tractionLoss = clamp((Math.abs(slope) - 24 * DEG) / (12 * DEG), 0, 1);
    if (grounded) {
      const accel = c.brake ? 2.2 : Math.sign(targetV - this.v) === Math.sign(this.v) || this.v === 0 ? 0.9 : 1.6;
      const dv = clamp(targetV - this.v, -accel * dt, accel * dt) * (1 - 0.8 * tractionLoss);
      this.v += c.brake ? clamp(-this.v, -2.2 * dt, 2.2 * dt) : dv;
      // gravity along the slope (only rolls the rover when traction is lost)
      this.v += -g * Math.sin(slope) * dt * (0.15 + 0.85 * tractionLoss);
      // rolling resistance
      this.v -= Math.sign(this.v) * Math.min(Math.abs(this.v), 0.05 * dt);
    }

    // yaw
    const steerMax = 32 * DEG;
    let targetW;
    if (pivotTurn) targetW = c.steer * 0.55 * (c.boost ? 1.6 : 1) * this.powerLimit;
    else {
      targetW = (this.v * Math.tan(c.steer * steerMax)) / 1.12;
      // lateral grip in lunar gravity limits how hard the rover can turn at speed
      const wGrip = (0.75 * g) / Math.max(0.3, Math.abs(this.v));
      targetW = clamp(targetW, -wGrip, wGrip);
    }
    if (grounded) this.w += clamp(targetW - this.w, -2.5 * dt, 2.5 * dt);
    this.yaw = wrapPi(this.yaw + this.w * dt);

    // horizontal motion
    const fx = Math.sin(this.yaw), fz = Math.cos(this.yaw);
    const hv = this.v * Math.cos(this.pitch);
    const nx = this.pos.x + fx * hv * dt;
    const nz = this.pos.z + fz * hv * dt;
    const limit = BLEND_START - 20;
    const block = this.ground.collide(nx, nz, this.yaw);
    if (block || Math.abs(nx) > limit || Math.abs(nz) > limit) {
      if (block && Math.abs(nx) <= limit && Math.abs(nz) <= limit) {
        this.pos.x = nx + block.x;
        this.pos.z = nz + block.z;
      }
      this.collided = 0.4;
      this.v *= -0.15;
    } else {
      this.pos.x = nx;
      this.pos.z = nz;
    }
    this.odometer += Math.abs(hv * dt);
    this.collided = Math.max(0, this.collided - dt);

    // --- suspension & attitude ------------------------------------------
    const tgt = this._solve();
    // the linkage solve re-samples rocks and grains every step; low-pass the
    // articulation so wheels and their shadows do not shake
    if (!this.airborne) {
      const k = 1 - Math.exp(-dt / 0.12);
      const pt = this._poseT, po = this.pose;
      po.rocker.L += (pt.rL - po.rocker.L) * k;
      po.rocker.R += (pt.rR - po.rocker.R) * k;
      po.bogie.L += (pt.bL - po.bogie.L) * k;
      po.bogie.R += (pt.bR - po.bogie.R) * k;
    }
    const k = 90, d = 2 * Math.sqrt(k) * 0.9;
    const above = this.pos.y - tgt.y;
    if (above > 0.03) {
      // ballistic in lunar gravity
      this.airborne = true;
      this.airTime += dt;
      this.vy -= g * dt;
      this.pitchRate *= 1 - 0.3 * dt;
      this.rollRate *= 1 - 0.3 * dt;
    } else {
      const wasAir = this.airborne;
      this.airborne = false;
      this.airTime = 0;
      let ay = k * (tgt.y - this.pos.y) - d * this.vy;
      ay = Math.max(ay, -g);
      this.vy += ay * dt;
      const kp = 60, dp = 2 * Math.sqrt(kp) * 0.85;
      this.pitchRate += (kp * (tgt.pitch - this.pitch) - dp * this.pitchRate) * dt;
      this.rollRate += (kp * (tgt.roll - this.roll) - dp * this.rollRate) * dt;
      if (wasAir) this.landing = Math.min(1, Math.abs(this.vy) * 0.6);
    }
    this.pos.y += this.vy * dt;
    // cannot sink into the ground (small compliance)
    if (this.pos.y < tgt.y - 0.04) {
      const push = (tgt.y - 0.04 - this.pos.y) / dt;
      this.pos.y = tgt.y - 0.04;
      this.vy = Math.max(this.vy, Math.min(push, 3.5));
    }
    this.pitch += this.pitchRate * dt;
    this.roll += this.rollRate * dt;
    // keep attitude near terrain when grounded
    if (!this.airborne) {
      this.pitch = clamp(this.pitch, tgt.pitch - 0.12, tgt.pitch + 0.12);
      this.roll = clamp(this.roll, tgt.roll - 0.12, tgt.roll + 0.12);
    }
    this._updateQuaternion();

    // --- wheels -------------------------------------------------------------
    for (let i = 0; i < 6; i++) {
      const w = RIG.wheels[i];
      // contact velocity in body frame (x lateral, z forward)
      const vx = -this.w * w.c.z, vz = this.v + this.w * w.c.x;
      let steer = 0;
      let speed = vz;
      if (w.steer && (Math.abs(vx) > 1e-3 || Math.abs(vz) > 1e-3)) {
        steer = Math.atan2(vx, vz);
        speed = Math.hypot(vx, vz);
        if (steer > Math.PI / 2) { steer -= Math.PI; speed = -speed; }
        else if (steer < -Math.PI / 2) { steer += Math.PI; speed = -speed; }
      } else if (w.steer) {
        steer = this.pose.steer[i];
      }
      if (pivotTurn && !w.steer) speed = vz;
      const ds = clamp(steer - this.pose.steer[i], -2.5 * dt, 2.5 * dt);
      this.pose.steer[i] += ds;
      this.wheelSpeed[i] = speed;
      this.pose.spin[i] += (speed / w.radius) * dt;
    }
    if (this.airborne) {
      // suspension droops while flying
      for (const s of ['L', 'R']) {
        this.pose.rocker[s] *= 1 - 2 * dt;
        this.pose.bogie[s] *= 1 - 2 * dt;
      }
    }
  }

  /** World positions of the wheel bottoms (for tracks & dust). */
  updateWheelWorld(model) {
    for (let i = 0; i < 6; i++) {
      const node = model.wheelNodes[i];
      node.getWorldPosition(this.wheelWorld[i]);
      this.wheelWorld[i].y -= RIG.wheels[i].radius;
      const gy = this.ground.surfaceAt(this.wheelWorld[i].x, this.wheelWorld[i].z);
      this.wheelContact[i] = this.wheelWorld[i].y - gy < 0.06;
    }
  }

  get speed() {
    return this.v;
  }
}
