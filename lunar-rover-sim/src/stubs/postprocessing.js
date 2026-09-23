// n8ao also ships a pass for the pmndrs "postprocessing" library, which this
// app does not use. Aliasing the import to this stub keeps ~300 kB out of the
// bundle; only the three.js EffectComposer pass (N8AOPass) is used.
export class Pass {}
