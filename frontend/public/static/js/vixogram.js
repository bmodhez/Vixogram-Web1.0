/* Vixogram site JS extracted from Django templates.
   This file is loaded on every page.
*/

// Tailwind CDN configuration must be defined BEFORE tailwindcss.com script runs.
// (base.html includes this file before tailwind.)
(() => {
  // eslint-disable-next-line no-undef
  if (typeof window !== 'undefined') {
    // Tailwind CDN looks for a global `tailwind.config`.
    window.tailwind = window.tailwind || {};
    window.tailwind.config = {
      theme: {
        extend: {
          colors: {
            emerald: {
              50:  '#f0f9ff',
              100: '#e0f2fe',
              200: '#bae6fd',
              300: '#7dd3fc',
              400: '#38bdf8',
              500: '#0ea5e9',
              600: '#0284c7',
              700: '#0369a1',
              800: '#075985',
              900: '#0c4a6e',
              950: '#082f49',
            },
          },
          fontFamily: {
            sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
          },
        },
      },
    };
  }
})();

(function () {
  'use strict';

  // --- Theme (light/dark) ---
  // Default: dark. Persist in localStorage. Apply early to reduce flash.
  const THEME_KEY = 'vixo_theme';

  function getStoredTheme() {
    try {
      const v = String(window.localStorage.getItem(THEME_KEY) || '').toLowerCase();
      return (v === 'light' || v === 'dark') ? v : 'dark';
    } catch {
      return 'dark';
    }
  }

  function applyTheme(theme) {
    const t = (theme === 'light' || theme === 'dark') ? theme : 'dark';
    try {
      document.documentElement.classList.toggle('theme-light', t === 'light');
      document.documentElement.classList.toggle('theme-dark', t === 'dark');
      document.documentElement.setAttribute('data-theme', t);
    } catch {
      // ignore
    }

    try {
      const btn = document.getElementById('theme_toggle');
      if (btn) {
        const label = (t === 'light') ? 'Dark' : 'Light';
        btn.setAttribute('data-theme', t);
        btn.setAttribute('aria-label', `Switch to ${label} theme`);
        btn.innerHTML = (t === 'light')
          ? '<span class="inline-flex items-center gap-2"><span aria-hidden="true">☀️</span><span class="hidden sm:inline">Light</span></span>'
          : '<span class="inline-flex items-center gap-2"><span aria-hidden="true">🌙</span><span class="hidden sm:inline">Dark</span></span>';
      }
    } catch {
      // ignore
    }
  }

  function setTheme(theme) {
    const t = (theme === 'light' || theme === 'dark') ? theme : 'dark';
    try { window.localStorage.setItem(THEME_KEY, t); } catch {}
    applyTheme(t);
  }

  function toggleTheme() {
    const next = (getStoredTheme() === 'light') ? 'dark' : 'light';
    setTheme(next);
  }

  // Apply before most DOM work.
  applyTheme(getStoredTheme());

  function initThemeToggle() {
    const btn = document.getElementById('theme_toggle');
    if (!btn) return;
    btn.addEventListener('click', (e) => {
      try { e.preventDefault(); } catch {}
      toggleTheme();
    });
  }

  // Expose for debugging/other scripts.
  window.__vixoTheme = window.__vixoTheme || { get: getStoredTheme, set: setTheme, toggle: toggleTheme };

  function readJsonScript(id) {
    try {
      const el = document.getElementById(id);
      if (!el) return null;
      const txt = (el.textContent || '').trim();
      if (!txt) return null;
      return JSON.parse(txt);
    } catch {
      return null;
    }
  }

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  // Expose for other scripts.
  window.getCookie = window.getCookie || getCookie;

  // Smooth, burst-friendly chat autoscroll.
  const __vixoScrollAnim = {
    raf: null,
    startTime: 0,
    duration: 180,
    startTop: 0,
    targetTop: 0,
    container: null,
  };

  function scrollToBottom(opts) {
    const chatContainer = document.getElementById('chat_container');
    if (!chatContainer) return;

    const options = (opts && typeof opts === 'object') ? opts : {};
    const force = !!options.force;
    const behavior = (options.behavior === 'auto' || options.behavior === 'instant') ? 'auto' : 'smooth';

    // Only autoscroll if user is already near bottom (prevents yanking user while reading old messages).
    const distanceFromBottom = (chatContainer.scrollHeight - (chatContainer.scrollTop + chatContainer.clientHeight));
    const nearBottom = distanceFromBottom <= 140;
    if (!force && !nearBottom) return;

    const targetTop = Math.max(0, chatContainer.scrollHeight - chatContainer.clientHeight);

    if (behavior === 'auto') {
      chatContainer.scrollTop = targetTop;
      return;
    }

    const now = (window.performance && typeof performance.now === 'function') ? performance.now() : Date.now();
    const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);

    __vixoScrollAnim.container = chatContainer;
    __vixoScrollAnim.startTop = chatContainer.scrollTop;
    __vixoScrollAnim.targetTop = targetTop;
    __vixoScrollAnim.startTime = now;

    const step = (ts) => {
      const s = __vixoScrollAnim;
      if (!s.container) return;
      const tnow = (window.performance && typeof performance.now === 'function') ? ts : Date.now();
      const elapsed = Math.max(0, tnow - s.startTime);
      const t = Math.min(1, elapsed / s.duration);
      const eased = easeOutCubic(t);
      const nextTop = s.startTop + (s.targetTop - s.startTop) * eased;
      try {
        s.container.scrollTop = nextTop;
      } catch {
        // ignore
      }
      if (t < 1) {
        s.raf = window.requestAnimationFrame(step);
      } else {
        s.raf = null;
      }
    };

    if (__vixoScrollAnim.raf) {
      try { window.cancelAnimationFrame(__vixoScrollAnim.raf); } catch {}
      __vixoScrollAnim.raf = null;
    }
    __vixoScrollAnim.raf = window.requestAnimationFrame(step);
  }

  window.scrollToBottom = window.scrollToBottom || scrollToBottom;

  function initToasts() {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toasts = container.querySelectorAll('.toast');
    toasts.forEach((toast) => {
      let dismissed = false;
      const duration = Number(toast.getAttribute('data-duration') || '4000');
      const closeBtn = toast.querySelector('[data-toast-close]');

      const dismiss = () => {
        if (dismissed) return;
        dismissed = true;
        toast.classList.add('opacity-0', '-translate-y-1');
        toast.classList.add('transform');
        window.setTimeout(() => {
          toast.remove();
          if (container.childElementCount === 0) container.remove();
        }, 220);
      };

      if (closeBtn) closeBtn.addEventListener('click', dismiss);
      window.setTimeout(dismiss, Math.max(1000, duration));
    });
  }

  // Init small UI hooks that need DOM nodes.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      try { initThemeToggle(); } catch {}
    }, { once: true });
  } else {
    try { initThemeToggle(); } catch {}
  }

  function initGlobalLoadingIndicator() {
    const el = document.getElementById('global-loading');
    const textEl = document.getElementById('global-loading-text');
    if (!el) return;

    let pending = 0;
    let hideTimer = null;
    let minVisibleUntil = 0;
    const uploadRequests = new WeakMap();

    const show = (text) => {
      // Never show the loader on top of the custom confirm modal.
      try {
        const confirmModal = document.getElementById('confirm-modal');
        if (confirmModal && !confirmModal.classList.contains('hidden')) return;
      } catch {
        // ignore
      }
      if (hideTimer) {
        clearTimeout(hideTimer);
        hideTimer = null;
      }
      if (textEl) textEl.textContent = text || 'Loading…';
      el.classList.remove('hidden');
      el.classList.add('flex');
    };

    const hide = () => {
      if (hideTimer) clearTimeout(hideTimer);
      const now = Date.now();
      const wait = Math.max(150, minVisibleUntil - now);
      hideTimer = setTimeout(() => {
        el.classList.add('hidden');
        el.classList.remove('flex');
      }, wait);
    };

    const inc = (text) => {
      pending += 1;
      show(text);
    };

    const dec = () => {
      pending = Math.max(0, pending - 1);
      if (pending === 0) hide();
    };

    window.__vixoLoading = { show, hide, inc, dec };

    // Defer so other handlers (custom confirm, unsaved changes, htmx, etc.) can call preventDefault().
    const defer = (fn) => {
      try {
        if (typeof queueMicrotask === 'function') queueMicrotask(fn);
        else Promise.resolve().then(fn);
      } catch {
        setTimeout(fn, 0);
      }
    };

    document.addEventListener('click', (e) => {
      const a = e.target && e.target.closest ? e.target.closest('a') : null;
      if (!a) return;
      if (a.hasAttribute('download')) return;
      if ((a.getAttribute('target') || '').toLowerCase() === '_blank') return;
      if (a.getAttribute('data-no-loading') !== null) return;

      const href = (a.getAttribute('href') || '').trim();
      if (!href) return;
      if (href.startsWith('#')) return;
      if (href.startsWith('mailto:') || href.startsWith('tel:')) return;

      try {
        const url = new URL(href, window.location.href);
        if (url.origin !== window.location.origin) return;
      } catch {
        return;
      }

      defer(() => {
        try {
          if (window.__vixoSkipLoadingOnce) {
            window.__vixoSkipLoadingOnce = false;
            return;
          }
        } catch {
          // ignore
        }
        if (e.defaultPrevented) return;
        show('Loading…');
      });
    }, true);

    document.addEventListener('submit', (e) => {
      const form = e.target;
      if (!form || !form.getAttribute) return;
      if (form.getAttribute('data-no-loading') !== null) return;

      const text = (form.getAttribute('data-loading-text') || 'Loading…').trim() || 'Loading…';

      defer(() => {
        if (e.defaultPrevented) return;
        show(text);
      });
    }, true);

    window.addEventListener('pageshow', () => {
      pending = 0;
      hide();
    });

    const shouldSkipHtmxLoader = (event) => {
      try {
        const elt = (event && event.detail && event.detail.elt) ? event.detail.elt : event.target;
        if (!elt) return false;

        // If the request originates from (or is within) a no-loading element,
        // never show the global loader.
        // This avoids loader mismatches when the UI clears inputs during afterRequest.
        if (typeof elt.closest === 'function') {
          const noLoading = elt.closest('[data-no-loading]');
          if (noLoading) {
            // Exception: chat file uploads should show a loader.
            // We detect uploads at beforeRequest and remember the xhr for afterRequest.
            if (elt.id === 'chat_message_form') {
              const xhr = (event && event.detail) ? event.detail.xhr : null;
              if (xhr && uploadRequests.has(xhr)) return false;
            }
            return true;
          }
        } else if (elt.getAttribute && elt.getAttribute('data-no-loading') !== null) {
          return true;
        }

        return false;
      } catch {
        // ignore
      }
      return false;
    };

    document.body.addEventListener('htmx:beforeRequest', (e) => {
      try {
        const elt = (e && e.detail && e.detail.elt) ? e.detail.elt : e.target;
        const xhr = (e && e.detail) ? e.detail.xhr : null;

        if (elt && elt.id === 'chat_message_form' && xhr) {
          const fileInput = document.getElementById('chat_file_input');
          const inUploadMode = !!(fileInput && fileInput.files && fileInput.files.length);
          if (inUploadMode) {
            uploadRequests.set(xhr, true);
            minVisibleUntil = Math.max(minVisibleUntil, Date.now() + 5000);
            inc('Uploading… Please wait');
            return;
          }
        }
      } catch {
        // ignore
      }

      if (shouldSkipHtmxLoader(e)) return;
      inc('Loading…');
    });
    document.body.addEventListener('htmx:afterRequest', (e) => {
      try {
        const xhr = (e && e.detail) ? e.detail.xhr : null;
        if (xhr && uploadRequests.has(xhr)) {
          uploadRequests.delete(xhr);
          dec();
          return;
        }
      } catch {
        // ignore
      }

      if (shouldSkipHtmxLoader(e)) return;
      dec();
    });
    document.body.addEventListener('htmx:responseError', () => { pending = 0; hide(); });
    document.body.addEventListener('htmx:sendError', () => { pending = 0; hide(); });
    document.body.addEventListener('htmx:timeout', () => { pending = 0; hide(); });

    try {
      if (typeof window.fetch === 'function' && !window.fetch.__vixo_patched) {
        const origFetch = window.fetch.bind(window);
        const wrapped = function (...args) {
          inc('Loading…');
          return origFetch(...args).finally(() => dec());
        };
        wrapped.__vixo_patched = true;
        window.fetch = wrapped;
      }
    } catch {
      // ignore
    }
  }


  function initContactDropdown() {
    const btn = document.getElementById('contact_btn');
    const dropdown = document.getElementById('contact_dropdown');
    const closeBtn = document.getElementById('contact_close');
    if (!btn || !dropdown) return;

    function open() {
      dropdown.classList.remove('hidden');
      btn.setAttribute('aria-expanded', 'true');
    }

    function close() {
      dropdown.classList.add('hidden');
      btn.setAttribute('aria-expanded', 'false');
    }

    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (dropdown.classList.contains('hidden')) open();
      else close();
    });

    if (closeBtn) closeBtn.addEventListener('click', (e) => { e.preventDefault(); close(); });

    document.addEventListener('click', (e) => {
      if (dropdown.classList.contains('hidden')) return;
      const inside = e.target && e.target.closest ? e.target.closest('#contact_dropdown, #contact_btn') : null;
      if (!inside) close();
    }, true);
  }

  function initUserMenuDropdown() {
    const btn = document.getElementById('user_menu_btn');
    const dropdown = document.getElementById('user_menu');
    if (!btn || !dropdown) return;

    function open() {
      dropdown.classList.remove('hidden');
      btn.setAttribute('aria-expanded', 'true');
    }

    function close() {
      dropdown.classList.add('hidden');
      btn.setAttribute('aria-expanded', 'false');
    }

    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (dropdown.classList.contains('hidden')) open();
      else close();
    });

    document.addEventListener('click', (e) => {
      if (dropdown.classList.contains('hidden')) return;
      const inside = e.target && e.target.closest ? e.target.closest('#user_menu, #user_menu_btn') : null;
      if (!inside) close();
    }, true);
  }

  function initCustomConfirm() {
    const modal = document.getElementById('confirm-modal');
    const titleEl = document.getElementById('confirm-title');
    const msgEl = document.getElementById('confirm-message');
    const okBtn = document.getElementById('confirm-ok');
    const cancelBtn = document.getElementById('confirm-cancel');

    if (!modal || !okBtn || !cancelBtn || !titleEl || !msgEl) return;

    let pendingAction = null;

    const open = ({ title, message, onConfirm, showCancel, okText, cancelText } = {}) => {
      try {
        if (window.__vixoLoading && typeof window.__vixoLoading.hide === 'function') {
          window.__vixoLoading.hide();
        }
      } catch {
        // ignore
      }
      titleEl.textContent = title || 'Confirm';
      msgEl.textContent = message || 'Are you sure?';
      pendingAction = onConfirm || null;

      const show = (typeof showCancel === 'boolean') ? showCancel : true;
      cancelBtn.classList.toggle('hidden', !show);
      okBtn.textContent = (okText || 'Yes');
      cancelBtn.textContent = (cancelText || 'Cancel');

      modal.classList.remove('hidden');
      modal.setAttribute('aria-hidden', 'false');
    };

    const close = () => {
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
      pendingAction = null;
    };

    okBtn.addEventListener('click', () => {
      const fn = pendingAction;
      close();
      if (typeof fn === 'function') fn();
    });
    cancelBtn.addEventListener('click', close);
    modal.addEventListener('click', (e) => {
      if (e.target === modal || e.target === modal.firstElementChild) close();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') close();
    });

    document.addEventListener('submit', (e) => {
      const form = e.target;
      if (!(form instanceof HTMLFormElement)) return;
      if (form.dataset && form.dataset.confirming === '1') {
        delete form.dataset.confirming;
        return;
      }
      const message = form.getAttribute('data-confirm');
      if (!message) return;
      e.preventDefault();
      open({
        title: form.getAttribute('data-confirm-title') || 'Confirm',
        message,
        onConfirm: () => {
          try {
            if (form.dataset) form.dataset.confirming = '1';
            if (typeof form.requestSubmit === 'function') form.requestSubmit();
            else form.submit();
          } catch {
            try { form.submit(); } catch {}
          }
        },
      });
    }, true);

    document.addEventListener('click', (e) => {
      const btn = e.target && e.target.closest ? e.target.closest('[data-confirm]') : null;
      if (!btn) return;
      if (btn.closest('form')) return;
      const message = btn.getAttribute('data-confirm');
      if (!message) return;
      e.preventDefault();
      open({
        title: btn.getAttribute('data-confirm-title') || 'Confirm',
        message,
        onConfirm: () => {
          if (btn.tagName === 'A' && btn.href) window.location.href = btn.href;
          else btn.click();
        },
      });
    }, true);

    window.__openConfirm = open;
    window.__closeConfirm = close;
  }

  function initPremiumUpgradePopup() {
    document.addEventListener('click', (e) => {
      const t = e.target;
      const btn = t && t.closest ? t.closest('[data-premium-upgrade]') : null;
      if (!btn) return;
      try { e.preventDefault(); } catch {}

      const open = (typeof window.__openConfirm === 'function') ? window.__openConfirm : null;
      if (open) {
        open({
          title: 'Premium',
          message: 'Premium is not available yet.',
          showCancel: false,
          okText: 'OK',
        });
      } else {
        // eslint-disable-next-line no-alert
        alert('Premium is not available yet.');
      }
    }, true);
  }

  function initImageViewer() {
    const modal = document.getElementById('image-viewer');
    const img = document.getElementById('image-viewer-img');
    if (!modal || !img) return;

    const open = (src, alt) => {
      if (!src) return;
      img.src = src;
      img.alt = alt || 'Image';
      modal.classList.remove('hidden');
      modal.setAttribute('aria-hidden', 'false');
    };

    const close = () => {
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
      img.src = '';
      img.alt = '';
    };

    document.addEventListener('click', (e) => {
      const t = e.target;
      if (!(t instanceof HTMLElement)) return;

      const clickable = t.closest('img[data-image-viewer]');
      if (clickable && clickable instanceof HTMLImageElement) {
        e.preventDefault();
        open(clickable.currentSrc || clickable.src, clickable.alt || 'Image');
        return;
      }

      if (t.closest('[data-image-viewer-close]') || t.closest('[data-image-viewer-backdrop]')) {
        e.preventDefault();
        close();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !modal.classList.contains('hidden')) close();
    });
  }

  function initVideoViewer() {
    const modal = document.getElementById('video-viewer');
    const video = document.getElementById('video-viewer-video');
    const source = document.getElementById('video-viewer-source');
    if (!modal || !video || !source) return;

    const open = (src, type) => {
      if (!src) return;
      source.src = src;
      if (type) source.type = type;
      modal.classList.remove('hidden');
      modal.setAttribute('aria-hidden', 'false');
      try { video.load(); } catch {}
    };

    const close = () => {
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
      try { video.pause(); } catch {}
      source.src = '';
      source.removeAttribute('type');
      try { video.load(); } catch {}
    };

    document.addEventListener('click', (e) => {
      const t = e.target;
      if (!(t instanceof HTMLElement)) return;

      const clickable = t.closest('video[data-video-viewer]');
      if (clickable && clickable instanceof HTMLVideoElement) {
        e.preventDefault();
        const src = clickable.getAttribute('data-video-src') || '';
        const type = clickable.getAttribute('data-video-type') || '';
        open(src, type);
        return;
      }

      if (t.closest('[data-video-viewer-close]') || t.closest('[data-video-viewer-backdrop]')) {
        e.preventDefault();
        close();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !modal.classList.contains('hidden')) close();
    });
  }

  function initVideoDecodeFallback() {
    document.addEventListener('error', (e) => {
      const el = e && e.target;
      if (!el || el.tagName !== 'VIDEO') return;
      const wrap = el.parentElement;
      if (!wrap) return;
      const fallback = wrap.querySelector('[data-video-fallback]');
      if (fallback) fallback.classList.remove('hidden');
    }, true);

    document.addEventListener('loadeddata', (e) => {
      const el = e && e.target;
      if (!el || el.tagName !== 'VIDEO') return;
      const wrap = el.parentElement;
      if (!wrap) return;
      const fallback = wrap.querySelector('[data-video-fallback]');
      if (fallback) fallback.classList.add('hidden');
    }, true);
  }

  function initHtmxConfirmBridge() {
    document.body.addEventListener('htmx:confirm', (e) => {
      try {
        if (!e || !e.detail) return;
        if (typeof window.__openConfirm !== 'function') return;

        const elt = e.target;
        const question = e.detail.question || (elt && elt.getAttribute ? elt.getAttribute('hx-confirm') : '') || '';
        if (!question) return;

        e.preventDefault();

        const title = (elt && elt.getAttribute) ? (elt.getAttribute('data-confirm-title') || 'Confirm') : 'Confirm';
        window.__openConfirm({
          title,
          message: question,
          onConfirm: () => {
            try {
              if (typeof e.detail.issueRequest === 'function') e.detail.issueRequest(true);
              else if (typeof e.detail.issueRequest === 'function') e.detail.issueRequest();
            } catch {
              // ignore
            }
          },
        });
      } catch {
        // ignore
      }
    });
  }

  function escapeHtml(str) {
    return String(str)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function initAuthenticatedNotifiers(baseCfg) {
    if (!baseCfg || !baseCfg.userAuthenticated) return;

    // Lets chat pages know a global handler exists (avoid duplicate toasts)
    window.__hasGlobalCallInvite = true;
    window.__hasGlobalMentionNotify = true;

    const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${wsScheme}://${window.location.host}/ws/notify/`;

    let audioCtx = null;
    let ringTimer = null;
    let ringAudio = null;
    let audioUnlocked = false;
    const notifAudio = document.getElementById('notif_sound');
    const incomingAudioEl = document.getElementById('incoming_sound');
    const recentInvites = new Map();
    const recentMentions = new Map();
    let notifUnread = parseInt(String(baseCfg.navNotifUnread || 0), 10) || 0;

    // Tab title badge like: "(1) Vixogram - Chat. Call. Connect."
    const __rawInitialTitle = String(document.title || '');
    const baseTitle = __rawInitialTitle.replace(/^\(\d+\)\s*/i, '').trim() || 'Vixogram';
    let titleBlinkTimer = null;
    let titleBlinkStopTimer = null;
    let titleBlinkOn = true;

    function setTabTitle() {
      try {
        if (notifUnread > 0) document.title = `(${notifUnread}) ${baseTitle}`;
        else document.title = baseTitle;
      } catch {
        // ignore
      }
    }

    function startTabTitleBlink() {
      try {
        if (titleBlinkTimer) { clearInterval(titleBlinkTimer); titleBlinkTimer = null; }
        if (titleBlinkStopTimer) { clearTimeout(titleBlinkStopTimer); titleBlinkStopTimer = null; }
      } catch {}

      if (notifUnread <= 0) {
        setTabTitle();
        return;
      }

      // Blink for ~5 seconds, then settle with the unread prefix.
      titleBlinkOn = true;
      titleBlinkTimer = setInterval(() => {
        try {
          titleBlinkOn = !titleBlinkOn;
          document.title = titleBlinkOn ? `(${notifUnread}) ${baseTitle}` : baseTitle;
        } catch {
          // ignore
        }
      }, 650);

      titleBlinkStopTimer = setTimeout(() => {
        try {
          if (titleBlinkTimer) { clearInterval(titleBlinkTimer); titleBlinkTimer = null; }
        } catch {}
        setTabTitle();
      }, 5000);
    }

    function primeNotifSoundOnce() {
      if (!notifAudio) return;
      try {
        notifAudio.muted = false;
        notifAudio.volume = 1.0;
        try { notifAudio.load(); } catch {}
        const p = notifAudio.play();
        if (p && typeof p.then === 'function') {
          p.then(() => {
            notifAudio.pause();
            notifAudio.currentTime = 0;
          }).catch(() => {});
        }
      } catch {
        // ignore
      }
    }

    function primeIncomingSoundOnce() {
      if (!incomingAudioEl) return;
      try {
        incomingAudioEl.muted = false;
        incomingAudioEl.volume = 1.0;
        incomingAudioEl.loop = false;
        try { incomingAudioEl.load(); } catch {}
        const p = incomingAudioEl.play();
        if (p && typeof p.then === 'function') {
          p.then(() => {
            incomingAudioEl.pause();
            incomingAudioEl.currentTime = 0;
          }).catch(() => {});
        }
      } catch {
        // ignore
      }
    }

    function playFallbackBeep() {
      try {
        audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});

        const ctx = audioCtx;
        const now = ctx.currentTime;
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = 'sine';
        o.frequency.setValueAtTime(880, now);
        g.gain.setValueAtTime(0.0001, now);
        g.gain.exponentialRampToValueAtTime(0.08, now + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, now + 0.18);
        o.connect(g);
        g.connect(ctx.destination);
        o.start(now);
        o.stop(now + 0.2);
      } catch {
        // ignore
      }
    }

    function playNotifSound() {
      try {
        const src = notifAudio ? (notifAudio.getAttribute('src') || '') : '';
        if (!src) {
          playFallbackBeep();
          return;
        }

        const a = new Audio(src);
        a.preload = 'auto';
        a.muted = false;
        a.volume = 1.0;
        const p = a.play();
        if (p && typeof p.catch === 'function') {
          p.catch(() => {
            playFallbackBeep();
          });
        }
      } catch {
        playFallbackBeep();
      }
    }

    function animateToastIn(el) {
      if (!el) return;
      try {
        el.classList.add('opacity-0', '-translate-x-4');
        requestAnimationFrame(() => {
          el.classList.remove('opacity-0', '-translate-x-4');
        });
      } catch {
        // ignore
      }
    }

    function updateNotifBadge() {
      const el = document.getElementById('nav_notif_badge');
      if (el) {
        if (notifUnread > 0) {
          el.textContent = notifUnread > 99 ? '99+' : String(notifUnread);
          el.classList.remove('hidden');
        } else {
          el.classList.add('hidden');
        }
      }
      setTabTitle();
    }

    function bumpNotifUnread() {
      notifUnread = Math.min(999, (notifUnread || 0) + 1);
      updateNotifBadge();
      startTabTitleBlink();
    }

    function isOnChatRoom(roomName) {
      try {
        if (!roomName) return false;
        const p = String(window.location.pathname || '');
        if (!p.startsWith('/chat/room/')) return false;
        const raw = p.slice('/chat/room/'.length).replace(/\/+$/, '');
        const current = decodeURIComponent(raw || '');
        return current === String(roomName);
      } catch {
        return false;
      }
    }

    function ensureIncomingContainer() {
      let c = document.getElementById('incoming-call-container');
      if (c) return c;
      c = document.createElement('div');
      c.id = 'incoming-call-container';
      c.className = 'fixed top-24 right-6 z-50 w-[min(24rem,calc(100vw-3rem))] space-y-3';
      document.body.appendChild(c);
      return c;
    }

    function stopIncomingRing() {
      if (ringTimer) {
        clearInterval(ringTimer);
        ringTimer = null;
      }

      if (ringAudio) {
        try {
          ringAudio.pause();
          ringAudio.currentTime = 0;
        } catch {
          // ignore
        }
        ringAudio = null;
      }
    }

    function playIncomingRing() {
      stopIncomingRing();

      try {
        const src = incomingAudioEl ? (incomingAudioEl.getAttribute('src') || '') : '';
        const a = new Audio(src || '/static/incoming.wav');
        a.preload = 'auto';
        a.loop = true;
        a.muted = false;
        a.volume = 1.0;
        ringAudio = a;
        const p = a.play();
        if (p && typeof p.catch === 'function') {
          p.catch(() => {
            try { ringAudio = null; } catch {}
            try {
              audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
              if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
            } catch {
              return;
            }

            const ringOnce = () => {
              try {
                const ctx = audioCtx;
                const now = ctx.currentTime;
                const g = ctx.createGain();
                g.gain.setValueAtTime(0.0001, now);
                g.gain.exponentialRampToValueAtTime(0.15, now + 0.02);
                g.gain.exponentialRampToValueAtTime(0.0001, now + 1.8);
                g.connect(ctx.destination);

                const o1 = ctx.createOscillator();
                const o2 = ctx.createOscillator();
                o1.type = 'sine';
                o2.type = 'sine';
                o1.frequency.setValueAtTime(480, now);
                o2.frequency.setValueAtTime(620, now);
                o1.connect(g);
                o2.connect(g);
                o1.start(now);
                o2.start(now);
                o1.stop(now + 1.9);
                o2.stop(now + 1.9);
              } catch {
                // ignore
              }
            };

            ringOnce();
            ringTimer = setInterval(ringOnce, 5000);
          });
        }
        return;
      } catch {
        // ignore
      }

      try {
        audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
      } catch {
        return;
      }

      const ringOnce = () => {
        try {
          const ctx = audioCtx;
          const now = ctx.currentTime;
          const g = ctx.createGain();
          g.gain.setValueAtTime(0.0001, now);
          g.gain.exponentialRampToValueAtTime(0.15, now + 0.02);
          g.gain.exponentialRampToValueAtTime(0.0001, now + 1.8);
          g.connect(ctx.destination);

          const o1 = ctx.createOscillator();
          const o2 = ctx.createOscillator();
          o1.type = 'sine';
          o2.type = 'sine';
          o1.frequency.setValueAtTime(480, now);
          o2.frequency.setValueAtTime(620, now);
          o1.connect(g);
          o2.connect(g);
          o1.start(now);
          o2.start(now);
          o1.stop(now + 1.9);
          o2.stop(now + 1.9);
        } catch {
          // ignore
        }
      };

      ringOnce();
      ringTimer = setInterval(ringOnce, 5000);
    }

    async function declineInvite(callEventUrl, callType) {
      if (!callEventUrl) return;
      try {
        const body = new URLSearchParams();
        body.set('action', 'decline');
        body.set('type', callType || 'voice');
        await fetch(callEventUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCookie('csrftoken'),
          },
          body,
        });
      } catch {
        // ignore
      }
    }

    function showIncomingCall(payload) {
      const from = payload.from_username || 'Someone';
      const type = (payload.call_type || 'voice').toLowerCase() === 'video' ? 'video' : 'voice';
      const room = payload.chatroom_name || '';
      const key = `${room}:${type}:${from}`;
      const now = Date.now();
      const last = recentInvites.get(key) || 0;
      if (now - last < 1200) return;
      recentInvites.set(key, now);

      const callUrl = payload.call_url || '';
      const callEventUrl = payload.call_event_url || '';
      if (!callUrl) return;

      playIncomingRing();

      let handled = false;
      let autoDeclineTimer = null;

      const container = ensureIncomingContainer();
      const toast = document.createElement('div');
      toast.className = 'pointer-events-auto flex items-start gap-3 rounded-xl border border-gray-800 bg-gray-900/90 px-4 py-3 text-sm text-gray-100 shadow-lg shadow-black/20 transition duration-200 ease-out transform-gpu';
      toast.innerHTML = `
        <div class="mt-0.5 h-2.5 w-2.5 flex-none rounded-full bg-emerald-400"></div>
        <div class="flex-1">
          <div class="font-semibold">Incoming ${type === 'video' ? 'video' : 'voice'} call</div>
          <div class="text-gray-300 text-xs mt-0.5">from ${from}${room ? ` • room ${room}` : ''}</div>
          <div class="mt-3 flex gap-2">
            <a href="${callUrl}" class="vixo-btn text-xs bg-emerald-500 hover:bg-emerald-600 text-white px-3 py-1.5 rounded-lg transition-colors">Accept</a>
            <button type="button" data-decline class="text-xs bg-gray-800 hover:bg-gray-700 text-white px-3 py-1.5 rounded-lg transition-colors">Decline</button>
          </div>
        </div>
        <button type="button" data-close class="-mr-1 -mt-1 inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-300 hover:text-white hover:bg-gray-800/60 transition" aria-label="Dismiss">
          <span aria-hidden="true">×</span>
        </button>
      `;

      const removeToast = () => {
        toast.classList.add('opacity-0');
        setTimeout(() => toast.remove(), 200);
        stopIncomingRing();
      };

      toast.querySelector('[data-close]')?.addEventListener('click', async () => {
        if (!handled) {
          handled = true;
          if (autoDeclineTimer) { clearTimeout(autoDeclineTimer); autoDeclineTimer = null; }
          try { await declineInvite(callEventUrl, type); } catch {}
        }
        removeToast();
      });
      toast.querySelector('[data-decline]')?.addEventListener('click', async () => {
        handled = true;
        if (autoDeclineTimer) { clearTimeout(autoDeclineTimer); autoDeclineTimer = null; }
        await declineInvite(callEventUrl, type);
        removeToast();
      });
      const accept = toast.querySelector('a');
      if (accept) accept.addEventListener('click', () => {
        handled = true;
        if (autoDeclineTimer) { clearTimeout(autoDeclineTimer); autoDeclineTimer = null; }
        stopIncomingRing();
      });

      autoDeclineTimer = setTimeout(async () => {
        if (handled) return;
        handled = true;
        try { await declineInvite(callEventUrl, type); } catch {}
        removeToast();
      }, 14000);

      container.appendChild(toast);
      animateToastIn(toast);
    }

    function showMention(payload) {
      const from = payload.from_username || 'Someone';
      const room = payload.chatroom_name || '';
      const messageId = payload.message_id || 0;
      const preview = (payload.preview || '').trim();

      if (!room) return;

      const key = `${room}:${from}:${messageId}`;
      const now = Date.now();
      const last = recentMentions.get(key) || 0;
      if (now - last < 1200) return;
      recentMentions.set(key, now);

      try {
        window.dispatchEvent(new CustomEvent('chat:mention', {
          detail: {
            chatroom_name: room,
            message_id: messageId,
            from_username: from,
          },
        }));
      } catch {
        // ignore
      }

      if (isOnChatRoom(room)) {
        let nearBottom = true;
        try {
          if (typeof window.__isChatNearBottom === 'function') {
            nearBottom = !!window.__isChatNearBottom();
          }
        } catch {
          nearBottom = true;
        }
        if (nearBottom) return;
      }

      const url = `/chat/room/${encodeURIComponent(room)}`;

      bumpNotifUnread();
      playNotifSound();

      const container = ensureIncomingContainer();
      const toast = document.createElement('div');
      toast.className = 'pointer-events-auto flex items-start gap-3 rounded-xl border border-gray-800 bg-gray-900/90 px-4 py-3 text-sm text-gray-100 shadow-lg shadow-black/20 transition duration-200 ease-out transform-gpu';
      toast.innerHTML = `
        <div class="mt-0.5 h-2.5 w-2.5 flex-none rounded-full bg-emerald-400"></div>
        <div class="flex-1 min-w-0">
          <div class="font-semibold">You were mentioned</div>
          <div class="text-gray-300 text-xs mt-0.5">by @${from} • room ${room}</div>
          ${preview ? `<div class="mt-2 text-xs text-gray-300 truncate">${escapeHtml(preview)}</div>` : ''}
          <div class="mt-3">
            <a href="${url}" class="text-xs bg-gray-800 hover:bg-gray-700 text-white px-3 py-1.5 rounded-lg transition-colors">Open chat</a>
          </div>
        </div>
        <button type="button" data-close class="-mr-1 -mt-1 inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-300 hover:text-white hover:bg-gray-800/60 transition" aria-label="Dismiss">
          <span aria-hidden="true">×</span>
        </button>
      `;

      const removeToast = () => {
        toast.classList.add('opacity-0');
        setTimeout(() => toast.remove(), 200);
      };

      toast.querySelector('[data-close]')?.addEventListener('click', removeToast);
      setTimeout(removeToast, 12000);
      container.appendChild(toast);
      animateToastIn(toast);
    }

    function initNotifDropdown() {
      const btn = document.getElementById('notif_btn');
      const panel = document.getElementById('notif_dropdown');
      const closeBtn = document.getElementById('notif_close');
      if (!btn || !panel) return;

      function clampPanelToViewport() {
        try {
          if (window.matchMedia && window.matchMedia('(max-width: 639px)').matches) return;
          if (!panel || panel.classList.contains('hidden')) return;
          panel.style.transform = '';

          const pad = 12;
          const rect = panel.getBoundingClientRect();
          const vw = window.innerWidth || 0;
          if (!vw) return;

          let dx = 0;
          if (rect.left < pad) dx = pad - rect.left;
          if (rect.right + dx > vw - pad) dx = (vw - pad) - rect.right;

          if (dx) panel.style.transform = `translateX(${Math.round(dx)}px)`;
        } catch {
          // ignore
        }
      }

      let refreshTimer = null;
      function refreshDropdownIfOpen() {
        try {
          if (!panel || panel.classList.contains('hidden')) return;
          if (!window.htmx || typeof window.htmx.ajax !== 'function') return;
          if (refreshTimer) return;
          refreshTimer = setTimeout(() => {
            refreshTimer = null;
            const url = btn.getAttribute('hx-get');
            if (url) window.htmx.ajax('GET', url, { target: '#notif_dropdown_body', swap: 'innerHTML' });
          }, 150);
        } catch {
          // ignore
        }
      }

      function markNotificationRead(anchorEl) {
        if (!anchorEl) return;
        const url = anchorEl.getAttribute('data-notif-mark-url') || '';
        const isRead = (anchorEl.getAttribute('data-notif-read') || '0') === '1';
        if (!url || isRead) return;

        anchorEl.setAttribute('data-notif-read', '1');
        const dot = anchorEl.querySelector('[data-notif-dot]');
        if (dot) {
          dot.classList.remove('bg-emerald-400');
          dot.classList.add('bg-gray-600');
        }
        notifUnread = Math.max(0, (notifUnread || 0) - 1);
        updateNotifBadge();

        try {
          const csrf = (typeof getCookie === 'function') ? (getCookie('csrftoken') || '') : '';
          const fd = new FormData();
          if (csrf) fd.append('csrfmiddlewaretoken', csrf);
          const ok = navigator.sendBeacon(url, fd);
          if (ok) return;
        } catch {}

        try {
          const body = new URLSearchParams();
          const csrf = (typeof getCookie === 'function') ? (getCookie('csrftoken') || '') : '';
          if (csrf) body.set('csrfmiddlewaretoken', csrf);
          fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body,
            keepalive: true,
          }).catch(() => {});
        } catch {}
      }

      const open = () => {
        panel.classList.remove('hidden');
        btn.setAttribute('aria-expanded', 'true');
        setTimeout(clampPanelToViewport, 0);
        try {
          if (window.htmx && typeof window.htmx.ajax === 'function') {
            const url = btn.getAttribute('hx-get');
            if (url) window.htmx.ajax('GET', url, { target: '#notif_dropdown_body', swap: 'innerHTML' });
          }
        } catch {}
      };

      const close = () => {
        panel.classList.add('hidden');
        btn.setAttribute('aria-expanded', 'false');
        try { panel.style.transform = ''; } catch {}
      };

      btn.addEventListener('click', (e) => {
        e.preventDefault();
        if (panel.classList.contains('hidden')) open();
        else close();
      });

      if (closeBtn) closeBtn.addEventListener('click', (e) => {
        e.preventDefault();
        close();
      });

      document.addEventListener('click', (e) => {
        const t = e.target;
        if (!t) return;
        if (panel.classList.contains('hidden')) return;
        if (panel.contains(t) || btn.contains(t)) return;
        close();
      }, true);

      panel.addEventListener('click', (e) => {
        const t = e.target;
        if (!(t instanceof HTMLElement)) return;
        const a = t.closest('a[data-notif-id]');
        if (!(a instanceof HTMLAnchorElement)) return;
        markNotificationRead(a);
      }, true);

      document.body.addEventListener('htmx:afterRequest', (e) => {
        const target = e && e.target;
        if (!target) return;
        if (target.getAttribute && String(target.getAttribute('hx-post') || '').includes('notifications/read-all')) {
          notifUnread = 0;
          updateNotifBadge();
        }
        if (target.getAttribute && String(target.getAttribute('hx-post') || '').includes('notifications/clear-all')) {
          notifUnread = 0;
          updateNotifBadge();
        }
      });

      document.body.addEventListener('htmx:afterSwap', (e) => {
        const target = e && e.target;
        if (!target) return;
        if (target.id !== 'notif_dropdown_body') return;

        clampPanelToViewport();

        const marker = target.querySelector('[data-notif-unread]');
        if (!marker) return;
        const raw = marker.getAttribute('data-notif-unread') || '0';
        const n = parseInt(raw, 10);
        if (Number.isFinite(n)) {
          notifUnread = Math.max(0, n);
          updateNotifBadge();
        }
      });

      window.__refreshNotifDropdownIfOpen = refreshDropdownIfOpen;

      window.addEventListener('resize', clampPanelToViewport);
    }

    function unlockAudioOnce() {
      if (audioUnlocked) return;
      try {
        audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
        const o = audioCtx.createOscillator();
        const g = audioCtx.createGain();
        g.gain.value = 0.00001;
        o.connect(g);
        g.connect(audioCtx.destination);
        o.start();
        o.stop(audioCtx.currentTime + 0.01);
        audioUnlocked = true;
      } catch {
        // ignore
      }

      primeNotifSoundOnce();
      primeIncomingSoundOnce();
    }

    document.addEventListener('click', unlockAudioOnce, { once: true, capture: true });

    updateNotifBadge();
    initNotifDropdown();

    function connect() {
      let socket;
      try {
        socket = new WebSocket(wsUrl);
      } catch {
        return;
      }

      socket.onmessage = function (event) {
        let payload;
        try { payload = JSON.parse(event.data); } catch { return; }
        if (payload.type === 'call_invite') showIncomingCall(payload);
        if (payload.type === 'call_control') {
          try { window.dispatchEvent(new CustomEvent('call:control', { detail: payload })); } catch {}
        }
        if (payload.type === 'mention') {
          showMention(payload);
          try { window.__refreshNotifDropdownIfOpen && window.__refreshNotifDropdownIfOpen(); } catch {}
        }
        if (payload.type === 'chat_block_status') {
          try { window.dispatchEvent(new CustomEvent('chat:block_status', { detail: payload })); } catch {}
        }
        if (payload.type === 'reply') {
          showMention({
            from_username: payload.from_username,
            chatroom_name: payload.chatroom_name,
            message_id: payload.message_id,
            preview: payload.preview,
          });
          try { window.__refreshNotifDropdownIfOpen && window.__refreshNotifDropdownIfOpen(); } catch {}
        }
        if (payload.type === 'follow') {
          const from = payload.from_username || 'Someone';
          bumpNotifUnread();
          playNotifSound();
          const container = ensureIncomingContainer();
          const toast = document.createElement('div');
          toast.className = 'pointer-events-auto flex items-start gap-3 rounded-xl border border-gray-800 bg-gray-900/90 px-4 py-3 text-sm text-gray-100 shadow-lg shadow-black/20 transition duration-200 ease-out transform-gpu';
          const url = payload.url || '/';
          const preview = (payload.preview || '').trim();
          toast.innerHTML = `
            <div class="mt-0.5 h-2.5 w-2.5 flex-none rounded-full bg-emerald-400"></div>
            <div class="flex-1 min-w-0">
              <div class="font-semibold">New follower</div>
              <div class="text-gray-300 text-xs mt-0.5">@${escapeHtml(from)}</div>
              ${preview ? `<div class="mt-2 text-xs text-gray-300 truncate">${escapeHtml(preview)}</div>` : ''}
              <div class="mt-3">
                <a href="${url}" class="vixo-btn text-xs bg-gray-800 hover:bg-gray-700 text-white px-3 py-1.5 rounded-lg transition-colors">Open profile</a>
              </div>
            </div>
            <button type="button" data-close class="-mr-1 -mt-1 inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-300 hover:text-white hover:bg-gray-800/60 transition" aria-label="Dismiss">
              <span aria-hidden="true">×</span>
            </button>
          `;
          const removeToast = () => { toast.classList.add('opacity-0'); setTimeout(() => toast.remove(), 200); };
          toast.querySelector('[data-close]')?.addEventListener('click', removeToast);
          setTimeout(removeToast, 12000);
          container.appendChild(toast);
          animateToastIn(toast);

          try { window.__refreshNotifDropdownIfOpen && window.__refreshNotifDropdownIfOpen(); } catch {}
        }

        if (payload.type === 'support') {
          bumpNotifUnread();
          playNotifSound();
          const container = ensureIncomingContainer();
          const toast = document.createElement('div');
          toast.className = 'pointer-events-auto flex items-start gap-3 rounded-xl border border-gray-800 bg-gray-900/90 px-4 py-3 text-sm text-gray-100 shadow-lg shadow-black/20 transition duration-200 ease-out transform-gpu';
          const url = payload.url || '/profile/support/';
          const preview = (payload.preview || '').trim();
          toast.innerHTML = `
            <div class="mt-0.5 h-2.5 w-2.5 flex-none rounded-full bg-emerald-400"></div>
            <div class="flex-1 min-w-0">
              <div class="font-semibold">Vixogram Team</div>
              ${preview ? `<div class="mt-2 text-xs text-gray-300">${escapeHtml(preview)}</div>` : ''}
              <div class="mt-3">
                <a href="${url}" class="vixo-btn text-xs bg-gray-800 hover:bg-gray-700 text-white px-3 py-1.5 rounded-lg transition-colors">View</a>
              </div>
            </div>
            <button type="button" data-close class="-mr-1 -mt-1 inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-300 hover:text-white hover:bg-gray-800/60 transition" aria-label="Dismiss">
              <span aria-hidden="true">×</span>
            </button>
          `;
          const removeToast = () => { toast.classList.add('opacity-0'); setTimeout(() => toast.remove(), 200); };
          toast.querySelector('[data-close]')?.addEventListener('click', removeToast);
          setTimeout(removeToast, 12000);
          container.appendChild(toast);
          animateToastIn(toast);
          try { window.__refreshNotifDropdownIfOpen && window.__refreshNotifDropdownIfOpen(); } catch {}
        }
      };

      socket.onclose = function () {
        setTimeout(connect, 1200);
      };
    }

    connect();

    // Firebase web push
    if (baseCfg.firebaseEnabled && ('serviceWorker' in navigator) && ('Notification' in window)) {
      (function initFcmWebPush() {
        const cfgUrl = (baseCfg.pushConfigUrl || '').trim();
        if (!cfgUrl) return;

        let vapidKey = '';
        let cfg = {};

        const postToken = (token) => {
          if (!token) return;
          const body = new URLSearchParams();
          body.set('token', token);
          const url = baseCfg.pushRegisterUrl || '/';
          fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded',
              'X-CSRFToken': (typeof getCookie === 'function' ? getCookie('csrftoken') : ''),
            },
            body,
          }).catch(() => {});
        };

        async function init() {
          // Pull public config at runtime (keeps it out of base HTML)
          try {
            const res = await fetch(cfgUrl, {
              method: 'GET',
              credentials: 'same-origin',
              headers: { 'Accept': 'application/json' },
            });
            if (!res.ok) return;
            const data = await res.json();
            vapidKey = String(data.vapidKey || '').trim();
            cfg = (data && data.config && typeof data.config === 'object') ? data.config : {};
          } catch {
            return;
          }

          if (!vapidKey || !cfg || !cfg.messagingSenderId) return;

          const loadScript = (src) => new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = src;
            s.async = true;
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
          });

          try {
            await loadScript('https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js');
            await loadScript('https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging-compat.js');
          } catch {
            return;
          }

          // eslint-disable-next-line no-undef
          if (!window.firebase || !firebase.initializeApp) return;

          try {
            // eslint-disable-next-line no-undef
            if (!firebase.apps || !firebase.apps.length) firebase.initializeApp(cfg);
          } catch {
            // ignore
          }

          let registration;
          try {
            registration = await navigator.serviceWorker.register('/firebase-messaging-sw.js');
          } catch {
            return;
          }

          if (Notification.permission === 'denied') return;

          let messaging;
          try {
            // eslint-disable-next-line no-undef
            messaging = firebase.messaging();
          } catch {
            return;
          }

          let tokenSetupDone = false;
          async function setupTokenOnce() {
            if (tokenSetupDone) return;
            tokenSetupDone = true;
            try {
              const token = await messaging.getToken({ vapidKey, serviceWorkerRegistration: registration });
              postToken(token);
            } catch {
              // ignore
            }
          }

          async function ensurePermissionViaGesture() {
            if (Notification.permission === 'granted') return true;
            if (Notification.permission === 'denied') return false;
            try {
              const p = await Notification.requestPermission();
              return p === 'granted';
            } catch {
              return false;
            }
          }

          if (Notification.permission === 'granted') {
            await setupTokenOnce();
          } else if (Notification.permission !== 'denied') {
            document.addEventListener('click', async () => {
              const ok = await ensurePermissionViaGesture();
              if (ok) await setupTokenOnce();
            }, { once: true, capture: true });
          }

          try {
            messaging.onMessage((payload) => {
              try {
                if (document.visibilityState === 'visible') return;
                const n = (payload && payload.notification) || {};
                const data = (payload && payload.data) || {};
                const title = n.title || data.title || 'Vixo Connect';
                const opts = {
                  body: n.body || data.body || '',
                  icon: n.icon || '/static/favicon.png',
                  data: { url: data.url || '/' },
                };
                if (registration && registration.showNotification) {
                  registration.showNotification(title, opts);
                } else {
                  const notif = new Notification(title, opts);
                  notif.onclick = () => {
                    try { window.open(opts.data.url || '/', '_blank'); } catch {}
                  };
                }
              } catch {
                // ignore
              }
            });
          } catch {
            // ignore
          }
        }

        init();
      })();
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const baseCfg = readJsonScript('vixo-config') || {};

    // Global init
    initGlobalLoadingIndicator();
    initContactDropdown();
    initUserMenuDropdown();
    initToasts();
    initCustomConfirm();
    initPremiumUpgradePopup();
    initImageViewer();
    initVideoViewer();
    initVideoDecodeFallback();
    initHtmxConfirmBridge();

    document.body.addEventListener('htmx:configRequest', (event) => {
      event.detail.headers['X-CSRFToken'] = getCookie('csrftoken');
    });

    initAuthenticatedNotifiers(baseCfg);
  });
})();
