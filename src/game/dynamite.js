import * as THREE from 'three';
import { audio } from '../core/audio.js';

const UP = new THREE.Vector3(0, 1, 0);

export class Dynamite {
  constructor(game) {
    this.g = game;
    this.stock = 3;
    this.active = [];
    this.bodyGeometry = new THREE.CylinderGeometry(0.085, 0.085, 0.62, 8);
    this.bodyMaterial = new THREE.MeshStandardMaterial({ color: 0x8e241c, roughness: 0.62 });
    this.fuseGeometry = new THREE.CylinderGeometry(0.018, 0.018, 0.16, 6);
    this.fuseMaterial = new THREE.MeshStandardMaterial({ color: 0x30241c, roughness: 1 });
    this.emberGeometry = new THREE.SphereGeometry(0.04, 6, 5);
    this.emberMaterial = new THREE.MeshBasicMaterial({ color: 0xffa33b });
    this.g.hud.setDynamite(this.stock);
  }

  throw() {
    const g = this.g;
    if (!this.stock || g.over) {
      if (!this.stock) g.hud.banner('No dynamite left', '', 1.2);
      return false;
    }
    const root = new THREE.Group();
    const stick = new THREE.Mesh(this.bodyGeometry, this.bodyMaterial);
    const fuse = new THREE.Mesh(this.fuseGeometry, this.fuseMaterial);
    const ember = new THREE.Mesh(this.emberGeometry, this.emberMaterial);
    fuse.position.y = 0.37;
    ember.position.y = 0.47;
    root.add(stick, fuse, ember);
    root.position.copy(g.player.model.hand.getWorldPosition(new THREE.Vector3()));
    root.quaternion.setFromUnitVectors(UP, g.player.aimDir);
    g.scene.add(root);

    const velocity = g.player.aimDir.clone().multiplyScalar(21)
      .addScaledVector(g.coach.fwd, 8)
      .add(new THREE.Vector3(0, 6.5, 0));
    this.active.push({ root, velocity, age: 0, trail: 0 });
    this.stock--;
    g.hud.setDynamite(this.stock);
    audio.play('ui_click', { volume: 0.55, pitch: 0.72 });
    return true;
  }

  update(dt) {
    const g = this.g;
    for (let i = this.active.length - 1; i >= 0; i--) {
      const bomb = this.active[i];
      bomb.age += dt;
      bomb.velocity.y -= 13 * dt;
      bomb.root.position.addScaledVector(bomb.velocity, dt);
      bomb.root.quaternion.setFromUnitVectors(UP, bomb.velocity.clone().normalize());
      bomb.root.rotateY(dt * 9);
      bomb.trail -= dt;
      if (bomb.trail <= 0) {
        bomb.trail = 0.055;
        const ember = bomb.root.localToWorld(new THREE.Vector3(0, 0.47, 0));
        g.fx.add.spawn({ pos: ember, life: 0.1, size: 0.12, size1: 0.08, color: { r: 1, g: 0.44, b: 0.12 }, alpha: 1, fadeIn: 0 });
        g.fx.smoke.spawn({ pos: ember, vel: new THREE.Vector3(0, 0.6, 0), life: 0.3, size: 0.08, size1: 0.22, color: g.fx.smokeCol, alpha: 0.45, drag: 2, grav: -0.3 });
      }
      const ground = g.route.height(bomb.root.position.x, bomb.root.position.z) + 0.15;
      if (bomb.age >= 1.55 || (bomb.age > 0.16 && bomb.root.position.y <= ground)) {
        const impact = bomb.root.position.clone();
        impact.y = Math.max(ground, impact.y);
        g.scene.remove(bomb.root);
        this.active.splice(i, 1);
        this._explode(impact);
      }
    }
  }

  _explode(position) {
    const g = this.g, radius = 15;
    g.fx.explosion(position, radius);
    g.shake += 1.8;
    g.hitStop(0.12);
    audio.play('shotgun_shot', { position, volume: 2.1, pitch: 0.58, maxDist: 900 });
    audio.play('hit_wood_1', { position, volume: 0.8, pitch: 0.6, delay: 0.04, maxDist: 700 });
    let knockedOut = 0;
    for (const enemy of g.enemies.list) {
      if (!enemy.alive) continue;
      const distance = enemy.pos.distanceTo(position);
      if (distance > radius) continue;
      const away = enemy.pos.clone().sub(position);
      if (away.lengthSq() < 0.001) away.set(0, 0, 1);
      else away.normalize();
      if (enemy.damage(999, 'horse', away)) {
        g.combat._onKill(enemy, 'horse', position);
        knockedOut++;
      }
    }
    g.hud.banner('DYNAMITE!', `${knockedOut} rider${knockedOut === 1 ? '' : 's'} knocked out`, 1.7);
  }

  dispose() {
    for (const bomb of this.active) this.g.scene.remove(bomb.root);
    this.active.length = 0;
    this.bodyGeometry.dispose();
    this.bodyMaterial.dispose();
    this.fuseGeometry.dispose();
    this.fuseMaterial.dispose();
    this.emberGeometry.dispose();
    this.emberMaterial.dispose();
  }
}
