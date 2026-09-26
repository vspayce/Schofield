// Getting the browser's tabs and address bar out of the way on phones.
// Android/Chrome (and iPad) allow real fullscreen from a tap; iPhone Safari
// doesn't, so there the only way is launching from a home-screen icon.
const root = document.documentElement;

export const fullscreen = {
  supported: !!(root.requestFullscreen || root.webkitRequestFullscreen),
  get active() { return !!(document.fullscreenElement || document.webkitFullscreenElement); },
  // launched from the home screen: no browser UI to hide
  standalone: matchMedia('(display-mode: fullscreen), (display-mode: standalone)').matches || navigator.standalone === true,

  // must be called from inside a tap/click handler
  enter() {
    if (this.active || this.standalone || !this.supported) return;
    const req = root.requestFullscreen ? root.requestFullscreen({ navigationUI: 'hide' }) : root.webkitRequestFullscreen();
    Promise.resolve(req).then(() => screen.orientation?.lock?.('landscape')).catch(() => {});
  },

  // iPhone in the browser: point the player at Add to Home Screen instead
  get needsHomeScreen() { return !this.supported && !this.standalone && /iPhone|iPod/.test(navigator.userAgent); },
};
