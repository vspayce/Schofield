// Unified input: desktop (pointer lock mouse + keys) and touch (drag-to-aim on
// the whole screen, plus on-screen buttons; dragging from the FIRE button also
// aims, so you can shoot and track in one thumb motion).

export class Input {
  constructor(canvas) {
    this.canvas = canvas;
    this.touch = matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window;
    document.body.classList.toggle('touch', this.touch);
    this.dx = 0; this.dy = 0;
    this.fireHeld = false; this.firePressed = false;
    this.reload = false; this.swap = false; this.deadeye = false; this.pause = false;
    this.whip = false; this.brake = false;
    this.enabled = false;
    this.sens = 1;
    this.invertY = false;
    this._pointers = new Map();
    this._bind();
  }

  consume() {
    const r = {
      dx: this.dx, dy: this.dy * (this.invertY ? -1 : 1), fire: this.fireHeld, firePressed: this.firePressed,
      reload: this.reload, swap: this.swap, deadeye: this.deadeye, pause: this.pause,
      whip: this.whip, brake: this.brake,
    };
    this.dx = this.dy = 0;
    this.firePressed = this.reload = this.swap = this.deadeye = this.pause = false;
    return r;
  }

  _bind() {
    // ---------- desktop
    window.addEventListener('mousemove', (e) => {
      if (!this.enabled || this.touch) return;
      // pointer lock, or (where lock is unavailable, e.g. embedded views) drag with any button
      if (document.pointerLockElement === this.canvas || (e.buttons & 1 && this._noLock)) {
        this.dx += e.movementX * 0.0022 * this.sens;
        this.dy += e.movementY * 0.0022 * this.sens;
      }
    });
    this.canvas.addEventListener('mousedown', (e) => {
      if (!this.enabled || this.touch) return;
      if (document.pointerLockElement !== this.canvas && !this._noLock) { this.lock(); return; }
      if (e.button === 0) { this.fireHeld = true; this.firePressed = true; }
      if (e.button === 2) this.deadeye = true;
    });
    window.addEventListener('mouseup', (e) => { if (e.button === 0) this.fireHeld = false; });
    this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    window.addEventListener('keydown', (e) => {
      if (!this.enabled) return;
      switch (e.code) {
        case 'KeyR': this.reload = true; break;
        case 'KeyQ': case 'Digit1': case 'Digit2': case 'Tab': this.swap = true; e.preventDefault(); break;
        case 'KeyE': case 'Space': this.deadeye = true; e.preventDefault(); break;
        case 'KeyW': case 'ShiftLeft': this.whip = true; break;
        case 'KeyS': case 'ControlLeft': this.brake = true; break;
        case 'Escape': case 'KeyP': this.pause = true; break;
      }
    });
    window.addEventListener('keyup', (e) => {
      if (e.code === 'KeyW' || e.code === 'ShiftLeft') this.whip = false;
      if (e.code === 'KeyS' || e.code === 'ControlLeft') this.brake = false;
    });
    document.addEventListener('pointerlockchange', () => {
      if (this.enabled && !this.touch && !this._noLock && document.pointerLockElement !== this.canvas) this.pause = true;
    });

    // ---------- touch
    const zone = document.getElementById('aim-zone');
    const onDown = (id, x, y, role) => this._pointers.set(id, { x, y, role });
    const onMove = (id, x, y) => {
      const p = this._pointers.get(id); if (!p) return;
      if (p.role === 'aim' || p.role === 'fire') {
        const k = 0.0052 * this.sens * (900 / Math.max(600, innerWidth));
        this.dx += (x - p.x) * k; this.dy += (y - p.y) * k;
      }
      p.x = x; p.y = y;
    };
    const onUp = (id) => {
      const p = this._pointers.get(id); if (!p) return;
      if (p.role === 'fire') this.fireHeld = false;
      if (p.role === 'whip') this.whip = false;
      if (p.role === 'brake') this.brake = false;
      if (p.el) p.el.classList.remove('pressed');
      this._pointers.delete(id);
    };
    zone.addEventListener('pointerdown', (e) => { if (!this.enabled) return; zone.setPointerCapture(e.pointerId); onDown(e.pointerId, e.clientX, e.clientY, 'aim'); });
    zone.addEventListener('pointermove', (e) => onMove(e.pointerId, e.clientX, e.clientY));
    zone.addEventListener('pointerup', (e) => onUp(e.pointerId));
    zone.addEventListener('pointercancel', (e) => onUp(e.pointerId));

    const btn = (id, role, onPress) => {
      const el = document.getElementById(id);
      const img = el.querySelector('img');
      if (img) img.addEventListener('error', () => img.setAttribute('data-missing', ''));
      el.addEventListener('pointerdown', (e) => {
        e.preventDefault(); e.stopPropagation();
        if (!this.enabled) return;
        el.setPointerCapture(e.pointerId);
        el.classList.add('pressed');
        this._pointers.set(e.pointerId, { x: e.clientX, y: e.clientY, role, el });
        onPress?.();
      });
      el.addEventListener('pointermove', (e) => onMove(e.pointerId, e.clientX, e.clientY));
      el.addEventListener('pointerup', (e) => onUp(e.pointerId));
      el.addEventListener('pointercancel', (e) => onUp(e.pointerId));
    };
    btn('btn-fire', 'fire', () => { this.fireHeld = true; this.firePressed = true; });
    btn('btn-reload', 'tap', () => { this.reload = true; });
    btn('btn-swap', 'tap', () => { this.swap = true; });
    btn('btn-deadeye', 'tap', () => { this.deadeye = true; });
    btn('btn-whip', 'whip', () => { this.whip = true; });
    btn('btn-brake', 'brake', () => { this.brake = true; });
    document.getElementById('btn-pause').addEventListener('pointerdown', (e) => { e.stopPropagation(); if (this.enabled) this.pause = true; });
  }

  setEnabled(v) {
    this.enabled = v;
    if (!v) {
      this.fireHeld = this.whip = this.brake = false;
      this._pointers.clear();
      if (document.pointerLockElement) document.exitPointerLock?.();
    }
  }

  lock() {
    if (this.touch || this._noLock) return;
    if (!this.canvas.requestPointerLock) { this._noLock = true; return; }
    try {
      const p = this.canvas.requestPointerLock();
      p?.catch?.((e) => {
        // embedded/iframe contexts can never lock: fall back to drag-to-aim.
        // Anything else (e.g. re-lock too soon after Esc) just retries on the next click.
        if (e?.name === 'WrongDocumentError' || e?.name === 'NotSupportedError') this._noLock = true;
      });
    } catch { /* retry on next click */ }
  }
}
