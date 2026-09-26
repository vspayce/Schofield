// The guns. You carry two: a sidearm and a long gun (SWAP flips between
// them). The Schofield and the messenger shotgun are yours from the start;
// the rest are sold by the gunsmith in town.
//
// kind: revolver | shotgun | rifle | gatling   (drives HUD ammo art, feel)
// model: node in weapons.glb, or 'Gatling' (built in code)
// zoom: magnification through the scope
// auto: holding FIRE keeps shooting
// stats: 0..1 bars for the menus

export const WEAPONS = {
  // ------------------------------------------------------------ sidearms
  schofield: {
    id: 'schofield', slot: 'side', kind: 'revolver', name: 'Schofield Revolver', year: 1875, price: 0,
    model: 'Schofield', mag: 6, interval: 0.26, reload: 1.6, auto: true,
    pellets: 1, spread: 0.0045, damage: 60, headMult: 3, range: 260, falloff: [90, 260], floor: 0.5, kick: 0.028, zoom: 2.5,
    snd: ['schofield_shot', 'schofield_shot2'], reloadSnd: 'schofield_reload',
    stats: { power: 0.5, range: 0.5, rate: 0.7, accuracy: 0.7 },
    blurb: 'Smith & Wesson top-break .45. Six quick, true shots and a fast reload. Jesse James carried one.',
  },
  paterson: {
    id: 'paterson', slot: 'side', kind: 'revolver', name: 'Colt Paterson', year: 1836, price: 150,
    model: 'Schofield', finish: [0.55, 0.55, 0.6], mag: 5, interval: 0.2, reload: 2.6, auto: true,
    pellets: 1, spread: 0.0055, damage: 58, headMult: 3, range: 230, falloff: [70, 230], floor: 0.45, kick: 0.024, zoom: 2.5,
    snd: ['schofield_shot2'], pitch: 1.12, reloadSnd: 'schofield_reload',
    stats: { power: 0.45, range: 0.45, rate: 0.85, accuracy: 0.6 },
    blurb: 'Colt\'s first revolver. The Texas Rangers proved it against Comanche riders. Five shots fired fast, but slow to reload.',
  },
  navy: {
    id: 'navy', slot: 'side', kind: 'revolver', name: 'Colt Navy', year: 1851, price: 300,
    model: 'Schofield', finish: [1.25, 1.05, 0.7], mag: 6, interval: 0.25, reload: 2.1, auto: true,
    pellets: 1, spread: 0.0025, damage: 64, headMult: 3, range: 300, falloff: [110, 300], floor: 0.55, kick: 0.024, zoom: 2.5,
    snd: ['schofield_shot'], pitch: 1.05, reloadSnd: 'schofield_reload',
    stats: { power: 0.55, range: 0.6, rate: 0.7, accuracy: 0.9 },
    blurb: 'A brass-framed .36 that points like your finger. Wild Bill Hickok wore a pair of them.',
  },
  russian: {
    id: 'russian', slot: 'side', kind: 'revolver', name: 'S&W Russian', year: 1870, price: 500,
    model: 'Schofield', finish: [0.7, 0.72, 0.8], mag: 6, interval: 0.27, reload: 1.2, auto: true,
    pellets: 1, spread: 0.004, damage: 74, headMult: 3, range: 280, falloff: [100, 280], floor: 0.5, kick: 0.03, zoom: 2.5,
    snd: ['schofield_shot', 'schofield_shot2'], pitch: 0.95, reloadSnd: 'schofield_reload',
    stats: { power: 0.65, range: 0.55, rate: 0.65, accuracy: 0.75 },
    blurb: 'Built for the Tsar\'s army in .44 Russian. The top-break action ejects all six at once for the fastest reload out West.',
  },
  peacemaker: {
    id: 'peacemaker', slot: 'side', kind: 'revolver', name: 'Colt Peacemaker', year: 1873, price: 800,
    model: 'Schofield', finish: [0.45, 0.47, 0.55], mag: 6, interval: 0.3, reload: 2.0, auto: true,
    pellets: 1, spread: 0.0035, damage: 90, headMult: 3, range: 300, falloff: [110, 300], floor: 0.55, kick: 0.036, zoom: 2.5,
    snd: ['schofield_shot'], pitch: 0.88, reloadSnd: 'schofield_reload',
    stats: { power: 0.8, range: 0.6, rate: 0.6, accuracy: 0.8 },
    blurb: 'The Single Action Army in .45 Colt, the frontier lawman\'s gun. Bat Masterson ordered his straight from the factory. One shot drops most men.',
  },
  lightning: {
    id: 'lightning', slot: 'side', kind: 'revolver', name: 'Colt Double-Action', year: 1877, price: 1100,
    model: 'Schofield', finish: [1.3, 1.3, 1.35], mag: 6, interval: 0.13, reload: 1.8, auto: true,
    pellets: 1, spread: 0.005, damage: 66, headMult: 3, range: 260, falloff: [90, 260], floor: 0.5, kick: 0.022, zoom: 2.5,
    snd: ['schofield_shot2'], pitch: 1.08, reloadSnd: 'schofield_reload',
    stats: { power: 0.55, range: 0.5, rate: 1, accuracy: 0.65 },
    blurb: 'The \'77 Thunderer. No thumbing the hammer, so hold the trigger and empty it. Billy the Kid favored one.',
  },

  // ----------------------------------------------------------- long guns
  shotgun: {
    id: 'shotgun', slot: 'long', kind: 'shotgun', name: 'Messenger Shotgun', year: 1870, price: 0,
    model: 'CoachGun', mag: 2, interval: 0.32, reload: 1.8,
    pellets: 9, spread: 0.06, damage: 20, headMult: 1.5, range: 70, falloff: [14, 55], floor: 0.15, kick: 0.075, zoom: 1.6, knock: true,
    snd: ['shotgun_shot'], reloadSnd: 'shotgun_reload',
    stats: { power: 1, range: 0.2, rate: 0.45, accuracy: 0.25 },
    blurb: 'The Wells Fargo guard\'s double-barrel 10 gauge. Doc Holliday carried one at the O.K. Corral. Knocks a man clean out of the saddle.',
  },
  springfield: {
    id: 'springfield', slot: 'long', kind: 'rifle', name: 'Springfield Allin', year: 1866, price: 400,
    model: 'Winchester', finish: [0.8, 0.75, 0.7], mag: 1, interval: 0.4, reload: 1.1,
    pellets: 1, spread: 0.0018, damage: 140, headMult: 2.5, range: 420, falloff: [200, 420], floor: 0.6, kick: 0.06, zoom: 5, knock: true,
    snd: ['schofield_shot'], pitch: 0.7, reloadSnd: 'schofield_cock',
    stats: { power: 0.85, range: 0.75, rate: 0.3, accuracy: 0.9 },
    blurb: 'The Army\'s trapdoor .50-70, one round at a time. Flip the breech, drop in a cartridge, and reach out past any pistol.',
  },
  winchester: {
    id: 'winchester', slot: 'long', kind: 'rifle', name: 'Winchester 1873', year: 1873, price: 650,
    model: 'Winchester', mag: 12, interval: 0.36, reload: 3.0,
    pellets: 1, spread: 0.0025, damage: 78, headMult: 2.5, range: 360, falloff: [150, 360], floor: 0.55, kick: 0.04, zoom: 4,
    snd: ['schofield_shot'], pitch: 0.8, reloadSnd: 'shotgun_reload',
    stats: { power: 0.65, range: 0.7, rate: 0.6, accuracy: 0.85 },
    blurb: '"The gun that won the West." Twelve rounds of .44-40 through the lever. Buffalo Bill swore by his.',
  },
  sharps: {
    id: 'sharps', slot: 'long', kind: 'rifle', name: 'Sharps "Old Reliable"', year: 1874, price: 1000,
    model: 'Winchester', finish: [0.6, 0.5, 0.42], mag: 1, interval: 0.5, reload: 1.5,
    pellets: 1, spread: 0.0007, damage: 260, headMult: 2, range: 700, falloff: [400, 700], floor: 0.7, kick: 0.09, zoom: 8, knock: true,
    snd: ['shotgun_shot'], pitch: 0.75, reloadSnd: 'schofield_cock',
    stats: { power: 1, range: 1, rate: 0.2, accuracy: 1 },
    blurb: 'The buffalo hunter\'s .50-90. Billy Dixon knocked a man off his horse at nearly a mile with one at Adobe Walls.',
  },
  gatling: {
    id: 'gatling', slot: 'long', kind: 'gatling', name: 'Gatling Gun', year: 1866, price: 2000,
    model: 'Gatling', mag: 40, interval: 0.075, reload: 4.2, auto: true,
    pellets: 1, spread: 0.018, damage: 34, headMult: 2, range: 300, falloff: [80, 300], floor: 0.4, kick: 0.012, zoom: 2,
    snd: ['schofield_shot2'], pitch: 0.9, reloadSnd: 'shotgun_reload',
    stats: { power: 0.5, range: 0.6, rate: 1, accuracy: 0.35 },
    blurb: 'Six barrels turned by a crank, some 200 rounds a minute. The Army bought it in 1866. Bolted to the roof rail, it\'s the end of any ambush.',
  },
};

export const STARTERS = ['schofield', 'shotgun'];
export const SIDEARMS = Object.values(WEAPONS).filter((w) => w.slot === 'side');
export const LONG_GUNS = Object.values(WEAPONS).filter((w) => w.slot === 'long');
