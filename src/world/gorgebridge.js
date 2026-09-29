import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const UP = new THREE.Vector3(0, 1, 0);
const FORWARD = new THREE.Vector3(0, 0, 1);
const _direction = new THREE.Vector3();
const _center = new THREE.Vector3();
const _quaternion = new THREE.Quaternion();
const _scale = new THREE.Vector3();
const _matrix = new THREE.Matrix4();

export class GorgeBridge {
  constructor(route, scene) {
    this.scene = scene;
    this.group = new THREE.Group();
    this.group.name = 'Thunder Gorge trestle';
    scene.add(this.group);
    const bridge = route.bridge;
    const box = new THREE.BoxGeometry(1, 1, 1);
    const deckParts = [], timberParts = [], ironParts = [];
    const addBox = (parts, size, position, rotation) => {
      _scale.set(size[0], size[1], size[2]);
      _matrix.compose(position, rotation, _scale);
      parts.push(box.clone().applyMatrix4(_matrix));
    };
    const point = (s, d, y = 0) => {
      const frame = route.frame(s, {});
      return new THREE.Vector3(frame.x + frame.rx * d, route.roadHeightAt(s) + y, frame.z + frame.rz * d);
    };
    const forwardAt = (s) => {
      const frame = route.frame(s, {});
      _direction.set(frame.tx, 0, frame.tz).normalize();
      return new THREE.Quaternion().setFromUnitVectors(FORWARD, _direction);
    };
    const beam = (parts, a, b, thickness) => {
      _direction.subVectors(b, a);
      const length = _direction.length();
      if (length < 0.01) return;
      _center.addVectors(a, b).multiplyScalar(0.5);
      _quaternion.setFromUnitVectors(UP, _direction.multiplyScalar(1 / length));
      addBox(parts, [thickness, length, thickness], _center, _quaternion);
    };
    for (let s = bridge.s0; s < bridge.s1; s += 1.25) {
      const at = Math.min(s + 0.625, bridge.s1);
      addBox(deckParts, [bridge.width, 0.18, Math.min(1.3, bridge.s1 - s)], point(at, 0, 0.02), forwardAt(at));
    }
    const bents = [];
    for (let s = bridge.s0; s <= bridge.s1; s += 14) bents.push(s);
    if (bents[bents.length - 1] < bridge.s1 - 1) bents.push(bridge.s1);
    for (const s of bents) {
      for (const d of [-3.45, 3.45]) {
        const top = point(s, d, -0.48);
        const base = top.clone();
        base.y = route.height(base.x, base.z) - 0.35;
        beam(timberParts, base, top, 0.72);
        beam(timberParts, point(s, d, -0.2), point(s, d, 1.35), 0.28);
      }
      beam(timberParts, point(s, -3.8, -0.48), point(s, 3.8, -0.48), 0.62);
    }
    for (let i = 0; i < bents.length - 1; i++) {
      const a = bents[i], b = bents[i + 1];
      for (const d of [-3.45, 3.45]) {
        beam(timberParts, point(a, d, 1.35), point(b, d, 1.35), 0.3);
        beam(timberParts, point(a, d, -1.1), point(b, d, -1.1), 0.32);
        for (let level = -2.2; level > -bridge.depth + 2; level -= 6) {
          beam(timberParts, point(a, d, level), point(b, d, level + 5.8), 0.3);
          beam(timberParts, point(a, d, level + 5.8), point(b, d, level), 0.3);
        }
      }
    }
    for (const s of [bridge.s0, bridge.s1]) {
      for (const d of [-3.8, 3.8]) beam(ironParts, point(s, d, -0.2), point(s, d, 1.4), 0.12);
      beam(ironParts, point(s, -3.8, -0.2), point(s, 3.8, -0.2), 0.12);
    }
    const addMerged = (parts, material, name) => {
      const geometry = mergeGeometries(parts, false);
      parts.forEach((part) => part.dispose());
      geometry.computeBoundingSphere();
      const mesh = new THREE.Mesh(geometry, material);
      mesh.name = name;
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      this.group.add(mesh);
    };
    addMerged(deckParts, new THREE.MeshStandardMaterial({ color: 0x504a40, roughness: 0.92 }), 'Bridge deck');
    addMerged(timberParts, new THREE.MeshStandardMaterial({ color: 0x373936, roughness: 0.88 }), 'Trestle');
    addMerged(ironParts, new THREE.MeshStandardMaterial({ color: 0x282e30, roughness: 0.65, metalness: 0.55 }), 'Ironwork');
    box.dispose();
  }

  dispose() {
    this.scene.remove(this.group);
    this.group.traverse((object) => {
      object.geometry?.dispose();
      if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose());
      else object.material?.dispose();
    });
  }
}