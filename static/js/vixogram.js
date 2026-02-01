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
      const nextLabel = (t === 'light') ? 'Dark' : 'Light';

      const btn = document.getElementById('theme_toggle');
      if (btn) {
        btn.setAttribute('data-theme', t);
        btn.setAttribute('aria-label', `Switch to ${nextLabel} theme`);
        btn.innerHTML = (t === 'light')
          ? '<span class="inline-flex items-center gap-2"><span aria-hidden="true">☀️</span><span class="hidden sm:inline">Light</span></span>'
          : '<span class="inline-flex items-center gap-2"><span aria-hidden="true">🌙</span><span class="hidden sm:inline">Dark</span></span>';
      }

      const menuBtn = document.getElementById('theme_toggle_menu');
      if (menuBtn) {
        menuBtn.setAttribute('data-theme', t);
        menuBtn.setAttribute('aria-label', `Switch to ${nextLabel} theme`);
        const icon = menuBtn.querySelector('[data-theme-icon]');
        const label = menuBtn.querySelector('[data-theme-label]');
        if (icon) icon.textContent = (t === 'light') ? '☀️' : '🌙';
        if (label) label.textContent = (t === 'light') ? 'Light' : 'Dark';
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
    const ids = ['theme_toggle', 'theme_toggle_menu'];
    ids.forEach((id) => {
      const btn = document.getElementById(id);
      if (!btn) return;
      btn.addEventListener('click', (e) => {
        try { e.preventDefault(); } catch {}
        toggleTheme();
      });
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

  // --- Small animation helpers (used by dropdowns & modals) ---
  const __vixoNextFrame = (cb) => {
    try {
      window.requestAnimationFrame(() => window.requestAnimationFrame(cb));
    } catch {
      try { cb(); } catch {}
    }
  };

  function __vixoAnimateDropdownOpen(panel, { withTransform = true } = {}) {
    if (!panel) return;
    try {
      if (panel.dataset) delete panel.dataset.vixoCloseToken;
    } catch {}

    panel.classList.remove('hidden');
    panel.classList.add('transition', 'duration-200', 'ease-out');
    panel.classList.add('opacity-0', 'pointer-events-none');
    panel.classList.remove('opacity-100');

    if (withTransform) {
      panel.classList.add('transform');
      panel.classList.add('-translate-y-2', 'scale-95');
      panel.classList.remove('translate-y-0', 'scale-100');
    }

    __vixoNextFrame(() => {
      panel.classList.remove('opacity-0', 'pointer-events-none');
      panel.classList.add('opacity-100');
      if (withTransform) {
        panel.classList.remove('-translate-y-2', 'scale-95');
        panel.classList.add('translate-y-0', 'scale-100');
      }
    });
  }

  function __vixoAnimateDropdownClose(panel, { withTransform = true } = {}) {
    if (!panel) return;

    panel.classList.add('transition', 'duration-150', 'ease-in');
    panel.classList.add('opacity-0', 'pointer-events-none');
    panel.classList.remove('opacity-100');

    if (withTransform) {
      panel.classList.remove('translate-y-0', 'scale-100');
      panel.classList.add('-translate-y-2', 'scale-95');
    }

    const closeToken = String(Date.now());
    try {
      if (panel.dataset) panel.dataset.vixoCloseToken = closeToken;
    } catch {}

    window.setTimeout(() => {
      try {
        if (panel.dataset && panel.dataset.vixoCloseToken !== closeToken) return;
      } catch {}
      panel.classList.add('hidden');
    }, 170);
  }

  function __vixoModalOpen(modal, backdrop, panel) {
    if (!modal) return;
    try {
      modal.classList.remove('hidden');
      modal.setAttribute('aria-hidden', 'false');
    } catch {}

    try {
      if (backdrop) {
        backdrop.classList.remove('opacity-0');
        backdrop.classList.add('opacity-100');
      }
      if (panel) {
        panel.classList.remove('opacity-0', '-translate-y-2', 'scale-95');
        panel.classList.add('opacity-100', 'translate-y-0', 'scale-100');
      }
    } catch {}
  }

  function __vixoModalClose(modal, backdrop, panel, afterClose) {
    if (!modal) return;
    try {
      modal.setAttribute('aria-hidden', 'true');
    } catch {}

    try {
      if (backdrop) {
        backdrop.classList.add('opacity-0');
        backdrop.classList.remove('opacity-100');
      }
      if (panel) {
        panel.classList.add('opacity-0', '-translate-y-2', 'scale-95');
        panel.classList.remove('opacity-100', 'translate-y-0', 'scale-100');
      }
    } catch {}

    window.setTimeout(() => {
      try { modal.classList.add('hidden'); } catch {}
      try { if (typeof afterClose === 'function') afterClose(); } catch {}
    }, 210);
  }

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
    // Site-wide: only show the global loader for actual file uploads.
    // Background fetches/HTMX requests can be frequent and would cause flashing.

    const el = document.getElementById('global-loading');
    const textEl = document.getElementById('global-loading-text');
    if (!el) {
      window.__vixoLoading = {
        show: () => {},
        hide: () => {},
        inc: () => {},
        dec: () => {},
      };
      return;
    }

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

    const hasFileSelected = (form) => {
      try {
        if (!form || !form.querySelectorAll) return false;
        const inputs = form.querySelectorAll('input[type="file"]');
        for (const inp of inputs) {
          if (inp && inp.files && inp.files.length) return true;
        }
      } catch {
        // ignore
      }
      return false;
    };

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
      // Loader is intentionally NOT shown for navigation.
      // Kept only for upload submits.
    }, true);

    document.addEventListener('submit', (e) => {
      const form = e.target;
      if (!form || !form.getAttribute) return;
      if (form.getAttribute('data-no-loading') !== null) return;

      // Only show loader when an actual file is being uploaded.
      if (!hasFileSelected(form)) return;

      const text = (form.getAttribute('data-loading-text') || 'Uploading… Please wait').trim() || 'Uploading… Please wait';

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
      // Only show loader for HTMX requests that are file uploads.
      try {
        const elt = (e && e.detail && e.detail.elt) ? e.detail.elt : e.target;
        const xhr = (e && e.detail) ? e.detail.xhr : null;
        const form = (elt && elt.closest) ? elt.closest('form') : null;
        if (!xhr) return;
        if (!form) return;
        if (form.getAttribute && form.getAttribute('data-no-loading') !== null) return;
        if (!hasFileSelected(form)) return;

        uploadRequests.set(xhr, true);
        minVisibleUntil = Math.max(minVisibleUntil, Date.now() + 5000);
        inc('Uploading… Please wait');
      } catch {
        // ignore
      }
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
      // Non-upload HTMX requests don't touch the loader.
    });
    document.body.addEventListener('htmx:responseError', () => { pending = 0; hide(); });
    document.body.addEventListener('htmx:sendError', () => { pending = 0; hide(); });
    document.body.addEventListener('htmx:timeout', () => { pending = 0; hide(); });

    try {
      if (typeof window.fetch === 'function' && !window.fetch.__vixo_patched) {
        const origFetch = window.fetch.bind(window);
        const wrapped = function (...args) {
          // Default: do not show loader for fetch (prevents idle flashing).
          // Opt-in by passing init.showLoading=true or header X-Vixo-Loading: 1
          let shouldShow = false;
          try {
            const req = args && args.length ? args[0] : null;
            const init = (args && args.length > 1) ? args[1] : null;
            if (init && init.noLoading) shouldShow = false;

            const pickHeader = (headers, key) => {
              if (!headers) return '';
              try {
                if (typeof headers.get === 'function') return String(headers.get(key) || '');
              } catch {}
              try {
                // Plain object
                return String(headers[key] || headers[key.toLowerCase()] || '');
              } catch {}
              return '';
            };

            const initHeaders = init && init.headers ? init.headers : null;
            const reqHeaders = req && req.headers ? req.headers : null;
            const flag = (pickHeader(initHeaders, 'X-Vixo-No-Loading') || pickHeader(reqHeaders, 'X-Vixo-No-Loading')).trim();
            if (flag === '1' || flag.toLowerCase() === 'true') shouldShow = false;

            const enable = (pickHeader(initHeaders, 'X-Vixo-Loading') || pickHeader(reqHeaders, 'X-Vixo-Loading')).trim();
            if (enable === '1' || enable.toLowerCase() === 'true') shouldShow = true;
            if (init && init.showLoading === true) shouldShow = true;
          } catch {
            // ignore
          }

          if (shouldShow) inc('Loading…');
          return origFetch(...args).finally(() => { if (shouldShow) dec(); });
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
      __vixoAnimateDropdownOpen(dropdown, { withTransform: true });
      btn.setAttribute('aria-expanded', 'true');
    }

    function close() {
      __vixoAnimateDropdownClose(dropdown, { withTransform: true });
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
      __vixoAnimateDropdownOpen(dropdown, { withTransform: true });
      btn.setAttribute('aria-expanded', 'true');
    }

    function close() {
      __vixoAnimateDropdownClose(dropdown, { withTransform: true });
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
    const backdrop = document.getElementById('confirm-backdrop');
    const panel = document.getElementById('confirm-panel');
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

      // Fallback: if backdrop/panel aren't present, this still works.
      __vixoModalOpen(modal, backdrop, panel);
    };

    const close = () => {
      __vixoModalClose(modal, backdrop, panel, () => {
        pendingAction = null;
      });
    };

    okBtn.addEventListener('click', () => {
      const fn = pendingAction;
      close();
      if (typeof fn === 'function') fn();
    });
    cancelBtn.addEventListener('click', close);
    modal.addEventListener('click', (e) => {
      if (e.target === modal || (backdrop && e.target === backdrop)) close();
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

  function initPromptModal() {
    const modal = document.getElementById('prompt-modal');
    const backdrop = document.getElementById('prompt-backdrop');
    const panel = document.getElementById('prompt-panel');
    const titleEl = document.getElementById('prompt-title');
    const msgEl = document.getElementById('prompt-message');
    const inputEl = document.getElementById('prompt-input');
    const okBtn = document.getElementById('prompt-ok');
    const cancelBtn = document.getElementById('prompt-cancel');

    if (!modal || !titleEl || !inputEl || !okBtn || !cancelBtn) return;

    let pendingResolve = null;
    let isOpen = false;

    const open = ({ title, message, defaultValue, placeholder, okText, cancelText } = {}) => {
      titleEl.textContent = title || 'Enter value';

      const msg = String(message || '').trim();
      if (msgEl) {
        msgEl.textContent = msg;
        msgEl.classList.toggle('hidden', !msg);
      }

      inputEl.value = (defaultValue === undefined || defaultValue === null) ? '' : String(defaultValue);
      if (placeholder !== undefined && placeholder !== null) {
        try { inputEl.setAttribute('placeholder', String(placeholder)); } catch {}
      }
      okBtn.textContent = okText || 'OK';
      cancelBtn.textContent = cancelText || 'Cancel';

      __vixoModalOpen(modal, backdrop, panel);
      isOpen = true;

      window.setTimeout(() => {
        try {
          inputEl.focus();
          inputEl.select();
        } catch {}
      }, 0);
    };

    const close = (value) => {
      if (!isOpen) return;
      isOpen = false;
      __vixoModalClose(modal, backdrop, panel, () => {
        const r = pendingResolve;
        pendingResolve = null;
        try {
          if (typeof r === 'function') r(value);
        } catch {}
      });
    };

    okBtn.addEventListener('click', () => {
      close(String(inputEl.value || ''));
    });
    cancelBtn.addEventListener('click', () => close(null));

    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        try { e.preventDefault(); } catch {}
        close(String(inputEl.value || ''));
      }
      if (e.key === 'Escape') {
        try { e.preventDefault(); } catch {}
        close(null);
      }
    });

    modal.addEventListener('click', (e) => {
      if (e.target === modal || (backdrop && e.target === backdrop)) close(null);
    });

    document.addEventListener('keydown', (e) => {
      if (!isOpen) return;
      if (e.key === 'Escape') close(null);
    });

    window.__openPrompt = open;
    window.__closePrompt = () => close(null);
    window.__vixoPrompt = (opts) => {
      return new Promise((resolve) => {
        pendingResolve = resolve;
        open(opts || {});
      });
    };
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
        // Fallback (should be rare if base.html includes the modal)
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

    // Safety: if this bundle is included twice, avoid spawning duplicate WS clients/timers.
    if (window.__vixoAuthenticatedNotifiersStarted) return;
    window.__vixoAuthenticatedNotifiersStarted = true;

    // Lets chat pages know a global handler exists (avoid duplicate toasts)
    window.__hasGlobalCallInvite = true;
    window.__hasGlobalMentionNotify = true;
    window.__hasGlobalOnlineStatus = true;

    const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${wsScheme}://${window.location.host}/ws/notify/`;
    const wsOnlineUrl = `${wsScheme}://${window.location.host}/ws/online-status/`;

    const __WS_HEARTBEAT_MS = 25_000;
    const __WS_RECONNECT_BASE_MS = 900;
    const __WS_RECONNECT_FACTOR = 1.7;
    const __WS_RECONNECT_MAX_MS = 30_000;

    // Maintain a global online presence socket.
    // NOTE: This socket also drives "am I online" presence. Keep it connected,
    // but only do HTML parsing / UI updates when the legacy navbar pill exists.
    (function connectOnlineStatus() {
      let onlineSocket;
      let pingTimer;
      let reconnectTimer;
      let attempt = 0;
      let stopped = false;

      const stopPing = () => {
        try { if (pingTimer) clearInterval(pingTimer); } catch {}
        pingTimer = null;
      };

      const scheduleReconnect = () => {
        if (reconnectTimer) return;
        const a = Math.min(30, Math.max(0, attempt));
        attempt = a + 1;
        if (attempt >= 5) warnRealtimeOnce('online-status', 'Online status is reconnecting. Some realtime features may be delayed.');
        let delay = Math.min(__WS_RECONNECT_MAX_MS, Math.round(__WS_RECONNECT_BASE_MS * Math.pow(__WS_RECONNECT_FACTOR, a)));
        delay = Math.round(delay * (0.7 + Math.random() * 0.6));
        try { if (document.visibilityState === 'hidden') delay = Math.max(delay, 5000); } catch {}
        reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, delay);
      };

      const connect = () => {
        if (stopped) return;
        try {
          onlineSocket = new WebSocket(wsOnlineUrl);
        } catch {
          return;
        }

        onlineSocket.onopen = () => {
          attempt = 0;
          stopPing();
          pingTimer = setInterval(() => {
            try {
              if (!onlineSocket || onlineSocket.readyState !== WebSocket.OPEN) return;
              onlineSocket.send(JSON.stringify({ type: 'ping' }));
            } catch {}
          }, __WS_HEARTBEAT_MS);
        };

        onlineSocket.onmessage = (event) => {
          // If the UI doesn't show online counts, skip expensive parsing work.
          try {
            if (!document.getElementById('nav_online_count')) return;
          } catch {
            // ignore
          }
          const raw = (event && typeof event.data === 'string') ? event.data : '';
          if (!raw) return;

          let total = null;
          try {
            const doc = new DOMParser().parseFromString(raw, 'text/html');
            const el = doc.querySelector('#global-online-total');
            total = el ? el.getAttribute('data-total-online') : null;
          } catch {}

          if (total === null || total === undefined) return;
          const count = parseInt(String(total), 10);
          if (!Number.isFinite(count)) return;

          try {
            const wrap = document.getElementById('nav_online_count');
            const countEl = document.getElementById('online-count');
            if (countEl) countEl.textContent = String(count);
            if (wrap && count > 0) wrap.classList.remove('hidden');
          } catch {}
        };
        onlineSocket.onclose = () => {
          stopPing();
          try {
            if (document.visibilityState === 'hidden') return;
          } catch {}
          if (stopped) return;
          scheduleReconnect();
        };
      };

      window.addEventListener('beforeunload', () => {
        stopped = true;
        stopPing();
        try { if (reconnectTimer) clearTimeout(reconnectTimer); } catch {}
        reconnectTimer = null;
        try { if (onlineSocket && onlineSocket.close) onlineSocket.close(); } catch {}
      }, { once: true });
      connect();
    })();

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
        // Next frame: animate to visible
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

    function warnRealtimeOnce(key, message) {
      try {
        const k = String(key || 'ws');
        window.__vixoRealtimeWarned = window.__vixoRealtimeWarned || {};
        if (window.__vixoRealtimeWarned[k]) return;
        window.__vixoRealtimeWarned[k] = true;

        const container = ensureIncomingContainer();
        const toast = document.createElement('div');
        toast.className = 'pointer-events-auto flex items-start gap-3 rounded-xl border border-amber-700/40 bg-gray-900/90 px-4 py-3 text-sm text-gray-100 shadow-lg shadow-black/20 transition duration-200 ease-out transform-gpu';
        const msg = String(message || 'Realtime connection is unstable. Retrying…');
        toast.innerHTML = `
          <div class="mt-0.5 h-2.5 w-2.5 flex-none rounded-full bg-amber-400"></div>
          <div class="flex-1 min-w-0">
            <div class="font-semibold">Realtime issue</div>
            <div class="mt-1 text-xs text-gray-300">${escapeHtml(msg)}</div>
          </div>
          <button type="button" data-close class="-mr-1 -mt-1 inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-300 hover:text-white hover:bg-gray-800/60 transition" aria-label="Dismiss">
            <span aria-hidden="true">×</span>
          </button>
        `;

        const removeToast = () => { toast.classList.add('opacity-0'); setTimeout(() => toast.remove(), 200); };
        toast.querySelector('[data-close]')?.addEventListener('click', removeToast);
        setTimeout(removeToast, 8000);

        container.appendChild(toast);
        animateToastIn(toast);
      } catch {
        // ignore
      }
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

      // Prefer an actual ringtone file (best UX). If autoplay is blocked,
      // fall back to the existing synth ring.
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
            // Autoplay blocked -> fallback
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
        // ignore -> fallback below
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

      // Auto-decline if not accepted within 14 seconds.
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
          // Reset any previous adjustment so we measure the natural position.
          panel.style.transform = '';

          const pad = 12;
          const rect = panel.getBoundingClientRect();
          const vw = window.innerWidth || 0;
          if (!vw) return;

          let dx = 0;
          if (rect.left < pad) dx = pad - rect.left;
          // Apply dx from left clamp first, then ensure right edge is also within.
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
        // Opacity-only animation here: this panel may use style.transform for viewport clamping.
        __vixoAnimateDropdownOpen(panel, { withTransform: false });
        btn.setAttribute('aria-expanded', 'true');
        // Clamp after the panel is visible to avoid going off-screen on mobile.
        setTimeout(clampPanelToViewport, 0);
        try {
          if (window.htmx && typeof window.htmx.ajax === 'function') {
            const url = btn.getAttribute('hx-get');
            if (url) window.htmx.ajax('GET', url, { target: '#notif_dropdown_body', swap: 'innerHTML' });
          }
        } catch {}
      };

      const close = () => {
        __vixoAnimateDropdownClose(panel, { withTransform: false });
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

      // Expose for websocket handlers
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
      let pingTimer;
      let reconnectTimer;
      let attempt = 0;

      let stopped = false;

      const stopPing = () => {
        try { if (pingTimer) clearInterval(pingTimer); } catch {}
        pingTimer = null;
      };

      const scheduleReconnect = () => {
        if (reconnectTimer) return;
        const a = Math.min(30, Math.max(0, attempt));
        attempt = a + 1;
        if (attempt >= 5) warnRealtimeOnce('notify', 'Notifications are reconnecting. Calls/mentions may be delayed.');
        let delay = Math.min(__WS_RECONNECT_MAX_MS, Math.round(__WS_RECONNECT_BASE_MS * Math.pow(__WS_RECONNECT_FACTOR, a)));
        delay = Math.round(delay * (0.7 + Math.random() * 0.6));
        try { if (document.visibilityState === 'hidden') delay = Math.max(delay, 5000); } catch {}
        reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, delay);
      };

      try {
        socket = new WebSocket(wsUrl);
      } catch {
        return;
      }

      socket.onopen = () => {
        attempt = 0;
        stopPing();
        pingTimer = setInterval(() => {
          try {
            if (!socket || socket.readyState !== WebSocket.OPEN) return;
            socket.send(JSON.stringify({ type: 'ping' }));
          } catch {}
        }, __WS_HEARTBEAT_MS);
      };

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
        stopPing();
        if (stopped) return;
        scheduleReconnect();
      };

      window.addEventListener('beforeunload', () => {
        stopped = true;
        stopPing();
        try { if (reconnectTimer) clearTimeout(reconnectTimer); } catch {}
        reconnectTimer = null;
        try { if (socket && socket.close) socket.close(); } catch {}
      }, { once: true });
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

  function initGlobalAnnouncementSocket() {
    const banner = document.getElementById('global-announcement-banner');
    if (!banner) return;

    // Prevent duplicates (in case this script is loaded twice).
    if (window.__globalAnnouncementSocketStarted) return;
    window.__globalAnnouncementSocketStarted = true;

    const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${wsScheme}://${window.location.host}/ws/global-announcement/`;

    const __WS_HEARTBEAT_MS = 25_000;
    const __WS_RECONNECT_BASE_MS = 900;
    const __WS_RECONNECT_FACTOR = 1.7;
    const __WS_RECONNECT_MAX_MS = 30_000;

    let __gaPingTimer = null;
    let __gaReconnectTimer = null;
    let __gaAttempt = 0;
    let __gaSocket = null;
    let __gaNeedsReconnect = false;

    const __gaStopPing = () => {
      try { if (__gaPingTimer) clearInterval(__gaPingTimer); } catch {}
      __gaPingTimer = null;
    };

    const __gaScheduleReconnect = (connectFn) => {
      if (__gaReconnectTimer) return;
      const a = Math.min(30, Math.max(0, __gaAttempt));
      __gaAttempt = a + 1;
      let delay = Math.min(__WS_RECONNECT_MAX_MS, Math.round(__WS_RECONNECT_BASE_MS * Math.pow(__WS_RECONNECT_FACTOR, a)));
      delay = Math.round(delay * (0.7 + Math.random() * 0.6));
      try { if (document.visibilityState === 'hidden') delay = Math.max(delay, 5000); } catch {}
      __gaReconnectTimer = setTimeout(() => { __gaReconnectTimer = null; connectFn(); }, delay);
    };

    const applyState = (active, message) => {
      const text = String(message || '');
      const shouldShow = Boolean(active) && text.trim().length > 0;

      try {
        banner.querySelectorAll('.global-announcement-msg').forEach((el) => {
          el.textContent = text;
        });
      } catch {
        // ignore
      }

      try {
        if (shouldShow) banner.classList.remove('hidden');
        else banner.classList.add('hidden');
      } catch {
        // ignore
      }
    };

    const connectGlobalAnnouncement = () => {
      let socket;
      try {
        socket = new WebSocket(wsUrl);
      } catch {
        return;
      }

      __gaSocket = socket;
      __gaNeedsReconnect = false;

      socket.onopen = () => {
        __gaAttempt = 0;
        __gaStopPing();
        __gaPingTimer = setInterval(() => {
          try {
            if (!socket || socket.readyState !== WebSocket.OPEN) return;
            socket.send(JSON.stringify({ type: 'ping' }));
          } catch {}
        }, __WS_HEARTBEAT_MS);
      };

      socket.onmessage = (event) => {
        let payload;
        try { payload = JSON.parse(event.data); } catch { return; }
        if (!payload || payload.type !== 'global_announcement') return;
        applyState(payload.active, payload.message);
      };

      socket.onclose = () => {
        __gaStopPing();
        __gaSocket = null;
        try {
          if (document.visibilityState === 'hidden') {
            __gaNeedsReconnect = true;
            return;
          }
        } catch {}
        __gaScheduleReconnect(connectGlobalAnnouncement);
      };

      socket.onerror = () => {
        // Some browsers fire onerror without onclose; let onclose handle reconnect.
      };
    };

    // Initial connect.
    connectGlobalAnnouncement();

    // If the socket was dropped while the tab was hidden, reconnect when visible.
    try {
      document.addEventListener('visibilitychange', () => {
        try {
          if (document.visibilityState !== 'visible') return;
          if (!__gaNeedsReconnect) return;
          if (__gaReconnectTimer) return;
          if (__gaSocket && __gaSocket.readyState === WebSocket.OPEN) {
            __gaNeedsReconnect = false;
            return;
          }
          connectGlobalAnnouncement();
        } catch {
          // ignore
        }
      });
    } catch {
      // ignore
    }
  }

  function initMaintenancePolling(baseCfg) {
    try {
      const statusUrl = String(baseCfg && baseCfg.maintenanceStatusUrl ? baseCfg.maintenanceStatusUrl : '');
      const maintenancePageUrl = String(baseCfg && baseCfg.maintenancePageUrl ? baseCfg.maintenancePageUrl : '/maintenance/');
      const isStaff = !!(baseCfg && baseCfg.userIsStaff);
      if (!statusUrl || isStaff) return;

      const isOnMaintenancePage = () => {
        try { return String(window.location.pathname || '').startsWith('/maintenance/'); } catch { return false; }
      };

      let stopped = false;

      async function check() {
        if (stopped) return;
        if (isOnMaintenancePage()) return;
        try {
          const res = await fetch(statusUrl, {
            method: 'GET',
            credentials: 'same-origin',
            cache: 'no-store',
            headers: { 'Accept': 'application/json' },
          });
          if (!res.ok) return;
          const data = await res.json();
          if (data && data.enabled) {
            window.location.href = maintenancePageUrl;
          }
        } catch {
          // ignore
        }
      }

      // Fast initial check + interval for near-realtime lock.
      check();
      const intervalMs = 3000;
      const t = window.setInterval(check, intervalMs);
      window.addEventListener('beforeunload', () => {
        stopped = true;
        try { window.clearInterval(t); } catch {}
      }, { once: true });
    } catch {
      // ignore
    }
  }

  function initDisableContextMenu() {
    // NOTE: This only hides the context menu; it does not prevent users from viewing source/devtools.
    try {
      document.addEventListener('contextmenu', (e) => {
        try {
          e.preventDefault();
          e.stopPropagation();
        } catch {
          // ignore
        }
        return false;
      }, true);
    } catch {
      // ignore
    }
  }

  function initChatViewportSizing() {
    // Chat-only: ensure the chat panels fit below the real header height on mobile.
    // The header can vary (navbar + optional announcement banner), so avoid hard-coded offsets.
    try {
      const isChatPage = document.documentElement.classList.contains('vixo-chat-page')
        || document.body.classList.contains('vixo-chat-page');
      if (!isChatPage) return;

      const root = document.documentElement;
      const nav = document.querySelector('.vixo-topbar');
      const banner = document.getElementById('global-announcement-banner');

      const computeOffset = () => {
        let px = 0;
        try {
          if (nav) px += nav.getBoundingClientRect().height;
        } catch {
          // ignore
        }
        try {
          if (banner && !banner.classList.contains('hidden')) px += banner.getBoundingClientRect().height;
        } catch {
          // ignore
        }

        // Small buffer for borders/subpixel rounding.
        px += 1;
        root.style.setProperty('--vixo-chat-top-offset', `${Math.max(0, Math.round(px))}px`);
      };

      computeOffset();

      // Recompute on viewport changes.
      const onResize = () => {
        try {
          window.requestAnimationFrame(computeOffset);
        } catch {
          computeOffset();
        }
      };

      window.addEventListener('resize', onResize, { passive: true });
      window.addEventListener('orientationchange', onResize, { passive: true });

      // If the banner toggles, recompute.
      try {
        if (banner && 'MutationObserver' in window) {
          const mo = new MutationObserver(() => computeOffset());
          mo.observe(banner, { attributes: true, attributeFilter: ['class', 'style'] });
        }
      } catch {
        // ignore
      }
    } catch {
      // ignore
    }
  }

  function initStoriesViewer() {
    // Any element with data-story-username="<username>" opens the stories viewer.
    // Stories are images only and auto-advance every 10 seconds.
    try {
      const SEEN_PREFIX = 'vixo_story_seen:';

      const safeKey = (username) => SEEN_PREFIX + String(username || '').trim().toLowerCase();

      const getSeenVersion = (username) => {
        try {
          return String(window.localStorage.getItem(safeKey(username)) || '');
        } catch {
          return '';
        }
      };

      const setSeenVersion = (username, version) => {
        const u = String(username || '').trim();
        const v = String(version || '').trim();
        if (!u || !v) return;
        try {
          window.localStorage.setItem(safeKey(u), v);
        } catch {
          // ignore
        }
      };

      const computeVersionFromStories = (stories) => {
        try {
          const items = Array.isArray(stories) ? stories : [];
          let best = '';
          for (let i = 0; i < items.length; i += 1) {
            const c = items[i] && items[i].created_at ? String(items[i].created_at) : '';
            if (c && (!best || c > best)) best = c;
          }
          return best;
        } catch {
          return '';
        }
      };

      const updateStoryRings = (root) => {
        try {
          const scope = root || document;
          const triggers = scope.querySelectorAll('[data-story-username][data-story-version]');
          triggers.forEach((el) => {
            try {
              const username = el.getAttribute('data-story-username') || '';
              const version = el.getAttribute('data-story-version') || '';
              const ring = el.querySelector('[data-story-ring]');
              if (!ring) return;

              const seen = getSeenVersion(username);
              const hide = !!(seen && version && seen === version);
              ring.classList.toggle('hidden', hide);
            } catch {
              // ignore
            }
          });
        } catch {
          // ignore
        }
      };

      const buildUrl = (username) => {
        const u = String(username || '').trim();
        if (!u) return null;
        return `/profile/u/${encodeURIComponent(u)}/stories/`;
      };

      const removeExisting = () => {
        try {
          const old = document.getElementById('vixo-story-viewer');
          if (old) old.remove();
        } catch {
          // ignore
        }
      };

      const showMiniToast = (text) => {
        try {
          const t = document.createElement('div');
          t.className = 'fixed left-1/2 -translate-x-1/2 bottom-6 z-[90] max-w-[min(28rem,calc(100vw-2rem))] rounded-xl border border-gray-800 bg-gray-900/90 px-4 py-3 text-sm text-gray-100 shadow-2xl shadow-black/40';
          t.textContent = String(text || '');
          document.body.appendChild(t);
          window.setTimeout(() => {
            try {
              t.classList.add('opacity-0');
              t.style.transition = 'opacity 180ms ease-out';
            } catch {}
          }, 1600);
          window.setTimeout(() => {
            try { t.remove(); } catch {}
          }, 1900);
        } catch {
          // ignore
        }
      };

      const buildPlaybackItems = (stories) => {
        const storyItems = Array.isArray(stories) ? stories.filter(s => s && s.image_url) : [];
        const n = storyItems.length;
        if (n <= 1) {
          return {
            storyCount: n,
            playback: storyItems.map((s) => ({ type: 'story', story: s })),
          };
        }

        // Insert an ad story after every 2 stories.
        // Special case: if there are exactly 2 stories, insert after the 1st.
        const playback = [];
        const block = (n === 2) ? 1 : 2;

        for (let i = 0; i < n; i += 1) {
          playback.push({ type: 'story', story: storyItems[i] });

          const atEnd = (i === n - 1);
          const shouldInsert = !atEnd && ((i + 1) % block === 0);
          if (shouldInsert) {
            playback.push({ type: 'ad' });
          }
        }

        return { storyCount: n, playback };
      };

      const openViewer = ({ username, durationSeconds, stories, canDelete, storiesUrl }) => {
        removeExisting();

        const durStoryMs = Math.max(1000, Number(durationSeconds || 10) * 1000);
        const durAdMs = 6000;

        const built = buildPlaybackItems(stories);
        const storyCount = built.storyCount;
        const items = built.playback;

        if (!items.length) {
          // Best-effort: show a toast if available, else fallback.
          try {
            const container = document.getElementById('toast-container');
            if (container) {
              const toast = document.createElement('div');
              toast.className = 'toast pointer-events-auto flex items-start gap-3 rounded-xl border border-gray-800 bg-gray-900/90 px-4 py-3 text-sm text-gray-100 shadow-lg shadow-black/20 transition duration-200 ease-out';
              toast.setAttribute('data-duration', '2500');
              toast.innerHTML = '<div class="mt-0.5 h-2.5 w-2.5 flex-none rounded-full bg-gray-500"></div><div class="flex-1 leading-5">No stories yet.</div>';
              container.appendChild(toast);
              // initToasts runs once at DOMContentLoaded; dismiss this toast manually.
              window.setTimeout(() => {
                try { toast.remove(); } catch {}
              }, 2600);
              return;
            }
          } catch {}
          showMiniToast('No stories yet.');
          return;
        }

        let index = 0;
        let startedAt = 0;
        let tickTimer = null;

        const root = document.createElement('div');
        root.id = 'vixo-story-viewer';
        root.className = 'fixed inset-0 z-[80] bg-black/95 opacity-0 transition-opacity duration-200 ease-out';
        root.setAttribute('role', 'dialog');
        root.setAttribute('aria-modal', 'true');
        root.setAttribute('aria-label', 'Stories');

        root.innerHTML = `
          <div class="absolute inset-0"></div>
          <div class="relative w-full h-full flex items-center justify-center opacity-0 translate-y-1 scale-[0.985] transition-all duration-200 ease-out" data-story-panel>
            <div class="absolute top-0 left-0 right-0 p-3 sm:p-4">
              <div class="mx-auto max-w-md">
                <div class="flex items-center justify-between gap-3">
                  <div class="min-w-0 text-sm font-semibold text-gray-100 truncate">@${String(username || '').replace(/</g, '')}</div>
                  <div class="flex items-center gap-2">
                    <div class="relative">
                      <button type="button" data-story-menu-btn class="inline-flex h-9 w-9 items-center justify-center rounded-full bg-gray-900/60 hover:bg-gray-900/80 text-gray-100 border border-white/10" aria-label="Story menu">
                        <svg viewBox="0 0 24 24" class="h-5 w-5" fill="currentColor" aria-hidden="true"><circle cx="12" cy="5" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="12" cy="19" r="1.8"/></svg>
                      </button>
                      <div data-story-menu-panel class="hidden absolute right-0 mt-2 w-44 overflow-hidden rounded-xl border border-white/10 bg-gray-950/95 shadow-2xl shadow-black/50">
                        <button type="button" data-story-delete class="w-full text-left px-4 py-3 text-sm text-red-200 hover:bg-red-500/10">Delete story</button>
                      </div>
                    </div>
                    <button type="button" data-story-close class="inline-flex h-9 w-9 items-center justify-center rounded-full bg-gray-900/60 hover:bg-gray-900/80 text-gray-100 border border-white/10">×</button>
                  </div>
                </div>
                <div class="mt-2 flex items-center gap-1" data-story-progress></div>
              </div>
            </div>

            <div class="w-full h-full flex items-center justify-center">
              <div class="w-full max-w-md px-3 sm:px-4">
                <div class="relative rounded-2xl overflow-hidden bg-black shadow-2xl shadow-black/40 border border-white/10">
                  <img data-story-img class="block w-full h-[70vh] sm:h-[75vh] object-contain bg-black" alt="Story" />
                  <div data-story-ad class="absolute inset-0 hidden bg-gradient-to-b from-gray-900/80 via-black to-black">
                    <div class="w-full h-full flex items-center justify-center p-6">
                      <div class="w-full max-w-sm text-center">
                        <div class="text-[10px] tracking-[0.35em] text-white/60">ADVERTISEMENT</div>
                        <div class="mt-3 text-xl font-semibold text-white">Vixogram Premium</div>
                        <div class="mt-2 text-sm text-white/70">Unlock more features and support the app.</div>
                        <a href="/pricing/" class="inline-flex mt-4 items-center justify-center rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-400">View Plans</a>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <button type="button" data-story-prev class="absolute left-0 top-0 bottom-0 w-1/3" aria-label="Previous story">
              <span data-story-prev-arrow class="absolute left-3 top-1/2 -translate-y-1/2 inline-flex h-11 w-11 items-center justify-center rounded-full bg-black/35 text-white/90 border border-white/10 backdrop-blur-sm">
                <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>
              </span>
            </button>
            <button type="button" data-story-next class="absolute right-0 top-0 bottom-0 w-1/3" aria-label="Next story">
              <span data-story-next-arrow class="absolute right-3 top-1/2 -translate-y-1/2 inline-flex h-11 w-11 items-center justify-center rounded-full bg-black/35 text-white/90 border border-white/10 backdrop-blur-sm">
                <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>
              </span>
            </button>

            <div data-story-delete-confirm class="hidden absolute inset-0 z-[6] bg-black/70 backdrop-blur-[1px]">
              <div class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[min(22rem,calc(100vw-2rem))] rounded-2xl border border-white/10 bg-gray-950/95 p-4 shadow-2xl shadow-black/60">
                <div class="text-sm font-semibold text-white">Delete this story?</div>
                <div class="mt-1 text-xs text-white/70" data-story-delete-countdown>Deleting in 5s…</div>
                <div class="mt-3 flex items-center justify-end gap-2">
                  <button type="button" data-story-delete-cancel class="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white hover:bg-white/10">Cancel</button>
                  <button type="button" data-story-delete-now class="rounded-xl bg-red-500 px-3 py-2 text-sm font-semibold text-white hover:bg-red-400">Delete now</button>
                </div>
              </div>
            </div>
          </div>
        `;

        document.body.appendChild(root);
        try { document.body.style.overflow = 'hidden'; } catch {}

        // Open animation.
        try {
          const panel = root.querySelector('[data-story-panel]');
          __vixoNextFrame(() => {
            try { root.classList.remove('opacity-0'); } catch {}
            try {
              if (panel) {
                panel.classList.remove('opacity-0', 'translate-y-1', 'scale-[0.985]');
              }
            } catch {}
          });
        } catch {
          // ignore
        }

        const closeBtn = root.querySelector('[data-story-close]');
        const menuBtn = root.querySelector('[data-story-menu-btn]');
        const menuPanel = root.querySelector('[data-story-menu-panel]');
        const deleteBtn = root.querySelector('[data-story-delete]');
        const deleteConfirm = root.querySelector('[data-story-delete-confirm]');
        const deleteCountdown = root.querySelector('[data-story-delete-countdown]');
        const deleteCancel = root.querySelector('[data-story-delete-cancel]');
        const deleteNow = root.querySelector('[data-story-delete-now]');
        const img = root.querySelector('[data-story-img]');
        const ad = root.querySelector('[data-story-ad]');
        const progress = root.querySelector('[data-story-progress]');
        const prevBtn = root.querySelector('[data-story-prev]');
        const nextBtn = root.querySelector('[data-story-next]');
        const prevArrow = root.querySelector('[data-story-prev-arrow]');
        const nextArrow = root.querySelector('[data-story-next-arrow]');

        const segments = [];
        if (progress) {
          progress.innerHTML = '';
          for (let i = 0; i < items.length; i += 1) {
            const seg = document.createElement('div');
            seg.className = 'h-1.5 flex-1 rounded-full bg-white/20 overflow-hidden';
            seg.innerHTML = '<div class="h-full w-0 bg-white/90" data-fill></div>';
            progress.appendChild(seg);
            segments.push(seg.querySelector('[data-fill]'));
          }
        }

        const cleanupTimers = () => {
          if (tickTimer) {
            try { window.clearInterval(tickTimer); } catch {}
            tickTimer = null;
          }
        };

        let deleteTimer = null;
        let deleteInterval = null;
        const cleanupDeleteTimers = () => {
          if (deleteTimer) {
            try { window.clearTimeout(deleteTimer); } catch {}
            deleteTimer = null;
          }
          if (deleteInterval) {
            try { window.clearInterval(deleteInterval); } catch {}
            deleteInterval = null;
          }
        };

        const close = () => {
          cleanupDeleteTimers();
          cleanupTimers();
          try { window.removeEventListener('keydown', onKeyDown); } catch {}
          try {
            const panel = root.querySelector('[data-story-panel]');
            root.classList.add('opacity-0');
            if (panel) {
              panel.classList.add('opacity-0', 'translate-y-1', 'scale-[0.985]');
            }
          } catch {}
          window.setTimeout(() => {
            try { root.remove(); } catch {}
            try { document.body.style.overflow = ''; } catch {}
          }, 190);
        };

        const setSegment = (i, pct) => {
          try {
            for (let j = 0; j < segments.length; j += 1) {
              if (!segments[j]) continue;
              if (j < i) {
                segments[j].style.width = '100%';
              } else if (j > i) {
                segments[j].style.width = '0%';
              } else {
                segments[j].style.width = `${Math.max(0, Math.min(100, pct))}%`;
              }
            }
          } catch {
            // ignore
          }
        };

        const preload = (url) => {
          try {
            const im = new Image();
            im.src = url;
          } catch {
            // ignore
          }
        };

        const getItemDurationMs = (item) => {
          try {
            return (item && item.type === 'ad') ? durAdMs : durStoryMs;
          } catch {
            return durStoryMs;
          }
        };

        const updateNavUi = () => {
          // Only show arrow controls if there are 2+ real stories.
          const showArrows = storyCount >= 2;
          try {
            if (prevArrow) prevArrow.classList.toggle('hidden', !showArrows);
            if (nextArrow) nextArrow.classList.toggle('hidden', !showArrows);
          } catch {}

          // Subtle disable at edges.
          try {
            if (prevArrow) prevArrow.classList.toggle('opacity-30', index <= 0);
            if (nextArrow) nextArrow.classList.toggle('opacity-30', index >= items.length - 1);
          } catch {}
        };

        const hideMenu = () => {
          try { if (menuPanel) menuPanel.classList.add('hidden'); } catch {}
        };

        const toggleMenu = () => {
          try {
            if (!menuPanel) return;
            menuPanel.classList.toggle('hidden');
          } catch {}
        };

        const getCurrentStoryId = () => {
          try {
            const it = items[index];
            if (it && it.type === 'story' && it.story && it.story.id) return Number(it.story.id);
          } catch {
            // ignore
          }
          return null;
        };

        const hideDeleteConfirm = () => {
          cleanupDeleteTimers();
          try { if (deleteConfirm) deleteConfirm.classList.add('hidden'); } catch {}
        };

        const showDeleteConfirm = () => {
          try { if (deleteConfirm) deleteConfirm.classList.remove('hidden'); } catch {}
        };

        const performDelete = async () => {
          const storyId = getCurrentStoryId();
          if (!storyId) {
            showMiniToast('No story selected.');
            hideDeleteConfirm();
            return;
          }

          cleanupDeleteTimers();

          let res = null;
          try {
            res = await fetch(`/profile/story/${storyId}/delete/`, {
              method: 'POST',
              headers: {
                'Accept': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
              },
              credentials: 'same-origin',
            });
          } catch {
            res = null;
          }

          if (!res) {
            showMiniToast('Network error.');
            hideDeleteConfirm();
            return;
          }

          if (res.status === 403) {
            showMiniToast('Not allowed.');
            hideDeleteConfirm();
            return;
          }

          if (!res.ok) {
            showMiniToast('Delete failed.');
            hideDeleteConfirm();
            return;
          }

          showMiniToast('Story deleted.');

          // Refresh stories after delete.
          try {
            const u = storiesUrl || buildUrl(username);
            if (u) {
              const r2 = await fetch(u, {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
                credentials: 'same-origin',
              });
              if (r2 && r2.ok) {
                const d2 = await r2.json();
                const nextStories = d2 && d2.stories;
                if (Array.isArray(nextStories) && nextStories.length) {
                  openViewer({
                    username: d2 && d2.username,
                    durationSeconds: d2 && d2.duration_seconds,
                    stories: nextStories,
                    canDelete: d2 && d2.can_delete,
                    storiesUrl: u,
                  });
                  return;
                }
              }
            }
          } catch {
            // ignore
          }

          // No stories left or refresh failed: close viewer.
          hideDeleteConfirm();
          close();
        };

        const startDeleteCountdown = () => {
          cleanupDeleteTimers();

          const storyId = getCurrentStoryId();
          if (!storyId) {
            showMiniToast('Only stories can be deleted.');
            return;
          }

          let remaining = 5;
          showDeleteConfirm();

          const update = () => {
            try {
              if (deleteCountdown) deleteCountdown.textContent = `Deleting in ${remaining}s…`;
            } catch {}
          };

          update();

          deleteInterval = window.setInterval(() => {
            remaining = Math.max(0, remaining - 1);
            update();
          }, 1000);

          deleteTimer = window.setTimeout(() => {
            performDelete();
          }, 5000);
        };

        const show = (i) => {
          const nextIndex = Math.max(0, Math.min(items.length - 1, i));
          index = nextIndex;
          startedAt = Date.now();

          const item = items[index];
          if (item && item.type === 'ad') {
            try {
              if (img) {
                img.classList.add('hidden');
                img.removeAttribute('src');
              }
              if (ad) ad.classList.remove('hidden');
            } catch {}
          } else {
            try {
              if (ad) ad.classList.add('hidden');
              if (img) {
                img.classList.remove('hidden');
                img.src = item && item.story ? item.story.image_url : (item ? item.image_url : '');
              }
            } catch {}
          }
          setSegment(index, 0);

          updateNavUi();

          // Preload next image.
          try {
            const n = items[index + 1];
            if (n && n.type !== 'ad') {
              const url = (n.story && n.story.image_url) ? n.story.image_url : n.image_url;
              if (url) preload(url);
            }
          } catch {}

          cleanupTimers();
          tickTimer = window.setInterval(() => {
            const elapsed = Date.now() - startedAt;
            const pct = (elapsed / getItemDurationMs(item)) * 100;
            setSegment(index, pct);
            if (elapsed >= getItemDurationMs(item)) {
              goNext();
            }
          }, 50);
        };

        const goPrev = () => {
          if (index <= 0) {
            show(0);
            return;
          }
          show(index - 1);
        };

        const goNext = () => {
          if (index >= items.length - 1) {
            close();
            return;
          }
          show(index + 1);
        };

        const onKeyDown = (e) => {
          const k = String(e && e.key || '');
          if (k === 'Escape') {
            try {
              if (deleteConfirm && !deleteConfirm.classList.contains('hidden')) {
                hideDeleteConfirm();
                return;
              }
            } catch {}
            try {
              if (menuPanel && !menuPanel.classList.contains('hidden')) {
                hideMenu();
                return;
              }
            } catch {}
            close();
            return;
          }
          if (k === 'ArrowLeft') { goPrev(); return; }
          if (k === 'ArrowRight') { goNext(); return; }
        };

        if (closeBtn) closeBtn.addEventListener('click', close);
        if (menuBtn) {
          // Hide menu entirely unless permitted.
          try { menuBtn.classList.toggle('hidden', !canDelete); } catch {}
          menuBtn.addEventListener('click', (e) => {
            try { e.preventDefault(); } catch {}
            try { e.stopPropagation(); } catch {}
            if (!canDelete) return;
            toggleMenu();
          });
        }
        if (deleteBtn) {
          deleteBtn.addEventListener('click', (e) => {
            try { e.preventDefault(); } catch {}
            try { e.stopPropagation(); } catch {}
            hideMenu();
            if (!canDelete) return;

            // Only allow delete when the current item is a real story.
            const storyId = getCurrentStoryId();
            if (!storyId) {
              showMiniToast('Only stories can be deleted.');
              return;
            }
            startDeleteCountdown();
          });
        }
        if (deleteCancel) {
          deleteCancel.addEventListener('click', (e) => {
            try { e.preventDefault(); } catch {}
            try { e.stopPropagation(); } catch {}
            hideDeleteConfirm();
          });
        }
        if (deleteNow) {
          deleteNow.addEventListener('click', (e) => {
            try { e.preventDefault(); } catch {}
            try { e.stopPropagation(); } catch {}
            performDelete();
          });
        }
        if (prevBtn) prevBtn.addEventListener('click', goPrev);
        if (nextBtn) nextBtn.addEventListener('click', goNext);

        // Click outside image closes.
        root.addEventListener('click', (e) => {
          try {
            if (menuPanel && !menuPanel.classList.contains('hidden')) {
              // Clicking anywhere outside the menu closes it.
              const inMenu = (e.target && e.target.closest) ? e.target.closest('[data-story-menu-panel]') : null;
              const inBtn = (e.target && e.target.closest) ? e.target.closest('[data-story-menu-btn]') : null;
              if (!inMenu && !inBtn) hideMenu();
            }
            if (e.target === root) close();
          } catch {}
        });

        window.addEventListener('keydown', onKeyDown);
        show(0);
      };

      // Initial pass (page load)
      updateStoryRings(document);

      // HTMX swaps (e.g., profile modal)
      try {
        if (!document.body.dataset.vixoStoryRingBound) {
          document.body.dataset.vixoStoryRingBound = '1';
          document.body.addEventListener('htmx:afterSwap', (e) => {
            try {
              const target = e && e.detail && e.detail.target;
              if (!target) return;
              updateStoryRings(target);
            } catch {
              // ignore
            }
          });
        }
      } catch {
        // ignore
      }

      document.addEventListener('click', async (e) => {
        try {
          const t = e.target;
          const el = t && t.closest ? t.closest('[data-story-username]') : null;
          if (!el) return;
          const username = el.getAttribute('data-story-username') || '';
          const pageVersion = el.getAttribute('data-story-version') || '';
          const url = buildUrl(username);
          if (!url) return;
          try { e.preventDefault(); } catch {}
          try { e.stopPropagation(); } catch {}

          const res = await fetch(url, {
            method: 'GET',
            headers: { 'Accept': 'application/json' },
            credentials: 'same-origin',
          });

          if (res.status === 403) {
            try { alert('Private account.'); } catch {}
            return;
          }

          if (!res.ok) {
            try { alert('Failed to load stories.'); } catch {}
            return;
          }

          const data = await res.json();

          // Mark as seen once stories successfully load.
          try {
            const computed = computeVersionFromStories(data && data.stories);
            const v = String(pageVersion || computed || '').trim();
            if (v) setSeenVersion(username, v);
            updateStoryRings(document);
          } catch {
            // ignore
          }

          openViewer({
            username: data && data.username,
            durationSeconds: data && data.duration_seconds,
            stories: data && data.stories,
            canDelete: data && data.can_delete,
            storiesUrl: url,
          });
        } catch {
          // ignore
        }
      }, true);
    } catch {
      // ignore
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const baseCfg = readJsonScript('vixo-config') || {};

    // Global init
    initDisableContextMenu();
    initGlobalLoadingIndicator();
    initContactDropdown();
    initUserMenuDropdown();
    initToasts();
    initCustomConfirm();
    initPromptModal();
    initPremiumUpgradePopup();
    initImageViewer();
    initVideoViewer();
    initVideoDecodeFallback();
    initHtmxConfirmBridge();
    initGlobalAnnouncementSocket();
    initMaintenancePolling(baseCfg);
    initChatViewportSizing();
    initStoriesViewer();

    document.body.addEventListener('htmx:configRequest', (event) => {
      event.detail.headers['X-CSRFToken'] = getCookie('csrftoken');
    });

    initAuthenticatedNotifiers(baseCfg);
  });
})();
