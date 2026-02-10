(function () {
  "use strict";

  const svgDataUri = (svg) => {
    // Keep it simple + self-contained: inline SVGs as data URIs.
    // Use black fill and let tsParticles recolor via replaceColor.
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  };

  const prefersReducedMotion = () => {
    try {
      return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch {
      return false;
    }
  };

  const isMobile = () => {
    try {
      return window.matchMedia && window.matchMedia("(max-width: 639px)").matches;
    } catch {
      return (window.innerWidth || 0) <= 639;
    }
  };

  const makeId = (scope) => `vixo_auth_particles_${scope}_${Math.random().toString(16).slice(2)}`;

  const getOptions = () => {
    const mobile = isMobile();

    const icons = [
      {
        src: svgDataUri(
          `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="black"><path d="M12 2l1.6 6.1L20 10l-6.4 1.9L12 18l-1.6-6.1L4 10l6.4-1.9L12 2z"/></svg>`
        ),
        width: 24,
        height: 24,
        replaceColor: true,
      },
      {
        src: svgDataUri(
          `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="black"><path d="M12 3l7 9-7 9-7-9 7-9z"/></svg>`
        ),
        width: 24,
        height: 24,
        replaceColor: true,
      },
      {
        src: svgDataUri(
          `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="black"><path d="M10.8 4h2.4v6.8H20v2.4h-6.8V20h-2.4v-6.8H4v-2.4h6.8V4z"/></svg>`
        ),
        width: 24,
        height: 24,
        replaceColor: true,
      },
    ];

    return {
      fullScreen: { enable: false },
      detectRetina: true,
      fpsLimit: mobile ? 45 : 60,
      background: { color: { value: "transparent" } },
      interactivity: {
        events: {
          onHover: { enable: false },
          onClick: { enable: false },
          resize: true,
        },
      },
      particles: {
        number: {
          value: mobile ? 34 : 52,
          density: { enable: true, area: 1100 },
        },
        links: { enable: false },
        move: {
          enable: true,
          speed: mobile ? 0.6 : 0.8,
          direction: "none",
          outModes: { default: "out" },
        },
        opacity: {
          value: { min: 0.12, max: 0.65 },
          animation: { enable: true, speed: 0.55, minimumValue: 0.1, sync: false },
        },
        size: {
          // Smaller range so circles feel like dots; blur/shadow makes some read as "blurred dots".
          value: { min: mobile ? 3 : 4, max: mobile ? 14 : 18 },
        },
        rotate: {
          value: { min: 0, max: 360 },
          direction: "random",
          animation: { enable: true, speed: mobile ? 1.6 : 2.4 },
        },
        color: { value: ["#ffffff"] },
        shadow: {
          enable: true,
          color: { value: "#ffffff" },
          blur: mobile ? 10 : 12,
          offset: { x: 0, y: 0 },
        },
        shape: {
          // Requested replacement for emoji particles:
          // - circles
          // - small SVG icons
          // - blurred dots (via small sizes + soft shadow blur)
          type: ["circle", "image"],
          options: {
            image: icons,
          },
        },
      },
    };
  };

  const mountParticles = async (container, { className, scope }) => {
    if (!container) return false;
    if (container.dataset.vixoParticlesMounted === "1") return true;
    container.dataset.vixoParticlesMounted = "1";

    const mount = document.createElement("div");
    const id = makeId(scope);
    mount.id = id;
    mount.className = className;
    container.insertBefore(mount, container.firstChild);

    try {
      if (!window.tsParticles || typeof window.tsParticles.load !== "function") return true;
      await window.tsParticles.load(id, getOptions());
      return true;
    } catch {
      // best-effort; keep page usable if particles fail
      return true;
    }
  };

  const init = () => {
    if (prefersReducedMotion()) return;

    // Primary: full-page background on auth pages.
    const bg = document.querySelector(".vixo-auth-bg");
    if (bg) {
      void mountParticles(bg, { className: "vixo-auth-bg-particles", scope: "bg" });
      return;
    }

    // Fallback: card-only (in case markup changes).
    const cards = document.querySelectorAll(".vixo-auth-card");
    if (!cards || !cards.length) return;
    cards.forEach((card, idx) => {
      void mountParticles(card, { className: "vixo-auth-particles", scope: `card_${idx}` });
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
