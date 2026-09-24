import * as THREE from 'three';

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
