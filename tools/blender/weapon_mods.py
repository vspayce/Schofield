"""Per-weapon geometry modules for build_weapons.py.

Each gun added after the original three (Schofield, CoachGun, Winchester) lives in
its own `w_<name>.py` here, so they can be worked on independently. A module is:

    NAME   = 'Sharps'          # node name in weapons.glb; code looks this up
    LENGTH = 1.25              # nominal overall length in metres, for the sanity check

    def build(ctx):
        ...
        return (x, y, z)       # muzzle position, in the same space

`ctx` carries everything a module needs — see WeaponCtx below. Modules must not
import bpy or touch the scene directly; they only build bmesh geometry and hand
it to ctx.P(), which registers the part for the shared atlas bake.

World space (same as the rest of the file): the barrel points **-Y** (which the
glTF exporter turns into +Z forward), Z is up, X is across. The origin sits where
the firing hand grips — the wrist of the stock on a long gun.
"""


class WeaponCtx:
    """What a weapon module is handed. Attribute access only, no globals."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


# Modules are listed here in the order they're built and baked.
MODULES = ['w_springfield', 'w_sharps', 'w_gatling']


def load(ctx, strict=True):
    """Import each module, run its build(), and return {NAME: (muzzle, length)}.

    With strict=False a module that raises is reported and skipped instead of
    killing the run, so a broken gun doesn't block checking the others.
    """
    import importlib
    import traceback
    out = {}
    for modname in MODULES:
        try:
            mod = importlib.import_module(modname)
            ctx.weapon = mod.NAME
            muzzle = mod.build(ctx)
            if muzzle is None:
                raise RuntimeError('build() returned no muzzle position')
        except Exception:
            if strict:
                raise
            ctx.log('SKIPPED %s:' % modname, traceback.format_exc().strip().splitlines()[-1])
            continue
        out[mod.NAME] = (tuple(muzzle), getattr(mod, 'LENGTH', None))
    return out
