import * as THREE from 'three';
import { SunLightShadow } from 'three/examples/jsm/lights/SunLightShadow.js';

// three.js r186 filters PCF shadows with 5 taps rotated by screen-space noise.
// As the camera moves that noise slides over the penumbra, so shadow edges
// shimmer. Replace it with a fixed 3×3 tent of hardware-PCF taps anchored to
// the shadow map: soft and perfectly stable from frame to frame.
const chunk = THREE.ShaderChunk.shadowmap_pars_fragment;
const start = chunk.indexOf('float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;');
const endMarker = ') * 0.2;';
const end = start >= 0 ? chunk.indexOf(endMarker, start) : -1;
if (start >= 0 && end > start) {
  THREE.ShaderChunk.shadowmap_pars_fragment =
    chunk.slice(0, start) +
    `vec2 st = texelSize * max( shadowRadius, 1.0 ) * 0.75;
				shadow = 0.0;
				for ( int sy = -1; sy <= 1; sy ++ ) {
					for ( int sx = -1; sx <= 1; sx ++ ) {
						float w = ( sx == 0 ? 2.0 : 1.0 ) * ( sy == 0 ? 2.0 : 1.0 );
						shadow += w * texture( shadowMap, vec3( shadowCoord.xy + vec2( float( sx ), float( sy ) ) * st, shadowCoord.z ) );
					}
				}
				shadow *= 1.0 / 16.0;` +
    chunk.slice(end + endMarker.length);
} else {
  console.warn('stableShadows: PCF chunk not found, keeping the default filter');
}

// The sun cascades are refitted to the view frustum every frame. Their XY is
// snapped to texels, but the depth range (near plane position and far) moves
// continuously with the camera, so depth quantisation and bias change every
// frame and terrain self-shadowing flickers. Snap the depth range too.

const _fwd = new THREE.Vector3();
const DEPTH_STEP = 64; // m
const FAR_STEP = 256; // m
const original = SunLightShadow.prototype.updateMatrices;
SunLightShadow.prototype.updateMatrices = function (light, viewCamera) {
  original.call(this, light, viewCamera);
  if (viewCamera === undefined) return;
  for (let i = 0; i < this._cameras.length; i++) {
    const cam = this._cameras[i];
    cam.getWorldDirection(_fwd);
    const s = cam.position.dot(_fwd);
    const delta = s - Math.floor(s / DEPTH_STEP) * DEPTH_STEP;
    cam.position.addScaledVector(_fwd, -delta);
    cam.far = Math.ceil((cam.far + delta) / FAR_STEP) * FAR_STEP;
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld();
    this._updateMatrix(cam, this._matrices[i], this._frustums[i], this._viewports[i]);
  }
};
