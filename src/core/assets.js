// Asset loading with graceful fallbacks: a missing file resolves to null so the
// game still runs (placeholder geometry / generated textures take over).
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

export const BASE = import.meta.env.BASE_URL + 'assets/';

const gltfLoader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
const texLoader = new THREE.TextureLoader();

export const assets = {
  models: {},   // name -> gltf
  textures: {}, // name -> THREE.Texture
  audio: {},    // name -> ArrayBuffer (decoded later by audio module)
};

async function exists(url) {
  try {
    const r = await fetch(url, { method: 'HEAD' });
    const ct = r.headers.get('content-type') || '';
    // Vite dev server answers unknown paths with index.html
    return r.ok && !ct.includes('text/html');
  } catch { return false; }
}

function loadModel(name) {
  const url = `${BASE}models/${name}.glb`;
  return exists(url).then((ok) => ok
    ? gltfLoader.loadAsync(url).then((g) => (assets.models[name] = g)).catch((e) => { console.warn('model failed', name, e); return null; })
    : null);
}

function loadTexture(name, { srgb = true, repeat = true, ext = 'jpg' } = {}) {
  const url = `${BASE}textures/${name}.${ext}`;
  return exists(url).then((ok) => {
    if (!ok) return null;
    return texLoader.loadAsync(url).then((t) => {
      t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
      if (repeat) t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.anisotropy = 4;
      assets.textures[name] = t;
      return t;
    }).catch(() => null);
  });
}

function loadAudio(name) {
  const url = `${BASE}audio/${name}.mp3`;
  return fetch(url).then((r) => {
    const ct = r.headers.get('content-type') || '';
    if (!r.ok || ct.includes('text/html')) return null;
    return r.arrayBuffer().then((b) => (assets.audio[name] = b));
  }).catch(() => null);
}

export const MODEL_LIST = ['stagecoach', 'horse', 'rider', 'weapons', 'props', 'town'];
export const TEX_LIST = [
  ['dirt_road'], ['dry_grass'], ['green_grass'], ['sand'], ['rock'], ['red_rock'], ['snow'], ['gravel'],
  ...['dirt_road', 'dry_grass', 'green_grass', 'sand', 'rock', 'red_rock', 'snow', 'gravel'].map((n) => [n + '_n', { srgb: false }]),
  ['grass_blade', { ext: 'png', repeat: false }], ['cloud_noise', { ext: 'png', srgb: false }],
  ['mountain_silhouette', { ext: 'png' }],
];
export const AUDIO_LIST = [
  'schofield_shot', 'schofield_shot2', 'schofield_cock', 'schofield_reload', 'shotgun_shot', 'shotgun_reload',
  'rifle_shot_far', 'bullet_whiz_1', 'bullet_whiz_2', 'bullet_whiz_3', 'ricochet_1', 'ricochet_2', 'ricochet_3',
  'hit_flesh_1', 'hit_flesh_2', 'hit_wood_1', 'hit_wood_2', 'horse_neigh', 'horse_gallop_loop', 'coach_rumble_loop',
  'wind_loop', 'whip_crack', 'deadeye_in', 'deadeye_out', 'heartbeat_loop', 'bell_town', 'music_ride_loop',
  'music_menu', 'music_town_loop', 'music_results', 'sting_victory', 'sting_death', 'ui_click',
];

// big music files load after the title is showing (except the menu theme)
export const DEFERRED_AUDIO = ['music_ride_loop', 'music_town_loop', 'music_results'];
export function loadDeferredAudio() { return Promise.all(DEFERRED_AUDIO.map((n) => loadAudio(n))); }

export async function loadAll(onProgress) {
  const jobs = [
    ...MODEL_LIST.map((n) => loadModel(n)),
    ...TEX_LIST.map(([n, o]) => loadTexture(n, o)),
    ...AUDIO_LIST.filter((n) => !DEFERRED_AUDIO.includes(n)).map((n) => loadAudio(n)),
  ];
  let done = 0;
  jobs.forEach((j) => j.finally(() => onProgress?.(++done / jobs.length)));
  await Promise.all(jobs);
  return assets;
}

// Find a node by exact name inside a loaded gltf scene
export function findNode(root, name) {
  let hit = null;
  root.traverse((o) => { if (!hit && o.name === name) hit = o; });
  return hit;
}
