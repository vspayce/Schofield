# SCHOFIELD — design & asset contracts

A 3rd-person western rail-shooter for the browser (mobile landscape first).
You ride shotgun on a Concord stagecoach between frontier towns, fighting off
riders who try to overtake the coach and riflemen on the ridgelines.

Reference photos live in `reference/` and `references/` (guns). Both are
gitignored — they stay on the artist's machine and never go to GitHub, so the
paths below won't resolve in a fresh clone.

Visual target: Red Dead Redemption 2 mood (reference/images-7/8) — warm
golden-hour light, atmospheric haze/fog, dusty painterly palette, heavy
silhouettes. We're a web game, so: strong lighting + fog + colour grade +
good silhouettes do the heavy lifting, not polygon counts.

## Stack
- Vite + Three.js (vanilla ES modules), DOM/CSS HUD. `npm run dev`, `npm run deploy` (gh-pages).
- Assets are built by scripts checked into `tools/` so they're reproducible:
  - `tools/blender/*.py`  — run with `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python tools/blender/<x>.py`
  - `tools/textures/*.py` — Python 3 + numpy/PIL/scipy
  - `tools/audio/*.py`    — Python 3 + numpy/scipy, encoded with ffmpeg
- Output goes to `public/assets/{models,textures,audio,ui}/`.

## Gameplay
- The coach runs on a spline route automatically (driver NPC holds the reins).
  Player can **whip** (speed burst, limited stamina) or **brake**.
- Player = shotgun messenger on the coach roof, camera over the right shoulder.
  Aim anywhere 360° (drag on mobile / mouse on desktop). Soft aim-assist on touch.
- Weapons: you carry a **sidearm** and a **long gun** and swap between them any time.
  The Schofield revolver and the messenger shotgun are free; the rest are bought from the
  **gunsmith** with your purse (bounties + mail contract, kept between runs; bounties are
  kept even when a run fails). Definitions live in `src/game/weapons.js`.
  - Sidearms: Schofield, Colt Paterson, Colt Navy, S&W Russian, Colt Peacemaker,
    Colt double-action ('77 Thunderer).
  - Long guns: messenger shotgun, Springfield Allin, Winchester 1873, Sharps "Old
    Reliable", Gatling gun (built in code; no GLB).
- **Scope** (button next to Dead Eye / F): magnified view from the guard's own eyes.
  Zoom depends on the gun (revolvers 2.5x, rifles 4-8x). Slows aim, steadies spread.
- Riflemen and gunmen who can see you get a marker overhead with their distance; it
  flashes red when they're about to fire.
- **Dead Eye**: meter fills with kills; activate for ~5 s of slow motion.
- Enemies:
  - **Riders**: approach from behind / flanks, ride alongside and shoot, try to reach the
    team horses. Shoot the rider (drops, horse runs off) or the horse (tumble).
  - **Ridge riflemen**: on hilltops / rocks / rooftops; telegraph with a lens glint
    before firing. Higher damage.
  - **Town gunmen**: in ghost-town windows/rooftops/behind barrels.
- Coach has HP (damage from hits on the coach); player has HP. Either at 0 = run failed.
- Reach town = results: bounty earned, accuracy, headshots, time; star rating.

## Routes (levels)
1. **Dry Creek Plains** — Mercy Springs → Dry Creek. Golden hour, open grassland, riders.
2. **Widow's Pass** — Dry Creek → Silver Notch. Winding mountain road, pines, snow on top,
   drop-offs, ridge riflemen. Overcast/cool.
3. **Perdition** — through a ghost town at dusk: gunmen in windows and rooftops, riders in
   the main street.
4. **Devil's Gulch** — red canyon at sunset, everything at once.
5. **Thunder Gorge** — Fort Providence → Cascade. A ledge road above a river gorge; a
   stream pours off a stone arch (`src/world/fallsrock.js`, merged procedural
   boulders) straight across the road, and the coach drives through the curtain.
   Going through: a splash and the coach rocks, the falls' synthesized roar opens
   up, and water sheets then beads down the lens for a few seconds (`uWet` /
   `uSheet` in the renderer's final pass, driven by `Water._burst`).

## World conventions (ALL assets must follow)
- Units: **metres**. Y-up in three.js. glTF 2.0 binary (`.glb`).
- In Blender: model faces **-Y** (Blender's "Front" view), Z up. The glTF exporter
  (`export_yup=True`) turns that into **+Z forward, +Y up** in three.js. Origin at ground
  level, centred on the footprint, unless stated otherwise.
- Apply all transforms before export. No cameras/lights in the GLB.
- Materials: Principled BSDF only (base colour texture/vertex colour, roughness, metallic,
  normal map optional). Keep textures embedded, ≤1024², JPEG-able when opaque.
  Alpha-cut foliage uses PNG + alphaMode MASK.
- Budget (mobile!): hero assets (coach, horse, human) ≤ 12k tris each; props ≤ 2k;
  buildings ≤ 6k. Each GLB ≤ ~1.5 MB.
- Skinned characters: ≤ 40 bones, ≤ 4 influences/vertex, animations as named glTF
  actions (NLA/actions exported with `export_animation_mode='ACTIONS'`).

## Asset list & node-name contracts (code looks these up by name)

### models/stagecoach.glb (Concord coach, ~5.2 m long incl. pole, body ~1.6 m wide)
- Nodes: `Body` (everything that bounces on the thoroughbraces), `Chassis`,
  `Wheel_FL`, `Wheel_FR`, `Wheel_RL`, `Wheel_RR` — each wheel a separate object with its
  origin at the hub and the axle along local X so code spins it about X.
  Front wheels ~1.0 m diameter, rear ~1.45 m.
- Empties: `Seat_Driver` (driver's bench, left), `Seat_Guard` (player sits on roof at the
  rear-right luggage rail, facing forward), `Hitch` (front end of the pole, where the team
  attaches), `Lamp_L`, `Lamp_R`.
- Look: dark oxblood/red-brown painted body with gold pinstripe, yellow-ochre running gear,
  leather boot at rear (reference/Pasted*.png, images-8), luggage on roof, leather curtains.

### models/horse.glb (skinned, ~2.4 m nose-to-tail, ~1.6 m at withers)
- Animations: `Gallop` (loop, ~0.5 s cycle), `Canter` (loop), `Idle`, `Fall` (one-shot,
  crumple sideways/forward), `Rear` (optional).
- Root motion NOT baked (in place). Saddle as a separate mesh `Saddle` (hideable),
  harness as `Harness` (hideable). Empty `Mount` at the saddle seat.
- Coat colours handled in code by tinting; bake a neutral light-brown coat with dark
  mane/tail/lower legs in the texture or vertex colours.

### models/horse_clydesdale.glb, horse_clevelandbay.glb, horse_thoroughbred.glb (coach team)
- The six-horse hitch: Clydesdale wheelers (1870s type, feathered, breeching), Cleveland
  Bay swing pair, Thoroughbred leaders (a matched chestnut pair). `build_horse.py -- --breed <b>`.
- Same bones, clips and `Horse`/`Saddle`/`Harness`/`Mount` nodes as horse.glb, so
  `createHorse({ breed })` drives them; colour is baked per breed (no code tint).
- `Harness` is the draught harness. Empties on the bones: `Trace_L/R` (where the traces
  leave the body), `Terret_L/R` (pad), `HameTerret_L/R`, `Bit_L/R`, `HeadRing_L/R`
  (rein drops the lines to the pairs ahead pass through), `PoleStrap` (collar bottom).
  `src/game/hitch.js` hangs the pole head, bars, lead chain, traces and six lines on them.

### models/rider.glb (skinned human, ~1.8 m, seated riding pose basis)
- Built by `tools/blender/build_rider.py`; previews by `preview_outlaws.py` / `preview_driver.py`
  (run them on the UNPACKED build, then `gltfpack` rider.glb as in `tools/pack_models.sh`).
- Origins: the seated clips have the SEAT CONTACT at the origin (parent to the horse's `Mount`,
  the coach's `Seat_Driver`/`Seat_Guard`). The standing clips lift the root so the FEET are at
  the origin. `Sit` is the exception: root at the bench SEAT SURFACE, feet on the ground 0.46 m
  below (SIT_DROP).
- Animations:
  - Riding: `Ride` (seated bounce loop matching Gallop), `RideAim` (pistol forward-right, loop),
    `Shoot` (additive recoil against RideAim), `FallOff` (one-shot, thrown backwards),
    `RideAimL` (left hand forward-left) + `ShootL` (its additive recoil), `RideAimDual` (both
    arms forward), `RideHolstered` (reins in the left hand, right hand by the sash).
  - Coach: `Drive` (driver: feet on the footboard, hands on the lines), `SeatAim` (the guard on the
    roof: knees up, torso still, gun shouldered along RideAim's AIM_DIR so player.js's +0.67 yaw
    holds) + `SeatShoot` (its additive recoil; `kick()` picks it while SeatAim plays).
  - Standing: `StandIdle`, `StandShoot`, `DieStanding` (one-shot), `Talk`, `LeanRail` (forearms on
    a rail 1.07 m high, 0.45 m ahead of the root).
  - Moving in place: `Walk` 1.4 m/s (cycle 64 frames = 1.067 s, stride 1.493 m per cycle,
    0.747 m per step), `Run` 3.6 m/s (42 frames = 0.70 s, stride 2.52 m). Planted feet slide back
    at exactly that speed, so a root moved at it doesn't skate.
- Bones include `spine`, `chest`, `neck`, `head`, `upperarm.R/L`, `forearm.R/L`, `hand.R/L` (code aims
  these; GLTFLoader names them `upperarmR`, `handL`, ...). Weapons go on the hand bones with an
  identity transform (+Z barrel, +Y up); `Grip_R` / `Grip_L` are equivalent empties.
- Looks are mesh toggles plus per-look colour multipliers in `createRider`'s LOOKS table
  (`src/game/characters.js`, exported as `VARIANTS` / `RIDER_VARIANTS`). Caller `tint` multiplies
  materials named *body*/*coat* (the dress material is `Dress_coat_mat`).
  - Old pieces, kept byte-identical: `Body`, `Duster`, `Hat_Wide`, `Hat_Bowler` (`townsman`,
    `drifter` = the guard's old look).
  - `Body_Man` (shared male body: real face, vest over shirt, cartridge belt, tucked boots) with
    `Coat_Guard` (linen duster, tinted dark for other men), `Hat_Guard`, `Moustache_Guard`,
    `Jacket` (canvas coat / shell jacket), `Serape`, `Bandana_Man`, `Gauntlets`, `Coat_Buffalo`,
    `Beard_Long`, `Moustache_Vaquero`, `Mask_Sack`, `Hat_Sugarloaf`, `Hat_Sombrero`, `Hat_Slouch`,
    `Hat_Lawman` (hat + moustache + star in one mesh).
  - `Body_Female` (Pearl Hart), `Body_Woman` + `Dress` (bodice and bustle skirt in one mesh; the
    skirt is modelled standing and inverse-skinned into the bind pose) + `Bonnet` / `Hat_Lady`.
  - The driver's own set: `Body_Driver`, `Coat_Driver`, `Hat_Driver`, `Moustache_Walrus`,
    `Neckerchief_Driver`, `Watch_Driver`. Hickok's: `Body_Hickok`, `Hat_Hickok`, `Colts_Hickok`
    (the Navies in his sash; hide it while the guns are in his hands) + `Coat_Guard` in black.
- Looks: `player` (Wells Fargo messenger), `driver`; the gang `outlaw`, `sugarloaf`, `vaquero`,
  `reb`, `mountain`, `pearl`, `bart` (Black Bart, on foot, rare); townsfolk `woman` (one of
  `woman_slate` / `woman_plum` / `woman_calico`), `lawman`, `townsman`, `drifter`; the old
  `bandit`, `bandit2`, `bandit3`, `gunman` names now on Body_Man; `hickok`. 5 meshes or fewer
  per look, 3 for the townsfolk.

### models/weapons.glb
- `Schofield` (nickel/blued S&W revolver, ~0.32 m, grip origin), `CoachGun` (double
  barrel, ~0.95 m, grip origin), `Winchester` (enemy rifle + player lever gun),
  `Springfield` (~1.31 m trapdoor musket), `Sharps` (~1.25 m falling block),
  `Gatling` (~1.19 m, six barrels). Each has a muzzle empty `Muzzle_<Name>`.
- The gun's **right** side is -X in Blender (forward x up, with the barrel down -Y),
  so a lock, hammer or loading gate belongs at -X.
- A weapon may ship one animated child node: `Gatling_Barrels` is the barrel cluster,
  its origin on the bore axis, spun about local Z by `createWeapon(...).spin()`.
- The five other revolvers reuse the `Schofield` mesh with a colour `finish`, and are
  told apart by their engravings in the gunsmith rather than in the hand.
- Built by `tools/blender/build_weapons.py`; the three long guns above live in
  `tools/blender/w_*.py` (see `weapon_mods.py`). All six share one baked 2048 atlas.

### models/props.glb (one file, many named root objects, each origin at base)
`Pine_A`, `Pine_B`, `Pine_Snow`, `DeadTree`, `Saguaro`, `Joshua`, `Sagebrush`,
`Rock_A`, `Rock_B`, `Rock_C`, `Boulder_Big`, `CliffChunk`, `Fence_Rail` (3 m section),
`TelegraphPole`, `Barrel`, `Crate`, `Wagon_Wreck`, `CowSkull`, `GraveCross`,
`Tumbleweed`, `Signpost`, `WaterTrough`, `Windmill`.
(Code instances these, so keep materials few and shared — atlas where possible.)

### models/town.glb (ghost-town kit, each root object origin at front-centre ground)
`Saloon` (2-storey, balcony), `GeneralStore`, `Sheriff`, `Bank`, `Church` (with steeple),
`Hotel`, `Livery` (barn), `WaterTower`, `Gallows`, `Boardwalk` (6 m section), `Shack`,
`CourtHouse` (two-storey brick county court house on a fenced lot, clock tower with four
dials, louvred belfry and weathervane; origin on the lot fence), and the street props
`Bench`, `HitchRail`, `Buckboard` (parked wagon, tongue toward -Y).
Street-facing side = -Y in Blender (+Z in three.js). Weathered, sun-bleached, broken
boards, faded painted signs. Add empties named `Spawn_*` at windows/roof edges where a
gunman can appear (e.g. `Spawn_Window_1`, `Spawn_Roof_1`), facing the street.
The clock hands are child nodes `Clock_Hour_<i>` / `Clock_Minute_<i>` (i = 0..3: front,
+X, back, -X), origin on the arbor, modelled at XII; code turns each about its dial's
normal (`setClock` in town.js, time from the route's `clock: 'h:mm'`) and merges them.

### textures/ (tiling, 1024², JPG; `_n` normal maps optional)
`dirt_road`, `dry_grass`, `green_grass`, `sand`, `rock`, `red_rock`, `snow`, `gravel`
+ `grass_blade.png` (alpha, for grass cards), `cloud_noise.png`, `mountain_silhouette.png`
(for far horizon layers), `wood_planks`, `lens_dirt.png`.

### ui/ (PNG, alpha)
Western HUD: revolver cylinder pieces (`cyl_full.png`, `cyl_empty.png`), shotgun shell icons,
`deadeye_icon.png`, `health_heart.png`, `coach_icon.png`, wanted-poster panel
`poster.png`, parchment `paper.png`, crosshair, touch button bases (`btn_fire.png`, etc.).
Fonts: load from Google Fonts (e.g. "Rye", "Smokum", "IM Fell English") in index.html.

### audio/ (OGG + M4A? → just `.mp3`, 44.1 kHz)
`schofield_shot`, `schofield_shot2`, `schofield_cock`, `schofield_reload`,
`shotgun_shot`, `shotgun_reload`, `rifle_shot_far`, `bullet_whiz_1..3`, `ricochet_1..3`,
`hit_flesh_1..2`, `hit_wood_1..2`, `horse_neigh`, `horse_gallop_loop`, `coach_rumble_loop`,
`wind_loop`, `whip_crack`, `deadeye_in`, `deadeye_out`, `heartbeat_loop`, `bell_town`,
`music_ride_loop`, `music_menu`, `sting_victory`, `sting_death`, `ui_click`.

## Missions
- `src/game/missions.js` — the same route three ways. **Mail** is the baseline;
  **Bank** pays 2.1x with one extra marauder band and an armoured coach;
  **Prisoner** pays 3.4x with three bands and the hardest opposition. The choice
  sits between route select and loadout, and multiplies into the route's DIFF.
- The coach is dressed for the job by `Coach.setLivery`: `concord` as built,
  `treasure` (iron shutters with firing slots, roof strongbox, dark green) and
  `prison` (barred windows, padlocked rear door). Same model, added ironwork.

## Wildlife and the railroad
- `src/game/wildlife.js` — a buffalo herd crosses the road (timed off how long the
  coach takes to reach it at cruise, so reining is the answer), plus grazing
  buffalo/bears/goats and circling hawks. Shootable for a hide price; butchering
  gives meat that restores health. Deliberately not Enemies, so chevrons and Dead
  Eye ignore them. Per-route in `routes.js` as `wildlife: { kinds, every }`.
- `src/world/town.js` — the start and end towns are populated. A court house
  stands on the start town's street and across the head of the end town's, so the
  stage pulls up in front of its clock. Folk walk the boardwalks (lawmen patrol by
  the jail), stand talking in twos and threes (the bank, hotel and saloon
  busiest), lean on hitching rails, sit on porch benches and cross the street
  when the road is clear; saddled horses stand at the rails and a buckboard or two
  is parked. They turn to watch the stage come in, and at gunfire (any `*shot*`
  sound) those within 90 m of the coach run for the nearest door. None are
  Enemies, so they can't be shot. Up to 32 people and 7 horses a town on desktop,
  fewer by quality tier and on touch (~14 and 3). Rider meshes have frustum
  culling off, so folk are hidden and unanimated more than 45 m behind or 160 m
  ahead of the coach, animate at a third of the rate beyond 70 m, and cast
  shadows only within 40 m. Clips used if the rig has them: `Walk` (in place,
  authored at 1.4 m/s), `Run`, `Sit` (root on the seat), `LeanRail`, `Talk`;
  without them they idle, and walkers glide. Variants `woman` and `lawman` are
  used once characters.js lists them in an exported `VARIANTS`. The ghost town
  stays deserted.
- `src/world/railroad.js` — a line crossing the road: the land along it is cut
  and filled to grade (`Route.setRail`, so terrain and scatter respect it),
  ballast, ties, a flat-bottomed rail, planks at the crossing with the road
  ramped up to them, a water tower from the town kit, material stacks and a
  section gang. Without a train the line is still under construction (rail stops
  at a railhead just past the road, the gang swinging sledges). The coach bangs
  over the rails. Per-route as `railroad: { at, workers, train }`.
- **The train** — `railroad.train: { cars, gunmen, speed, lead, caboose, from }`
  (plains and desert routes). With a train the line is finished end to end
  (±360 m, so it comes and goes in the haze) and the camp stands >3.5 m clear of
  the rails.
  - `src/world/train.js` builds it entirely in code: an 1870s 4-4-0 "American"
    (Russia-iron boiler with brass bands, balloon stack, brass steam dome, bell,
    whistle, green headlamp with glowing lens, slatted pilot, red spoked
    drivers with counterweights, working main and side rods and crossheads,
    varnished wood cab with a crew of two), a green tender with flared coping and
    cordwood, three board-and-batten boxcars (roof walks, brake wheels, ladders,
    sliding doors, truss rods, arch-bar trucks, link-and-pin couplers) and a
    caboose with a cupola. Parts are merged per car per material; wheelsets are
    two InstancedMeshes; lettering, lining and board grain are one 2048x1024
    canvas atlas. ~50 draw calls / ~75k tris for the whole train incl. crew.
    Smoke, cylinder-cock steam and ballast dust are one particle pool; the train
    is hidden and idle except while it runs.
  - `src/game/crossing.js` runs it: dispatched when the coach is `lead` (330 m)
    out, paced so the middle of the train is on the crossing when a coach at
    cruise gets there (like the herd). A warning banner and the long-long-short-
    long whistle come ~10 s out, then the bell. Gunmen (`Gunman` with a
    `carrier`, mixed rifles/pistols) ride the boxcar roofs as ordinary Enemies
    and topple off when shot. A slow coach (<4.5 m/s) is held at the edge while
    the train is across; one that drives in is hit: 16-55 coach damage by speed,
    stopped dead and knocked clear. The cars stop bullets (wood splinters, the
    engine sparks). Train sounds are synthesised at runtime (`src/core/synth.js`).
  - Debug: `?route=0&train=170` starts 170 m short of the crossing with the
    train dispatched.

## Code layout
```
src/
  main.js            boot, loader, state machine (menu → loadout → ride → results)
  core/              renderer, post, quality tiers, input, audio, assets
  world/             route spline, terrain chunks + splat shader, scatter, sky, route defs
  game/              coach, player/weapons, enemies, combat, deadeye, fx
  ui/                hud, menus
```
