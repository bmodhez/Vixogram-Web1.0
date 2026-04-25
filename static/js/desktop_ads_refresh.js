(function () {
  'use strict';

  function resolveRefreshMs() {
    const fallbackSeconds = 45;
    try {
      const raw = document.body && document.body.dataset
        ? document.body.dataset.vixoAdRefreshSeconds
        : '';
      const seconds = parseInt(String(raw || fallbackSeconds), 10);
      const normalized = Number.isFinite(seconds) ? Math.max(10, Math.min(3600, seconds)) : fallbackSeconds;
      return normalized * 1000;
    } catch {
      return fallbackSeconds * 1000;
    }
  }

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

  function slotHasRenderableMedia(slot) {
    if (!slot) return false;
    try {
      if (slot.querySelector('iframe')) return true;
      if (slot.querySelector('img[src], video[src], source[src]')) return true;
    } catch {
      return false;
    }
    return false;
  }

  function frameHasAd(frame) {
    if (!frame) return false;
    try {
      const doc = frame.contentDocument;
      if (!doc) return false;
      if (doc.querySelector('iframe, img[src], video[src], source[src], a[href]')) return true;
      const txt = String((doc.body && doc.body.textContent) || '').trim();
      return txt.length > 30;
    } catch {
      return false;
    }
  }

  function buildAdsterraSrcdoc(key, width, height) {
    const cfg = [
      'window.atOptions = {',
      `  \'key\' : \'${key}\',`,
      "  'format' : 'iframe',",
      `  'height' : ${height},`,
      `  'width' : ${width},`,
      "  'params' : {}",
      '};',
    ].join('\n');

    return [
      '<!doctype html>',
      '<html><head><meta charset="utf-8">',
      '<meta name="viewport" content="width=device-width,initial-scale=1">',
      '<style>html,body{margin:0;padding:0;overflow:hidden;width:100%;height:100%;background:transparent;}</style>',
      '</head><body>',
      `<script>${cfg}<\/script>`,
      `<script src="https://www.highperformanceformat.com/${key}/invoke.js?cb=${Date.now()}"><\/script>`,
      '</body></html>',
    ].join('');
  }

  function renderAdsterraSlot(slot) {
    if (!slot) return false;
    if (slot.getAttribute('data-vixo-ad-render-pending') === '1') return false;

    const key = String(slot.getAttribute('data-adsterra-key') || '').trim();
    const width = parseInt(String(slot.getAttribute('data-adsterra-width') || ''), 10);
    const height = parseInt(String(slot.getAttribute('data-adsterra-height') || ''), 10);
    if (!key || !Number.isFinite(width) || !Number.isFinite(height)) return false;

    const previousHtml = String(slot.innerHTML || '');

    try {
      slot.setAttribute('data-vixo-ad-render-pending', '1');
      slot.innerHTML = '';

      const wrap = document.createElement('div');
      wrap.className = 'overflow-hidden mx-auto';
      wrap.style.width = `${width}px`;
      wrap.style.height = `${height}px`;
      wrap.style.maxWidth = '100%';

      const frame = document.createElement('iframe');
      frame.setAttribute('data-vixo-ad-frame', '1');
      frame.setAttribute('title', 'Advertisement');
      frame.setAttribute('scrolling', 'no');
      frame.setAttribute('frameborder', '0');
      frame.width = String(width);
      frame.height = String(height);
      frame.style.width = `${width}px`;
      frame.style.height = `${height}px`;
      frame.style.maxWidth = '100%';
      frame.style.border = '0';
      frame.style.overflow = 'hidden';
      frame.srcdoc = buildAdsterraSrcdoc(key, width, height);

      wrap.appendChild(frame);
      slot.appendChild(wrap);

      const startedAt = Date.now();
      const timeoutMs = 8000;

      const probe = () => {
        try {
          if (frameHasAd(frame)) {
            slot.removeAttribute('data-vixo-ad-render-pending');
            return;
          }

          if (Date.now() - startedAt >= timeoutMs) {
            if (previousHtml.trim()) slot.innerHTML = previousHtml;
            slot.removeAttribute('data-vixo-ad-render-pending');
            return;
          }

          window.setTimeout(probe, 220);
        } catch {
          if (previousHtml.trim()) slot.innerHTML = previousHtml;
          slot.removeAttribute('data-vixo-ad-render-pending');
        }
      };

      probe();
      return true;
    } catch {
      if (previousHtml.trim()) slot.innerHTML = previousHtml;
      try { slot.removeAttribute('data-vixo-ad-render-pending'); } catch {}
      return false;
    }
  }

  function slotLooksBlank(slot) {
    if (!slot) return true;
    const frame = slot.querySelector('iframe[data-vixo-ad-frame]');
    if (frame) return !frameHasAd(frame);
    return !slotHasRenderableMedia(slot);
  }

  function refreshSlot(slot) {
    if (!slot) return;

    const renderedByAdsterra = renderAdsterraSlot(slot);

    let didRefresh = false;
    if (!renderedByAdsterra) {
      const media = slot.querySelectorAll('iframe[src], img[src], source[src], video[src]');
      media.forEach((el) => {
        const tag = (el.tagName || '').toLowerCase();
        if (tag === 'source') didRefresh = refreshMediaSource(el, 'src') || didRefresh;
        else didRefresh = refreshMediaSource(el, 'src') || didRefresh;
      });
    }

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

    if (!didRefresh && !renderedByAdsterra) {
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

    const selfHeal = () => {
      if (document.hidden) return;
      slots.forEach((slot) => {
        if (!slotLooksBlank(slot)) return;
        try { renderAdsterraSlot(slot); } catch {}
      });
    };

    // Render Adsterra slots immediately on page load.
    slots.forEach((slot) => {
      try { renderAdsterraSlot(slot); } catch {}
    });

    window.setInterval(tick, resolveRefreshMs());
    window.setInterval(selfHeal, 5000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDesktopAdAutoRefresh);
  } else {
    initDesktopAdAutoRefresh();
  }
})();
