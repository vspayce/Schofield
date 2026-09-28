// What the coach is carrying. The same road three ways: the cargo sets the
// pay, how hard the run is, and which coach you drive.
//
// pay      multiplier on the route's mail contract
// diff     multiplied into the route's difficulty (see DIFF in main.js)
// bands    extra marauder waves, as fractions along the route
// coach    which GLB to drive
// livery   extra ironwork on top of it (see Coach.setLivery)

export const MISSIONS = {
  mail: {
    id: 'mail', name: 'Mail Contract', cargo: 'Overland mail and a light strongbox',
    pay: 1, coach: 'stagecoach', livery: 'concord', bands: [],
    diff: { countMult: 1, fireMult: 1, dmgMult: 1, riderAcc: 1, rifleAcc: 1 },
    blurb: 'Letters, parcels and a modest box. The road knows it, and mostly leaves you be.',
    risk: 0.25,
  },
  bank: {
    id: 'bank', name: 'Bank Transfer', cargo: 'Sealed bullion for the Territorial Bank',
    pay: 2.1, coach: 'stagecoach_treasure', livery: 'treasure', bands: [0.55],
    diff: { countMult: 1.35, fireMult: 0.88, dmgMult: 1.1, riderAcc: 1.1, rifleAcc: 1.12 },
    blurb: 'An armoured Abbott-Downing with shuttered ports. Word of a bullion run travels ahead of you.',
    risk: 0.6,
  },
  prisoner: {
    id: 'prisoner', name: 'Prisoner Transfer', cargo: 'A man due to hang, and friends who disagree',
    pay: 3.4, coach: 'stagecoach_treasure', livery: 'prison', bands: [0.32, 0.58, 0.78],
    diff: { countMult: 1.7, fireMult: 0.76, dmgMult: 1.2, riderAcc: 1.2, rifleAcc: 1.25 },
    blurb: 'A barred wagon and a hanging at the end of it. His people will come for him the whole way.',
    risk: 1,
  },
};

export const MISSION_LIST = Object.values(MISSIONS);

// fold a mission's multipliers into a route's base difficulty
export function applyMission(base, m) {
  const d = m.diff;
  return {
    riderAcc: Math.min(0.85, base.riderAcc * d.riderAcc),
    rifleAcc: Math.min(0.9, base.rifleAcc * d.rifleAcc),
    fireMult: base.fireMult * d.fireMult,        // lower = they shoot more often
    dmgMult: base.dmgMult * d.dmgMult,
    countMult: base.countMult * d.countMult,
  };
}
