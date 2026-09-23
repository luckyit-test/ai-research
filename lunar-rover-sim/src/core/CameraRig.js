import * as THREE from 'three';

const MODES = ['chase', 'orbit', 'mast', 'cinematic'];
export const MODE_NAMES = {
  chase: 'Камера: сопровождение',
  orbit: 'Камера: орбита',
  mast: 'Камера: Mastcam-Z',
  cinematic: 'Камера: кино',
};

const damp = (a, b, lambda, dt) => THREE.MathUtils.lerp(a, b, 1 - Math.exp(-lambda * dt));

export class CameraRig {
  constructor(camera, dom, groundHeight) {
    this.camera = camera;
    this.dom = dom;
    this.groundHeight = groundHeight;
    this.mode = 'chase';
    this.yawOff = 0.12;
    this.pitch = 0.44;
    this.dist = 7.8;
    this.orbitYaw = 0.8;
    this.orbitPitch = 0.35;
    this.orbitDist = 12;
    this.mastYaw = 0;
    this.mastPitch = -0.08;
    this.cineT = 0;
    this.pos = new THREE.Vector3();
    this.look = new THREE.Vector3();
    this._first = true;
    this._drag = null;
    this.lastInput = 0;

    dom.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 && e.button !== 2) return;
      this._drag = { x: e.clientX, y: e.clientY, id: e.pointerId };
      dom.setPointerCapture(e.pointerId);
    });
    dom.addEventListener('pointermove', (e) => {
      if (!this._drag || this._drag.id !== e.pointerId) return;
      const dx = (e.clientX - this._drag.x) / dom.clientHeight;
      const dy = (e.clientY - this._drag.y) / dom.clientHeight;
      this._drag.x = e.clientX;
      this._drag.y = e.clientY;
      this.rotate(dx * 3.2, dy * 2.2);
    });
    const end = (e) => {
      if (this._drag && this._drag.id === e.pointerId) this._drag = null;
    };
    dom.addEventListener('pointerup', end);
    dom.addEventListener('pointercancel', end);
    dom.addEventListener('contextmenu', (e) => e.preventDefault());
    dom.addEventListener('wheel', (e) => {
      e.preventDefault();
      this.zoom(Math.exp(e.deltaY * 0.001));
    }, { passive: false });
  }

  rotate(dx, dy) {
    this.lastInput = performance.now();
    if (this.mode === 'chase') {
      this.yawOff -= dx;
      this.pitch = THREE.MathUtils.clamp(this.pitch + dy, -0.05, 1.35);
    } else if (this.mode === 'orbit' || this.mode === 'cinematic') {
      this.orbitYaw -= dx;
      this.orbitPitch = THREE.MathUtils.clamp(this.orbitPitch + dy, -0.1, 1.5);
    } else if (this.mode === 'mast') {
      this.mastYaw -= dx * 0.8;
      this.mastPitch = THREE.MathUtils.clamp(this.mastPitch - dy * 0.8, -1.2, 0.9);
    }
  }

  zoom(f) {
    if (this.mode === 'chase') this.dist = THREE.MathUtils.clamp(this.dist * f, 4, 60);
    else if (this.mode === 'orbit' || this.mode === 'cinematic') this.orbitDist = THREE.MathUtils.clamp(this.orbitDist * f, 3.5, 400);
    else if (this.mode === 'mast') this.camera.fov = THREE.MathUtils.clamp(this.camera.fov * f, 8, 70);
    this.camera.updateProjectionMatrix();
  }

  next() {
    const i = MODES.indexOf(this.mode);
    this.setMode(MODES[(i + 1) % MODES.length]);
    return this.mode;
  }

  setMode(m) {
    this.mode = m;
    this.camera.fov = m === 'mast' ? 48 : 50;
    this.camera.updateProjectionMatrix();
    this._first = true;
  }

  update(dt, rover, physics) {
    const cam = this.camera;
    const rp = rover.root.position;
    const yaw = physics.yaw;
    const target = new THREE.Vector3(rp.x, rp.y + 1.1, rp.z);
    const desired = new THREE.Vector3();
    const look = new THREE.Vector3();

    if (this.mode === 'chase') {
      // relax the manual yaw offset slowly back behind the rover while driving
      if (performance.now() - this.lastInput > 2500 && Math.abs(physics.v) > 0.3) {
        this.yawOff = damp(this.yawOff, 0.2 * Math.sign(this.yawOff || 1), 0.4, dt);
      }
      const a = yaw + Math.PI + this.yawOff;
      const hd = this.dist * Math.cos(this.pitch);
      desired.set(rp.x + Math.sin(a) * hd, rp.y + 1.0 + this.dist * Math.sin(this.pitch), rp.z + Math.cos(a) * hd);
      look.set(rp.x + Math.sin(yaw) * 6.5, rp.y + 0.2, rp.z + Math.cos(yaw) * 6.5);
    } else if (this.mode === 'orbit' || this.mode === 'cinematic') {
      if (this.mode === 'cinematic') {
        this.cineT += dt;
        this.orbitYaw += dt * 0.07;
        this.orbitPitch = 0.12 + 0.18 * (0.5 + 0.5 * Math.sin(this.cineT * 0.11));
        this.orbitDist = 9 + 7 * (0.5 + 0.5 * Math.sin(this.cineT * 0.07 + 1.3));
      }
      const hd = this.orbitDist * Math.cos(this.orbitPitch);
      desired.set(target.x + Math.sin(this.orbitYaw) * hd, target.y + this.orbitDist * Math.sin(this.orbitPitch), target.z + Math.cos(this.orbitYaw) * hd);
      look.copy(target);
    } else if (this.mode === 'mast') {
      rover.mastHeadWorld(desired);
      const a = yaw + this.mastYaw;
      look.set(desired.x + Math.sin(a) * Math.cos(this.mastPitch) * 10, desired.y + Math.sin(this.mastPitch) * 10, desired.z + Math.cos(a) * Math.cos(this.mastPitch) * 10);
    }

    // keep above the ground
    if (this.mode !== 'mast') {
      const gh = this.groundHeight(desired.x, desired.z) + 0.45;
      if (desired.y < gh) desired.y = gh;
    }

    if (this._first || this.mode === 'mast') {
      this.pos.copy(desired);
      this.look.copy(look);
      this._first = false;
    } else {
      const k = this.mode === 'chase' ? 5 : 8;
      this.pos.x = damp(this.pos.x, desired.x, k, dt);
      this.pos.y = damp(this.pos.y, desired.y, k, dt);
      this.pos.z = damp(this.pos.z, desired.z, k, dt);
      this.look.x = damp(this.look.x, look.x, 10, dt);
      this.look.y = damp(this.look.y, look.y, 10, dt);
      this.look.z = damp(this.look.z, look.z, 10, dt);
      const gh = this.groundHeight(this.pos.x, this.pos.z) + 0.4;
      if (this.pos.y < gh) this.pos.y = gh;
    }
    cam.position.copy(this.pos);
    cam.lookAt(this.look);
    cam.updateMatrixWorld();
  }
}
