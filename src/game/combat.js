// Shot resolution for both sides.
import * as THREE from 'three';
import { audio } from '../core/audio.js';
import { smoothstep } from '../core/noise.js';

const _v = new THREE.Vector3(), _ray = new THREE.Ray();

export const BOUNTY = { rider: 25, rifleman: 40, gunman: 30, head: 25, horse: 10 };

export class Combat {
  constructor(game) { this.g = game; }

  // ray from the camera (dir already includes spread). Returns {hit, killed}
  playerShot(origin, dir, W, muzzle, guaranteed) {
    const g = this.g;
    const hit = g.enemies.rayHit(origin, dir, W.range);
    // occluders: terrain and town buildings
    let occT = g.terrain.raycast(origin, dir, Math.min(W.range, hit ? hit.t : W.range));
    let occKind = 'ground';
    _ray.set(origin, dir);
    for (const box of g.towns.solids) {
      const p = _ray.intersectBox(box, _v);
      if (p) { const t = p.distanceTo(origin); if (t > 1.5 && t < occT) { occT = t; occKind = 'wood'; } }
    }
    if (hit && (guaranteed || hit.t < occT)) {
      const e = hit.enemy, part = hit.part;
      const fall = 1 - smoothstep(W.falloff[0], W.falloff[1], hit.t) * 0.85;
      let dmg = W.damage * fall * (part === 'head' ? W.headMult : 1);
      const killed = e.damage(dmg, part, dir);
      g.fx.tracer(muzzle, hit.point);
      if (part === 'horse') g.fx.blood(hit.point, dir);
      else g.fx.blood(hit.point, dir);
      audio.play('hit_flesh_' + (1 + (Math.random() * 2 | 0)), { position: hit.point, volume: 1.2 });
      if (killed) this._onKill(e, part, hit.point);
      return { hit: true, killed };
    }
    const end = origin.clone().addScaledVector(dir, Math.min(occT, 250));
    g.fx.tracer(muzzle, end);
    if (occT < W.range) {
      if (occKind === 'wood') { g.fx.splinters(end, dir); audio.play('hit_wood_' + (1 + (Math.random() * 2 | 0)), { position: end, volume: 0.9 }); }
      else {
        g.fx.dust(end, { amount: 5, size: 0.35, up: 1.2 });
        if (Math.random() < 0.3) audio.play('ricochet_' + (1 + (Math.random() * 3 | 0)), { position: end, volume: 0.6 });
      }
    }
    return { hit: false, killed: false };
  }

  _onKill(e, part, point) {
    const g = this.g, p = g.player;
    p.stats.kills++;
    const head = part === 'head';
    if (head) p.stats.headshots++;
    let bounty = BOUNTY[e.type] || 25;
    let label = e.type === 'rifleman' ? 'Rifleman' : e.type === 'gunman' ? 'Gunman' : 'Outlaw';
    if (part === 'horse') { label = 'Unhorsed'; bounty = BOUNTY.horse + 10; }
    if (head) bounty += BOUNTY.head;
    g.addBounty(bounty, head ? `HEADSHOT +$${bounty}` : `${label} +$${bounty}`, head);
    p.addDeadeye(head ? 0.16 : 0.1);
  }

  // an enemy fires at the player or the coach
  enemyShot(enemy, muzzle, { dist, acc, dmgPlayer, dmgCoach, rifle = false }) {
    const g = this.g;
    const atPlayer = Math.random() < 0.6;
    const target = atPlayer ? g.player.headPos.clone().add(new THREE.Vector3(0, -0.35, 0)) : g.coach.targetPoint(new THREE.Vector3());
    // accuracy: worse at range, worse when the coach is being whipped, better in Dead Eye? (no)
    let chance = acc * (1 - smoothstep(10, rifle ? 220 : 48, dist) * 0.7);
    if (g.coach.speed > g.coach.cruise + 3) chance *= 0.7;
    const hits = Math.random() < chance;
    const dir = _v.subVectors(target, muzzle).normalize();
    g.fx.muzzle(muzzle, dir, { big: rifle });
    // report
    if (rifle && dist > 60) audio.play('rifle_shot_far', { position: muzzle, volume: 1, delay: dist / 340, maxDist: 900 });
    else audio.play('schofield_shot2', { position: muzzle, volume: 0.9, pitch: 0.85 + Math.random() * 0.1, maxDist: 600 });
    if (hits) {
      g.fx.tracer(muzzle, target);
      if (atPlayer) g.player.damage(dmgPlayer * g.diff.dmgMult, muzzle);
      else {
        g.coach.hp -= dmgCoach * g.diff.dmgMult;
        g.fx.splinters(target, dir);
        audio.play('hit_wood_' + (1 + (Math.random() * 2 | 0)), { position: target, volume: 1 });
        g.onCoachDamage();
      }
    } else {
      // near miss that whizzes past the player's head
      const miss = target.clone().add(new THREE.Vector3((Math.random() - 0.5) * 3, Math.random() * 1.6, (Math.random() - 0.5) * 3));
      const far = miss.clone().addScaledVector(_v.subVectors(miss, muzzle).normalize(), 60);
      g.fx.tracer(muzzle, far);
      if (atPlayer || Math.random() < 0.5) audio.play('bullet_whiz_' + (1 + (Math.random() * 3 | 0)), { volume: 0.8, delay: rifle ? 0 : 0.02 });
      if (Math.random() < 0.35) audio.play('ricochet_' + (1 + (Math.random() * 3 | 0)), { position: miss, volume: 0.5 });
    }
  }
}
