import * as THREE from 'three';
import { SunLight } from 'three/examples/jsm/lights/SunLight.js';
import { TerrainData } from './terrain/TerrainData.js';
import { TerrainMesh } from './terrain/TerrainMesh.js';
import { ShadowBaker } from './terrain/ShadowBaker.js';
import { CSM_FAR } from './terrain/constants.js';
import { Sky } from './render/Sky.js';
import { Post } from './render/Post.js';
import { lunarUniforms, patchMaterial } from './render/lunarShading.js';
import { RockField } from './rocks/RockField.js';
import { RoverModel, RIG } from './rover/RoverModel.js';
import { RoverPhysics } from './rover/RoverPhysics.js';
import { Tracks } from './fx/Tracks.js';
import { Dust } from './fx/Dust.js';
import { CameraRig, MODE_NAMES } from './core/CameraRig.js';
import { Input } from './core/Input.js';
import { Hud } from './ui/Hud.js';

const params = new URLSearchParams(location.search);
const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent) || (navigator.maxTouchPoints > 1 && innerWidth < 900);

const PRESETS = {
  low: { pr: 0.75, seg: 32, lodK: 1.3, macro: 1024, far: 512, detail: 512, micro: 256, shadow: 1024, ao: false, bloom: false, smaa: true, halfAO: true, rocks: 0.6, tracks: 2048 },
  medium: { pr: 1, seg: 48, lodK: 1.45, macro: 2048, far: 1024, detail: 1024, micro: 512, shadow: 2048, ao: true, bloom: true, smaa: true, halfAO: true, rocks: 0.8, tracks: 2048 },
  high: { pr: 1.5, bakedShadow: 2048, seg: 64, lodK: 1.6, macro: 2048, far: 1024, detail: 1024, micro: 512, shadow: 2048, ao: true, bloom: true, smaa: true, halfAO: true, rocks: 1, tracks: 4096 },
  ultra: { pr: 2, bakedShadow: 2048, seg: 64, lodK: 2.0, macro: 2048, far: 1024, detail: 1024, micro: 512, shadow: 4096, ao: true, bloom: true, smaa: true, halfAO: false, rocks: 1.3, tracks: 4096 },
};

let savedPrefs = {};
try { savedPrefs = JSON.parse(localStorage.getItem('lunar-rover-prefs') || '{}'); } catch { savedPrefs = {}; }
const savePrefs = () => { try { localStorage.setItem('lunar-rover-prefs', JSON.stringify(savedPrefs)); } catch { /* storage unavailable */ } };

const qualityName = params.get('q') || savedPrefs.quality || (isMobile ? 'low' : 'high');
const Q = PRESETS[qualityName] || PRESETS.high;

const $ = (id) => document.getElementById(id);
const loaderBar = $('loader-bar'), loaderLabel = $('loader-label');
const progress = (f, label) => {
  loaderBar.style.width = `${Math.round(f * 100)}%`;
  if (label) loaderLabel.textContent = label;
};
const nextFrame = () => new Promise((r) => requestAnimationFrame(() => r()));

function fail(msg) {
  const e = $('error');
  e.textContent = msg;
  e.classList.remove('hidden');
  $('loader').classList.add('hidden');
}

async function main() {
  const canvas = $('view');
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance', stencil: false });
  } catch (err) {
    fail('Не удалось создать WebGL2-контекст. Нужен современный браузер с аппаратным ускорением графики.');
    return;
  }
  const gl = renderer.getContext();
  if (!renderer.capabilities.isWebGL2 && !(gl instanceof WebGL2RenderingContext)) {
    fail('Требуется WebGL2.');
    return;
  }
  if (!gl.getExtension('EXT_color_buffer_float')) {
    fail('Видеокарта/браузер не поддерживает рендер в float-текстуры (EXT_color_buffer_float).');
    return;
  }
  const pixelRatio = Math.min(window.devicePixelRatio || 1, Q.pr);
  renderer.setPixelRatio(pixelRatio);
  renderer.setSize(innerWidth, innerHeight);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = savedPrefs.exposure ?? 1.3;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0);
  const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.15, 40000);

  // start loading the rover while the terrain is generated
  const roverPromise = RoverModel.load('./models/perseverance.glb', (f) => {
    if (f < 1) loaderLabel.dataset.model = `${Math.round(f * 100)}%`;
  });

  progress(0.03, 'Генерация рельефа');
  await nextFrame();
  const data = new TerrainData(renderer, { macroRes: Q.macro, farRes: Q.far, detailRes: Q.detail, microRes: Q.micro });
  await data.generate((f, l) => progress(f * 0.6, l));

  // --- sun ---------------------------------------------------------------
  const sunState = {
    az: savedPrefs.sunAz ?? 250,
    el: savedPrefs.sunEl ?? 21,
  };
  const sunDir = new THREE.Vector3();
  const updateSunDir = () => {
    const az = THREE.MathUtils.degToRad(sunState.az), el = THREE.MathUtils.degToRad(sunState.el);
    sunDir.set(Math.cos(el) * Math.sin(az), Math.sin(el), Math.cos(el) * Math.cos(az)).normalize();
  };
  updateSunDir();

  progress(0.62, 'Тени от горизонта');
  await nextFrame();
  const baker = new ShadowBaker(renderer, data, Q.macro <= 1024 ? { macroShadowRes: 512, farShadowRes: 256 } : { macroShadowRes: Q.bakedShadow || 1024, farShadowRes: 512 });
  baker.bake(sunDir);
  lunarUniforms.uSunVisMacro.value = baker.macroRT.texture;
  lunarUniforms.uSunVisFar.value = baker.farRT.texture;

  const sun = new SunLight(0xfff5ea, 3.6);
  sun.position.copy(sunDir);
  sun.castShadow = true;
  sun.shadow.mapSize.set(Q.shadow, Q.shadow);
  sun.shadow.camera.far = CSM_FAR;
  sun.shadow.camera.near = 1;
  sun.shadow.bias = -0.0005;
  sun.shadow.normalBias = 0.035;
  sun.shadow.radius = 1.3;
  scene.add(sun);

  // environment: black sky above, sunlit regolith below (bounce light)
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envScene = new THREE.Scene();
  const envMat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    uniforms: { uGround: { value: new THREE.Color(0.105, 0.098, 0.09) } },
    vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: `uniform vec3 uGround; varying vec3 vP;
      void main(){ vec3 d = normalize(vP); float g = smoothstep(0.04, -0.12, d.y); float hz = exp(-abs(d.y) * 14.0) * 0.35;
      gl_FragColor = vec4(uGround * (g + hz), 1.0); }`,
  });
  envScene.add(new THREE.Mesh(new THREE.SphereGeometry(10, 32, 16), envMat));
  const updateEnv = () => {
    const k = Math.max(0.15, Math.sin(THREE.MathUtils.degToRad(sunState.el)) / Math.sin(THREE.MathUtils.degToRad(21)));
    envMat.uniforms.uGround.value.setRGB(0.085 * k, 0.08 * k, 0.073 * k);
    if (scene.environment) scene.environment.dispose();
    scene.environment = pmrem.fromScene(envScene, 0.02).texture;
  };
  updateEnv();

  // --- world objects ------------------------------------------------------
  progress(0.68, 'Лунный грунт');
  const tracks = new Tracks(renderer, { size: 128, res: Q.tracks });
  const trackUniforms = tracks.uniforms();
  const terrain = new TerrainMesh(data, { ...trackUniforms, uTrackStrength: { value: 1 } }, { segments: Q.seg, casterSegments: 32, lodK: Q.lodK });
  scene.add(terrain.group);

  progress(0.74, 'Камни и валуны');
  await nextFrame();
  const rocks = new RockField(data, data.microTex, { quality: Q.rocks });
  scene.add(rocks.group);

  const sky = new Sky();
  sky.uniforms.uSunDir.value.copy(sunDir);
  sky.uniforms.uStars.value = savedPrefs.stars ? 0.35 : 0;
  scene.add(sky.mesh);

  const dust = new Dust(isMobile ? 5000 : 14000);
  scene.add(dust.points);

  progress(0.8, 'Модель Perseverance (NASA/JPL)');
  let rover;
  try {
    rover = await roverPromise;
  } catch (err) {
    console.error(err);
    fail('Не удалось загрузить модель ровера (models/perseverance.glb). Запустите через HTTP-сервер: npm run dev');
    return;
  }
  for (const m of rover.materials) patchMaterial(m, { brdf: false });
  scene.add(rover.root);

  // --- physics ------------------------------------------------------------
  const ground = {
    surfaceAt: (x, z) => rocks.surfaceAt(x, z, data.heightAt(x, z)),
    collide: (x, z, yaw) => rocks.collide(x, z, yaw),
  };
  const physics = new RoverPhysics(ground);
  physics.maxSpeed = savedPrefs.speed ?? 2.2;

  const spawn = findSpawn(data);
  rocks._buildPhysics(spawn.x, spawn.z);
  physics.reset(spawn.x, spawn.z, spawn.yaw);

  // sun relative to the start heading so the first view reads like a photo
  if (savedPrefs.sunAz === undefined) {
    sunState.az = THREE.MathUtils.radToDeg(spawn.yaw) + 222;
    sunState.az = ((sunState.az % 360) + 360) % 360;
    updateSunDir();
    baker.bake(sunDir);
    sun.position.copy(sunDir);
    sky.uniforms.uSunDir.value.copy(sunDir);
  }
  {
    // Earth hangs low over the terrain ahead-left of the start heading
    const ea = spawn.yaw + THREE.MathUtils.degToRad(38), ee = THREE.MathUtils.degToRad(12);
    sky.uniforms.uEarthDir.value.set(Math.cos(ee) * Math.sin(ea), Math.sin(ee), Math.cos(ee) * Math.cos(ea)).normalize();
  }

  // --- camera, post, input --------------------------------------------------
  const rig = new CameraRig(camera, canvas, (x, z) => data.heightAt(x, z));
  const post = new Post(renderer, scene, camera, { ao: Q.ao, bloom: Q.bloom, smaa: Q.smaa, halfResAO: Q.halfAO });
  const input = new Input();
  const hud = new Hud({ data, physics, rig, sunState });

  const applyToggles = () => {
    const p = savedPrefs;
    if (post.aoPass) post.aoPass.enabled = p.ao !== false;
    if (post.bloomPass) post.bloomPass.enabled = p.bloom !== false;
    post.finalPass.uniforms.uGrain.value = p.film === false ? 0 : 0.035;
    post.finalPass.uniforms.uVignette.value = p.film === false ? 0.12 : 0.32;
    post.finalPass.uniforms.uAberration.value = p.film === false ? 0 : 0.0014;
    sky.uniforms.uStars.value = p.stars ? 0.35 : 0;
    sky.uniforms.uEarth.value = p.earth === false ? 0 : 1;
    dust.enabled = p.dust !== false;
    dust.points.visible = dust.enabled;
    terrain.uniforms.uTrackStrength.value = p.tracks === false ? 0 : 1;
    tracks.enabled = p.tracks !== false;
    $('minimap').classList.toggle('hidden', p.minimap === false);
  };
  applyToggles();

  let shadowRebake = null;
  hud.bindSettings({
    quality: qualityName,
    onQuality: (q) => { savedPrefs.quality = q; savePrefs(); location.search = `?q=${q}`; },
    onSun: (az, el, final) => {
      sunState.az = az; sunState.el = el;
      updateSunDir();
      sun.position.copy(sunDir);
      sky.uniforms.uSunDir.value.copy(sunDir);
      clearTimeout(shadowRebake);
      shadowRebake = setTimeout(() => { baker.bake(sunDir); updateEnv(); }, final ? 0 : 120);
      savedPrefs.sunAz = az; savedPrefs.sunEl = el; savePrefs();
    },
    onExposure: (v) => { renderer.toneMappingExposure = v; savedPrefs.exposure = v; savePrefs(); },
    onSpeed: (v) => { physics.maxSpeed = v; savedPrefs.speed = v; savePrefs(); },
    onToggle: (key, v) => { savedPrefs[key] = v; savePrefs(); applyToggles(); },
    prefs: savedPrefs,
    exposure: renderer.toneMappingExposure,
    speed: physics.maxSpeed,
  });

  input.on('KeyC', () => hud.flashMode(MODE_NAMES[rig.next()]));
  input.on('KeyR', () => {
    physics.reset(physics.pos.x, physics.pos.z, physics.yaw);
    hud.flashMode('Ровер выровнен');
  });
  input.on('KeyG', () => hud.toggle('settings'));
  input.on('KeyH', () => hud.toggle('help'));
  input.on('KeyP', () => {
    post.render(0);
    const a = document.createElement('a');
    a.download = `lunar-rover-${Date.now()}.png`;
    a.href = renderer.domElement.toDataURL('image/png');
    a.click();
  });
  $('b-cam').onclick = () => hud.flashMode(MODE_NAMES[rig.next()]);
  hud.setupTouch(input, isMobile);

  window.addEventListener('resize', () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
    post.setSize(innerWidth, innerHeight);
  });

  // --- simulation loop ---------------------------------------------------------
  const STEP = 1 / 120;
  let acc = 0;
  let last = performance.now();
  const prevContact = RIG.wheels.map(() => new THREE.Vector3());
  const hasPrev = new Array(6).fill(false);
  const rolled = new Array(6).fill(0);
  const tmpV = new THREE.Vector3();
  let frames = 0, fpsT = 0;

  const syncRover = () => {
    rover.root.position.copy(physics.pos);
    rover.root.quaternion.copy(physics.quaternion);
    rover.applyPose(physics.pose);
    rover.root.updateMatrixWorld(true);
  };
  syncRover();
  rig.update(0.016, rover, physics);
  terrain.update(camera);
  rocks.update(camera, true);
  tracks.follow(physics.pos.x, physics.pos.z, trackUniforms);

  const dustColor = new THREE.Color();
  const update = (dt) => {
    acc += dt;
    let steps = 0;
    while (acc >= STEP && steps < 24) {
      physics.step(STEP);
      acc -= STEP;
      steps++;
    }
    if (steps >= 24) acc = 0;
    syncRover();
    physics.updateWheelWorld(rover);

    // tracks & dust
    tracks.follow(physics.pos.x, physics.pos.z, trackUniforms);
    for (let i = 0; i < 6; i++) {
      const c = physics.wheelWorld[i];
      const contact = physics.wheelContact[i];
      if (contact && hasPrev[i]) {
        const d = c.distanceTo(prevContact[i]);
        if (d > 0.015 && d < 1.0) {
          const r0 = rolled[i];
          rolled[i] += d;
          if (tracks.enabled) tracks.addSegment(prevContact[i].x, prevContact[i].z, c.x, c.z, 0.34, r0, rolled[i], 1);
          prevContact[i].copy(c);
        } else if (d >= 1.0) {
          prevContact[i].copy(c);
        }
        const sp = physics.wheelSpeed[i];
        if (Math.abs(sp) > 0.15) {
          const st = physics.pose.steer[i] + physics.yaw;
          dust.spray(c, Math.sin(st), Math.cos(st), sp, dt, c.y);
        }
      } else if (contact) {
        prevContact[i].copy(c);
      }
      hasPrev[i] = contact;
    }
    tracks.flush();

    rig.update(dt, rover, physics);
    terrain.update(camera);
    rocks.update(camera);
    sky.update(camera, renderer);
    dustColor.setRGB(0.36, 0.34, 0.31).multiplyScalar(sun.intensity * Math.max(0.25, sunDir.y) * 1.05);
    dust.uniforms.uColor.value.copy(dustColor);
    dust.uniforms.uScale.value = renderer.getDrawingBufferSize(tmpV).y / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
    dust.update(dt);
  };

  let paused = params.has('test');
  // dynamic resolution: keep the frame rate smooth on weaker GPUs
  const dyn = { scale: 1, min: 0.55, t: 0, n: 0, sum: 0, enabled: !params.has('test') && savedPrefs.dynres !== false };
  const applyScale = () => {
    renderer.setPixelRatio(pixelRatio * dyn.scale);
    renderer.setSize(innerWidth, innerHeight);
    post.setPixelRatio(pixelRatio * dyn.scale);
  };
  const frame = (now) => {
    const rawDt = (now - last) / 1000;
    const dt = Math.min(0.1, rawDt);
    last = now;
    if (dyn.enabled && !document.hidden) {
      dyn.sum += rawDt; dyn.n++; dyn.t += rawDt;
      if (dyn.t > 1.5) {
        const avg = dyn.sum / dyn.n;
        let next = dyn.scale;
        if (avg > 1 / 42) next = Math.max(dyn.min, dyn.scale * 0.85);
        else if (avg < 1 / 57 && dyn.scale < 1) next = Math.min(1, dyn.scale * 1.08);
        if (Math.abs(next - dyn.scale) > 0.01) { dyn.scale = next; applyScale(); }
        dyn.t = dyn.sum = dyn.n = 0;
      }
    }
    if (!paused) {
      input.read(physics.controls);
      update(dt);
      post.render(dt);
      hud.update(dt, now);
    }
    frames++;
    fpsT += dt;
    if (fpsT > 0.5) {
      hud.setFps(frames / fpsT, terrain.stats, rocks.visibleCount);
      frames = 0;
      fpsT = 0;
    }
    requestAnimationFrame(frame);
  };

  // deterministic stepping hook (used for automated testing)
  const simulate = (seconds, controls = {}, dt = 1 / 30) => {
    paused = true;
    Object.assign(physics.controls, { throttle: 0, steer: 0, brake: false, boost: false }, controls);
    for (let t = 0; t < seconds; t += dt) update(dt);
    post.render(dt);
    hud.update(1, performance.now());
    paused = params.has('test');
    return physics;
  };

  progress(1, 'Готово');
  await nextFrame();
  $('loader').classList.add('fade');
  $('hud').classList.remove('hidden');
  hud.flashMode(MODE_NAMES[rig.mode]);
  setTimeout(() => $('loader').classList.add('hidden'), 900);
  window.__app = { renderer, scene, camera, physics, rover, terrain, rocks, data, rig, post, sun, tracks, dust, simulate, input, hud };
  window.__ready = true;
  requestAnimationFrame(frame);
}

/**
 * Pick a start location: level ground for the rover itself, but with fresh
 * craters and boulder fields nearby, facing the most interesting view.
 */
function findSpawn(data) {
  const rough = (x, z, r) => {
    const h = data.heightAt(x, z);
    let s = 0;
    for (let k = 0; k < 8; k++) {
      const b = (k / 8) * Math.PI * 2;
      s += Math.abs(data.heightAt(x + Math.cos(b) * r, z + Math.sin(b) * r) - h);
    }
    return s / 8;
  };
  let best = { score: Infinity, x: 0, z: 0 };
  for (let r = 0; r <= 360; r += 18) {
    const n = r === 0 ? 1 : Math.round((2 * Math.PI * r) / 18);
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2;
      const x = Math.cos(a) * r, z = Math.sin(a) * r;
      const local = rough(x, z, 3) + data.rockiness(x, z) * 0.6;
      let interest = 0;
      for (let k = 0; k < 12; k++) {
        const b = (k / 12) * Math.PI * 2;
        for (const d of [14, 28, 45]) interest += data.rockiness(x + Math.cos(b) * d, z + Math.sin(b) * d);
      }
      interest /= 36;
      const h0 = data.heightAt(x, z);
      let ring = 0;
      for (let k = 0; k < 12; k++) {
        const b = (k / 12) * Math.PI * 2;
        ring += data.heightAt(x + Math.cos(b) * 70, z + Math.sin(b) * 70);
      }
      const depression = Math.max(0, ring / 12 - h0 - 0.5);
      const score = local * 4 - interest * 1.5 + depression * 0.25 + r * 0.0008;
      if (score < best.score) best = { score, x, z };
    }
  }
  // face the direction with the most relief & rocks (like a photo composition)
  let bestYaw = 0, bestVal = -1;
  for (let k = 0; k < 24; k++) {
    const yaw = (k / 24) * Math.PI * 2;
    let v = 0;
    for (let d = 12; d <= 90; d += 6) {
      const x = best.x + Math.sin(yaw) * d, z = best.z + Math.cos(yaw) * d;
      v += data.rockiness(x, z) * 1.5 + rough(x, z, 6) * 0.8;
    }
    // the path straight ahead should be drivable, and the view open
    for (let d = 3; d <= 12; d += 3) v -= rough(best.x + Math.sin(yaw) * d, best.z + Math.cos(yaw) * d, 2) * 4;
    const h0 = data.heightAt(best.x, best.z);
    for (const d of [40, 80, 120]) v -= Math.max(0, data.heightAt(best.x + Math.sin(yaw) * d, best.z + Math.cos(yaw) * d) - h0) * 0.35;
    if (v > bestVal) { bestVal = v; bestYaw = yaw; }
  }
  return { x: best.x, z: best.z, yaw: bestYaw };
}

main().catch((err) => {
  console.error(err);
  fail('Ошибка запуска: ' + (err && err.message ? err.message : err));
});
