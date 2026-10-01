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
    // game before outlaws: whichever is nearer along the ray
    const beast = g.wildlife && g.wildlife.rayHit(origin, dir, W.range);
    const hit = g.enemies.rayHit(origin, dir, W.range);
    if (beast && (!hit || beast.t < hit.t)) return this._animalShot(beast, origin, dir, W, muzzle);
    // a roadside sign, shot for a wagon repair
    const sign = g.boards && g.boards.rayHit(origin, dir, W.range);
    if (sign && (!hit || sign.t < hit.t) && (!beast || sign.t < beast.t)) {
      g.fx.tracer(muzzle, sign.point);
      sign.board.strike(g, sign.point);
      g.onCoachDamage?.();
      return { hit: true, killed: false, head: false };
    }
    // occluders: terrain and town buildings
    let occT = g.terrain.raycast(origin, dir, Math.min(W.range, hit ? hit.t : W.range));
    let occKind = 'ground';
    _ray.set(origin, dir);
    for (const box of g.towns.solids) {
      const p = _ray.intersectBox(box, _v);
      if (p) { const t = p.distanceTo(origin); if (t > 1.5 && t < occT) { occT = t; occKind = 'wood'; } }
    }
    // a passing train stops bullets: boxcar boards splinter, the engine rings
    const car = g.crossing?.train.rayHit(origin, dir, occT);
    if (car && car.t < occT) { occT = car.t; occKind = car.kind; }
    if (hit && (guaranteed || hit.t < occT)) {
      const e = hit.enemy, part = hit.part;
      const fall = 1 - smoothstep(W.falloff[0], W.falloff[1], hit.t) * (1 - W.floor);
      let dmg = W.damage * fall * (part === 'head' ? W.headMult : 1);
      if (guaranteed && part !== 'horse') dmg = 999; // Dead Eye shots are lethal
      const killed = e.damage(dmg, part, dir);
      this._rattle(origin, dir, hit.t);
      g.fx.tracer(muzzle, hit.point);
      if (part === 'horse') g.fx.blood(hit.point, dir);
      else g.fx.blood(hit.point, dir);
      audio.play('hit_flesh_' + (1 + (Math.random() * 2 | 0)), { position: hit.point, volume: 1.2 });
      if (killed) this._onKill(e, part, hit.point);
      return { hit: true, killed, head: part === 'head' };
    }
    this._rattle(origin, dir, Math.min(occT, 260));
    const end = origin.clone().addScaledVector(dir, Math.min(occT, 250));
    g.fx.tracer(muzzle, end);
    if (occT < W.range) {
      if (occKind === 'wood') { g.fx.splinters(end, dir); audio.play('hit_wood_' + (1 + (Math.random() * 2 | 0)), { position: end, volume: 0.9 }); }
      else if (occKind === 'iron') { g.fx.sparks(end); audio.play('ricochet_' + (1 + (Math.random() * 3 | 0)), { position: end, volume: 0.8 }); }
      else {
        g.fx.dust(end, { amount: 5, size: 0.35, up: 1.2 });
        if (Math.random() < 0.3) audio.play('ricochet_' + (1 + (Math.random() * 3 | 0)), { position: end, volume: 0.6 });
      }
    }
    return { hit: false, killed: false };
  }

  // Game animals: no headshots, no bounty feed spam — a kill pays a hide price
  // and, for anything worth butchering, sends up some meat that heals you.
  _animalShot(hit, origin, dir, W, muzzle) {
    const g = this.g, a = hit.animal;
    const fall = 1 - smoothstep(W.falloff[0], W.falloff[1], hit.t) * (1 - W.floor);
    const killed = a.damage(W.damage * fall, dir);   // called once per pellet, as for enemies
    g.fx.tracer(muzzle, hit.point);
    g.fx.blood(hit.point, dir);
    audio.play('hit_flesh_' + (1 + (Math.random() * 2 | 0)), { position: hit.point, volume: 1.1 });
    if (killed) {
      const p = g.player;
      if (a.cfg.hide) g.addBounty(a.cfg.hide, `${a.kind[0].toUpperCase()}${a.kind.slice(1)} hide +$${a.cfg.hide}`, false);
      if (a.cfg.meat && p.hp < 100) {
        p.hp = Math.min(100, p.hp + a.cfg.meat);
        g.hud.feedMsg(`Fresh meat +${a.cfg.meat} health`, true);
      }
      g.hitStop(0.05);
    }
    return { hit: true, killed, head: false };
  }

  // a hit or near-miss (within 1.5 m) on a glinting rifleman spoils his shot
  _rattle(origin, dir, maxT) {
    for (const e of this.g.enemies.list) {
      if (!e.alive || !(e.glintT > 0)) continue;
      const c = e.spheres[0].c;
      const t = _v.subVectors(c, origin).dot(dir);
      if (t < 0 || t > maxT + 2) continue;
      const miss = _v.copy(origin).addScaledVector(dir, t).distanceTo(c);
      if (miss < 1.5) { e.glintT = 0; e.fireT += 1.6; this.g.hud.feedMsg('Rattled him!', false); }
    }
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

  // A hired escort fires at an enemy. The escort has already checked the line
  // is clear of the coach, team and player; this only resolves the bullet. Kills
  // go through the enemy's own damage(), so falls, bounty and wave-clearing all
  // work as for the player's shots, but they don't count as the player's kills.
  escortShot(esc, muzzle, aim, e, part, hits) {
    const g = this.g, cfg = esc.cfg;
    const dir = _v.subVectors(aim, muzzle).normalize().clone();
    g.fx.muzzle(muzzle, dir, { big: !!cfg.rifle });
    audio.play(cfg.snd, { position: muzzle, volume: 0.85, pitch: cfg.pitch * (0.97 + Math.random() * 0.06), maxDist: 600 });
    if (!hits) {
      // past him into the dirt
      const miss = aim.clone().add(new THREE.Vector3((Math.random() - 0.5) * 2.4, (Math.random() - 0.5) * 1.2, (Math.random() - 0.5) * 2.4));
      const md = miss.clone().sub(muzzle).normalize();
      const t = g.terrain.raycast(muzzle, md, 120);
      const end = muzzle.clone().addScaledVector(md, Math.min(t, 120));
      g.fx.tracer(muzzle, end);
      if (t < 120) g.fx.dust(end, { amount: 4, size: 0.3, up: 1 });
      return false;
    }
    const dmg = cfg.dmg * (part === 'head' ? cfg.headMult : 1);
    const killed = e.damage(dmg, part, dir);
    g.fx.tracer(muzzle, aim);
    g.fx.blood(aim, dir);
    audio.play('hit_flesh_' + (1 + (Math.random() * 2 | 0)), { position: aim, volume: 1 });
    if (killed) {
      let bounty = BOUNTY[e.type] || 25;
      if (part === 'horse') bounty = BOUNTY.horse + 10;
      if (part === 'head') bounty += BOUNTY.head;
      g.escorts.credit(esc, bounty, part === 'head');
    }
    return killed;
  }

  // an enemy fires at one of the hired escorts instead of the coach
  _shotAtEscort(esc, muzzle, { dist, acc, dmgPlayer, rifle }) {
    const g = this.g;
    const target = esc.chest.clone();
    let chance = acc * 0.85 * (1 - smoothstep(10, rifle ? 220 : 48, dist) * 0.7);
    const dir = _v.subVectors(target, muzzle).normalize();
    g.fx.muzzle(muzzle, dir, { big: rifle });
    if (rifle && dist > 60) audio.play('rifle_shot_far', { position: muzzle, volume: 1, delay: dist / 340, maxDist: 900 });
    else audio.play('schofield_shot2', { position: muzzle, volume: 0.9, pitch: 0.85 + Math.random() * 0.1, maxDist: 600 });
    if (Math.random() < chance) {
      g.fx.tracer(muzzle, target);
      g.fx.blood(target, dir);
      esc.damage(dmgPlayer * 1.4 * g.diff.dmgMult, muzzle);
    } else {
      const miss = target.add(new THREE.Vector3((Math.random() - 0.5) * 3, Math.random() * 1.4, (Math.random() - 0.5) * 3));
      g.fx.tracer(muzzle, miss.addScaledVector(_v.subVectors(miss, muzzle).normalize(), 40));
    }
  }

  // an enemy fires at the player or the coach
  enemyShot(enemy, muzzle, { dist, acc, dmgPlayer, dmgCoach, rifle = false }) {
    const g = this.g;
    // now and then at an escort riding nearer to him
    const esc = g.escorts?.pickTarget(enemy, muzzle, rifle);
    if (esc) return this._shotAtEscort(esc, muzzle, { dist: muzzle.distanceTo(esc.chest), acc, dmgPlayer, rifle });
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
        g.damageCoach(dmgCoach * g.diff.dmgMult);
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
