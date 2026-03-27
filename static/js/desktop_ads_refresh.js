(function () {
  'use strict';

  const REFRESH_MS = 45 * 1000;

  function withCacheBust(url) {
    try {
      const u = new URL(String(url || ''), window.location.origin);
      u.searchParams.set('vixo_ad_refresh', String(Date.now()));
      return u.toString();
    } catch {
      return String(url || '');
    }
  }

  function refreshMediaSource(el, attrName) {
    try {
      const src = el.getAttribute(attrName);
      if (!src) return false;
      const next = withCacheBust(src);
      if (!next) return false;
      el.setAttribute(attrName, next);
      return true;
    } catch {
      return false;
    }
  }

  function refreshSlot(slot) {
    if (!slot) return;

    let didRefresh = false;
    const media = slot.querySelectorAll('iframe[src], img[src], source[src], video[src]');
    media.forEach((el) => {
      const tag = (el.tagName || '').toLowerCase();
      if (tag === 'source') didRefresh = refreshMediaSource(el, 'src') || didRefresh;
      else didRefresh = refreshMediaSource(el, 'src') || didRefresh;
    });

    // Allow other ad integrations to hook into this event if needed.
    try {
      slot.dispatchEvent(new CustomEvent('vixo:ad-refresh', { bubbles: true }));
    } catch {}

    // Tiny visual pulse so refresh feels intentional even for placeholders.
    try {
      slot.classList.add('ring-1', 'ring-emerald-400/35');
      window.setTimeout(() => {
        try { slot.classList.remove('ring-1', 'ring-emerald-400/35'); } catch {}
      }, 700);
    } catch {}

    if (!didRefresh) {
      try {
        slot.setAttribute('data-vixo-ad-refreshed-at', String(Date.now()));
      } catch {}
    }
  }

  function initDesktopAdAutoRefresh() {
    const slots = Array.from(
      document.querySelectorAll('[data-vixo-side-ad-slot], [data-vixo-footer-ad-slot]')
    );
    if (!slots.length) return;

    const tick = () => {
      if (document.hidden) return;
      slots.forEach(refreshSlot);
    };

    window.setInterval(tick, REFRESH_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDesktopAdAutoRefresh);
  } else {
    initDesktopAdAutoRefresh();
  }
})();
