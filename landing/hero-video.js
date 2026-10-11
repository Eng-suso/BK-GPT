// Il video hero: parte da solo, si ferma quando non si vede e rispetta
// "riduci movimento" (resta il poster).
(() => {
  const video = document.querySelector(".hero-video");
  if (!video) return;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

  const play = () => {
    const attempt = video.play();
    if (attempt && typeof attempt.catch === "function") attempt.catch(() => { /* autoplay bloccato: resta il poster */ });
  };

  const apply = () => {
    if (reduced.matches) {
      video.removeAttribute("autoplay");
      video.pause();
      video.currentTime = 0;
    } else if (!document.hidden) {
      play();
    }
  };

  // Fuori schermo non consuma CPU e batteria.
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(([entry]) => {
      if (reduced.matches) return;
      if (entry.isIntersecting) play(); else video.pause();
    }, { threshold: 0.15 }).observe(video);
  }
  document.addEventListener("visibilitychange", () => (document.hidden ? video.pause() : apply()));
  reduced.addEventListener("change", apply);
  apply();
})();
