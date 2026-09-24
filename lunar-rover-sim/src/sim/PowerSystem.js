import { ARRAY } from '../rover/SolarArray.js';
import { MOON_RADIUS } from '../terrain/constants.js';

const SOLAR_CONSTANT = 1361; // W/m² at 1 AU, no atmosphere
const CELL_EFFICIENCY = 0.29; // triple-junction GaAs
const SUN_RADIUS = 0.00465; // angular radius, rad

/**
 * Battery + solar array energy balance, integrated in real (wall-clock)
 * seconds. The Sun's position may run accelerated, the energy budget does not.
 */
export class PowerSystem {
  constructor(data, { capacityWh = 4000, soc = 0.78 } = {}) {
    this.data = data;
    this.capacity = capacityWh;
    this.energy = capacityWh * soc;
    this.solarW = 0;
    this.loadW = 0;
    this.sunVis = 1;
    this.incidence = 1;
    this.mode = 'normal'; // normal | low | depleted
    this._visT = 1;
  }

  get soc() {
    return this.energy / this.capacity;
  }

  /** Soft visibility of the Sun disk from a point, by marching the height map. */
  sunVisibility(p, sunDir) {
    if (sunDir.y < -SUN_RADIUS * 2) return 0;
    const horiz = Math.hypot(sunDir.x, sunDir.z) || 1e-6;
    const dx = sunDir.x / horiz, dz = sunDir.z / horiz;
    const tanE = sunDir.y / horiz;
    let vis = 1;
    let t = 2;
    for (let i = 0; i < 120 && t < 12000; i++) {
      const x = p.x + dx * t, z = p.z + dz * t;
      if (Math.abs(x) > 15500 || Math.abs(z) > 15500) break;
      const hs = this.data.heightAt(x, z) - (t * t) / (2 * MOON_RADIUS);
      const hr = p.y + t * tanE;
      vis = Math.min(vis, (hr - hs) / (t * SUN_RADIUS * 2) + 0.5);
      if (vis <= 0) return 0;
      t += Math.max(1.5, t * 0.06);
    }
    // the part of the disk above the mathematical horizon
    const disk = Math.min(1, Math.max(0, (sunDir.y + SUN_RADIUS) / (2 * SUN_RADIUS)));
    return Math.max(0, Math.min(1, vis)) * disk;
  }

  update(dt, { array, sunDir, physics, night }) {
    // terrain shadowing is expensive enough to refresh a few times a second
    this._visT += dt;
    if (this._visT > 0.25) {
      this._visT = 0;
      this.sunVis = this.sunVisibility(array.center, sunDir);
    }
    this.incidence = Math.max(0, array.normal.dot(sunDir));
    this.solarW = ARRAY.area * CELL_EFFICIENCY * SOLAR_CONSTANT * this.incidence * this.sunVis * 0.96;

    const c = physics.controls;
    const speed = Math.abs(physics.v);
    const climb = Math.max(0, Math.sin(physics.pitch) * Math.sign(physics.v || 1));
    let drive = 0;
    if (speed > 0.02 || Math.abs(physics.w) > 0.02) {
      drive = 90 + 170 * speed * (1 + climb * 6) + 60 * Math.abs(physics.w);
      if (c.boost) drive *= 1.25;
    }
    const avionics = 95;
    const heaters = night ? 210 : 35;
    this.loadW = avionics + heaters + drive;

    this.energy += ((this.solarW - this.loadW) * dt) / 3600;
    this.energy = Math.max(0, Math.min(this.capacity, this.energy));

    const soc = this.soc;
    this.mode = soc <= 0.002 ? 'depleted' : soc < 0.08 ? 'low' : 'normal';
    // what the drive system is allowed to do
    // a flat battery still allows an emergency crawl so the rover is never stuck
    return this.mode === 'depleted' ? 0.15 : this.mode === 'low' ? 0.35 : 1;
  }

  /** Human readable estimate of time to full / empty (real minutes). */
  eta() {
    const net = this.solarW - this.loadW;
    if (Math.abs(net) < 1) return null;
    const wh = net > 0 ? this.capacity - this.energy : this.energy;
    return { charging: net > 0, minutes: (wh / Math.abs(net)) * 60 };
  }
}
