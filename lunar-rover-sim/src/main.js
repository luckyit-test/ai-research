import * as THREE from 'three';
import './render/stableShadows.js';
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
import { LunarClock } from './sim/LunarClock.js';
import { PowerSystem } from './sim/PowerSystem.js';
import { SolarArray } from './rover/SolarArray.js';

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
  let userExposure = savedPrefs.exposure ?? 1.3;
  renderer.toneMappingExposure = userExposure;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0);
  const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.15, 40000);

  // start loading the rover while the terrain is generated
  const roverPromise = RoverModel.load(window.ROVER_MODEL_URL || './models/perseverance.glb', (f) => {
    if (f < 1) loaderLabel.dataset.model = `${Math.round(f * 100)}%`;
  });

  progress(0.03, 'Генерация рельефа');
  await nextFrame();
  const data = new TerrainData(renderer, { macroRes: Q.macro, farRes: Q.far, detailRes: Q.detail, microRes: Q.micro });
  await data.generate((f, l) => progress(f * 0.6, l));

  // --- sun ---------------------------------------------------------------
  // --- lunar time & sun -----------------------------------------------------
  const clock = new LunarClock({
    latitude: 26,
    dayFraction: savedPrefs.lunarT ?? 0.317,
    timeScale: 1, // real time on start: a moving Sun costs shadow re-bakes
  });
  const sunDir = clock.sunDir;

  progress(0.62, 'Тени от горизонта');
  await nextFrame();
  const baker = new ShadowBaker(renderer, data, Q.macro <= 1024 ? { macroShadowRes: 512, farShadowRes: 256 } : { macroShadowRes: Q.bakedShadow || 1024, farShadowRes: 512 });
  baker.bake(sunDir);
  lunarUniforms.uSunVisMacro.value = baker.macroRT.texture;
  lunarUniforms.uSunVisFar.value = baker.farRT.texture;
  baker.onSwap = (macro, far) => {
    lunarUniforms.uSunVisMacro.value = macro;
    lunarUniforms.uSunVisFar.value = far;
  };

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
  // earthshine: the only light during the two-week lunar night
  const earthLight = new THREE.DirectionalLight(0xb4c8ff, 0);
  earthLight.position.copy(clock.earthDir);
  scene.add(earthLight);

  // environment: black sky above, sunlit regolith below (bounce light)
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envScene = new THREE.Scene();
  const envMat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    uniforms: { uGround: { value: new THREE.Color(0.105, 0.098, 0.09) }, uEarthGlow: { value: new THREE.Color(0, 0, 0) }, uEarthDir: { value: clock.earthDir.clone() } },
    vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: `uniform vec3 uGround; uniform vec3 uEarthGlow; uniform vec3 uEarthDir; varying vec3 vP;
      void main(){ vec3 d = normalize(vP); float g = smoothstep(0.04, -0.12, d.y); float hz = exp(-abs(d.y) * 14.0) * 0.35;
      float e = pow(max(dot(d, uEarthDir), 0.0), 600.0);
      gl_FragColor = vec4(uGround * (g + hz) + uEarthGlow * e, 1.0); }`,
  });
  envScene.add(new THREE.Mesh(new THREE.SphereGeometry(10, 32, 16), envMat));
  // ground bounce from sunlit regolith by day, from earthlit regolith by night
  let envKey = -1;
  const updateEnv = (force = false) => {
    const sinEl = Math.max(0, sunDir.y);
    const day = (sinEl / Math.sin(THREE.MathUtils.degToRad(21))) * sunDisk();
    const night = 0.05 * clock.earthPhase;
    const k = Math.max(day, 0) + night;
    if (!force && envKey > 0 && Math.abs(k - envKey) / envKey < 0.06) return;
    envKey = Math.max(k, 1e-4);
    envMat.uniforms.uGround.value.setRGB(0.085 * k, 0.08 * k, 0.073 * k);
    envMat.uniforms.uEarthGlow.value.setRGB(0.5, 0.62, 0.9).multiplyScalar(clock.earthPhase * 0.04);
    if (scene.environment) scene.environment.dispose();
    scene.environment = pmrem.fromScene(envScene, 0.02).texture;
  };
  const sunDisk = () => THREE.MathUtils.clamp((sunDir.y + 0.00465) / 0.0093, 0, 1);
  updateEnv(true);

  // --- world objects ------------------------------------------------------
  progress(0.68, 'Лунный грунт');
  const tracks = new Tracks(renderer, { size: 128, res: Q.tracks });
  const trackUniforms = tracks.uniforms();
  const terrain = new TerrainMesh(data, { ...trackUniforms, uTrackStrength: { value: 1 } }, { segments: Q.seg, casterSegments: 48, lodK: Q.lodK });
  scene.add(terrain.group);

  progress(0.74, 'Камни и валуны');
  await nextFrame();
  const rocks = new RockField(data, data.microTex, { quality: Q.rocks });
  scene.add(rocks.group);

  // photographic surface textures (generated, made seamless offline); the
  // procedural look stays as a fallback if they fail to load
  {
    const loader = new THREE.TextureLoader();
    const maxAniso = renderer.capabilities.getMaxAnisotropy();
    // hosts that cannot serve images cross-origin get the textures as data URLs
    const embedded = window.TEXTURES_MODULE_URL ? import(/* @vite-ignore */ window.TEXTURES_MODULE_URL).then((m) => m.default).catch(() => null) : Promise.resolve(null);
    const load = (name) => embedded.then((emb) => new Promise((resolve) => loader.load(emb && emb[name] ? emb[name] : `./textures/${name}`, (t) => {
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.anisotropy = Math.min(8, maxAniso);
      t.colorSpace = THREE.NoColorSpace;
      resolve(t);
    }, undefined, (err) => { console.warn('texture failed', name, err); resolve(null); })));
    Promise.all(['regolith_albedo.jpg', 'regolith_normal.jpg', 'rubble_albedo.jpg', 'rubble_normal.jpg',
      'basalt_albedo.jpg', 'basalt_normal.jpg', 'breccia_albedo.jpg', 'breccia_normal.jpg'].map(load)).then((t) => {
      if (t.some((x) => !x)) { console.warn('surface textures missing, using procedural look'); return; }
      const u = terrain.uniforms;
      u.uRegA.value = t[0]; u.uRegN.value = t[1]; u.uRubA.value = t[2]; u.uRubN.value = t[3];
      u.uPhoto.value = 1;
      const r = rocks.photoUniforms;
      r.uRockA0.value = t[4]; r.uRockN0.value = t[5]; r.uRockA1.value = t[6]; r.uRockN1.value = t[7];
      r.uPhoto.value = 1;
      window.__texturesReady = true;
    });
  }

  const sky = new Sky();
  sky.setClock(clock);
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
  const solar = new SolarArray();
  rover.body.add(solar.root);
  for (const m of [...rover.materials, ...solar.materials]) patchMaterial(m, { brdf: false });
  scene.add(rover.root);
  const power = new PowerSystem(data, { capacityWh: 4000, soc: 0.8 });

  // --- physics ------------------------------------------------------------
  const ground = {
    surfaceAt: (x, z) => rocks.surfaceAt(x, z, data.heightAt(x, z)),
    collide: (x, z, yaw) => rocks.collide(x, z, yaw),
  };
  const physics = new RoverPhysics(ground);
  physics.maxSpeed = savedPrefs.speed ?? 2.2;

  const spawn = findSpawn(data);
  // face so that the Sun lights the scene from behind-right, like a photo
  spawn.yaw = Math.atan2(sunDir.x, sunDir.z) - THREE.MathUtils.degToRad(222);
  rocks._buildPhysics(spawn.x, spawn.z);
  physics.reset(spawn.x, spawn.z, spawn.yaw);

  // --- camera, post, input --------------------------------------------------
  const rig = new CameraRig(camera, canvas, (x, z) => data.heightAt(x, z));
  const post = new Post(renderer, scene, camera, { ao: Q.ao, bloom: Q.bloom, smaa: Q.smaa, halfResAO: Q.halfAO });
  const input = new Input();
  const hud = new Hud({ data, physics, rig, clock, power });

  const skyPrefs = { stars: true, earth: true };
  const applyToggles = () => {
    const p = savedPrefs;
    if (post.aoPass) post.aoPass.enabled = p.ao !== false;
    if (post.bloomPass) post.bloomPass.enabled = p.bloom !== false;
    post.finalPass.uniforms.uGrain.value = 0; // animated grain read as flickering shadows
    post.finalPass.uniforms.uVignette.value = p.film === false ? 0.12 : 0.32;
    post.finalPass.uniforms.uAberration.value = p.film === false ? 0 : 0.0014;
    skyPrefs.stars = p.stars !== false;
    skyPrefs.earth = p.earth !== false;
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
    onQuality: (q) => {
      savedPrefs.quality = q;
      savePrefs();
      if (params.has('q')) location.search = `?q=${q}`;
      else location.reload();
    },
    onTime: (t, final) => {
      clock.setDayFraction(t);
      savedPrefs.lunarT = clock.t; savePrefs();
      if (final) { baker.bake(sunDir); updateEnv(true); } else if (!baker.busy) baker.begin(sunDir);
    },
    onTimeScale: (v) => { clock.timeScale = v; savedPrefs.timeScale = v; savePrefs(); hud.flashMode(`Ход времени: ${v === 0 ? 'пауза' : '×' + v}`); },
    onExposure: (v) => { userExposure = v; savedPrefs.exposure = v; savePrefs(); },
    onSpeed: (v) => { physics.maxSpeed = v; savedPrefs.speed = v; savePrefs(); },
    onToggle: (key, v) => { savedPrefs[key] = v; savePrefs(); applyToggles(); },
    prefs: savedPrefs,
    exposure: userExposure,
    speed: physics.maxSpeed,
  });

  input.on('KeyC', () => hud.flashMode(MODE_NAMES[rig.next()]));
  input.on('KeyR', () => {
    physics.reset(physics.pos.x, physics.pos.z, physics.yaw);
    hud.flashMode('Ровер выровнен');
  });
  input.on('KeyG', () => hud.toggle('settings'));
  const TIME_SCALES = [0, 1, 1000, 10000, 100000];
  input.on('KeyT', () => {
    const i = TIME_SCALES.indexOf(clock.timeScale);
    clock.timeScale = TIME_SCALES[(i + 1) % TIME_SCALES.length];
    savedPrefs.timeScale = clock.timeScale; savePrefs();
    hud.syncTimeScale();
    hud.flashMode(`Ход времени: ${clock.timeScale === 0 ? 'пауза' : '×' + clock.timeScale}`);
  });
  window.addEventListener('pagehide', () => { savedPrefs.lunarT = clock.t; delete savedPrefs.soc; savePrefs(); });
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
  const tmpQ = new THREE.Quaternion();
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
  let autoExp = 1;
  let shadowSunDir = null;
  const smooth = (a, b, x) => { const t = THREE.MathUtils.clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
  const updateSky = (dt) => {
    clock.update(dt);
    const elDeg = THREE.MathUtils.radToDeg(clock.sunElevation);
    const disk = sunDisk();
    const night = 1 - smooth(-1.5, 4, elDeg);
    // the shadow direction moves in small steps: re-rasterising the shadow
    // map every frame for a slowly moving Sun makes every edge crawl
    if (!shadowSunDir || shadowSunDir.angleTo(sunDir) > 0.0035) {
      shadowSunDir = (shadowSunDir || new THREE.Vector3()).copy(sunDir);
      sun.position.copy(sunDir);
    }
    sun.intensity = 3.6 * disk;
    earthLight.position.copy(clock.earthDir);
    earthLight.intensity = 0.3 * clock.earthPhase * (0.15 + 0.85 * night);
    // camera auto-exposure: long exposures at night, a little more at dawn
    const target = (1 + 5 * night) * (1 + 0.45 * (1 - smooth(4, 25, elDeg)) * (1 - night));
    autoExp += (target - autoExp) * (1 - Math.exp(-dt * 1.5));
    renderer.toneMappingExposure = userExposure * autoExp;
    sky.setClock(clock);
    sky.uniforms.uStars.value = skyPrefs.stars ? (0.5 + 0.7 * night) / autoExp : 0;
    sky.uniforms.uPlanetsK.value = skyPrefs.stars ? 1 / Math.pow(autoExp, 0.6) : 0;
    sky.uniforms.uEarth.value = skyPrefs.earth ? 1 / Math.pow(autoExp, 0.55) : 0;
    sky.uniforms.uGlare.value = disk;
    updateEnv();
    // re-bake horizon shadows progressively while the Sun moves
    if (disk > 0) {
      if (!baker.busy && baker.bakedDir && baker.bakedDir.angleTo(sunDir) > THREE.MathUtils.degToRad(0.5)) baker.begin(sunDir);
      baker.step(clock.timeScale > 5000 ? 4 : 1);
    }
    return night;
  };

  const update = (dt) => {
    const night = updateSky(dt);
    // equal sub-steps every frame: the rover moves exactly in sync with the
    // camera (a fixed 120 Hz step makes it judder against a 60/144 Hz display)
    const steps = Math.min(24, Math.max(1, Math.ceil(dt / STEP - 1e-6)));
    for (let i = 0; i < steps; i++) physics.step(dt / steps);
    syncRover();
    physics.updateWheelWorld(rover);
    rover.body.getWorldQuaternion(tmpQ);
    solar.update(dt, sunDir, tmpQ, sunDisk() > 0);
    physics.powerLimit = power.update(dt, { array: solar, sunDir, physics, night: night > 0.5 });

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
    dustColor.setRGB(0.36, 0.34, 0.31).multiplyScalar(sun.intensity * Math.max(0.25, sunDir.y) * 1.05 + earthLight.intensity * 0.5);
    dust.uniforms.uColor.value.copy(dustColor);
    dust.uniforms.uScale.value = renderer.getDrawingBufferSize(tmpV).y / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
    dust.update(dt);
  };

  let paused = params.has('test');
  // dynamic resolution: keep the frame rate smooth on weaker GPUs
  const dyn = { scale: 1, min: 0.55, t: 0, n: 0, sum: 0, bad: 0, good: 0, enabled: !params.has('test') && savedPrefs.dynres !== false };
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
        // hysteresis: resolution changes are visible, so only react to sustained trends
        dyn.bad = avg > 1 / 40 ? dyn.bad + 1 : 0;
        dyn.good = avg < 1 / 58 ? dyn.good + 1 : 0;
        if (dyn.bad >= 2) { next = Math.max(dyn.min, dyn.scale * 0.85); dyn.bad = 0; }
        else if (dyn.good >= 5 && dyn.scale < 1) { next = Math.min(1, dyn.scale * 1.1); dyn.good = 0; }
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
  window.__app = { renderer, scene, camera, physics, rover, terrain, rocks, data, rig, post, sun, tracks, dust, simulate, input, hud, clock, power, solar, baker };
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
