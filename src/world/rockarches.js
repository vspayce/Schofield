import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { mulberry32, makeNoise2D } from '../core/noise.js';

const FORWARD = new THREE.Vector3(0, 0, 1);
const _direction = new THREE.Vector3();
const _rotation = new THREE.Quaternion();
const _scale = new THREE.Vector3();
const _matrix = new THREE.Matrix4();

export class RockArches {
  constructor(route, scene, arches) {
    this.scene = scene;
    this.meshes = [];
    const source = new THREE.IcosahedronGeometry(1, 1);
    const noise = makeNoise2D(route.def.seed + 293);
    const random = mulberry32(route.def.seed + 617);
    const parts = [];
    for (const arch of arches) {
      const s = route.len * arch.at;
      const frame = route.frame(s, {});
      const halfSpan = (arch.span || 92) * 0.5;
      const stones = Math.ceil((arch.span || 92) / 3.2);
      for (let i = 0; i <= stones; i++) {
        const t = i / stones * 2 - 1;
        const d = t * halfSpan;
        const y = route.roadHeightAt(s) + arch.base + arch.rise * (1 - t * t);
        const radius = 3.2 + Math.sqrt(Math.max(0, 1 - t * t)) * 1.1;
        for (const along of [-2.4, 2.4]) {
          const jitter = noise(i * 0.31, along * 0.2) * 0.7;
          const center = new THREE.Vector3(
            frame.x + frame.rx * (d + jitter) + frame.tx * along,
            y + noise(i * 0.47, along + 4) * 0.65,
            frame.z + frame.rz * (d + jitter) + frame.tz * along,
          );
          _direction.set(frame.rx, 0, frame.rz).normalize();
          _rotation.setFromUnitVectors(FORWARD, _direction);
          _rotation.multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(random() * 0.45, random() * 6.28, random() * 0.35)));
          _scale.set(radius * (0.85 + random() * 0.35), radius * (0.75 + random() * 0.3), radius * (0.8 + random() * 0.35));
          _matrix.compose(center, _rotation, _scale);
          parts.push(source.clone().applyMatrix4(_matrix));
        }
      }
    }
    const geometry = mergeGeometries(parts, false);
    parts.forEach((part) => part.dispose());
    source.dispose();
    geometry.computeBoundingSphere();
    const material = new THREE.MeshStandardMaterial({ color: 0x9a6048, roughness: 0.94 });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = 'Devils Gulch rock arches';
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    scene.add(mesh);
    this.meshes.push(mesh);
  }

  dispose() {
    for (const mesh of this.meshes) {
      this.scene.remove(mesh);
      mesh.geometry.dispose();
      mesh.material.dispose();
    }
  }
}