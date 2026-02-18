(function () {
    const PRIVATE_ROOM_CREATE_COOLDOWN_MS = 4 * 60 * 1000;
    const PRIVATE_ROOM_CREATE_COOLDOWN_KEY = 'vixo_private_room_create_cooldown_until';

    function __escapeHtml(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function __getPrivateRoomCreateCooldownRemainingMs() {
        try {
            const untilRaw = window.localStorage ? window.localStorage.getItem(PRIVATE_ROOM_CREATE_COOLDOWN_KEY) : null;
            const until = Number(untilRaw || 0);
            if (!Number.isFinite(until) || until <= 0) return 0;
            return Math.max(0, until - Date.now());
        } catch {
            return 0;
        }
    }

    function __setPrivateRoomCreateCooldownUntil(untilMs) {
        try {
            if (!window.localStorage) return;
            window.localStorage.setItem(PRIVATE_ROOM_CREATE_COOLDOWN_KEY, String(Number(untilMs) || 0));
        } catch {
            // ignore
        }
    }

    function __formatCooldownMmSs(ms) {
        const totalSec = Math.max(0, Math.ceil(ms / 1000));
        const m = Math.floor(totalSec / 60);
        const s = totalSec % 60;
        const ss = String(s).padStart(2, '0');
        return `${m}:${ss}`;
    }

    function initPrivateRoomCreateCooldownUi() {
        const form = document.getElementById('vixo-private-room-create-form');
        if (!form) return;

        const btn = form.querySelector('button[type="submit"]');
        if (!btn) return;

        if (!btn.dataset.originalText) {
            btn.dataset.originalText = (btn.textContent || 'Create private room').trim();
        }

        function render() {
            const remaining = __getPrivateRoomCreateCooldownRemainingMs();
            if (remaining > 0) {
                btn.disabled = true;
                btn.textContent = `Wait ${__formatCooldownMmSs(remaining)}`;
                btn.classList.add('opacity-60', 'cursor-not-allowed');
            } else {
                btn.disabled = false;
                btn.textContent = btn.dataset.originalText;
                btn.classList.remove('opacity-60', 'cursor-not-allowed');
            }
        }

        // If the user landed on a newly created room via non-AJAX flow, activate cooldown once.
        try {
            const params = new URLSearchParams(window.location.search || '');
            if (params.get('created') === '1') {
                const existingRemaining = __getPrivateRoomCreateCooldownRemainingMs();
                if (existingRemaining <= 0) {
                    __setPrivateRoomCreateCooldownUntil(Date.now() + PRIVATE_ROOM_CREATE_COOLDOWN_MS);
                }
            }
        } catch {
            // ignore
        }

        render();

        // Update countdown while active.
        if (btn.dataset.cooldownTimerAttached === '1') return;
        btn.dataset.cooldownTimerAttached = '1';
        window.setInterval(render, 1000);
    }

    // --- Private room creation form AJAX handler (no page reload) ---
    function initPrivateRoomCreateAjax() {
        const form = document.getElementById('vixo-private-room-create-form');
        if (!form) return;

        const submitBtn = form.querySelector('button[type="submit"]');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const remaining = __getPrivateRoomCreateCooldownRemainingMs();
            if (remaining > 0) {
                const msg = `Please wait ${__formatCooldownMmSs(remaining)} before creating another private room.`;
                if (window.showToast) {
                    window.showToast(msg);
                } else {
                    alert(msg);
                }
                return;
            }

            const formData = new FormData(form);
            const action = form.getAttribute('action') || '';

            try {
                if (submitBtn) submitBtn.disabled = true;
                const resp = await fetch(action, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    body: formData,
                });

                const data = await resp.json();

                // If verification limit error (403), show toast and don't redirect.
                if (resp.status === 403 && !data.ok) {
                    if (window.showToast) {
                        window.showToast(data.error || 'Please verify your email.');
                    } else {
                        alert(data.error || 'Please verify your email.');
                    }
                    return;
                }

                // On success, redirect to the room.
                if (data.ok && data.redirect_url) {
                    __setPrivateRoomCreateCooldownUntil(Date.now() + PRIVATE_ROOM_CREATE_COOLDOWN_MS);
                    window.location.href = data.redirect_url;
                } else if (data.ok) {
                    // Fallback: reload page to show the new room.
                    __setPrivateRoomCreateCooldownUntil(Date.now() + PRIVATE_ROOM_CREATE_COOLDOWN_MS);
                    window.location.reload();
                } else {
                    // Other error.
                    if (window.showToast) {
                        window.showToast(data.error || 'Something went wrong.');
                    } else {
                        alert(data.error || 'Something went wrong.');
                    }
                }
            } catch (err) {
                console.error('Private room create error:', err);
                if (window.showToast) {
                    window.showToast('Network error. Please try again.');
                } else {
                    alert('Network error. Please try again.');
                }
            } finally {
                if (submitBtn) submitBtn.disabled = false;
            }
        });
    }

    function initPrivateRoomJoinValidation() {
        const form = document.getElementById('vixo-private-room-join-form');
        if (!form) return;

        const codeInput = form.querySelector('input[name="code"]');
        if (!codeInput) return;

        const errorEl = form.querySelector('[data-room-code-error]');

        function showError(message) {
            const text = String(message || '').trim() || 'Enter room code to join.';
            if (errorEl) {
                errorEl.textContent = text;
                errorEl.classList.remove('hidden');
            }
            codeInput.setAttribute('aria-invalid', 'true');
            codeInput.classList.add('border-rose-400/60');
        }

        function clearError() {
            if (errorEl) {
                errorEl.textContent = '';
                errorEl.classList.add('hidden');
            }
            codeInput.removeAttribute('aria-invalid');
            codeInput.classList.remove('border-rose-400/60');
        }

        form.addEventListener('submit', (e) => {
            const raw = String(codeInput.value || '');
            const value = raw.trim();

            if (!value) {
                e.preventDefault();
                const msg = 'Room code required.';
                showError(msg);
                if (window.showToast) window.showToast(msg);
                codeInput.focus();
                return;
            }

            clearError();
            codeInput.value = value.toUpperCase();
        });

        codeInput.addEventListener('input', () => {
            if (codeInput.value.trim()) clearError();
        });
    }

    // Init on DOMContentLoaded or immediately if already loaded.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPrivateRoomCreateAjax, { once: true });
        document.addEventListener('DOMContentLoaded', initPrivateRoomCreateCooldownUi, { once: true });
        document.addEventListener('DOMContentLoaded', initPrivateRoomJoinValidation, { once: true });
    } else {
        initPrivateRoomCreateAjax();
        initPrivateRoomCreateCooldownUi();
        initPrivateRoomJoinValidation();
    }

    // --- Room code click-to-copy ---
    function copyToClipboard(text) {
        const value = String(text || '').trim();
        if (!value) return Promise.resolve(false);

        // Modern async clipboard API
        try {
            if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                return navigator.clipboard.writeText(value).then(() => true).catch(() => false);
            }
        } catch {
            // ignore; fallback below
        }

        // Fallback: execCommand
        try {
            const ta = document.createElement('textarea');
            ta.value = value;
            ta.setAttribute('readonly', 'readonly');
            ta.style.position = 'fixed';
            ta.style.top = '-1000px';
            ta.style.left = '-1000px';
            document.body.appendChild(ta);
            ta.select();
            const ok = document.execCommand('copy');
            ta.remove();
            return Promise.resolve(!!ok);
        } catch {
            return Promise.resolve(false);
        }
    }

    function initRoomCodeCopy() {
        const buttons = document.querySelectorAll('[data-room-code-copy]');
        if (!buttons || !buttons.length) return;

        const hideTimers = new WeakMap();
        const invisibleTimers = new WeakMap();

        function showCopiedLabel(btn, ok) {
            const host = btn && (btn.closest('[data-room-code-wrap]') || btn.parentElement);
            const label = host ? host.querySelector('[data-room-code-copied]') : null;
            if (!label) return;

            // Cancel any pending hide/invisible timers
            const prevHide = hideTimers.get(label);
            if (prevHide) window.clearTimeout(prevHide);
            const prevInv = invisibleTimers.get(label);
            if (prevInv) window.clearTimeout(prevInv);

            if (!ok) {
                label.textContent = 'Copy failed';
                label.classList.add('text-red-300');
            } else {
                label.textContent = 'Code copied';
                label.classList.remove('text-red-300');
            }

            // Animate in
            label.classList.remove('invisible');
            // Start from hidden state (in case it's mid-transition)
            label.classList.add('opacity-0', '-translate-y-0.5', 'scale-95');
            label.classList.remove('opacity-100', 'translate-y-0', 'scale-100');
            requestAnimationFrame(() => {
                label.classList.remove('opacity-0', '-translate-y-0.5', 'scale-95');
                label.classList.add('opacity-100', 'translate-y-0', 'scale-100');
            });

            // Animate out, then set invisible after transition
            const hideDelay = ok ? 1200 : 1800;
            const t = window.setTimeout(() => {
                label.classList.add('opacity-0', '-translate-y-0.5', 'scale-95');
                label.classList.remove('opacity-100', 'translate-y-0', 'scale-100');
                const t2 = window.setTimeout(() => {
                    label.classList.add('invisible');
                }, 220);
                invisibleTimers.set(label, t2);
            }, hideDelay);
            hideTimers.set(label, t);
        }

        buttons.forEach((btn) => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const code = btn.getAttribute('data-room-code-copy') || '';
                const ok = await copyToClipboard(code);
                showCopiedLabel(btn, ok);
            });
        });
    }

    function initRoomShareHint() {
        const hint = document.getElementById('room_share_hint');
        if (!hint) return;

        // If tutorial is present, prefer that UX and don't also show the transient hint.
        const tutorialRoot = document.getElementById('vixo_room_tutorial');
        if (tutorialRoot) {
            try { hint.remove(); } catch {}
            return;
        }

        // Template renders this as hidden to avoid reserving space before JS runs.
        hint.classList.remove('hidden');

        // Animate in.
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                try {
                    hint.classList.remove('opacity-0', '-translate-y-2');
                    hint.classList.add('opacity-100', 'translate-y-0');
                } catch {
                    // ignore
                }
            });
        });

        // Auto-hide + remove (so it cannot leave a blank gap on mobile).
        window.setTimeout(() => {
            try {
                hint.classList.add('opacity-0', '-translate-y-2');
                hint.classList.remove('opacity-100', 'translate-y-0');
            } catch {
                // ignore
            }
            window.setTimeout(() => {
                try { hint.remove(); } catch {}
            }, 350);
        }, 4000);
    }

    function initPublicGroupAdBanner() {
        const banner = document.getElementById('vixo_public_group_ad_banner');
        if (!banner) return;

        function readMs(attr, fallback) {
            try {
                const v = parseInt(String(banner.getAttribute(attr) || ''), 10);
                return Number.isFinite(v) && v >= 0 ? v : fallback;
            } catch {
                return fallback;
            }
        }

        const initialDelayMs = readMs('data-ad-initial-delay-ms', 10000);
        const visibleMs = readMs('data-ad-visible-ms', 8000);
        const hiddenMs = readMs('data-ad-hidden-ms', 25000);

        let stopped = false;
        let t1 = null;
        let t2 = null;

        function show() {
            if (stopped) return;
            try { banner.classList.remove('hidden'); } catch {}
            // Stage the transition so the browser has a "from" state.
            try {
                banner.classList.add('opacity-0', '-translate-y-1');
                banner.classList.remove('opacity-100', 'translate-y-0');
            } catch {}
            try {
                window.requestAnimationFrame(() => {
                    if (stopped) return;
                    try {
                        banner.classList.remove('opacity-0', '-translate-y-1');
                        banner.classList.add('opacity-100', 'translate-y-0');
                    } catch {}
                });
            } catch {}
        }

        function hide() {
            if (stopped) return;
            try {
                banner.classList.add('opacity-0', '-translate-y-1');
                banner.classList.remove('opacity-100', 'translate-y-0');
            } catch {}
            // After transition, fully hide.
            t2 = window.setTimeout(() => {
                if (stopped) return;
                try { banner.classList.add('hidden'); } catch {}
            }, 220);
        }

        function cycle() {
            if (stopped) return;
            show();
            t1 = window.setTimeout(() => {
                hide();
                t1 = window.setTimeout(cycle, Math.max(0, hiddenMs));
            }, Math.max(0, visibleMs));
        }

        // Start hidden; show after a short delay, then repeat.
        try { banner.classList.add('hidden'); } catch {}
        t1 = window.setTimeout(cycle, Math.max(0, initialDelayMs));

        // Best-effort cleanup if page gets replaced.
        try {
            window.addEventListener('beforeunload', () => {
                stopped = true;
                try { if (t1) window.clearTimeout(t1); } catch {}
                try { if (t2) window.clearTimeout(t2); } catch {}
            }, { once: true });
        } catch {}
    }

    function initRoomTutorial() {
        const root = document.getElementById('vixo_room_tutorial');
        if (!root) return;

        const forceShow = String(root.getAttribute('data-tutorial-force') || '').trim() === '1';
        const tutorialMode = String(root.getAttribute('data-tutorial-mode') || '').trim();

        // Per-user key so multiple logins on same browser don't conflict.
        const username = String(cfg.currentUsername || '').trim();
        const storageScope = tutorialMode || 'private-room';
        const storageKey = `vixo_hide_room_tutorial:${storageScope}:${username || 'anon'}`;

        try {
            if (!forceShow && window.localStorage && window.localStorage.getItem(storageKey) === '1') {
                root.remove();
                return;
            }
        } catch {
            // ignore
        }

        const backdrop = root.querySelector('[data-tutorial-backdrop]');
        const closeButtons = root.querySelectorAll('[data-tutorial-close]');
        const dontShow = root.querySelector('#vixo_room_tutorial_dont_show');
        const hlWaiting = document.getElementById('vixo_room_tutorial_hl_waiting');
        const hlCode = document.getElementById('vixo_room_tutorial_hl_code');
        const callout = document.getElementById('vixo_room_tutorial_callout');
        const calloutText = document.getElementById('vixo_room_tutorial_callout_text');

        function stripTutorialParams() {
            try {
                const url = new URL(window.location.href);
                let changed = false;
                if (url.searchParams.has('created')) {
                    url.searchParams.delete('created');
                    changed = true;
                }
                if (url.searchParams.has('welcome')) {
                    url.searchParams.delete('welcome');
                    changed = true;
                }
                if (changed) {
                    window.history.replaceState({}, '', url.toString());
                }
            } catch {
                // ignore
            }
        }

        function setHighlight(el, highlightEl) {
            if (!el || !highlightEl) return false;
            const r = el.getBoundingClientRect();
            if (!r || !(r.width > 0 && r.height > 0)) return false;
            const pad = 6;
            highlightEl.style.left = `${Math.max(0, r.left - pad)}px`;
            highlightEl.style.top = `${Math.max(0, r.top - pad)}px`;
            highlightEl.style.width = `${Math.max(0, r.width + pad * 2)}px`;
            highlightEl.style.height = `${Math.max(0, r.height + pad * 2)}px`;
            highlightEl.classList.remove('hidden');
            return true;
        }

        function positionCalloutNear(el, text) {
            if (!callout || !calloutText) return;
            if (!el) {
                callout.classList.add('hidden');
                return;
            }
            const r = el.getBoundingClientRect();
            if (!r || !(r.width > 0 && r.height > 0)) {
                callout.classList.add('hidden');
                return;
            }
            calloutText.textContent = String(text || '');

            const top = Math.max(12, r.bottom + 10);
            // Keep on-screen (roughly)
            const left = Math.max(12, Math.min(r.left, window.innerWidth - 280));
            callout.style.left = `${left}px`;
            callout.style.top = `${top}px`;
            callout.classList.remove('hidden');
        }

        function positionHighlights() {
            const waitingBtn = document.getElementById('code_room_waiting_btn');
            const codeCandidates = [];
            try {
                const byId = document.getElementById('vixo_room_code_btn');
                if (byId) codeCandidates.push(byId);
            } catch {}
            try {
                document.querySelectorAll('[data-tutorial-target="room-code"]').forEach((el) => codeCandidates.push(el));
            } catch {}

            const codeBtn = (function pickVisible(items) {
                for (let i = 0; i < items.length; i++) {
                    const el = items[i];
                    if (!(el instanceof HTMLElement)) continue;
                    const r = el.getBoundingClientRect();
                    if (r && r.width > 0 && r.height > 0) return el;
                }
                return items.length ? items[0] : null;
            })(codeCandidates);

            const didWaiting = setHighlight(waitingBtn, hlWaiting);
            const didCode = setHighlight(codeBtn, hlCode);

            // Prefer callout on the waiting list button, else room code.
            if (didWaiting) {
                positionCalloutNear(waitingBtn, '👥 Waiting list: admit members (admin only)');
            } else if (didCode) {
                positionCalloutNear(codeBtn, 'Tap room code to copy & share');
            } else {
                if (callout) callout.classList.add('hidden');
            }
        }

        function closeTutorial() {
            const checked = !!(dontShow && dontShow.checked);
            if (checked) {
                try {
                    if (window.localStorage) window.localStorage.setItem(storageKey, '1');
                } catch {
                    // ignore
                }
            }

            try { document.body.classList.remove('overflow-hidden'); } catch {}
            try { root.remove(); } catch {}
            stripTutorialParams();
        }

        // Wire close actions.
        closeButtons.forEach((btn) => {
            try { btn.addEventListener('click', closeTutorial); } catch {}
        });
        if (backdrop) {
            try { backdrop.addEventListener('click', closeTutorial); } catch {}
        }

        function showTutorialNow() {
            root.classList.remove('hidden');
            try { document.body.classList.add('overflow-hidden'); } catch {}
            stripTutorialParams();

            // Suppress the transient share hint if present.
            try {
                const hint = document.getElementById('room_share_hint');
                if (hint) hint.remove();
            } catch {}

            // Position highlights.
            positionHighlights();
            window.addEventListener('resize', positionHighlights, { passive: true });
            window.addEventListener('scroll', positionHighlights, { passive: true, capture: true });
        }

        const welcomeModal = document.getElementById('welcome-modal');
        if (!welcomeModal) {
            showTutorialNow();
            return;
        }

        let opened = false;
        const openAfterWelcome = () => {
            if (opened) return;
            if (document.getElementById('welcome-modal')) return;
            opened = true;
            try { window.removeEventListener('vixo:welcome-closed', openAfterWelcome); } catch {}
            showTutorialNow();
        };

        try { window.addEventListener('vixo:welcome-closed', openAfterWelcome, { once: true }); } catch {}

        // Fallback for any path that removes modal without dispatching the event.
        try {
            const observer = new MutationObserver(() => {
                if (!document.getElementById('welcome-modal')) {
                    try { observer.disconnect(); } catch {}
                    openAfterWelcome();
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        } catch {}
    }

    // --- Message bubble context actions (right-click, swipe, long-press) ---
    function __isMobileChatViewport() {
        try {
            return !window.matchMedia('(min-width: 640px)').matches;
        } catch {
            return true;
        }
    }

    function closeAllMessageActionBars(exceptMsgEl) {
        const open = document.querySelectorAll('.vixo-msg.vixo-actions-open');
        open.forEach((el) => {
            if (exceptMsgEl && el === exceptMsgEl) return;
            el.classList.remove('vixo-actions-open');
        });
    }

    function openMessageActionBar(msgEl) {
        if (!msgEl) return;
        closeAllMessageActionBars(msgEl);
        msgEl.classList.add('vixo-actions-open');
    }

    function showMessageMenuFor(msgId) {
        // Find the menu for this message and open it
        const el = document.getElementById(`msg-${msgId}`);
        if (!el) return;
        const menu = el.querySelector('[data-message-menu]');
        const toggle = el.querySelector('[data-message-menu-toggle]');
        const actions = el.querySelector('[data-msg-actions]');
        if (menu && toggle) {
            closeAllMessageMenus(menu);
            if (actions) {
                actions.classList.remove('opacity-0', 'pointer-events-none');
                actions.classList.add('opacity-100', 'pointer-events-auto');
            }
            menu.classList.remove('hidden');
            toggle.setAttribute('aria-expanded', 'true');
        }
    }

    // Desktop: right-click context menu
    document.addEventListener('contextmenu', function(e) {
        const msg = e.target.closest('.vixo-msg');
        if (!msg) return;
        const msgId = msg.dataset.messageId;
        if (!msgId) return;
        e.preventDefault();
        showMessageMenuFor(msgId);
    });

    // Mobile: swipe left to reply, long-press to reveal options
    // Important: prevent horizontal page/container scrolling during the gesture.
    let touchStartX = 0, touchStartY = 0, touchStartTime = 0, touchTimer = null;
    let touchActiveMsg = null;
    document.addEventListener('touchstart', function(e) {
        const msg = e.target.closest('.vixo-msg');
        if (!msg) return;
        if (e.touches.length !== 1) return;

        touchActiveMsg = msg;
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        touchStartTime = Date.now();

        touchTimer = setTimeout(() => {
            // Long press: reveal reply/+ / ⋮ (tap ⋮ to open the menu)
            if (!__isMobileChatViewport()) return;
            try { closeAllReactionPickers(); } catch {}
            try { closeAllMessageMenus(); } catch {}
            openMessageActionBar(msg);
        }, 520); // ~0.5s hold
    }, { passive: true });

    document.addEventListener('touchmove', function(e) {
        if (touchTimer) clearTimeout(touchTimer);
        if (!touchActiveMsg) return;
        if (e.touches.length !== 1) return;

        // If this is primarily a horizontal swipe (reply gesture), block horizontal scroll.
        const dx = e.touches[0].clientX - touchStartX;
        const dy = e.touches[0].clientY - touchStartY;
        if (Math.abs(dx) > 8 && Math.abs(dx) > Math.abs(dy) + 6) {
            try { e.preventDefault(); } catch {}
        }
    }, { passive: false });

    document.addEventListener('touchend', function(e) {
        if (touchTimer) clearTimeout(touchTimer);
        const msg = touchActiveMsg;
        touchActiveMsg = null;
        if (!msg) return;
        if (e.changedTouches.length !== 1) return;

        const dx = e.changedTouches[0].clientX - touchStartX;
        const dy = e.changedTouches[0].clientY - touchStartY;
        const dt = Date.now() - touchStartTime;
        // Quick left swipe (horizontal, not vertical, not long-press)
        if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) && dx < 0 && dt < 400) {
            // Swipe left: quick reply
            closeAllMessageActionBars();
            const replyBtn = msg.querySelector('[data-reply-button]');
            if (replyBtn) replyBtn.click();
        }
    }, { passive: true });

    document.addEventListener('touchcancel', function() {
        if (touchTimer) clearTimeout(touchTimer);
        touchActiveMsg = null;
    }, { passive: true });

    // Mobile: tap outside closes the revealed action icons.
    document.addEventListener('click', function (e) {
        if (!__isMobileChatViewport()) return;

        // If user clicks inside action icons or an open menu, keep it open.
        const keep = e.target && e.target.closest
            ? e.target.closest('.vixo-msg.vixo-actions-open [data-msg-actions], .vixo-msg.vixo-actions-open [data-message-menu]')
            : null;
        if (keep) return;

        closeAllMessageActionBars();
    }, true);
    function readJsonScript(id) {
        try {
            const el = document.getElementById(id);
            if (!el) return null;
            const raw = (el.textContent || '').trim();
            if (!raw) return null;
            return JSON.parse(raw);
        } catch {
            return null;
        }
    }

    function initMaintenanceAdminToggle() {
        const toggle = document.getElementById('vixo-maintenance-toggle');
        if (!toggle) return;

        const stateEl = document.getElementById('vixo-maintenance-state');
        const hintEl = document.getElementById('vixo-maintenance-hint');
        const baseCfg = readJsonScript('vixo-config') || {};

        const statusUrl = String(baseCfg.maintenanceStatusUrl || '');
        const toggleUrl = String(baseCfg.maintenanceToggleUrl || '');
        if (!statusUrl || !toggleUrl) return;

        function setHint(msg, isError) {
            if (!hintEl) return;
            const m = String(msg || '').trim();
            if (!m) {
                hintEl.classList.add('hidden');
                hintEl.textContent = '';
                hintEl.classList.remove('text-red-300');
                return;
            }
            hintEl.textContent = m;
            hintEl.classList.remove('hidden');
            hintEl.classList.toggle('text-red-300', !!isError);
        }

        function setState(enabled) {
            toggle.checked = !!enabled;
            if (stateEl) stateEl.textContent = enabled ? 'On' : 'Off';
        }

        function setBusy(busy) {
            toggle.disabled = !!busy;
            toggle.style.opacity = busy ? '0.65' : '';
            if (stateEl && busy) stateEl.textContent = '…';
        }

        async function refresh() {
            setBusy(true);
            setHint('');
            try {
                const res = await fetch(statusUrl, { credentials: 'same-origin', cache: 'no-store', headers: { 'Accept': 'application/json' } });
                const data = res.ok ? await res.json() : null;
                setState(!!(data && data.enabled));
            } catch {
                setHint('Could not load maintenance status.', true);
            } finally {
                setBusy(false);
            }
        }

        toggle.addEventListener('change', async () => {
            const nextEnabled = !!toggle.checked;
            setBusy(true);
            setHint('');
            try {
                const body = new URLSearchParams();
                body.set('enabled', nextEnabled ? '1' : '0');
                const csrf = (typeof getCookie === 'function' ? getCookie('csrftoken') : '') || '';

                const res = await fetch(toggleUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                        'X-CSRFToken': csrf,
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    body,
                    credentials: 'same-origin',
                });

                const data = res.ok ? await res.json() : null;
                if (!data || !data.ok) {
                    throw new Error('toggle failed');
                }

                setState(!!data.enabled);
                setHint(data.enabled ? 'Maintenance enabled: users will be redirected.' : 'Maintenance disabled.', false);
                window.setTimeout(() => setHint(''), 2500);
            } catch {
                // Revert UI to actual state
                await refresh();
                setHint('Could not update maintenance mode.', true);
            } finally {
                setBusy(false);
            }
        });

        refresh();
    }

    const cfg = (window.__vixo_chat_config && typeof window.__vixo_chat_config === 'object')
        ? window.__vixo_chat_config
        : (readJsonScript('vixo-chat-config') || {});

    // chat.js is injected after DOMContentLoaded via chat_loader.js, so DOM is usually ready.
    // Still guard for rare cases.
    try {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                initRoomCodeCopy();
                initRoomTutorial();
                initRoomShareHint();
                initPublicGroupAdBanner();
                initMaintenanceAdminToggle();
            }, { once: true });
        } else {
            initRoomCodeCopy();
            initRoomTutorial();
            initRoomShareHint();
            initPublicGroupAdBanner();
            initMaintenanceAdminToggle();
        }
    } catch {
        // ignore
    }

    // --- GIF picker (initialize early so the button always responds) ---
    (function initGifPickerEarly() {
        if (window.__vixoGifPickerInitDone) return;

        const btn = document.getElementById('gif_btn');
        const panel = document.getElementById('gif_panel');
        if (!btn || !panel) return;

        const gifsAllowed = !!cfg.gifsAllowed;
        const apiKey = String(cfg.giphyApiKey || '').trim();
        const limit = parseInt(cfg.giphyLimit || '30', 10) || 30;

        const closeBtn = document.getElementById('gif_close');
        const searchInput = document.getElementById('gif_search');
        const statusEl = document.getElementById('gif_status');
        const resultsEl = document.getElementById('gif_results');
        const form = document.getElementById('chat_message_form');
        const input = document.getElementById('id_body');

        if (!gifsAllowed) {
            // Server should not render the button, but guard anyway.
            try { btn.classList.add('hidden'); } catch {}
            return;
        }

        // Mark initialized even if apiKey is missing (we still want a friendly response).
        window.__vixoGifPickerInitDone = true;

        let open = false;
        let debounceId = null;
        let activeReq = 0;
        let hasLoadedInitial = false;

        function renderStatus(text) {
            if (!statusEl) return;
            statusEl.textContent = String(text || '');
        }

        function renderResultsHtml(html) {
            if (!resultsEl) return;
            resultsEl.innerHTML = html || '';
        }

        function positionPanel() {
            if (!panel || !btn) return;
            if (panel.classList.contains('hidden')) return;

            // Desktop: let CSS positioning handle it.
            try {
                if (window.matchMedia && window.matchMedia('(min-width: 640px)').matches) {
                    panel.style.left = '';
                    panel.style.right = '';
                    panel.style.top = '';
                    panel.style.bottom = '';
                    panel.style.display = '';
                    panel.style.visibility = '';
                    return;
                }
            } catch {}

            const prevVis = panel.style.visibility;
            panel.style.visibility = 'hidden';
            panel.style.display = 'block';

            const panelRect = panel.getBoundingClientRect();
            const panelW = panelRect.width || 384;
            const panelH = panelRect.height || 320;
            const btnRect = btn.getBoundingClientRect();

            const padding = 12;
            const gap = 10;

            let left = btnRect.right - panelW;
            left = Math.max(padding, Math.min(left, window.innerWidth - panelW - padding));

            const canPlaceAbove = (btnRect.top - panelH - gap) >= padding;

            panel.style.left = `${Math.round(left)}px`;
            panel.style.right = 'auto';

            if (canPlaceAbove) {
                let top = btnRect.top - gap - panelH;
                top = Math.max(padding, Math.min(top, window.innerHeight - panelH - padding));
                panel.style.top = `${Math.round(top)}px`;
                panel.style.bottom = 'auto';
            } else {
                let top = btnRect.bottom + gap;
                top = Math.max(padding, Math.min(top, window.innerHeight - panelH - padding));
                panel.style.top = `${Math.round(top)}px`;
                panel.style.bottom = 'auto';
            }

            panel.style.visibility = prevVis || '';
        }

        function setPanelOpen(next) {
            open = !!next;
            if (open) {
                panel.classList.remove('hidden');
                try { panel.style.visibility = 'hidden'; } catch {}
                positionPanel();
                requestAnimationFrame(() => {
                    try {
                        panel.classList.remove('opacity-0', 'scale-95', 'pointer-events-none');
                        panel.classList.add('opacity-100', 'scale-100', 'pointer-events-auto');
                    } catch {}
                    try { panel.style.visibility = ''; } catch {}
                });
                try { if (searchInput) searchInput.focus(); } catch {}
            } else {
                try {
                    panel.classList.add('opacity-0', 'scale-95', 'pointer-events-none');
                    panel.classList.remove('opacity-100', 'scale-100', 'pointer-events-auto');
                } catch {}
                window.setTimeout(() => {
                    if (!open) {
                        try { panel.classList.add('hidden'); } catch {}
                    }
                }, 160);
            }
        }

        function renderResults(items) {
            if (!resultsEl) return;
            resultsEl.innerHTML = '';
            if (!items || !items.length) {
                resultsEl.innerHTML = '<div class="col-span-2 text-xs text-gray-400">No GIFs found.</div>';
                return;
            }
            const frag = document.createDocumentFragment();
            for (const it of items) {
                const images = it && it.images ? it.images : null;
                const url = images && images.fixed_width && images.fixed_width.url ? String(images.fixed_width.url) : '';
                const thumb = images && images.fixed_width_small && images.fixed_width_small.url ? String(images.fixed_width_small.url) : url;
                if (!url) continue;
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'relative overflow-hidden rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 transition';
                b.setAttribute('data-gif-url', url);
                b.innerHTML = `<img src="${__escapeHtml(thumb)}" alt="GIF" class="w-full h-28 object-cover" loading="lazy" decoding="async" />`;
                frag.appendChild(b);
            }
            resultsEl.appendChild(frag);
            try { positionPanel(); } catch {}
        }

        async function loadTrending() {
            if (!apiKey) return;
            const reqId = ++activeReq;
            renderStatus('Loading trending...');
            try {
                const url = `https://api.giphy.com/v1/gifs/trending?api_key=${encodeURIComponent(apiKey)}&limit=${encodeURIComponent(String(limit))}`;
                const resp = await fetch(url, { method: 'GET' });
                const data = await resp.json().catch(() => null);
                if (reqId !== activeReq) return;
                const items = data && Array.isArray(data.data) ? data.data : [];
                hasLoadedInitial = true;
                renderStatus(items.length ? 'Trending GIFs' : 'No trending GIFs');
                renderResults(items);
            } catch {
                if (reqId !== activeReq) return;
                renderStatus('Failed to load GIFs.');
                renderResultsHtml('<div class="col-span-2 text-xs text-red-300">Could not reach Giphy.</div>');
            }
        }

        async function search(q) {
            const query = String(q || '').trim();
            if (!apiKey) return;
            if (!query) {
                renderStatus('Trending GIFs');
                if (!hasLoadedInitial) await loadTrending();
                return;
            }

            const reqId = ++activeReq;
            renderStatus('Searching...');
            try {
                const url = `https://api.giphy.com/v1/gifs/search?q=${encodeURIComponent(query)}&api_key=${encodeURIComponent(apiKey)}&limit=${encodeURIComponent(String(limit))}`;
                const resp = await fetch(url, { method: 'GET' });
                const data = await resp.json().catch(() => null);
                if (reqId !== activeReq) return;
                const items = data && Array.isArray(data.data) ? data.data : [];
                renderStatus(items.length ? `Results: ${items.length}` : 'No results');
                renderResults(items);
            } catch {
                if (reqId !== activeReq) return;
                renderStatus('Failed to load GIFs.');
                renderResultsHtml('<div class="col-span-2 text-xs text-red-300">Could not reach Giphy.</div>');
            }
        }

        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const next = !open;
            setPanelOpen(next);
            if (!next) return;

            if (!apiKey) {
                renderStatus('GIFs are not configured.');
                renderResultsHtml('<div class="col-span-2 text-xs text-amber-200">Missing Giphy API key.</div>');
                try { __popup('GIFs not configured', 'Giphy API key is missing in chat config.'); } catch {}
                return;
            }

            // Load trending on first open.
            const q = String((searchInput && searchInput.value) || '').trim();
            if (!q) loadTrending();
            try { positionPanel(); } catch {}
        });

        if (closeBtn) closeBtn.addEventListener('click', (e) => { e.preventDefault(); setPanelOpen(false); });

        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            if (!open) return;
            setPanelOpen(false);
        }, true);

        document.addEventListener('click', (e) => {
            if (!open) return;
            const inside = e.target && e.target.closest ? e.target.closest('#gif_panel, #gif_btn') : null;
            if (!inside) setPanelOpen(false);
        }, true);

        window.addEventListener('resize', () => { if (open) positionPanel(); }, { passive: true });
        window.addEventListener('scroll', () => { if (open) positionPanel(); }, true);

        if (searchInput) {
            searchInput.addEventListener('input', () => {
                if (!apiKey) return;
                if (debounceId) window.clearTimeout(debounceId);
                debounceId = window.setTimeout(() => search(searchInput.value), 250);
            });
        }

        if (resultsEl) {
            resultsEl.addEventListener('click', (e) => {
                const pick = e.target && e.target.closest ? e.target.closest('[data-gif-url]') : null;
                if (!pick) return;
                const url = String(pick.getAttribute('data-gif-url') || '').trim();
                if (!url) return;
                if (!form || !input) return;

                const gifBody = `[GIF] ${url}`;
                setPanelOpen(false);

                const prevValue = input.value;
                try {
                    input.value = gifBody;
                    if (form.requestSubmit) form.requestSubmit();
                    else {
                        const send = document.getElementById('chat_send_btn');
                        if (send) send.click();
                    }
                } catch {
                    // ignore
                } finally {
                    try { input.value = prevValue; } catch {}
                }
            });
        }

        renderStatus(apiKey ? 'Trending GIFs' : 'GIFs');
        if (resultsEl && apiKey) {
            resultsEl.innerHTML = '<div class="col-span-2 text-xs text-gray-400">Opening…</div>';
        }
    })();

    // --- Private code room rename (admin/staff) ---
    function __isSmallScreen() {
        try { return !window.matchMedia('(min-width: 640px)').matches; } catch { return true; }
    }

    async function __renamePrivateRoomViaApi(url, group, nextName) {
        function getCsrf() {
            try { return (typeof getCookie === 'function' ? getCookie('csrftoken') : ''); } catch { return ''; }
        }

        const body = new URLSearchParams();
        body.set('name', String(nextName || '').trim());

        const resp = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'X-CSRFToken': getCsrf(),
                'X-Requested-With': 'XMLHttpRequest',
            },
            body,
            credentials: 'same-origin',
        });

        if (!resp.ok) return null;
        const data = await resp.json().catch(() => null);
        if (!data || !data.ok) return null;

        const display = String(data.display || '').trim();
        if (!display) return null;

        // Update header title if this room is currently open.
        if (group && String(chatroomName || '') === String(group)) {
            const titleEl = document.getElementById('vixo_private_room_title');
            if (titleEl) titleEl.textContent = display;

            const inlineTitleEl = document.getElementById('vixo_private_room_title_inline');
            if (inlineTitleEl) inlineTitleEl.textContent = display;
        }

        // Update sidebar label for this room (if present).
        if (group) {
            const sidebarLabel = document.querySelector(`[data-private-room-title-for="${CSS.escape(String(group))}"]`);
            if (sidebarLabel) sidebarLabel.textContent = display.slice(0, 30);
        }

        return display;
    }

    function initPrivateRoomRename() {
        const buttons = Array.from(document.querySelectorAll('[data-private-room-rename][data-private-room-rename-url]'));
        if (!buttons.length) return;

        buttons.forEach((btn) => {
            btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();

            const url = btn.getAttribute('data-private-room-rename-url') || '';
            const group = btn.getAttribute('data-private-room-group') || '';
            if (!url) return;

            const titleEl = document.getElementById('vixo_private_room_title');
            const inlineTitleEl = document.getElementById('vixo_private_room_title_inline');
            const currentTitle = (
                (titleEl && titleEl.textContent ? titleEl.textContent : '')
                || (inlineTitleEl && inlineTitleEl.textContent ? inlineTitleEl.textContent : '')
            ).trim();
            const next = (typeof window.__vixoPrompt === 'function')
                ? await window.__vixoPrompt({
                    title: 'Rename room',
                    message: 'Enter a new name (leave empty to clear). Max char: 35.',
                    defaultValue: currentTitle,
                    placeholder: 'Private room name (optional)',
                    maxLength: 35,
                    okText: 'Rename',
                    cancelText: 'Cancel',
                })
                : prompt('Rename room', currentTitle);
            if (next === null) return;

            const nextName = String(next || '').trim();
            if (!nextName) {
                if (!confirm('Clear room name and show code instead?')) return;
            }

            try {
                const ok = await __renamePrivateRoomViaApi(url, group, nextName);
                if (!ok && typeof __popup === 'function') __popup('Rename failed', 'Could not rename this room.');
            } catch {
                if (typeof __popup === 'function') __popup('Rename failed', 'Network error. Please try again.');
            }
            });
        });
    }

    // Mobile-only: long-press on a private room in the sidebar to rename (admin/staff only).
    function initPrivateRoomRenameLongPress() {
        if (!__isSmallScreen()) return;

        const items = Array.from(document.querySelectorAll('[data-private-room-item][data-private-room-rename-url][data-private-room-group]'));
        if (!items.length) return;

        items.forEach((el) => {
            let timer = null;
            let startX = 0;
            let startY = 0;
            let fired = false;

            function clear() {
                if (timer) window.clearTimeout(timer);
                timer = null;
            }

            function begin(clientX, clientY) {
                clear();
                fired = false;
                startX = clientX;
                startY = clientY;
                timer = window.setTimeout(async () => {
                    fired = true;
                    el.__vixoLongPressFired = true;

                    const url = el.getAttribute('data-private-room-rename-url') || '';
                    const group = el.getAttribute('data-private-room-group') || '';
                    if (!url || !group) return;

                    const label = el.querySelector(`[data-private-room-title-for="${CSS.escape(String(group))}"]`) || el;
                    const current = (label.textContent || '').trim();
                    const next = (typeof window.__vixoPrompt === 'function')
                        ? await window.__vixoPrompt({
                            title: 'Rename room',
                            message: 'Enter a new name (leave empty to clear). Max char: 35.',
                            defaultValue: current,
                            placeholder: 'Private room name (optional)',
                            maxLength: 35,
                            okText: 'Rename',
                            cancelText: 'Cancel',
                        })
                        : prompt('Rename room', current);
                    if (next === null) return;

                    const nextName = String(next || '').trim();
                    if (!nextName) {
                        if (!confirm('Clear room name and show code instead?')) return;
                    }

                    const ok = await __renamePrivateRoomViaApi(url, group, nextName);
                    if (!ok && typeof __popup === 'function') __popup('Rename failed', 'Could not rename this room.');
                }, 550);
            }

            el.addEventListener('pointerdown', (e) => {
                if (!__isSmallScreen()) return;
                if (e.pointerType === 'mouse') return;
                begin(e.clientX || 0, e.clientY || 0);
            });

            el.addEventListener('pointermove', (e) => {
                if (!timer) return;
                const dx = Math.abs((e.clientX || 0) - startX);
                const dy = Math.abs((e.clientY || 0) - startY);
                if (dx > 12 || dy > 12) clear();
            });

            el.addEventListener('pointerup', clear);
            el.addEventListener('pointercancel', clear);
            el.addEventListener('pointerleave', clear);

            el.addEventListener('click', (e) => {
                if (el.__vixoLongPressFired) {
                    el.__vixoLongPressFired = false;
                    e.preventDefault();
                    e.stopPropagation();
                }
            }, true);

            el.addEventListener('contextmenu', (e) => {
                // Prevent long-press context menu on mobile.
                if (!__isSmallScreen()) return;
                e.preventDefault();
            });
        });
    }

    // Mobile-only: hide any tiny "SD" badge in the top bar (if some script injects it).
    function initHideSdBadgeOnMobile() {
        if (!__isSmallScreen()) return;
        const topbar = document.getElementById('chat_topbar');
        if (!topbar) return;
        const nodes = Array.from(topbar.querySelectorAll('span, button, a, div'));
        nodes.forEach((n) => {
            const t = (n.textContent || '').trim();
            if (t === 'SD') {
                n.classList.add('hidden');
            }
        });
    }

    try {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initPrivateRoomRename, { once: true });
        } else {
            initPrivateRoomRename();
        }
    } catch {
        // ignore
    }

    try {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initPrivateRoomRenameLongPress, { once: true });
            document.addEventListener('DOMContentLoaded', initHideSdBadgeOnMobile, { once: true });
        } else {
            initPrivateRoomRenameLongPress();
            initHideSdBadgeOnMobile();
        }
    } catch {
        // ignore
    }

    function initSidebarSectionCollapse() {
        // Prevent double-binding if chat.js is injected multiple times.
        if (window.__vixoSidebarSectionCollapseInitDone) return;
        window.__vixoSidebarSectionCollapseInitDone = true;

        const esc = (window.CSS && typeof window.CSS.escape === 'function')
            ? window.CSS.escape
            : (s) => String(s || '').replace(/[^a-zA-Z0-9_\-]/g, (ch) => `\\${ch}`);

        function storageKey(k) {
            return `vixo_sidebar_section_collapsed:${String(k || '')}`;
        }

        function loadInitialState(key) {
            try {
                const v = window.localStorage.getItem(storageKey(key));
                return v === '1';
            } catch {
                return false;
            }
        }

        function findBodyForToggle(btn, key) {
            // Prefer a global lookup by key.
            const byKey = document.querySelector(`[data-vixo-collapse-body][data-vixo-collapse-key="${esc(String(key))}"]`);
            if (byKey) return byKey;

            // Fallback: look near the toggle (handles partial renders / swapped fragments).
            try {
                const parent = btn && btn.parentElement;
                if (parent) {
                    const near = parent.querySelector(`[data-vixo-collapse-body][data-vixo-collapse-key="${esc(String(key))}"]`);
                    if (near) return near;
                }
            } catch {
                // ignore
            }
            return null;
        }

        function setCollapsed(btn, key, collapsed) {
            const body = findBodyForToggle(btn, key);
            if (!body) return;

            const toggle = btn || document.querySelector(`[data-vixo-collapse-toggle][data-vixo-collapse-key="${esc(String(key))}"]`);
            if (!toggle) return;

            const chevron = toggle.querySelector ? toggle.querySelector('[data-vixo-collapse-chevron]') : null;
            if (collapsed) {
                body.classList.add('hidden');
                try { toggle.setAttribute('aria-expanded', 'false'); } catch {}
                if (chevron) chevron.style.transform = 'rotate(-90deg)';
            } else {
                body.classList.remove('hidden');
                try { toggle.setAttribute('aria-expanded', 'true'); } catch {}
                if (chevron) chevron.style.transform = '';
            }
        }

        function persist(key, collapsed) {
            try {
                window.localStorage.setItem(storageKey(key), collapsed ? '1' : '0');
            } catch {
                // ignore
            }
        }

        function applyInitial(root) {
            const scope = root || document;
            const toggles = scope.querySelectorAll ? scope.querySelectorAll('[data-vixo-collapse-toggle][data-vixo-collapse-key]') : [];
            if (!toggles || !toggles.length) return;
            toggles.forEach((btn) => {
                const key = btn.getAttribute('data-vixo-collapse-key') || '';
                if (!key) return;
                setCollapsed(btn, key, loadInitialState(key));
            });
        }

        // Apply initial state on first load.
        applyInitial(document);

        // Delegate clicks so it keeps working even if sidebar HTML is swapped.
        document.addEventListener('click', (e) => {
            const btn = e.target && e.target.closest ? e.target.closest('[data-vixo-collapse-toggle][data-vixo-collapse-key]') : null;
            if (!btn) return;

            const key = btn.getAttribute('data-vixo-collapse-key') || '';
            if (!key) return;

            const body = findBodyForToggle(btn, key);
            if (!body) return;

            const isCollapsed = body.classList.contains('hidden');
            const nextCollapsed = !isCollapsed;
            setCollapsed(btn, key, nextCollapsed);
            persist(key, nextCollapsed);
        }, true);

        // If HTMX swaps any part of the sidebar, re-apply initial collapsed state.
        try {
            document.body.addEventListener('htmx:afterSwap', (ev) => {
                const target = ev && ev.detail ? ev.detail.target : null;
                if (!target) return;
                applyInitial(target);
            });
        } catch {
            // ignore
        }
    }

    try {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initSidebarSectionCollapse, { once: true });
        } else {
            initSidebarSectionCollapse();
        }
    } catch {
        // ignore
    }

    const chatroomName = String(cfg.chatroomName || '');
    const currentUserId = parseInt(cfg.currentUserId || 0, 10) || 0;
    const currentUsername = String(cfg.currentUsername || '');
    let lastOtherReadId = parseInt(cfg.otherLastReadId || 0, 10) || 0;
    const pollUrl = String(cfg.pollUrl || '');
    const olderUrl = String(cfg.olderUrl || '');
    const inviteUrl = String(cfg.inviteUrl || '');
    const tokenUrl = String(cfg.tokenUrl || '');
    const presenceUrl = String(cfg.presenceUrl || '');

    const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${wsScheme}://${window.location.host}/ws/chatroom/${chatroomName}`;

    // Expose current room + scroll state helpers to global notification handlers
    window.__activeChatroomName = chatroomName;
    window.__isChatNearBottom = function () {
        const chatContainer = document.getElementById('chat_container');
        if (!chatContainer) return true;
        const distanceFromBottom = (chatContainer.scrollHeight - (chatContainer.scrollTop + chatContainer.clientHeight));
        return distanceFromBottom <= 140;
    };

    // Autoscroll behavior:
    // - If user is near bottom, follow new messages.
    // - If user scrolls up to read, stop auto-scrolling until they return near bottom.
    let __chatAutoScrollEnabled = true;
    const __privateNewMsgJumpBtn = document.getElementById('vixo_private_newmsg_jump');
    let __privateNewMsgArmed = false;

    function __hidePrivateNewMsgJump() {
        if (!__privateNewMsgJumpBtn) return;
        __privateNewMsgArmed = false;
        __privateNewMsgJumpBtn.classList.add('hidden');
        __privateNewMsgJumpBtn.classList.remove('vixo-private-newmsg-pulse');
    }

    function __showPrivateNewMsgJump() {
        if (!__privateNewMsgJumpBtn) return;
        if (__privateNewMsgArmed) return;
        __privateNewMsgArmed = true;
        __privateNewMsgJumpBtn.classList.remove('hidden');
        __privateNewMsgJumpBtn.classList.add('vixo-private-newmsg-pulse');
    }

    (function initPrivateNewMsgJump() {
        if (!__privateNewMsgJumpBtn) return;
        __privateNewMsgJumpBtn.addEventListener('click', () => {
            try {
                window.__forceNextChatScroll = true;
                __chatAutoScrollEnabled = true;
                forceScrollToBottomNow();
            } catch {
                // ignore
            }
            __hidePrivateNewMsgJump();
        });
    })();

    (function initAutoscrollToggle() {
        const chatContainer = document.getElementById('chat_container');
        if (!chatContainer) return;
        const recompute = () => {
            try {
                __chatAutoScrollEnabled = !!window.__isChatNearBottom();
            } catch {
                __chatAutoScrollEnabled = true;
            }

            // Private chats: if user returns near bottom, hide the "new messages" jump.
            try {
                if (__privateNewMsgJumpBtn && typeof window.__isChatNearBottom === 'function' && window.__isChatNearBottom()) {
                    __hidePrivateNewMsgJump();
                }
            } catch {
                // ignore
            }
        };
        recompute();
        chatContainer.addEventListener('scroll', recompute, { passive: true });
    })();

    function highlightMentionMessage(messageId) {
        const mid = parseInt(messageId || 0, 10) || 0;
        if (!mid) return;

        const el = document.getElementById(`msg-${mid}`);
        if (!el) return;

        // Full-row highlight (behind the bubble), without changing bubble background.
        const existing = el.querySelector('[data-mention-highlight]');
        if (existing) {
            try { existing.remove(); } catch {}
        }
        const overlay = document.createElement('div');
        overlay.setAttribute('data-mention-highlight', '1');
        overlay.className = 'absolute inset-x-0 -inset-y-1 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 pointer-events-none';
        el.insertBefore(overlay, el.firstChild);

        setTimeout(() => {
            try { overlay.remove(); } catch {}
        }, 2400);
    }

    // When a global mention notification arrives, highlight the message in this room.
    window.addEventListener('chat:mention', (e) => {
        const d = e && e.detail ? e.detail : {};
        if (!d || !d.chatroom_name) return;
        if (String(d.chatroom_name) !== String(chatroomName)) return;

        const messageId = d.message_id || 0;
        let tries = 0;
        const tick = () => {
            tries += 1;
            const el = document.getElementById(`msg-${messageId}`);
            if (el) {
                highlightMentionMessage(messageId);
                return;
            }
            if (tries < 12) setTimeout(tick, 120);
        };
        tick();
    });

    function normalizeRoomName(value) {
        let raw = String(value || '').trim();
        if (!raw) return '';
        raw = raw.replace(/\+/g, ' ');
        try {
            raw = decodeURIComponent(raw);
        } catch {
            // keep raw
        }
        return raw.replace(/\s+/g, ' ').trim().toLowerCase();
    }

    function roomNameFromChatHref(href) {
        const raw = String(href || '').trim();
        if (!raw) return '';
        try {
            const u = new URL(raw, window.location.origin);
            const m = u.pathname.match(/^\/chat\/room\/([^\/]+)\/?$/i);
            if (!m || !m[1]) return '';
            return m[1];
        } catch {
            return '';
        }
    }

    function ensureGroupsTabMentionBadge() {
        const groupsTab = document.getElementById('chat_mobile_tab_groups');
        if (!groupsTab) return null;

        let badge = groupsTab.querySelector('[data-groups-mention-badge]');
        if (!badge) {
            badge = document.createElement('span');
            badge.setAttribute('data-groups-mention-badge', '1');
            badge.className = 'hidden absolute -top-1 -right-1 min-w-5 h-5 px-1 rounded-full bg-red-500 text-[10px] leading-5 text-center font-bold text-white';
            badge.textContent = '1';
            groupsTab.classList.add('relative');
            groupsTab.appendChild(badge);
        }
        return badge;
    }

    function setGroupsTabMentionBadgeVisible(visible) {
        const badge = ensureGroupsTabMentionBadge();
        if (!badge) return;
        badge.classList.toggle('hidden', !visible);
        if (visible) badge.textContent = '1';
    }

    const GROUP_MENTION_STORAGE_KEY = 'vixo_group_mention_rooms_v1';

    function loadStoredMentionRooms() {
        try {
            if (!window.localStorage) return [];
            const raw = window.localStorage.getItem(GROUP_MENTION_STORAGE_KEY);
            if (!raw) return [];
            const parsed = JSON.parse(raw);
            if (!Array.isArray(parsed)) return [];
            return parsed
                .map((v) => normalizeRoomName(v))
                .filter((v) => !!v);
        } catch {
            return [];
        }
    }

    function saveStoredMentionRooms(rooms) {
        try {
            if (!window.localStorage) return;
            const normalized = Array.from(new Set((Array.isArray(rooms) ? rooms : [])
                .map((v) => normalizeRoomName(v))
                .filter((v) => !!v)));
            window.localStorage.setItem(GROUP_MENTION_STORAGE_KEY, JSON.stringify(normalized));
        } catch {
            // ignore
        }
    }

    function addStoredMentionRoom(roomName) {
        const r = normalizeRoomName(roomName);
        if (!r) return;
        const current = loadStoredMentionRooms();
        if (current.includes(r)) return;
        current.push(r);
        saveStoredMentionRooms(current);
    }

    function removeStoredMentionRoom(roomName) {
        const r = normalizeRoomName(roomName);
        if (!r) return;
        const current = loadStoredMentionRooms();
        const next = current.filter((v) => v !== r);
        if (next.length === current.length) return;
        saveStoredMentionRooms(next);
    }

    function markGroupRoomMentionBadge(roomName) {
        const target = normalizeRoomName(roomName);
        if (!target) return 0;

        const links = document.querySelectorAll('a.vixo-groupchat-link[data-chat-list-scope="group"], a.vixo-groupchat-link');
        if (!links || !links.length) return 0;

        let marked = 0;
        links.forEach((link) => {
            const hrefRoom = normalizeRoomName(roomNameFromChatHref(link.getAttribute('href')));
            if (!hrefRoom || hrefRoom !== target) return;

            let badge = link.querySelector('[data-group-mention-badge]');
            if (!badge) {
                badge = document.createElement('span');
                badge.setAttribute('data-group-mention-badge', '1');
                badge.className = 'ml-auto inline-flex shrink-0 min-w-5 h-5 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold leading-5 text-white';
                badge.textContent = '1';
                link.appendChild(badge);
            } else {
                badge.textContent = '1';
            }
            marked += 1;
        });

        return marked;
    }

    function initPersistedGroupMentionBadges() {
        // Opening a room means that room's mention/reply badge can be cleared.
        removeStoredMentionRoom(chatroomName);

        const fromServer = Array.isArray(cfg.unreadMentionRooms) ? cfg.unreadMentionRooms : [];
        const fromStorage = loadStoredMentionRooms();
        const merged = Array.from(new Set([
            ...fromServer.map((v) => normalizeRoomName(v)),
            ...fromStorage,
        ].filter((v) => !!v)));

        // Keep storage synced with server + realtime events.
        saveStoredMentionRooms(merged);

        let anyMarked = false;
        merged.forEach((room) => {
            if (room === normalizeRoomName(chatroomName)) return;
            const c = markGroupRoomMentionBadge(room);
            if (c > 0) anyMarked = true;
        });
        setGroupsTabMentionBadgeVisible(anyMarked);
    }

    initPersistedGroupMentionBadges();

    // For mentions/replies from other rooms, place a small "1" marker on that group row.
    window.addEventListener('chat:mention', (e) => {
        const d = e && e.detail ? e.detail : {};
        if (!d || !d.chatroom_name) return;
        if (String(d.chatroom_name) === String(chatroomName)) return;

        const markedCount = markGroupRoomMentionBadge(d.chatroom_name);
        if (markedCount > 0) {
            addStoredMentionRoom(d.chatroom_name);
            setGroupsTabMentionBadgeVisible(true);
        }
    });

    // When a global call control notification arrives, close the call popup.
    window.addEventListener('call:control', (e) => {
        const d = e && e.detail ? e.detail : {};
        if (!d || !d.chatroom_name) return;
        if (String(d.chatroom_name) !== String(chatroomName)) return;
        if (d.action === 'end' || d.action === 'decline') {
            endCallPopup(d.action === 'decline' ? 'Call declined' : 'Call ended');
        }
    });

    let __lastChatBlockedState = null;
    function applyChatBlockedUI(blocked, opts) {
        const options = opts || {};
        const normalized = !!blocked;
        const allowPopup = options.allowPopup !== false;
        const isTransition = (typeof __lastChatBlockedState === 'boolean' && __lastChatBlockedState !== normalized);
        __lastChatBlockedState = normalized;

        const form = document.getElementById('chat_message_form');
        const input = document.getElementById('id_body');
        const fileInput = document.getElementById('chat_file_input');
        const captionInput = document.getElementById('chat_file_caption');
        const sendBtn = document.getElementById('chat_send_btn');

        // If composer form is not present, avoid forcing any page refresh.
        if (!form) return;

        let banner = document.getElementById('chat_blocked_banner');
        if (normalized) {
            if (!banner) {
                banner = document.createElement('div');
                banner.id = 'chat_blocked_banner';
                banner.className = 'mb-2 rounded-xl border border-gray-800 bg-gray-900/80 px-4 py-3 text-sm text-gray-200';
                banner.textContent = 'You are blocked from sending messages.';
                form.parentNode.insertBefore(banner, form);
            }
        } else if (banner) {
            try { banner.remove(); } catch {}
        }

        const disable = normalized;
        if (input) input.disabled = disable;
        if (fileInput) fileInput.disabled = disable;
        if (captionInput) captionInput.disabled = disable;
        if (sendBtn) {
            sendBtn.disabled = disable;
            sendBtn.classList.toggle('opacity-70', disable);
            sendBtn.classList.toggle('cursor-not-allowed', disable);
        }

        // Only show popup when the state actually changes (not on initial page load).
        if (allowPopup && isTransition) {
            if (disable) {
                try { __popup('Blocked', 'You are blocked from chatting right now.'); } catch {}
            } else {
                try { __popup('Unblocked', 'You can chat again.'); } catch {}
            }
        }
    }

    let __verifyGateActive = false;
    function applyVerifyRequiredUI(required, reason) {
        const normalized = !!required;
        __verifyGateActive = normalized;

        const gate = document.getElementById('verify_gate');
        const reasonEl = document.getElementById('verify_gate_reason');
        const refreshBtn = document.getElementById('verify_gate_refresh');

        const chatContainer = document.getElementById('chat_container');
        const composerBar = document.getElementById('chat_composer_bar');
        const form = document.getElementById('chat_message_form');
        const input = document.getElementById('id_body');
        const sendBtn = document.getElementById('chat_send_btn');
        const fileInput = document.getElementById('chat_file_input');
        const captionInput = document.getElementById('chat_file_caption');

        if (reasonEl) {
            const msg = (reason && String(reason).trim()) ? String(reason).trim() : 'Verify your email to continue chatting.';
            reasonEl.textContent = msg;
        }

        if (gate) {
            gate.classList.toggle('hidden', !normalized);
        }

        // Blur + dim chat area while locked.
        if (chatContainer) {
            chatContainer.classList.toggle('blur-sm', normalized);
            chatContainer.classList.toggle('opacity-60', normalized);
        }
        if (composerBar) {
            composerBar.classList.toggle('opacity-60', normalized);
        }

        // Disable composer controls (if present).
        if (form) {
            form.classList.toggle('pointer-events-none', normalized);
        }
        if (input) input.disabled = normalized;
        if (fileInput) fileInput.disabled = normalized;
        if (captionInput) captionInput.disabled = normalized;
        if (sendBtn) {
            sendBtn.disabled = normalized;
            sendBtn.classList.toggle('opacity-70', normalized);
            sendBtn.classList.toggle('cursor-not-allowed', normalized);
        }

        if (refreshBtn && !refreshBtn.__vixoBound) {
            refreshBtn.__vixoBound = true;
            refreshBtn.addEventListener('click', async () => {
                if (refreshBtn.dataset && refreshBtn.dataset.loading === '1') return;
                try { if (refreshBtn.dataset) refreshBtn.dataset.loading = '1'; } catch {}
                refreshBtn.disabled = true;
                refreshBtn.classList.add('opacity-70', 'cursor-not-allowed');

                try {
                    const res = await fetch('/chat/verify/status/', {
                        method: 'GET',
                        credentials: 'same-origin',
                        headers: { 'Accept': 'application/json' },
                    });
                    const data = await res.json().catch(() => ({}));
                    if (data && data.verified && !data.requires_verification) {
                        try { window.location.reload(); } catch {}
                        return;
                    }

                    const msg = (data && data.reason) ? data.reason : 'Verification not yet done. Please verify your email and try again.';
                    applyVerifyRequiredUI(true, msg);
                    // Call showVerifyRequired instead of __popup directly
                    // This ensures the modal doesn't flicker if already open
                    try { showVerifyRequired(msg); } catch {}
                } catch {
                    const msg = 'Verification not yet done. Please verify your email and try again.';
                    applyVerifyRequiredUI(true, msg);
                    try { showVerifyRequired(msg); } catch {}
                } finally {
                    refreshBtn.disabled = false;
                    refreshBtn.classList.remove('opacity-70', 'cursor-not-allowed');
                    try { if (refreshBtn.dataset) refreshBtn.dataset.loading = '0'; } catch {}
                }
            });
        }
    }

    let __verifyModalOpen = false;  // Flag to prevent repeated modal opens
    
    function showVerifyRequired(reason) {
        applyVerifyRequiredUI(true, reason);
        
        // Only open modal if not already open
        if (!__verifyModalOpen) {
            __verifyModalOpen = true;
            try { 
                if (typeof window.__openConfirm === 'function') {
                    window.__openConfirm({
                        title: 'Verify required',
                        message: (reason || 'Verify your email to continue chatting.'),
                        showCancel: false,
                        okText: 'OK',
                        onConfirm: () => { __verifyModalOpen = false; }
                    });
                } else {
                    __popup('Verify required', (reason || 'Verify your email to continue chatting.'));
                }
            } catch {}
        }
    }

    // HTMX trigger from server
    document.body.addEventListener('verify_required', (e) => {
        const d = (e && e.detail) ? e.detail : {};
        showVerifyRequired(d && d.reason ? d.reason : null);
    });

    // Initial server-rendered state
    try {
        const gate = document.getElementById('verify_gate');
        if (gate && String(gate.getAttribute('data-initial') || '') === '1') {
            showVerifyRequired('Verify your email to continue chatting.');
        }
    } catch {
        // ignore
    }

    // Realtime block/unblock (admin action)
    window.addEventListener('chat:block_status', (e) => {
        const d = e && e.detail ? e.detail : {};
        applyChatBlockedUI(!!d.blocked, { allowPopup: true });
    });

    // Realtime ban/unban (admin action)
    window.addEventListener('chat:ban_status', (e) => {
        const d = e && e.detail ? e.detail : {};
        const banned = !!d.banned;
        if (banned) {
            try {
                const until = (d.until || '').trim();
                const msg = until ? `You are banned from chat until ${until}.` : 'You are banned from chat.';
                __popup('Banned', msg);
            } catch {}
        } else {
            try { __popup('Unbanned', 'You can chat again.'); } catch {}
        }
        applyChatBlockedUI(banned, { allowPopup: false });
    });

    // Initialize from embedded config (if present)
    if (typeof cfg.chatBlocked !== 'undefined') {
        // Initialize UI silently (no popups on load).
        applyChatBlockedUI(!!cfg.chatBlocked, { allowPopup: false });
    }

    (function initChatEmojiPicker() {
        const btn = document.getElementById('emoji_btn');
        const panel = document.getElementById('emoji_panel');
        const mount = document.getElementById('emoji_mart_mount');

        if (!btn || !panel || !mount) return;

        let pickerEl = null;
        const ANIM_MS = 160;

        function getActiveInput() {
            const captionWrap = document.getElementById('chat_file_caption_wrap');
            const captionInput = document.getElementById('chat_file_caption');
            if (captionWrap && !captionWrap.classList.contains('hidden') && captionInput && !captionInput.disabled) {
                return captionInput;
            }
            return document.getElementById('id_body');
        }

        function insertAtCursor(input, text) {
            if (!input) return;
            const start = input.selectionStart ?? input.value.length;
            const end = input.selectionEnd ?? input.value.length;
            const before = input.value.slice(0, start);
            const after = input.value.slice(end);
            input.value = before + text + after;
            const nextPos = start + text.length;
            try {
                input.setSelectionRange(nextPos, nextPos);
            } catch (e) {}
            try {
                input.focus();
            } catch (e) {}
        }

        function ensurePicker() {
            if (pickerEl) return;
            mount.innerHTML = '';

            // Primary: emoji-mart
            if (window.EmojiMart && window.EmojiMart.Picker) {
                pickerEl = new window.EmojiMart.Picker({
                    theme: 'dark',
                    set: 'native',
                    dynamicWidth: true,
                    previewPosition: 'none',
                    onEmojiSelect: (emoji) => {
                        const nativeEmoji = (emoji && emoji.native) ? emoji.native : '';
                        if (!nativeEmoji) return;
                        insertAtCursor(getActiveInput(), nativeEmoji);
                    },
                });

                // Make it wider and less tall (not "lamban"). Inline styles override the component's default :host height.
                try {
                    pickerEl.style.width = '100%';
                    pickerEl.style.height = '320px';
                } catch (e) {}

                mount.appendChild(pickerEl);
                return;
            }

            // Fallback: small built-in emoji grid (works offline / when CDN is blocked)
            const fallback = document.createElement('div');
            fallback.className = 'grid grid-cols-8 gap-1 text-lg select-none';
            const emojis = [
                '😀','😁','😂','🤣','😊','😍','😘','😎',
                '😅','😇','🙂','😉','😋','😜','🤔','😴',
                '😢','😭','😡','🤯','👍','👎','🙏','👏',
                '🔥','✨','💯','❤️','💔','🎉','😮','🤝',
            ];
            emojis.forEach((em) => {
                const b = document.createElement('button');
                b.type = 'button';
                b.textContent = em;
                b.className = 'h-9 w-9 rounded-lg hover:bg-gray-800/60';
                b.addEventListener('click', () => {
                    insertAtCursor(getActiveInput(), em);
                });
                fallback.appendChild(b);
            });
            pickerEl = fallback;
            mount.appendChild(fallback);
        }

        function ensureInViewport() {
            try {
                const rect = panel.getBoundingClientRect();
                const vh = window.innerHeight || document.documentElement.clientHeight || 0;
                const vw = window.innerWidth || document.documentElement.clientWidth || 0;
                const pad = 8;

                // Only adjust if it's actually out of bounds.
                if (rect.top < pad) {
                    panel.style.top = pad + 'px';
                    panel.style.bottom = 'auto';
                }
                if (rect.bottom > (vh - pad)) {
                    panel.style.bottom = pad + 'px';
                    panel.style.top = 'auto';
                }
                if (rect.left < pad) {
                    panel.style.left = pad + 'px';
                    panel.style.right = 'auto';
                }
                if (rect.right > (vw - pad)) {
                    panel.style.right = pad + 'px';
                    panel.style.left = 'auto';
                }
            } catch {
                // ignore
            }
        }

        const open = () => {
            ensurePicker();
            panel.classList.remove('hidden');
            // animate in
            requestAnimationFrame(() => {
                panel.classList.remove('opacity-0', 'scale-95', 'pointer-events-none');
                panel.classList.add('opacity-100', 'scale-100');
                ensureInViewport();
            });
            btn.setAttribute('aria-expanded', 'true');
        };
        const close = () => {
            if (panel.classList.contains('hidden')) {
                btn.setAttribute('aria-expanded', 'false');
                return;
            }
            // animate out
            panel.classList.remove('opacity-100', 'scale-100');
            panel.classList.add('opacity-0', 'scale-95', 'pointer-events-none');
            btn.setAttribute('aria-expanded', 'false');

            const done = () => {
                panel.classList.add('hidden');
                panel.removeEventListener('transitionend', done);
            };
            panel.addEventListener('transitionend', done);
            // fallback (in case transitionend doesn't fire)
            setTimeout(() => {
                if (!panel.classList.contains('hidden')) panel.classList.add('hidden');
                panel.removeEventListener('transitionend', done);
            }, ANIM_MS + 40);
        };
        const toggle = () => {
            if (panel.classList.contains('hidden')) open();
            else close();
        };

        btn.addEventListener('click', (e) => {
            e.preventDefault();
            toggle();
        });

        document.addEventListener('click', (e) => {
            const path = (e && typeof e.composedPath === 'function') ? e.composedPath() : null;
            if (path) {
                if (path.includes(btn) || path.includes(panel)) return;
            } else {
                const t = e.target;
                if (t && (panel.contains(t) || btn.contains(t))) return;
            }
            close();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && btn.getAttribute('aria-expanded') === 'true') close();
        });
    })();

    (function initChatUploadProgress() {
        const form = document.getElementById('chat_message_form');
        const sendBtn = document.getElementById('chat_send_btn');
        const sendText = document.getElementById('chat_send_text');
        const spinner = document.getElementById('chat_upload_spinner');
        const fileInput = document.getElementById('chat_file_input');
        const wrap = document.getElementById('chat_upload_progress');
        const bar = document.getElementById('chat_upload_bar');
        const percentEl = document.getElementById('chat_upload_percent');
        const statusEl = document.getElementById('chat_upload_status');

        if (!form || !sendBtn || !spinner || !wrap || !bar || !percentEl || !statusEl) return;

        let mediaUploadInFlight = false;

        function getSendPlaneIconEl() {
            try {
                const children = Array.from(sendBtn.children || []);
                for (const child of children) {
                    if (child && String(child.tagName || '').toUpperCase() === 'SVG') {
                        return child;
                    }
                }
            } catch {
                // ignore
            }
            return null;
        }

        function playSendPlaneAnimation() {
            if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
                return;
            }

            const iconEl = getSendPlaneIconEl();
            if (!iconEl) return;
            if (iconEl.dataset.vixoPlaneAnimating === '1') return;

            iconEl.dataset.vixoPlaneAnimating = '1';
            const prevWillChange = iconEl.style.willChange || '';
            const prevTransformOrigin = iconEl.style.transformOrigin || '';
            iconEl.style.willChange = 'transform, opacity';
            iconEl.style.transformOrigin = '50% 50%';

            const done = () => {
                try {
                    iconEl.dataset.vixoPlaneAnimating = '0';
                    iconEl.style.willChange = prevWillChange;
                    iconEl.style.transformOrigin = prevTransformOrigin;
                } catch {
                    // ignore
                }
            };

            try {
                const anim = iconEl.animate(
                    [
                        { transform: 'translate3d(0, 0, 0) rotate(0deg) scale(1)', opacity: 1, offset: 0 },
                        { transform: 'translate3d(14px, -16px, 0) rotate(12deg) scale(1.06)', opacity: 0.35, offset: 0.45 },
                        { transform: 'translate3d(-3px, 3px, 0) rotate(-8deg) scale(0.96)', opacity: 0.92, offset: 0.75 },
                        { transform: 'translate3d(0, 0, 0) rotate(0deg) scale(1)', opacity: 1, offset: 1 },
                    ],
                    {
                        duration: 760,
                        easing: 'cubic-bezier(0.2, 0.78, 0.2, 1)',
                        iterations: 1,
                        fill: 'none',
                    }
                );
                anim.addEventListener('finish', done, { once: true });
                anim.addEventListener('cancel', done, { once: true });
            } catch {
                done();
            }
        }

        function hasFileSelected() {
            return !!(fileInput && fileInput.files && fileInput.files.length > 0);
        }

        function setUploadingState(on) {
            if (on) {
                wrap.classList.remove('hidden');
                spinner.classList.remove('hidden');
                sendBtn.disabled = true;
                sendBtn.classList.add('opacity-70', 'cursor-not-allowed');
                if (sendText) sendText.textContent = 'Uploading…';
                if (fileInput) fileInput.disabled = true;
            } else {
                spinner.classList.add('hidden');
                sendBtn.disabled = false;
                sendBtn.classList.remove('opacity-70', 'cursor-not-allowed');
                if (sendText) sendText.textContent = 'Send';
                if (fileInput) fileInput.disabled = false;
                // Keep progress hidden after request to avoid UI flicker on text-only sends.
                wrap.classList.add('hidden');
                statusEl.textContent = 'Uploading…';
                percentEl.textContent = '0%';
                bar.style.width = '0%';
            }
        }

        // Only show upload UI when a file is being sent.
        document.body.addEventListener('htmx:beforeRequest', (e) => {
            if (!e || !e.target) return;
            if (e.target !== form) return;
            if (!hasFileSelected()) return;
            mediaUploadInFlight = true;
            setUploadingState(true);
        });

        document.body.addEventListener('htmx:xhr:progress', (e) => {
            if (!e || !e.target) return;
            if (e.target !== form) return;
            if (!hasFileSelected()) return;
            const detail = e.detail || {};
            const loaded = Number(detail.loaded || 0);
            const total = Number(detail.total || 0);
            if (!total || total <= 0) return;
            const pct = Math.max(0, Math.min(100, Math.round((loaded / total) * 100)));
            percentEl.textContent = pct + '%';
            bar.style.width = pct + '%';
            statusEl.textContent = pct >= 100 ? 'Processing…' : 'Uploading…';
        });

        document.body.addEventListener('htmx:afterRequest', (e) => {
            if (!e || !e.target) return;
            if (e.target !== form) return;
            const wasMediaUpload = !!mediaUploadInFlight;
            mediaUploadInFlight = false;

            if (wasMediaUpload) {
                try {
                    const xhr = e.detail && e.detail.xhr ? e.detail.xhr : null;
                    const status = xhr ? Number(xhr.status || 0) : 0;
                    if (status >= 200 && status < 300) {
                        playSendPlaneAnimation();
                    }
                } catch {
                    // ignore
                }
            }
            setUploadingState(false);
        });

        document.body.addEventListener('htmx:responseError', (e) => {
            if (!e || !e.target) return;
            if (e.target !== form) return;
            mediaUploadInFlight = false;
            setUploadingState(false);
        });
    })();

    // Keep the "Upload (x/y used)" counter in sync without requiring a page refresh.
    // The server triggers this event after a successful upload.
    document.body.addEventListener('uploadCountUpdated', (e) => {
        const detail = (e && e.detail) ? e.detail : {};
        const used = parseInt(detail.used ?? 0, 10) || 0;
        const limit = parseInt(detail.limit ?? 0, 10) || 0;
        const remaining = parseInt(detail.remaining ?? 0, 10);

        const counter = document.getElementById('upload_counter');
        if (counter && limit > 0) {
            counter.textContent = `Upload (${used}/${limit} used)`;
        }

        const msg = document.getElementById('upload_limit_reached_msg');
        if (msg && !Number.isNaN(remaining)) {
            msg.classList.toggle('hidden', remaining > 0);
        }

        const fileInput = document.getElementById('chat_file_input');
        if (fileInput && !Number.isNaN(remaining)) {
            fileInput.disabled = remaining <= 0;
            const uploadBtn = document.getElementById('chat_upload_btn');
            if (uploadBtn) uploadBtn.disabled = remaining <= 0;
            if (typeof window.__syncUploadMode === 'function') {
                window.__syncUploadMode();
            }
        }
    });

    function resetComposerAfterSend() {
        const form = document.getElementById('chat_message_form');
        if (!form) return;

        const input = document.getElementById('id_body');
        const typedMsInput = document.getElementById('typed_ms');
        const replyToIdInput = document.getElementById('reply_to_id');
        const fileInput = document.getElementById('chat_file_input');
        const captionInput = document.getElementById('chat_file_caption');
        const feedback = document.getElementById('upload_feedback');

        const replyBar = document.getElementById('reply_bar');
        const replyBarAuthor = document.getElementById('reply_bar_author');
        const replyBarPreview = document.getElementById('reply_bar_preview');

        if (input) input.value = '';
        if (typedMsInput) typedMsInput.value = '';
        if (replyToIdInput) replyToIdInput.value = '';

        if (captionInput) captionInput.value = '';
        if (fileInput) fileInput.value = '';
        if (feedback) feedback.innerHTML = '';

        if (replyBar) replyBar.classList.add('hidden');
        if (replyBarAuthor) replyBarAuthor.textContent = '';
        if (replyBarPreview) replyBarPreview.textContent = '';

        if (typeof window.__syncUploadMode === 'function') {
            window.__syncUploadMode();
        }

        try {
            if (typeof window.__autoGrowChatInput === 'function') {
                window.__autoGrowChatInput();
            }
        } catch {}
    }

    // Successful HTMX sends (covers file uploads and text sends when WS is unavailable).
    document.body.addEventListener('htmx:afterRequest', (event) => {
        const form = document.getElementById('chat_message_form');
        if (!form) return;
        if (!event || event.target !== form) return;
        if (!event.detail || !event.detail.successful) return;
        const xhr = event.detail.xhr;
        const status = xhr ? Number(xhr.status || 0) : 0;
        if (status && (status < 200 || status >= 300)) return;
        resetComposerAfterSend();
    });

    // If HTMX send is rate-limited, show the realtime cooldown countdown.
    document.body.addEventListener('htmx:responseError', (event) => {
        const form = document.getElementById('chat_message_form');
        if (!form) return;
        if (!event || event.target !== form) return;
        const xhr = event.detail ? event.detail.xhr : null;
        const status = xhr ? Number(xhr.status || 0) : 0;
        if (status !== 429) return;
        let retry = 0;
        try {
            retry = parseInt(xhr.getResponseHeader('Retry-After') || '0', 10) || 0;
        } catch {
            retry = 0;
        }
        if (typeof startSendCooldown === 'function') startSendCooldown(retry || 10);
    });

    function ensureChatFeedVisible() {
        const messagesEl = document.getElementById('chat_messages');
        if (messagesEl && messagesEl.classList.contains('hidden')) {
            messagesEl.classList.remove('hidden');
        }
        const emptyEl = document.getElementById('empty_state');
        if (emptyEl) {
            try { emptyEl.remove(); } catch { emptyEl.classList.add('hidden'); }
        }
    }

    // When HTMX appends the first message into an empty chat, the <ul> was initially hidden.
    // Ensure it becomes visible right after swap.
    document.body.addEventListener('htmx:afterSwap', (event) => {
        const target = event && event.detail ? event.detail.target : null;
        if (!target) return;
        if (target.id !== 'chat_messages') return;
        ensureChatFeedVisible();
        try {
            hydrateLocalTimes(target);
            applyConsecutiveHeaderGrouping(target);
            updateLastIdFromDom();
        } catch {
            // ignore
        }
        window.__forceNextChatScroll = true;
        try { __chatAutoScrollEnabled = true; } catch {}
        try { forceScrollToBottomNow(); } catch {}
    });

    // Explicit marker from server after a file upload; ensure the file chooser is cleared.
    document.body.addEventListener('chatFileUploaded', () => {
        ensureChatFeedVisible();
        resetComposerAfterSend();
    });

    (function initMentionAutocomplete() {
        const input = document.getElementById('id_body');
        const panel = document.getElementById('mention_panel');
        const list = document.getElementById('mention_list');
        const url = String(cfg.mentionSearchUrl || '');

        if (!input || !panel || !list) return;
        if (!url) return;

        let open = false;
        let activeIndex = 0;
        let results = [];
        let current = null; // { atIndex, caret }
        let debounceTimer = null;
        let abortController = null;

        function isOpen() {
            return open && !panel.classList.contains('hidden');
        }

        function close() {
            open = false;
            results = [];
            current = null;
            activeIndex = 0;
            panel.classList.add('hidden');
            list.innerHTML = '';
        }

        function show() {
            open = true;
            panel.classList.remove('hidden');
        }

        function getMentionContext() {
            const caret = input.selectionStart ?? (input.value || '').length;
            const before = (input.value || '').slice(0, caret);
            const atIndex = before.lastIndexOf('@');
            if (atIndex < 0) return null;
            if (atIndex > 0) {
                const prev = before[atIndex - 1];
                if (prev && !/\s/.test(prev)) return null;
            }
            const raw = before.slice(atIndex + 1);
            if (!raw) return null;
            if (/\s/.test(raw)) return null;
            if (!/^[A-Za-z0-9_.-]{1,32}$/.test(raw)) return null;
            return { atIndex, caret, q: raw };
        }

        function render() {
            if (!results.length) {
                close();
                return;
            }
            show();
            const safeIndex = Math.max(0, Math.min(activeIndex, results.length - 1));
            activeIndex = safeIndex;

            list.innerHTML = results
                .map((r, idx) => {
                    const active = idx === activeIndex;
                    const cls = active
                        ? 'bg-gray-800/80 text-white'
                        : 'hover:bg-gray-800/50 text-gray-200';
                    const avatar = r.avatar
                        ? `<img src="${r.avatar}" alt="" class="h-7 w-7 rounded-full border border-gray-800" />`
                        : `<div class="h-7 w-7 rounded-full border border-gray-800 bg-gray-800/70"></div>`;
                    const display = (r.display || r.username || '').toString();
                    const username = (r.username || '').toString();
                    return `
                            <button
                                type="button"
                                class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left ${cls}"
                                data-idx="${idx}"
                            >
                                ${avatar}
                                <div class="min-w-0">
                                    <div class="text-sm font-semibold truncate">${display}</div>
                                    <div class="text-[11px] text-gray-400 truncate">@${username}</div>
                                </div>
                            </button>
                        `;
                })
                .join('');
        }

        function insertMention(username) {
            if (!current || !username) return;
            const value = input.value || '';
            const before = value.slice(0, current.atIndex);
            const after = value.slice(current.caret);
            const insert = `@${username} `;
            input.value = before + insert + after;
            const nextPos = (before + insert).length;
            try { input.setSelectionRange(nextPos, nextPos); } catch (e) {}
            try { input.focus(); } catch (e) {}
            close();
        }

        async function fetchResults(q) {
            if (abortController) {
                try { abortController.abort(); } catch (e) {}
            }
            abortController = new AbortController();
            const resp = await fetch(`${url}?q=${encodeURIComponent(q)}`, {
                credentials: 'same-origin',
                signal: abortController.signal,
                headers: { 'Accept': 'application/json' },
            });
            if (!resp.ok) return [];
            const data = await resp.json();
            return Array.isArray(data && data.results) ? data.results : [];
        }

        function schedule() {
            const ctx = getMentionContext();
            if (!ctx) {
                close();
                return;
            }
            current = { atIndex: ctx.atIndex, caret: ctx.caret };
            const q = ctx.q;

            if (debounceTimer) window.clearTimeout(debounceTimer);
            debounceTimer = window.setTimeout(async () => {
                try {
                    const res = await fetchResults(q);
                    results = res || [];
                    activeIndex = 0;
                    render();
                } catch (e) {
                    // ignore abort/network errors
                }
            }, 150);
        }

        input.addEventListener('input', schedule);
        input.addEventListener('click', schedule);

        input.addEventListener('keydown', (e) => {
            if (!isOpen()) {
                if (e.key === 'Escape') close();
                return;
            }

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                activeIndex = Math.min(activeIndex + 1, results.length - 1);
                render();
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                activeIndex = Math.max(activeIndex - 1, 0);
                render();
                return;
            }
            if (e.key === 'Enter' || e.key === 'Tab') {
                const chosen = results[activeIndex];
                if (chosen && chosen.username) {
                    e.preventDefault();
                    insertMention(chosen.username);
                }
                return;
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                close();
            }
        });

        panel.addEventListener('click', (e) => {
            const btn = e.target && e.target.closest ? e.target.closest('button[data-idx]') : null;
            if (!btn) return;
            const idx = Number(btn.getAttribute('data-idx'));
            const chosen = results[idx];
            if (chosen && chosen.username) insertMention(chosen.username);
        });

        document.addEventListener('click', (e) => {
            const t = e.target;
            if (!t) return;
            if (panel.contains(t) || input.contains(t)) return;
            close();
        });
    })();

    // Realtime mute/cooldown lock for composer.
    let sendCooldownTimer = null;
    let __mutedComposerSavedValue = null;
    let __composerQuickActionsHiddenByMute = false;

    function __setComposerQuickActionsMuted(muted) {
        const emojiBtn = document.getElementById('emoji_btn');
        const gifBtn = document.getElementById('gif_btn');
        const emojiPanel = document.getElementById('emoji_panel');
        const gifPanel = document.getElementById('gif_panel');

        const hideBtn = (btn) => {
            if (!btn) return;
            try {
                btn.classList.add('hidden');
                btn.setAttribute('aria-hidden', 'true');
                btn.setAttribute('tabindex', '-1');
            } catch {
                // ignore
            }
        };

        const showBtnAnimated = (btn) => {
            if (!btn) return;
            try {
                btn.classList.remove('hidden');
                btn.classList.add('transition-all', 'duration-300', 'ease-out', 'opacity-0', 'scale-95', 'translate-y-1');
                btn.setAttribute('aria-hidden', 'false');
                btn.removeAttribute('tabindex');
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        try {
                            btn.classList.remove('opacity-0', 'scale-95', 'translate-y-1');
                            btn.classList.add('opacity-100', 'scale-100', 'translate-y-0');
                        } catch {
                            // ignore
                        }
                    });
                });

                window.setTimeout(() => {
                    try {
                        btn.classList.remove('transition-all', 'duration-300', 'ease-out', 'opacity-100', 'scale-100', 'translate-y-0');
                    } catch {
                        // ignore
                    }
                }, 360);
            } catch {
                // ignore
            }
        };

        if (muted) {
            __composerQuickActionsHiddenByMute = true;
            hideBtn(emojiBtn);
            hideBtn(gifBtn);

            try {
                if (emojiPanel) {
                    emojiPanel.classList.add('hidden', 'opacity-0', 'scale-95', 'pointer-events-none');
                    emojiPanel.classList.remove('opacity-100', 'scale-100');
                }
                if (gifPanel) {
                    gifPanel.classList.add('hidden', 'opacity-0', 'scale-95', 'pointer-events-none');
                    gifPanel.classList.remove('opacity-100', 'scale-100');
                }
                if (emojiBtn) emojiBtn.setAttribute('aria-expanded', 'false');
            } catch {
                // ignore
            }
            return;
        }

        if (!__composerQuickActionsHiddenByMute) return;
        __composerQuickActionsHiddenByMute = false;

        showBtnAnimated(emojiBtn);
        showBtnAnimated(gifBtn);
    }

    function __setMutedUiText(seconds) {
        const input = document.getElementById('id_body');
        const mutedRow = document.getElementById('chat_muted_row');
        const mutedText = document.getElementById('chat_muted_text');
        const s = Math.max(0, parseInt(seconds || 0, 10) || 0);
        const label = `You are muted for ${formatSeconds(s)}.`;
        if (mutedText) mutedText.textContent = label;
        if (mutedRow) mutedRow.classList.remove('hidden');
        if (input) input.value = label;
    }

    function __clearMutedUiText() {
        const input = document.getElementById('id_body');
        const mutedRow = document.getElementById('chat_muted_row');
        const mutedText = document.getElementById('chat_muted_text');
        if (mutedRow) mutedRow.classList.add('hidden');
        if (mutedText) mutedText.textContent = '';
        if (input) {
            if (__mutedComposerSavedValue !== null) input.value = __mutedComposerSavedValue;
            __mutedComposerSavedValue = null;
        }
    }

    function startSendCooldown(seconds) {
        const input = document.getElementById('id_body');
        const sendBtn = document.getElementById('chat_send_btn');
        const uploadBtn = document.getElementById('chat_upload_btn');
        const fileInput = document.getElementById('chat_file_input');
        if (!input || !sendBtn) return;

        const parsed = parseInt(seconds || 0, 10) || 0;
        if (sendCooldownTimer) {
            window.clearInterval(sendCooldownTimer);
            sendCooldownTimer = null;
        }

        if (parsed <= 0) {
            __clearMutedUiText();
            const verifyGate = document.getElementById('verify_gate');
            const verifyLocked = !!(verifyGate && !verifyGate.classList.contains('hidden'));
            const blockedBanner = document.getElementById('chat_blocked_banner');
            const stillBlocked = !!blockedBanner;
            if (!verifyLocked && !stillBlocked) {
                input.disabled = false;
                sendBtn.disabled = false;
                sendBtn.classList.remove('opacity-70', 'cursor-not-allowed');
                if (uploadBtn) {
                    uploadBtn.disabled = false;
                    uploadBtn.classList.remove('opacity-50', 'cursor-not-allowed');
                }
                if (fileInput) fileInput.disabled = false;
                __setComposerQuickActionsMuted(false);
                try { input.focus(); } catch {}
            }
            return;
        }

        if (__mutedComposerSavedValue === null) {
            __mutedComposerSavedValue = String(input.value || '');
        }

        let remaining = Math.max(1, parsed);
        input.disabled = true;
        sendBtn.disabled = true;
        sendBtn.classList.add('opacity-70', 'cursor-not-allowed');
        if (uploadBtn) {
            uploadBtn.disabled = true;
            uploadBtn.classList.add('opacity-50', 'cursor-not-allowed');
        }
        if (fileInput) fileInput.disabled = true;
        __setComposerQuickActionsMuted(true);

        const tick = () => {
            __setMutedUiText(remaining);
            remaining -= 1;
            if (remaining < 0) {
                startSendCooldown(0);
            }
        };

        tick();
        sendCooldownTimer = window.setInterval(tick, 1000);
    }

    // When a file is selected, switch the main form to upload mode.
    (function setupUploadModeSwitcher() {
        const msgForm = document.getElementById('chat_message_form');
        const fileInput = document.getElementById('chat_file_input');
        const uploadBtn = document.getElementById('chat_upload_btn');
        const captionInput = document.getElementById('chat_file_caption');
        const oneTimeInput = document.getElementById('chat_one_time_seconds');
        const msgInput = (msgForm && msgForm.querySelector('[name="body"]')) || document.getElementById('id_body');

        const modal = document.getElementById('upload_modal');
        const modalBackdrop = document.getElementById('upload_modal_backdrop');
        const modalPanel = document.getElementById('upload_modal_panel');
        const modalClose = document.getElementById('upload_modal_close');
        const modalCancel = document.getElementById('upload_modal_cancel');
        const modalSend = document.getElementById('upload_modal_send');
        const modalImg = document.getElementById('upload_modal_img');
        const modalVideo = document.getElementById('upload_modal_video');
        const modalCaption = document.getElementById('upload_modal_caption');
        const modalHint = document.getElementById('upload_modal_hint');

        const oneTimeBtn = document.getElementById('upload_one_time_btn');
        const oneTimePanel = document.getElementById('upload_one_time_panel');
        const oneTimeBadge = document.getElementById('upload_one_time_badge');

        if (!msgForm || !fileInput) return;

        function __insertNewlineAtCursor(el) {
            try {
                if (!el) return;
                const v = String(el.value ?? '');
                const start = (typeof el.selectionStart === 'number') ? el.selectionStart : v.length;
                const end = (typeof el.selectionEnd === 'number') ? el.selectionEnd : v.length;
                const before = v.slice(0, start);
                const after = v.slice(end);
                el.value = before + "\n" + after;
                const next = start + 1;
                try { el.setSelectionRange(next, next); } catch {}
            } catch {
                // ignore
            }
        }

        let cropper = null;
        let previewUrl = null;
        let modalOpen = false;

        function animateModalOpen() {
            if (!modal) return;
            if (modalBackdrop) {
                modalBackdrop.classList.remove('opacity-100');
                modalBackdrop.classList.add('opacity-0');
            }
            if (modalPanel) {
                modalPanel.classList.remove('opacity-100', 'translate-y-0', 'scale-100');
                modalPanel.classList.add('opacity-0', 'translate-y-3', 'scale-[0.98]');
            }

            modal.classList.remove('hidden');
            window.requestAnimationFrame(() => {
                window.requestAnimationFrame(() => {
                    if (!modalOpen) return;
                    if (modalBackdrop) {
                        modalBackdrop.classList.remove('opacity-0');
                        modalBackdrop.classList.add('opacity-100');
                    }
                    if (modalPanel) {
                        modalPanel.classList.remove('opacity-0', 'translate-y-3', 'scale-[0.98]');
                        modalPanel.classList.add('opacity-100', 'translate-y-0', 'scale-100');
                    }
                });
            });
        }

        function cleanupCropper() {
            if (cropper) {
                try { cropper.destroy(); } catch {}
                cropper = null;
            }
        }

        function cleanupPreviewUrl() {
            if (previewUrl) {
                try { URL.revokeObjectURL(previewUrl); } catch {}
                previewUrl = null;
            }
        }

        function clearSelectedFile() {
            try { fileInput.value = ''; } catch {}
        }

        function closeOneTimePanel() {
            if (!oneTimePanel) return;
            oneTimePanel.classList.add('opacity-0', 'scale-95', 'pointer-events-none');
            oneTimePanel.classList.remove('opacity-100', 'scale-100', 'pointer-events-auto');
            window.setTimeout(() => {
                try { oneTimePanel.classList.add('hidden'); } catch {}
            }, 160);
        }

        function openOneTimePanel() {
            if (!oneTimePanel) return;
            oneTimePanel.classList.remove('hidden');
            // next tick for transition
            window.requestAnimationFrame(() => {
                oneTimePanel.classList.remove('opacity-0', 'scale-95', 'pointer-events-none');
                oneTimePanel.classList.add('opacity-100', 'scale-100', 'pointer-events-auto');
            });
        }

        function setOneTimeSeconds(raw) {
            const v = (raw === null || raw === undefined) ? '' : String(raw).trim();
            if (oneTimeInput) oneTimeInput.value = v;
            if (oneTimeBadge) {
                if (v) {
                    oneTimeBadge.textContent = `1× ${v}s`;
                    oneTimeBadge.classList.remove('hidden');
                } else {
                    oneTimeBadge.classList.add('hidden');
                    oneTimeBadge.textContent = '1×';
                }
            }
        }

        function setOneTimeEnabled(enabled) {
            if (!oneTimeBtn) return;
            oneTimeBtn.disabled = !enabled;
            oneTimeBtn.classList.toggle('opacity-50', !enabled);
            oneTimeBtn.classList.toggle('cursor-not-allowed', !enabled);
            if (!enabled) closeOneTimePanel();
            if (!enabled) setOneTimeSeconds('');
        }

        function closeModal(opts) {
            const options = opts || {};
            modalOpen = false;
            closeOneTimePanel();
            cleanupCropper();
            cleanupPreviewUrl();
            if (modalImg) {
                modalImg.classList.add('hidden');
                try { modalImg.removeAttribute('src'); } catch {}
            }
            if (modalVideo) {
                modalVideo.classList.add('hidden');
                try { modalVideo.pause(); } catch {}
                try { modalVideo.removeAttribute('src'); } catch {}
                try { modalVideo.load(); } catch {}
            }
            if (modalHint) modalHint.textContent = '';
            if (modalBackdrop) {
                modalBackdrop.classList.remove('opacity-100');
                modalBackdrop.classList.add('opacity-0');
            }
            if (modalPanel) {
                modalPanel.classList.remove('opacity-100', 'translate-y-0', 'scale-100');
                modalPanel.classList.add('opacity-0', 'translate-y-3', 'scale-[0.98]');
            }
            if (modal) modal.classList.add('hidden');

            if (options.clearFile) {
                if (captionInput) captionInput.value = '';
                if (oneTimeInput) oneTimeInput.value = '';
                clearSelectedFile();
            }
        }

        function openModalWithFile(file) {
            if (!modal || !modalImg || !modalVideo || !modalCaption || !modalSend) return;
            if (!file) return;
            if (fileInput.disabled) return;

            modalOpen = true;
            cleanupCropper();
            cleanupPreviewUrl();
            if (modalHint) modalHint.textContent = '';

            // Default to off for each new preview.
            setOneTimeSeconds('');

            // Prefill caption from existing caption or from message body (matches previous behavior).
            const existingCap = (captionInput && captionInput.value ? String(captionInput.value) : '').trim();
            const bodyText = (msgInput && msgInput.value ? String(msgInput.value) : '').trim();
            if (modalCaption) {
                if (existingCap) modalCaption.value = existingCap.slice(0, 300);
                else if (bodyText) modalCaption.value = bodyText.slice(0, 300);
                else modalCaption.value = '';
            }

            previewUrl = URL.createObjectURL(file);

            const isImage = /^image\//i.test(file.type || '');
            const isVideo = /^video\//i.test(file.type || '');

            setOneTimeEnabled(!!isImage);

            if (isImage) {
                modalVideo.classList.add('hidden');
                try { modalVideo.removeAttribute('src'); } catch {}
                modalImg.classList.remove('hidden');
                modalImg.src = previewUrl;

                const enableCrop = !!window.Cropper;
                if (enableCrop) {
                    modalImg.onload = () => {
                        try {
                            cleanupCropper();
                            cropper = new window.Cropper(modalImg, {
                                viewMode: 1,
                                dragMode: 'move',
                                autoCropArea: 1,
                                responsive: true,
                                background: false,
                            });
                            if (modalHint) modalHint.textContent = 'Drag to crop, pinch/scroll to zoom.';
                        } catch {
                            cropper = null;
                        }
                    };
                } else {
                    if (modalHint) modalHint.textContent = 'Cropping unavailable (failed to load). Sending original image.';
                }
            } else if (isVideo) {
                cleanupCropper();
                modalImg.classList.add('hidden');
                try { modalImg.removeAttribute('src'); } catch {}
                modalVideo.classList.remove('hidden');
                modalVideo.src = previewUrl;
                if (modalHint) modalHint.textContent = 'Video preview.';
            } else {
                // Unknown type; just allow send (server will validate).
                cleanupCropper();
                modalImg.classList.add('hidden');
                modalVideo.classList.add('hidden');
                if (modalHint) modalHint.textContent = 'Preview unavailable for this file type.';
            }

            animateModalOpen();
        }

        // Caption box: Shift+Enter should always create a new line.
        try {
            if (modalCaption) {
                modalCaption.addEventListener('keydown', (e) => {
                    if (!e || e.key !== 'Enter') return;
                    if (!e.shiftKey) return;
                    if (e.isComposing) return;
                    try { e.preventDefault(); } catch {}
                    try { e.stopPropagation(); } catch {}
                    __insertNewlineAtCursor(modalCaption);
                });
            }
        } catch {
            // ignore
        }

        function syncUploadMode() {
            const hasFile = !!(fileInput.files && fileInput.files.length);
            if (!hasFile) {
                if (captionInput) captionInput.value = '';
                return;
            }

            // Open preview modal on selection (once).
            if (!modalOpen) {
                try {
                    const f = fileInput.files[0];
                    openModalWithFile(f);
                } catch {
                    // ignore
                }
            }
        }

        window.__syncUploadMode = syncUploadMode;

        if (uploadBtn) {
            uploadBtn.addEventListener('click', (e) => {
                e.preventDefault();
                if (fileInput && !fileInput.disabled) {
                    try { fileInput.click(); } catch (err) {}
                }
            });
        }
        fileInput.addEventListener('change', syncUploadMode);
        syncUploadMode();

        // Modal controls (optional, only when uploads_allowed)
        function handleCancel() {
            closeModal({ clearFile: true });
        }

        async function handleSend() {
            if (!fileInput || !fileInput.files || !fileInput.files.length) {
                closeModal({ clearFile: true });
                return;
            }

            const file = fileInput.files[0];
            const cap = (modalCaption && modalCaption.value ? String(modalCaption.value) : '').trim().slice(0, 300);
            if (captionInput) captionInput.value = cap;

            const isImage = /^image\//i.test(file.type || '');
            if (isImage && cropper && typeof cropper.getCroppedCanvas === 'function') {
                const canvas = cropper.getCroppedCanvas({
                    // Keep output reasonable; server also enforces size.
                    maxWidth: 1600,
                    maxHeight: 1600,
                    imageSmoothingEnabled: true,
                    imageSmoothingQuality: 'high',
                });

                if (canvas && typeof canvas.toBlob === 'function') {
                    const mime = (file.type && /^image\/(png|jpeg|webp)$/i.test(file.type)) ? file.type : 'image/jpeg';
                    const blob = await new Promise((resolve) => {
                        try {
                            canvas.toBlob((b) => resolve(b || null), mime, 0.92);
                        } catch {
                            resolve(null);
                        }
                    });
                    if (blob) {
                        try {
                            const dt = new DataTransfer();
                            const safeName = (file.name || 'upload').replace(/\s+/g, '_');
                            dt.items.add(new File([blob], safeName, { type: blob.type || mime }));
                            fileInput.files = dt.files;
                        } catch {
                            // If DataTransfer isn't supported, fall back to original file.
                        }
                    }
                }
            }

            closeModal({ clearFile: false });
            try {
                if (typeof msgForm.requestSubmit === 'function') msgForm.requestSubmit();
                else msgForm.submit();
            } catch {
                // ignore
            }
        }

        function wireModal() {
            if (!modal) return;

            if (oneTimeBtn && oneTimePanel) {
                oneTimeBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    if (oneTimeBtn.disabled) return;
                    const isHidden = oneTimePanel.classList.contains('hidden');
                    if (isHidden) openOneTimePanel();
                    else closeOneTimePanel();
                });

                oneTimePanel.addEventListener('click', (e) => {
                    const btn = e.target && e.target.closest ? e.target.closest('[data-one-time-seconds]') : null;
                    if (!btn) return;
                    const s = btn.getAttribute('data-one-time-seconds');
                    // Only allow the fixed options (plus off).
                    const allowed = new Set(['', '3', '8', '15']);
                    const next = allowed.has(String(s || '')) ? String(s || '') : '';
                    setOneTimeSeconds(next);
                    closeOneTimePanel();
                    if (modalHint) {
                        if (next) modalHint.textContent = `One-time view enabled (${next}s). Recipient can open once.`;
                        else modalHint.textContent = '';
                    }
                });

                // Close panel when clicking outside.
                document.addEventListener('click', (e) => {
                    if (!modalOpen) return;
                    if (oneTimePanel.classList.contains('hidden')) return;
                    const inside = (e.target && e.target.closest) ? e.target.closest('#upload_one_time_panel, #upload_one_time_btn') : null;
                    if (!inside) closeOneTimePanel();
                }, true);
            }

            if (modalBackdrop) {
                modalBackdrop.addEventListener('click', (e) => {
                    e.preventDefault();
                    handleCancel();
                });
            }
            if (modalClose) modalClose.addEventListener('click', (e) => { e.preventDefault(); handleCancel(); });
            if (modalCancel) modalCancel.addEventListener('click', (e) => { e.preventDefault(); handleCancel(); });
            if (modalSend) modalSend.addEventListener('click', (e) => { e.preventDefault(); handleSend(); });

            document.addEventListener('keydown', (e) => {
                if (e.key !== 'Escape') return;
                if (!modalOpen) return;
                handleCancel();
            });
        }

        wireModal();
    })();

    // --- Link policy (links only allowed in private chats) ---
    const __linksAllowed = !!cfg.linksAllowed;
    const __gifsAllowed = !!cfg.gifsAllowed;
    function __containsLink(text) {
        const s = (text || '').trim();
        if (!s) return false;
        // Catch http(s)://, www., and bare domains with a TLD.
        const schemeOrWww = /\b(?:https?:\/\/|www\.)[^\s<>"']+/i;
        if (schemeOrWww.test(s)) return true;
        const bare = /\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,})(?:\/[\S]*)?/i;
        const m = s.match(bare);
        if (!m) return false;
        return /[a-z]/i.test(m[0]);
    }

    function __isGifMessage(text) {
        const s = String(text || '').trim();
        if (!__gifsAllowed) return false;
        if (!s.startsWith('[GIF]')) return false;
        const url = s.slice(5).trim();
        if (!(url.startsWith('http://') || url.startsWith('https://'))) return false;
        return /giphy\.com|giphyusercontent\.com/i.test(url);
    }

    function __giphyMp4Url(url) {
        const s = String(url || '').trim();
        if (!s) return '';
        const parts = s.split('?');
        const base = parts[0] || '';
        const q = parts.length > 1 ? ('?' + parts.slice(1).join('?')) : '';
        if (/\.gif$/i.test(base)) return base.replace(/\.gif$/i, '.mp4') + q;
        return base + q;
    }

    function __giphyStillUrl(url) {
        const s = String(url || '').trim();
        if (!s) return '';
        const parts = s.split('?');
        const base = parts[0] || '';
        const q = parts.length > 1 ? ('?' + parts.slice(1).join('?')) : '';
        if (/\/giphy\.gif$/i.test(base)) return base.replace(/\/giphy\.gif$/i, '/giphy_s.gif') + q;
        // 200w.gif -> 200w_s.gif
        if (/\/\d+w\.gif$/i.test(base)) return base.replace(/\/(\d+w)\.gif$/i, '/$1_s.gif') + q;
        return base + q;
    }

    function __popup(title, message) {
        if (typeof window.__openConfirm === 'function') {
            window.__openConfirm({
                title: title || 'Notice',
                message: message || '',
                showCancel: false,
                okText: 'OK',
            });
        } else {
            alert(message || '');
        }
    }

    // Instant popup + cancel request if user tries to send links in non-private chats.
    document.body.addEventListener('htmx:beforeRequest', (event) => {
        const form = document.getElementById('chat_message_form');
        if (!form) return;
        if (event.target !== form) return;
        if (__linksAllowed) return;

        const fileInput = document.getElementById('chat_file_input');
        const inUploadMode = !!(fileInput && fileInput.files && fileInput.files.length);
        const bodyInput = document.getElementById('id_body');
        const captionInput = document.getElementById('chat_file_caption');
        const text = inUploadMode ? (captionInput && captionInput.value) : (bodyInput && bodyInput.value);

        if (__containsLink(text || '') && !__isGifMessage(text || '')) {
            event.preventDefault();
            event.stopPropagation();
            __popup('Links not allowed', 'Sending links is only allowed in private chats.');
        }
    }, true);

    // If server blocks links (HX-Trigger), show popup.
    document.body.addEventListener('linksNotAllowed', (e) => {
        const reason = (e && e.detail && e.detail.reason) ? e.detail.reason : 'Links are only allowed in private chats.';
        __popup('Links not allowed', reason);
    });

    // Confirm before opening external links.
    document.addEventListener('click', (e) => {
        const a = e.target && e.target.closest ? e.target.closest('a') : null;
        if (!a) return;
        const href = a.getAttribute('href') || '';
        if (!(href.startsWith('http://') || href.startsWith('https://'))) return;

        e.preventDefault();
        e.stopPropagation();

        const openLink = () => {
            try {
                window.open(href, '_blank', 'noopener');
            } catch {
                window.location.href = href;
            }
        };

        if (typeof window.__openConfirm === 'function') {
            window.__openConfirm({
                title: 'Open link?',
                message: 'Are you sure you want to open this link?',
                okText: 'Open',
                cancelText: 'Cancel',
                showCancel: true,
                onConfirm: openLink,
            });
        } else {
            if (confirm('Are you sure you want to open this link?')) openLink();
        }
    }, true);

    const initialMuted = Number(cfg.chatMutedSeconds || 0);
    if (Number.isFinite(initialMuted) && initialMuted > 0) {
        startSendCooldown(initialMuted);
    }

    const otherUsername = String(cfg.otherUsername || '');
    const meDisplayName = String(cfg.meDisplayName || '');
    const meAvatarUrl = String(cfg.meAvatarUrl || '');
    const otherDisplayName = String(cfg.otherDisplayName || '');
    const otherAvatarUrl = String(cfg.otherAvatarUrl || '');
    const callEventUrl = String(cfg.callEventUrl || '');
    const messageEditUrlTemplate = String(cfg.messageEditUrlTemplate || '');
    const messageDeleteUrlTemplate = String(cfg.messageDeleteUrlTemplate || '');
    const messageReactUrlTemplate = String(cfg.messageReactUrlTemplate || '');

    // -------- Ringtone (incoming) --------
    let audioCtx = null;
    let ringTimer = null;
    let audioUnlocked = false;

    function unlockAudioOnce() {
        if (audioUnlocked) return;
        try {
            audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
            // create a tiny silent buffer to unlock
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
    }

    document.addEventListener('click', unlockAudioOnce, { once: true, capture: true });

    function stopIncomingRing() {
        if (ringTimer) {
            clearInterval(ringTimer);
            ringTimer = null;
        }
    }

    function playIncomingRing() {
        // Browsers may block until user interacts; we try best-effort.
        try {
            audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
            if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
        } catch {
            return;
        }

        stopIncomingRing();

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

        // Classic ring cadence: ring ~2s, pause ~3s
        ringOnce();
        ringTimer = setInterval(ringOnce, 5000);
    }

    const form = document.getElementById('chat_message_form');
    const input = document.getElementById('id_body');
    const typedMsInput = document.getElementById('typed_ms');
    const messagesEl = document.getElementById('chat_messages');
    const loadOlderBtn = document.getElementById('chat_load_older');
    const loadOlderWrap = document.getElementById('chat_load_older_wrap');
    const onlineCountEl = document.getElementById('room-online-count');
    const onlineCountMirrors = Array.from(document.querySelectorAll('[data-online-count-mirror]'));

    let __loadingOlder = false;

    async function loadOlderMessages() {
        if (!olderUrl || !messagesEl || __loadingOlder) return;

        const first = messagesEl.firstElementChild;
        const beforeId = first && first.dataset ? (parseInt(first.dataset.messageId || '0', 10) || 0) : 0;
        if (!beforeId) {
            try { if (loadOlderWrap) loadOlderWrap.style.display = 'none'; } catch {}
            return;
        }

        __loadingOlder = true;
        const prevText = loadOlderBtn ? loadOlderBtn.textContent : '';
        try {
            if (loadOlderBtn) {
                loadOlderBtn.disabled = true;
                loadOlderBtn.textContent = 'Loading…';
            }

            const chatContainer = document.getElementById('chat_container');
            const prevScrollHeight = chatContainer ? chatContainer.scrollHeight : 0;
            const prevScrollTop = chatContainer ? chatContainer.scrollTop : 0;

            const res = await fetch(`${olderUrl}?before=${beforeId}`, {
                method: 'GET',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
            });
            if (!res.ok) throw new Error('history_fetch_failed');

            const data = await res.json();
            const html = data && typeof data.messages_html === 'string' ? data.messages_html : '';
            if (html) {
                messagesEl.insertAdjacentHTML('afterbegin', html);
                try { hydrateLocalTimes(messagesEl); } catch {}
                try { applyConsecutiveHeaderGrouping(messagesEl); } catch {}

                // Preserve viewport position when prepending.
                if (chatContainer) {
                    const newScrollHeight = chatContainer.scrollHeight;
                    const delta = newScrollHeight - prevScrollHeight;
                    chatContainer.scrollTop = prevScrollTop + (delta > 0 ? delta : 0);
                }
            }

            const hasMore = !!(data && data.has_more);
            if (!hasMore) {
                try { if (loadOlderWrap) loadOlderWrap.style.display = 'none'; } catch {}
            }
        } catch {
            // ignore
        } finally {
            __loadingOlder = false;
            try {
                if (loadOlderBtn) {
                    loadOlderBtn.disabled = false;
                    loadOlderBtn.textContent = prevText || 'Load older';
                }
            } catch {
                // ignore
            }
        }
    }

    (function initLoadOlder() {
        if (!loadOlderBtn) return;
        loadOlderBtn.addEventListener('click', (e) => {
            try { e.preventDefault(); } catch {}
            loadOlderMessages();
        });
    })();

    function __setOnlineCount(v) {
        const val = (v === undefined || v === null) ? '' : String(v);
        try { if (onlineCountEl) onlineCountEl.textContent = val; } catch {}
        for (const el of onlineCountMirrors) {
            try { el.textContent = val; } catch {}
        }
    }

    // If HTMX swaps #room-online-count out-of-band, keep mirrors synced.
    try {
        if (onlineCountEl && typeof MutationObserver !== 'undefined') {
            const obs = new MutationObserver(() => {
                try { __setOnlineCount(onlineCountEl.textContent || ''); } catch {}
            });
            obs.observe(onlineCountEl, { characterData: true, childList: true, subtree: true });
        }
    } catch {}

    // Chat input behavior:
    // - Enter: send
    // - Shift+Enter: new line
    // Note: when the mention panel is open, Enter is used to select a mention.
    if (form && input) {
        function __insertNewlineAtCursor(el) {
            try {
                if (!el) return;
                const v = String(el.value ?? '');
                const start = (typeof el.selectionStart === 'number') ? el.selectionStart : v.length;
                const end = (typeof el.selectionEnd === 'number') ? el.selectionEnd : v.length;
                const before = v.slice(0, start);
                const after = v.slice(end);
                el.value = before + "\n" + after;
                const next = start + 1;
                try { el.setSelectionRange(next, next); } catch {}
            } catch {
                // ignore
            }
        }

        function autoGrowChatInput() {
            try {
                if (!input || input.tagName !== 'TEXTAREA') return;
                // Reset then grow to fit content; cap height to avoid taking over the screen.
                input.style.height = 'auto';
                const maxPx = 180;
                const next = Math.min(maxPx, Math.max(0, input.scrollHeight || 0));
                input.style.height = (next > 0 ? next : 0) + 'px';
                input.style.overflowY = (input.scrollHeight > maxPx) ? 'auto' : 'hidden';
            } catch (err) {
                // ignore
            }
        }

        // Run once on load (helps when restoring draft / browser autofill).
        autoGrowChatInput();

        input.addEventListener('input', function () {
            autoGrowChatInput();
        });

        input.addEventListener('keydown', function (e) {
            if (e.key !== 'Enter') return;
            if (e.isComposing) return;

            // Ensure Shift+Enter always creates a new line (even if another handler prevents default).
            if (e.shiftKey) {
                try { e.preventDefault(); } catch {}
                try { e.stopPropagation(); } catch {}
                __insertNewlineAtCursor(input);
                autoGrowChatInput();
                return;
            }

            const mentionPanel = document.getElementById('mention_panel');
            const mentionOpen = !!(mentionPanel && !mentionPanel.classList.contains('hidden'));
            if (mentionOpen) return;

            e.preventDefault();
            try {
                if (typeof form.requestSubmit === 'function') {
                    form.requestSubmit();
                } else {
                    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
                }
            } catch (err) {
                // ignore
            }
        });

        // Expose for composer reset after send.
        try { window.__autoGrowChatInput = autoGrowChatInput; } catch {}
    }

    const replyBar = document.getElementById('reply_bar');
    const replyBarAuthor = document.getElementById('reply_bar_author');
    const replyBarPreview = document.getElementById('reply_bar_preview');
    const replyBarCancel = document.getElementById('reply_bar_cancel');
    const replyToIdInput = document.getElementById('reply_to_id');

    const editBar = document.getElementById('edit_bar');
    const editBarPreview = document.getElementById('edit_bar_preview');
    const editBarCancel = document.getElementById('edit_bar_cancel');
    let editingMessageId = null;

    function startEditingMessage(messageId, body) {
        if (!input) return;
        editingMessageId = messageId;
        if (replyToIdInput) replyToIdInput.value = '';
        if (replyBar) replyBar.classList.add('hidden');

        if (editBarPreview) editBarPreview.textContent = (body || '').slice(0, 120);
        if (editBar) editBar.classList.remove('hidden');

        input.value = body || '';
        input.focus();
    }

    function cancelEditingMessage() {
        editingMessageId = null;
        if (editBar) editBar.classList.add('hidden');
        if (editBarPreview) editBarPreview.textContent = '';
    }

    if (editBarCancel) {
        editBarCancel.addEventListener('click', function () {
            cancelEditingMessage();
        });
    }

    const typingIndicatorEl = document.getElementById('typing_indicator');
    const typingIndicatorTextEl = document.getElementById('typing_indicator_text');
    const typingUsers = new Map();
    const typingTimers = new Map();
    let typingStopTimer = null;
    let lastTypingPingAt = 0;

    function renderTypingIndicator() {
        if (!typingIndicatorEl || !typingIndicatorTextEl) return;
        const names = Array.from(typingUsers.values()).filter(Boolean);
        if (!names.length) {
            typingIndicatorEl.classList.add('hidden');
            typingIndicatorTextEl.textContent = '';
            return;
        }
        const visibleNames = names.slice(0, 3);
        const extraTypingCount = Math.max(0, names.length - visibleNames.length);
        typingIndicatorEl.classList.remove('hidden');
        typingIndicatorTextEl.textContent = extraTypingCount > 0
            ? `${visibleNames.join(', ')} +${extraTypingCount} typing...`
            : `${visibleNames.join(', ')} typing...`;
    }

    function handleTypingEvent(payload) {
        const authorId = payload.author_id;
        if (!authorId) return;

        const username = (payload.username || '').trim();
        const isTyping = !!payload.is_typing;

        if (typingTimers.has(authorId)) {
            clearTimeout(typingTimers.get(authorId));
            typingTimers.delete(authorId);
        }

        if (isTyping) {
            typingUsers.set(authorId, username);
            typingTimers.set(authorId, setTimeout(() => {
                typingUsers.delete(authorId);
                typingTimers.delete(authorId);
                renderTypingIndicator();
            }, 4000));
        } else {
            typingUsers.delete(authorId);
        }

        renderTypingIndicator();
    }

    function sendTyping(isTyping) {
        try {
            if (!socket || socket.readyState !== WebSocket.OPEN) return;
            socket.send(JSON.stringify({ type: 'typing', is_typing: !!isTyping }));
        } catch {
            // ignore
        }
    }

    if (input) {
        let typingStartedAt = null;
        input.addEventListener('input', () => {
            if (typingStartedAt === null && (input.value || '').trim().length > 0) {
                typingStartedAt = Date.now();
            }
            const now = Date.now();
            if (now - lastTypingPingAt > 1200) {
                sendTyping(true);
                lastTypingPingAt = now;
            }
            if (typingStopTimer) clearTimeout(typingStopTimer);
            typingStopTimer = setTimeout(() => {
                sendTyping(false);
                typingStopTimer = null;
            }, 1800);
        });

        input.addEventListener('blur', () => {
            if (typingStopTimer) clearTimeout(typingStopTimer);
            typingStopTimer = null;
            sendTyping(false);
        });

        document.body.addEventListener('htmx:beforeRequest', (event) => {
            if (!form || event.target !== form) return;
            if (!typedMsInput) return;
            if (typingStartedAt === null) {
                typedMsInput.value = '';
                return;
            }
            const ms = Math.max(0, Date.now() - typingStartedAt);
            typedMsInput.value = String(ms);
        });

        document.body.addEventListener('htmx:afterRequest', (event) => {
            if (!form || event.target !== form) return;
            if (!event.detail.successful) return;
            typingStartedAt = null;
            if (typedMsInput) typedMsInput.value = '';
        });
    }

    if (form) {
        // Capture submit before HTMX when editing.
        form.addEventListener('submit', async (e) => {
            if (!editingMessageId) return;
            e.preventDefault();
            e.stopPropagation();

            const body = (input && input.value ? input.value : '').trim();
            if (!body) return;

            const url = messageEditUrlTemplate.replace('/0/', `/${editingMessageId}/`);
            try {
                const params = new URLSearchParams();
                params.set('body', body);
                await fetch(url, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': (typeof getCookie === 'function' ? getCookie('csrftoken') : ''),
                    },
                    body: params,
                });
            } catch {
                // ignore
            }

            cancelEditingMessage();
            if (input) input.value = '';
            try {
                if (typeof window.__autoGrowChatInput === 'function') {
                    window.__autoGrowChatInput();
                }
            } catch {}
            if (__chatAutoScrollEnabled) forceScrollToBottomNow();
        }, true);

        // For normal text messages, prefer WebSocket for instant send.
        // Keep HTMX submit for file uploads and as a fallback when WS isn't connected.
        form.addEventListener('submit', async (e) => {
            if (editingMessageId) return;

            const fileInput = document.getElementById('chat_file_input');
            const inUploadMode = !!(fileInput && fileInput.files && fileInput.files.length);
            if (inUploadMode) return;

            const hasHtmx = !!(window.htmx && typeof window.htmx === 'object');
            const wsOk = !!(socket && socket.readyState === WebSocket.OPEN && wsConnected);

            // If HTMX isn't available (e.g., CDN blocked/offline) and WS isn't connected,
            // fall back to a direct AJAX POST that mimics an HTMX request.
            if (!wsOk && !hasHtmx) {
                e.preventDefault();
                e.stopPropagation();
                try { e.stopImmediatePropagation(); } catch {}

                const sendBtn = document.getElementById('chat_send_btn');
                if (sendBtn) {
                    sendBtn.disabled = true;
                    sendBtn.classList.add('opacity-70', 'cursor-not-allowed');
                }

                try {
                    const url = form.getAttribute('hx-post') || form.getAttribute('action') || window.location.pathname;
                    const fd = new FormData(form);

                    const res = await fetch(url, {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {
                            'HX-Request': 'true',
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                        body: fd,
                    });

                    if (res.status === 429) {
                        const retry = parseInt(res.headers.get('Retry-After') || '0', 10) || 0;
                        if (typeof startSendCooldown === 'function') startSendCooldown(retry || 10);
                        if (typeof __popup === 'function') {
                            __popup('Slow down', retry ? `Please wait ${retry}s and try again.` : 'Please wait and try again.');
                        }
                        return;
                    }

                    if (res.status === 403) {
                        if (typeof __popup === 'function') {
                            __popup('Not allowed', 'You cannot send messages right now.');
                        }
                        return;
                    }

                    const html = await res.text();
                    if (res.ok && html) {
                        const emptyEl = document.getElementById('empty_state');
                        if (emptyEl) emptyEl.remove();
                        if (messagesEl && messagesEl.classList.contains('hidden')) {
                            messagesEl.classList.remove('hidden');
                        }
                        if (messagesEl) {
                            messagesEl.insertAdjacentHTML('beforeend', html);
                            hydrateLocalTimes(messagesEl);
                            applyConsecutiveHeaderGrouping(messagesEl);
                            updateLastIdFromDom();
                        }
                        window.__forceNextChatScroll = true;
                        try { __chatAutoScrollEnabled = true; } catch {}
                        forceScrollToBottomNow();
                    }

                    // Reset UI after send
                    if (res.ok) {
                        resetComposerAfterSend();
                    }
                } catch {
                    // ignore
                } finally {
                    if (sendBtn) {
                        sendBtn.disabled = false;
                        sendBtn.classList.remove('opacity-70', 'cursor-not-allowed');
                    }
                }

                return;
            }

            if (!wsOk) return;

            const body = (input && input.value ? input.value : '').trim();
            if (!body) {
                e.preventDefault();
                e.stopPropagation();
                try { e.stopImmediatePropagation(); } catch {}
                return;
            }

            // Mirror the link policy UX when skipping HTMX.
            if (typeof __linksAllowed !== 'undefined' && typeof __containsLink === 'function') {
                const isGif = (typeof __isGifMessage === 'function') ? __isGifMessage(body) : false;
                if (!__linksAllowed && __containsLink(body) && !isGif) {
                    e.preventDefault();
                    e.stopPropagation();
                    try { e.stopImmediatePropagation(); } catch {}
                    if (typeof __popup === 'function') {
                        __popup('Links not allowed', 'Sending links is only allowed in private chats.');
                    }
                    return;
                }
            }

            e.preventDefault();
            e.stopPropagation();
            try { e.stopImmediatePropagation(); } catch {}

            const payload = {
                body: body,
            };
            try {
                const replyToId = replyToIdInput ? (replyToIdInput.value || '').trim() : '';
                if (replyToId) payload.reply_to_id = replyToId;
                const typedMs = typedMsInput ? (typedMsInput.value || '').trim() : '';
                if (typedMs) payload.typed_ms = typedMs;
            } catch {
                // ignore
            }

            const clientNonce = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
            payload.client_nonce = clientNonce;

            try {
                socket.send(JSON.stringify(payload));
            } catch {
                // If WS send fails, allow user to retry; don't fall back automatically.
                return;
            }

                        // Optimistic UI: show message instantly, then replace when server echoes back.
                        try {
                                const emptyEl = document.getElementById('empty_state');
                                if (emptyEl) emptyEl.remove();
                                if (messagesEl && messagesEl.classList.contains('hidden')) messagesEl.classList.remove('hidden');

                                const trimmed = String(body || '').trim();
                                const isGifMsg = trimmed.startsWith('[GIF]');
                                let bubbleInner = __escapeHtml(body).replace(/\n/g, '<br>');
                                if (isGifMsg) {
                                        const url = trimmed.slice(5).trim();
                                        if (url) {
                                        const safeUrl = __escapeHtml(url);
                                        const mp4 = __escapeHtml(__giphyMp4Url(url));
                                        const poster = __escapeHtml(__giphyStillUrl(url));
                                        bubbleInner = `<div class="w-full sm:w-auto max-w-full sm:max-w-72">
                  <video class="w-full h-auto rounded-lg bg-black/20" muted playsinline preload="metadata" poster="${poster}" data-gif-player data-gif-url="${safeUrl}" data-gif-loops="6">
                    <source src="${mp4}" type="video/mp4" />
                  </video>
                </div>`;
                                        }
                                }
                                const pendingHtml = `
<div data-pending="1" data-client-nonce="${clientNonce}" class="vixo-msg group relative w-full flex justify-end opacity-90">
    <div class="flex flex-col items-end max-w-[90%] sm:max-w-[75%] lg:max-w-[65%]">
        <div class="flex items-end gap-2">
            <div data-message-bubble class="relative px-3 py-2.5 rounded-2xl shadow-sm shadow-black/20 backdrop-blur-md bg-gradient-to-r from-purple-500 via-indigo-500 to-sky-500 text-white vixo-keep-white rounded-tr-none border border-white/10">
                <div class="text-[14px] sm:text-[15px] leading-relaxed text-white/95 vixo-keep-white">${bubbleInner}</div>
            </div>
        </div>
    </div>
</div>`;

                                messagesEl.insertAdjacentHTML('beforeend', pendingHtml);
                                const pendingEl = messagesEl.lastElementChild;
                                if (pendingEl) __pendingByNonce.set(clientNonce, pendingEl);
                        } catch {
                                // ignore
                        }

            // Flag for scroll on server echo (don't scroll twice on optimistic insert).
            window.__forceNextChatScroll = true;
            try { __chatAutoScrollEnabled = true; } catch {}

            // Reset UI immediately (HTMX won't run when we skip the submit).
            try {
                if (typingStopTimer) clearTimeout(typingStopTimer);
                typingStopTimer = null;
                sendTyping(false);
            } catch {
                // ignore
            }
            resetComposerAfterSend();
            // Don't auto-scroll here; we scroll once when the server echoes back.
        }, true);

        form.addEventListener('submit', () => {
            if (typingStopTimer) clearTimeout(typingStopTimer);
            typingStopTimer = null;
            sendTyping(false);
        });
    }

    let socket = null;
    let wsConnected = false;
    let lastId = 0;
    const __pendingByNonce = new Map();
    const __seenChatNonces = new Map();
    const __incomingRenderQueue = [];
    let __incomingRenderRaf = null;
    let __incomingRenderTimer = null;
    const __INCOMING_RENDER_BATCH_SIZE = 40;
    const __MAX_RENDERED_MESSAGES = 700;
    let __wsReconnectTimer = null;
    let __wsHeartbeatTimer = null;
    let __wsReconnectAttempt = 0;
    let __pollTimer = null;
    let __pollInFlight = false;
    const __WAITING_FOLLOW_SOUND_SRC = '/static/followsound.mp3';

    const __WS_HEARTBEAT_MS = 25_000;
    const __WS_RECONNECT_BASE_MS = 900;
    const __WS_RECONNECT_FACTOR = 1.7;
    const __WS_RECONNECT_MAX_MS = 30_000;

    function __stopWsHeartbeat() {
        try {
            if (__wsHeartbeatTimer) clearInterval(__wsHeartbeatTimer);
        } catch {
            // ignore
        }
        __wsHeartbeatTimer = null;
    }

    function __startWsHeartbeat() {
        __stopWsHeartbeat();
        __wsHeartbeatTimer = setInterval(() => {
            try {
                if (!socket || socket.readyState !== WebSocket.OPEN) return;
                // App-level ping; server responds with {type:'pong'}.
                socket.send(JSON.stringify({ type: 'ping' }));
            } catch {
                // ignore
            }
        }, __WS_HEARTBEAT_MS);
    }

    function playWaitingFollowSound() {
        try {
            const a = new Audio(__WAITING_FOLLOW_SOUND_SRC);
            a.preload = 'auto';
            a.muted = false;
            a.volume = 1.0;
            a.play().catch(() => {});
        } catch {
            // ignore
        }
    }

    function __scheduleWsReconnect() {
        if (__wsReconnectTimer) return;

        const attempt = Math.min(30, Math.max(0, __wsReconnectAttempt || 0));
        __wsReconnectAttempt = attempt + 1;

        let delay = Math.min(
            __WS_RECONNECT_MAX_MS,
            Math.round(__WS_RECONNECT_BASE_MS * Math.pow(__WS_RECONNECT_FACTOR, attempt))
        );

        // Add jitter (avoid thundering herd).
        const jitter = 0.7 + Math.random() * 0.6;
        delay = Math.round(delay * jitter);

        // When tab is hidden, browsers can heavily throttle timers; avoid tight loops.
        try {
            if (document.visibilityState === 'hidden') delay = Math.max(delay, 5000);
        } catch {
            // ignore
        }

        __wsReconnectTimer = setTimeout(() => {
            __wsReconnectTimer = null;
            connect();
        }, delay);
    }

    function __wsIsOpen() {
        try {
            return !!(socket && socket.readyState === WebSocket.OPEN);
        } catch {
            return false;
        }
    }

    function startPolling() {
        if (__pollTimer) return;
        __pollTimer = setInterval(poll, 3500);
    }

    function stopPolling() {
        if (!__pollTimer) return;
        try { clearInterval(__pollTimer); } catch {}
        __pollTimer = null;
    }

    function __pruneRenderedMessagesIfNeeded() {
        if (!messagesEl) return;
        const total = messagesEl.children ? messagesEl.children.length : 0;
        if (total <= __MAX_RENDERED_MESSAGES) return;

        const removeCount = total - __MAX_RENDERED_MESSAGES;
        if (removeCount <= 0) return;

        const chatContainer = document.getElementById('chat_container');
        const prevScrollHeight = chatContainer ? chatContainer.scrollHeight : 0;
        const prevScrollTop = chatContainer ? chatContainer.scrollTop : 0;

        let removed = 0;
        while (removed < removeCount && messagesEl.firstElementChild) {
            const node = messagesEl.firstElementChild;
            try {
                const nonce = node && node.dataset ? String(node.dataset.clientNonce || '').trim() : '';
                if (nonce) __pendingByNonce.delete(nonce);
            } catch {
                // ignore
            }
            try { node.remove(); } catch { break; }
            removed += 1;
        }

        if (!chatContainer || removed <= 0) return;

        try {
            const newScrollHeight = chatContainer.scrollHeight;
            const delta = Math.max(0, prevScrollHeight - newScrollHeight);
            if (delta > 0) {
                chatContainer.scrollTop = Math.max(0, prevScrollTop - delta);
            }
        } catch {
            // ignore
        }
    }

    function __flushAppendedHtmlChunk(htmlParts, insertedNodes) {
        if (!messagesEl || !Array.isArray(htmlParts) || !htmlParts.length) return;

        const beforeLast = messagesEl.lastElementChild;
        messagesEl.insertAdjacentHTML('beforeend', htmlParts.join(''));

        let cursor = beforeLast ? beforeLast.nextElementSibling : messagesEl.firstElementChild;
        while (cursor) {
            insertedNodes.push(cursor);
            cursor = cursor.nextElementSibling;
        }
        htmlParts.length = 0;
    }

    function __flushIncomingRenderQueue() {
        __incomingRenderRaf = null;
        if (__incomingRenderTimer) {
            try { clearTimeout(__incomingRenderTimer); } catch {}
            __incomingRenderTimer = null;
        }
        if (!messagesEl || !__incomingRenderQueue.length) return;

        const __wasNearBottom = isNearBottom();
        const insertedNodes = [];
        const appendHtmlParts = [];
        let forceScrollRequested = false;
        let shouldShowPrivateJump = false;
        let pendingChallengeState = null;
        let hadAnyMessageLikePayload = false;

        const maxTake = Math.min(__incomingRenderQueue.length, __INCOMING_RENDER_BATCH_SIZE);
        for (let i = 0; i < maxTake; i += 1) {
            const item = __incomingRenderQueue.shift();
            if (!item) continue;

            if (item.kind === 'append' && item.html) {
                appendHtmlParts.push(item.html);
                hadAnyMessageLikePayload = true;
                forceScrollRequested = forceScrollRequested || !!item.forceScroll;
                shouldShowPrivateJump = shouldShowPrivateJump || !!item.showPrivateJump;
                if (item.challengeState) pendingChallengeState = item.challengeState;
                continue;
            }

            if (item.kind === 'replace' && item.pendingEl && item.html) {
                __flushAppendedHtmlChunk(appendHtmlParts, insertedNodes);
                try {
                    item.pendingEl.style.visibility = 'hidden';
                    item.pendingEl.insertAdjacentHTML('afterend', item.html);
                    const inserted = item.pendingEl.nextElementSibling;
                    item.pendingEl.remove();
                    if (inserted) {
                        try { inserted.style.visibility = 'visible'; } catch {}
                        insertedNodes.push(inserted);
                    }
                } catch {
                    // ignore
                }

                hadAnyMessageLikePayload = true;
                forceScrollRequested = forceScrollRequested || !!item.forceScroll;
                shouldShowPrivateJump = shouldShowPrivateJump || !!item.showPrivateJump;
                if (item.challengeState) pendingChallengeState = item.challengeState;
            }
        }

        __flushAppendedHtmlChunk(appendHtmlParts, insertedNodes);

        if (hadAnyMessageLikePayload) {
            const emptyEl = document.getElementById('empty_state');
            if (emptyEl) emptyEl.remove();
            if (messagesEl.classList.contains('hidden')) messagesEl.classList.remove('hidden');
        }

        if (insertedNodes.length) {
            for (let i = 0; i < insertedNodes.length; i += 1) {
                const node = insertedNodes[i];
                try { hydrateLocalTimes(node); } catch {}
                try { applyConsecutiveHeaderGroupingWindow(node); } catch {}
            }
            updateLastIdFromDom();
            __pruneRenderedMessagesIfNeeded();
        }

        if (pendingChallengeState) {
            try { setChallengeState(pendingChallengeState); } catch {}
        }

        const shouldForce = forceScrollRequested || (!!__chatAutoScrollEnabled && __wasNearBottom);
        if (forceScrollRequested) {
            window.__forceNextChatScroll = false;
            __chatAutoScrollEnabled = true;
        }
        if (shouldForce) {
            forceScrollToBottomNow();
            __hidePrivateNewMsgJump();
        } else if (shouldShowPrivateJump) {
            __showPrivateNewMsgJump();
        }

        if (insertedNodes.length && document.visibilityState === 'visible') {
            sendReadAck(lastId);
        }

        if (__incomingRenderQueue.length) {
            __incomingRenderRaf = requestAnimationFrame(__flushIncomingRenderQueue);
        }
    }

    function __scheduleIncomingRenderFlush() {
        if (__incomingRenderRaf) return;
        __incomingRenderRaf = requestAnimationFrame(__flushIncomingRenderQueue);
        if (__incomingRenderTimer) {
            try { clearTimeout(__incomingRenderTimer); } catch {}
        }
        __incomingRenderTimer = setTimeout(() => {
            if (!__incomingRenderRaf) return;
            try { cancelAnimationFrame(__incomingRenderRaf); } catch {}
            __incomingRenderRaf = null;
            __flushIncomingRenderQueue();
        }, 48);
    }

    function __enqueueIncomingRender(item) {
        if (!item || !item.kind) return;
        __incomingRenderQueue.push(item);
        __scheduleIncomingRenderFlush();
    }

    // --- Challenges (private chats) ---
    let __challengeState = null;
    let __challengeTimer = null;
    let __challengePingTimer = null;

    function challengeKindLabel(kind) {
        const k = String(kind || '').toLowerCase();
        if (k === 'emoji_only') return 'Emoji-only';
        if (k === 'no_vowels') return 'No vowels';
        if (k === 'finish_meme') return 'Finish the meme';
        if (k === 'truth_or_dare') return 'Truth or dare';
        if (k === 'time_attack') return 'Time attack';
        return 'Challenge';
    }

    function challengeRuleShort(kind, prompt) {
        const k = String(kind || '').toLowerCase();
        if (k === 'emoji_only') return 'Only emojis allowed. Any other character = fail.';
        if (k === 'no_vowels') return 'No vowels (A,E,I,O,U). First vowel = fail.';
        if (k === 'time_attack') return 'Send the required number of messages before time runs out.';
        if (k === 'truth_or_dare') return 'Reply with a meaningful answer (truth) or follow the dare rule.';
        if (k === 'finish_meme') return 'First meaningful reply wins.';
        return String(prompt || '');
    }

    function formatSeconds(sec) {
        const s = Math.max(0, parseInt(sec || 0, 10) || 0);
        const m = Math.floor(s / 60);
        const r = s % 60;
        return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`;
    }

    function __showAnimated(el, fromClasses) {
        if (!el) return;
        if (!el.classList.contains('hidden')) {
            // Ensure we don't get stuck in the "from" state.
            for (const c of fromClasses) el.classList.remove(c);
            return;
        }
        el.classList.remove('hidden');
        for (const c of fromClasses) el.classList.add(c);
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                for (const c of fromClasses) el.classList.remove(c);
            });
        });
    }

    function __hideAnimated(el, toClasses, ms = 200) {
        if (!el || el.classList.contains('hidden')) return;
        for (const c of toClasses) el.classList.add(c);
        window.setTimeout(() => {
            el.classList.add('hidden');
        }, ms);
    }

    function renderChallengeCountdown() {
        const el = document.getElementById('challenge_countdown');
        const cancelBtn = document.getElementById('challenge_cancel_btn');
        const banner = document.getElementById('challenge_banner');
        const bannerTitle = document.getElementById('challenge_banner_title');
        const bannerDesc = document.getElementById('challenge_banner_desc');
        const bannerSelf = document.getElementById('challenge_banner_self');
        const bannerTime = document.getElementById('challenge_banner_time');
        if (!el) return;

        const st = __challengeState;
        if (!st || !st.active) {
            __hideAnimated(el, ['opacity-0', 'scale-95'], 200);
            el.textContent = '';
            if (cancelBtn) cancelBtn.classList.add('hidden');
            __hideAnimated(banner, ['opacity-0', '-translate-y-1'], 200);
            return;
        }

        const now = Math.floor(Date.now() / 1000);
        const ends = parseInt(st.ends_at || 0, 10) || 0;
        const remaining = Math.max(0, ends - now);
        el.textContent = `⏳ ${formatSeconds(remaining)}`;
        __showAnimated(el, ['opacity-0', 'scale-95']);
        if (cancelBtn) cancelBtn.classList.remove('hidden');

        if (banner && bannerTitle && bannerDesc && bannerSelf && bannerTime) {
            bannerTitle.textContent = `🎮 ${challengeKindLabel(st.kind)}`;
            bannerDesc.textContent = challengeRuleShort(st.kind, st.prompt);
            bannerTime.textContent = `⏳ ${formatSeconds(remaining)}`;

            const losers = Array.isArray(st.losers) ? st.losers.map((x) => parseInt(x, 10) || 0) : [];
            const winners = Array.isArray(st.winners) ? st.winners.map((x) => parseInt(x, 10) || 0) : [];
            if (currentUserId && losers.includes(currentUserId)) {
                bannerSelf.textContent = 'Status: You failed ❌ (you can keep chatting, but you already lost this challenge)';
                bannerSelf.className = 'mt-1 text-[11px] font-semibold text-red-200';
            } else if (currentUserId && winners.includes(currentUserId)) {
                bannerSelf.textContent = 'Status: You won ✅';
                bannerSelf.className = 'mt-1 text-[11px] font-semibold text-emerald-200';
            } else {
                bannerSelf.textContent = 'Status: In progress…';
                bannerSelf.className = 'mt-1 text-[11px] font-semibold text-emerald-200';
            }

            __showAnimated(banner, ['opacity-0', '-translate-y-1']);
        }
    }

    function setChallengeState(state) {
        __challengeState = (state && typeof state === 'object') ? state : null;
        if (__challengeTimer) {
            clearInterval(__challengeTimer);
            __challengeTimer = null;
        }
        if (__challengePingTimer) {
            clearInterval(__challengePingTimer);
            __challengePingTimer = null;
        }
        renderChallengeCountdown();
        if (__challengeState && __challengeState.active) {
            __challengeTimer = setInterval(renderChallengeCountdown, 1000);
            // Nudge the server to expire challenges based on server time.
            // This avoids "challenge never ends" if nobody sends messages.
            __challengePingTimer = setInterval(() => {
                if (!wsConnected || !socket) return;
                try { socket.send(JSON.stringify({ type: 'ping' })); } catch {}
            }, 5000);
        }
    }

    function initChallengeControls() {
        const openBtn = document.getElementById('challenge_drawer_open');
        const cancelBtn = document.getElementById('challenge_cancel_btn');
        const drawer = document.getElementById('challenge_drawer');
        const closeBtn = document.getElementById('challenge_drawer_close');
        const backdrop = document.getElementById('challenge_drawer_backdrop');
        if (!openBtn || !drawer) return;

        // Some chat layouts use CSS transforms that can break `position: fixed`.
        // Ensure the drawer is attached directly to <body> so it behaves consistently.
        try {
            if (drawer.parentElement !== document.body) {
                document.body.appendChild(drawer);
            }
        } catch {
            // ignore
        }

        const panel = document.getElementById('challenge_drawer_panel');
        let __drawerCloseTimer = null;

        function openDrawer() {
            if (__drawerCloseTimer) {
                clearTimeout(__drawerCloseTimer);
                __drawerCloseTimer = null;
            }
            drawer.classList.remove('opacity-0', 'pointer-events-none');
            document.body.classList.add('overflow-hidden');
            // Trigger enter animation on next frame.
            requestAnimationFrame(() => {
                if (backdrop) {
                    backdrop.classList.remove('opacity-0');
                    backdrop.classList.add('opacity-100');
                }
                if (panel) {
                    panel.classList.remove('opacity-0', 'translate-y-8', 'sm:translate-y-2', 'sm:scale-95');
                    panel.classList.add('opacity-100', 'translate-y-0', 'sm:scale-100');
                }
            });
        }

        function closeDrawer() {
            if (backdrop) {
                backdrop.classList.add('opacity-0');
                backdrop.classList.remove('opacity-100');
            }
            if (panel) {
                panel.classList.add('opacity-0', 'translate-y-8', 'sm:translate-y-2', 'sm:scale-95');
                panel.classList.remove('opacity-100', 'translate-y-0', 'sm:scale-100');
            }
            // Wait for animation to finish before hiding.
            __drawerCloseTimer = window.setTimeout(() => {
                drawer.classList.add('opacity-0', 'pointer-events-none');
                document.body.classList.remove('overflow-hidden');
                __drawerCloseTimer = null;
            }, 200);
        }

        openBtn.addEventListener('click', function () {
            openDrawer();
        });
        if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
        if (backdrop) backdrop.addEventListener('click', closeDrawer);

        document.addEventListener('keydown', function (e) {
            if (e && e.key === 'Escape' && !drawer.classList.contains('pointer-events-none')) {
                closeDrawer();
            }
        });

        drawer.addEventListener('click', function (e) {
            const btn = e.target && e.target.closest ? e.target.closest('[data-challenge-kind]') : null;
            if (!btn) return;
            const kind = String(btn.getAttribute('data-challenge-kind') || '').trim();
            if (!kind) return;

            if (!wsConnected || !socket) {
                if (typeof __popup === 'function') __popup('Not connected', 'Please wait for chat to connect.');
                return;
            }
            try {
                socket.send(JSON.stringify({ type: 'challenge_start', kind: kind }));
                closeDrawer();
            } catch {
                // ignore
            }
        });

        if (cancelBtn) {
            cancelBtn.addEventListener('click', function () {
                if (!wsConnected || !socket) return;
                try {
                    socket.send(JSON.stringify({ type: 'challenge_cancel' }));
                } catch {
                    // ignore
                }
            });
        }
    }

    function sendReadAck(id) {
        if (!wsConnected || !socket) return;
        const last = parseInt(id || 0, 10) || 0;
        if (last <= 0) return;
        try {
            socket.send(JSON.stringify({ type: 'read', last_read_id: last }));
        } catch {
            // ignore
        }
    }

    function applyReadTicks(lastReadId) {
        const maxId = parseInt(lastReadId || 0, 10) || 0;
        if (maxId <= 0) return;
        const ticks = document.querySelectorAll('[data-read-tick][data-message-id]') || [];
        ticks.forEach((el) => {
            const mid = parseInt(el.getAttribute('data-message-id') || '0', 10) || 0;
            if (mid && mid <= maxId) el.textContent = '✓✓';
        });
    }

    function maybeAckReadIfVisible() {
        if (document.visibilityState !== 'visible') return;
        updateLastIdFromDom();
        sendReadAck(lastId);
    }

    function hydrateLocalTimes(root) {
        const container = root || document;
        const nodeList = container && container.querySelectorAll ? container.querySelectorAll('time[data-dt]') : null;
        if (!nodeList || !nodeList.length) return;

        const nodes = Array.from(nodeList);
        const timeFmt = new Intl.DateTimeFormat(undefined, {
            hour: '2-digit',
            minute: '2-digit',
        });
        const fullFmt = new Intl.DateTimeFormat(undefined, {
            dateStyle: 'medium',
            timeStyle: 'short',
        });

        const applyOne = (el) => {
            const iso = el.getAttribute('data-dt');
            if (!iso) return;
            const d = new Date(iso);
            if (Number.isNaN(d.getTime())) return;
            try { el.textContent = timeFmt.format(d); } catch {}
            try { el.setAttribute('title', fullFmt.format(d)); } catch {}
            try { if (!el.getAttribute('datetime')) el.setAttribute('datetime', iso); } catch {}
        };

        // Chunk work to avoid long main-thread blocks on big rooms.
        const batchSize = 200;
        if (nodes.length <= batchSize) {
            nodes.forEach(applyOne);
            return;
        }

        let i = 0;
        const run = () => {
            const end = Math.min(nodes.length, i + batchSize);
            for (; i < end; i++) applyOne(nodes[i]);
            if (i < nodes.length) requestAnimationFrame(run);
        };
        requestAnimationFrame(run);
    }

    function vixoAnimateRemoveMessage(el) {
        if (!el) return;
        try {
            if (el.dataset && el.dataset.vixoRemoving === '1') {
                el.remove();
                return;
            }
        } catch {}

        // Respect reduced-motion.
        try {
            if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
                el.remove();
                return;
            }
        } catch {}

        try {
            if (el.dataset) el.dataset.vixoRemoving = '1';
        } catch {}

        // Telegram-like bubble roll-out: rotate + slide + fade + collapse height.
        let h = 0;
        try { h = el.offsetHeight || 0; } catch { h = 0; }

        let isMine = false;
        try {
            // `.vixo-msg` is a flex row with justify-end for current user's messages.
            isMine = el.classList && el.classList.contains('justify-end');
        } catch {
            isMine = false;
        }

        const slideX = isMine ? 18 : -18;
        const rot = isMine ? 10 : -10;
        try {
            el.style.overflow = 'hidden';
            if (h) el.style.maxHeight = h + 'px';
            el.style.willChange = 'opacity, transform, max-height';
            el.style.pointerEvents = 'none';
            el.style.transformOrigin = isMine ? 'right center' : 'left center';
            el.style.transition = 'max-height 190ms ease, opacity 150ms ease, transform 210ms ease';
            // Force style flush
            void el.offsetHeight;
            el.style.opacity = '0';
            el.style.transform = `translate(${slideX}px, 8px) rotate(${rot}deg) scale(0.94)`;
            el.style.maxHeight = '0px';
        } catch {
            try { el.remove(); } catch {}
            return;
        }

        window.setTimeout(() => {
            try { el.remove(); } catch {}
        }, 210);
    }

    // Expose for any legacy inline scripts.
    try { window.__vixoAnimateRemoveMessage = vixoAnimateRemoveMessage; } catch {}

    function __isMsgEl(el) {
        try {
            return !!(el && el.classList && el.classList.contains('vixo-msg') && el.getAttribute('data-message-id'));
        } catch {
            return false;
        }
    }

    function __prevMsgEl(el) {
        let cur = el ? el.previousElementSibling : null;
        while (cur && !__isMsgEl(cur)) cur = cur.previousElementSibling;
        return cur;
    }

    function __nextMsgEl(el) {
        let cur = el ? el.nextElementSibling : null;
        while (cur && !__isMsgEl(cur)) cur = cur.nextElementSibling;
        return cur;
    }

    function __applyHeaderForEl(el, prevEl) {
        if (!__isMsgEl(el)) return;
        const prev = prevEl || __prevMsgEl(el);
        const authorId = (el.getAttribute('data-author-id') || '').trim();
        const prevAuthorId = prev ? (prev.getAttribute('data-author-id') || '').trim() : '';
        const header = el.querySelector ? el.querySelector('[data-message-header]') : null;
        if (!header) return;
        if (prevAuthorId && authorId && authorId === prevAuthorId) header.classList.add('hidden');
        else header.classList.remove('hidden');
    }

    function applyConsecutiveHeaderGroupingIncremental() {
        if (!messagesEl) return;
        const last = messagesEl.lastElementChild;
        if (!last) return;
        __applyHeaderForEl(last);
    }

    function applyConsecutiveHeaderGroupingWindow(anchorEl) {
        if (!anchorEl) return;
        __applyHeaderForEl(anchorEl);
        __applyHeaderForEl(__nextMsgEl(anchorEl));
    }

    function applyConsecutiveHeaderGrouping(root) {
        const container = root || messagesEl;
        if (!container || !container.querySelectorAll) return;

        const items = Array.from(container.querySelectorAll('.vixo-msg[data-message-id]'));
        if (!items.length) return;

        const batchSize = 250;
        let i = 0;
        let prevAuthorId = null;

        const run = () => {
            const end = Math.min(items.length, i + batchSize);
            for (; i < end; i++) {
                const el = items[i];
                const authorId = (el.getAttribute('data-author-id') || '').trim();
                const header = el.querySelector ? el.querySelector('[data-message-header]') : null;
                if (header) {
                    if (prevAuthorId && authorId && authorId === prevAuthorId) header.classList.add('hidden');
                    else header.classList.remove('hidden');
                }
                prevAuthorId = authorId || null;
            }
            if (i < items.length) requestAnimationFrame(run);
        };

        // For small rooms, do it synchronously.
        if (items.length <= batchSize) {
            run();
            return;
        }
        requestAnimationFrame(run);
    }

    function revealChatContainer() {
        const c = document.getElementById('chat_container');
        if (c) c.classList.remove('vixo-chat-init-hidden');
    }

    function hardScrollToBottom(container) {
        const c = container || document.getElementById('chat_container');
        if (!c) return;
        try {
            const targetTop = Math.max(0, c.scrollHeight - c.clientHeight);
            c.scrollTop = targetTop;
        } catch {
            // ignore
        }
    }

    function safeScrollToBottom() {
        if (typeof scrollToBottom === 'function') scrollToBottom();
    }

    function forceScrollToBottomNow() {
        if (typeof scrollToBottom === 'function') {
            scrollToBottom({ force: true, behavior: 'auto' });
            return;
        }
        const c = document.getElementById('chat_container');
        if (c) {
            const prev = c.style.overflowY;
            try { c.style.overflowY = 'hidden'; } catch {}
            hardScrollToBottom(c);
            window.setTimeout(() => {
                try { c.style.overflowY = prev || ''; } catch {}
            }, 180);
            return;
        }
        hardScrollToBottom();
    }

    function updateLastIdFromDom() {
        const last = messagesEl && messagesEl.lastElementChild;
        const id = last && last.dataset ? parseInt(last.dataset.messageId || '0', 10) : 0;
        if (!Number.isNaN(id) && id > lastId) lastId = id;
    }

    function getMembersCountBadge() {
        try {
            return document.getElementById('vixo_members_count')
                || (document.getElementById('vixo_members_btn')
                    ? document.getElementById('vixo_members_btn').querySelector('span.text-emerald-300')
                    : null);
        } catch {
            return null;
        }
    }

    function updateMembersCountBadge(serverCount, fallbackDelta) {
        try {
            const badge = getMembersCountBadge();
            if (!badge) return;

            const hasServerCount = serverCount !== undefined && serverCount !== null && String(serverCount).trim() !== '';
            if (hasServerCount) {
                const parsedServer = parseInt(serverCount || 0, 10) || 0;
                badge.textContent = String(Math.max(0, parsedServer));
                return;
            }

            const current = parseInt(String(badge.textContent || '').trim(), 10);
            if (Number.isNaN(current)) return;

            const delta = parseInt(fallbackDelta || 0, 10) || 0;
            badge.textContent = String(Math.max(0, current + delta));
        } catch {
            // ignore
        }
    }

    function removeMemberRowById(userId) {
        const uid = parseInt(userId || 0, 10) || 0;
        if (!uid) return;
        try {
            const panel = document.getElementById('vixo_members_panel');
            if (!panel) return;
            const row = panel.querySelector(`[data-member-row][data-member-user-id="${uid}"]`);
            if (row) row.remove();

            const list = document.getElementById('vixo_members_list');
            if (list && !list.querySelector('[data-member-row]')) {
                const host = document.getElementById('vixo_panel_members') || panel;
                if (host && !document.getElementById('vixo_members_empty')) {
                    const empty = document.createElement('div');
                    empty.id = 'vixo_members_empty';
                    empty.className = 'text-xs text-gray-400 px-2 py-3';
                    empty.textContent = 'No members';
                    host.appendChild(empty);
                }
            }
        } catch {
            // ignore
        }
    }

    function upsertMemberRow(member) {
        try {
            const panel = document.getElementById('vixo_members_panel');
            if (!panel || !member || typeof member !== 'object') return;

            const uid = parseInt(member.id || 0, 10) || 0;
            if (!uid) return;

            let list = document.getElementById('vixo_members_list');
            if (!list) {
                const empty = document.getElementById('vixo_members_empty');
                if (empty) empty.remove();
                const host = document.getElementById('vixo_panel_members') || panel;
                if (!host) return;
                list = document.createElement('div');
                list.id = 'vixo_members_list';
                list.className = 'space-y-1';
                host.appendChild(list);
            }

            const displayName = String(member.name || member.username || 'Member');
            const username = String(member.username || '').trim();
            const avatarUrl = String(member.avatar || '').trim();
            const fallbackLetter = (displayName.slice(0, 1) || 'U').toUpperCase();

            let row = panel.querySelector(`[data-member-row][data-member-user-id="${uid}"]`);
            if (!row) {
                row = document.createElement('div');
                row.setAttribute('data-member-row', '');
                row.setAttribute('data-member-user-id', String(uid));
                row.className = 'px-2 py-2 rounded-xl border border-gray-800 bg-gray-900/40 text-sm text-gray-100 flex items-center justify-between gap-2 select-none';
                list.appendChild(row);
            }

            const isYou = uid === currentUserId;
            row.setAttribute('data-member-name', displayName);

            row.innerHTML = `
                <div class="min-w-0 flex items-center gap-2.5">
                    <span class="h-8 w-8 shrink-0 rounded-full border border-gray-700 bg-gray-800 overflow-hidden" data-member-avatar></span>
                    <div class="min-w-0 truncate" data-member-name-text></div>
                </div>
                <div class="shrink-0 flex items-center gap-2" data-member-right></div>
            `;

            const avatarSlot = row.querySelector('[data-member-avatar]');
            const nameEl = row.querySelector('[data-member-name-text]');
            if (nameEl) {
                nameEl.textContent = displayName;
                if (username && username !== displayName) nameEl.title = `@${username}`;
                if (isYou) {
                    const you = document.createElement('span');
                    you.className = 'text-gray-400 font-semibold';
                    you.textContent = ' (you)';
                    nameEl.appendChild(you);
                }
            }

            if (avatarSlot) {
                if (avatarUrl) {
                    avatarSlot.innerHTML = `<img src="${__escapeHtml(avatarUrl)}" alt="@${__escapeHtml(username || 'user')}" class="h-full w-full object-cover" />`;
                } else {
                    avatarSlot.innerHTML = `<span class="h-full w-full flex items-center justify-center text-[11px] font-bold text-gray-100">${__escapeHtml(fallbackLetter)}</span>`;
                }
            }
        } catch {
            // ignore
        }
    }

    function applyAdminBadges(admins) {
        try {
            const adminIds = new Set();
            (Array.isArray(admins) ? admins : []).forEach((a) => {
                const uid = parseInt((a && a.id) || 0, 10) || 0;
                if (uid > 0) adminIds.add(uid);
            });

            const panel = document.getElementById('vixo_members_panel');
            if (!panel) return;

            const rows = panel.querySelectorAll('[data-member-row][data-member-user-id]');
            rows.forEach((row) => {
                const uid = parseInt(String(row.getAttribute('data-member-user-id') || '0'), 10) || 0;
                if (!uid) return;
                const isAdmin = adminIds.has(uid);
                row.setAttribute('data-member-is-admin', isAdmin ? '1' : '0');

                const right = row.querySelector('[data-member-right]') || row.querySelector('.shrink-0.flex.items-center.gap-2') || row.lastElementChild;
                if (!right) return;

                const existing = row.querySelector('[data-admin-badge]');
                if (isAdmin) {
                    if (!existing) {
                        const badge = document.createElement('span');
                        badge.className = 'rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-2 py-1 text-[11px] font-extrabold text-emerald-200';
                        badge.setAttribute('data-admin-badge', '');
                        badge.textContent = 'Admin';
                        right.appendChild(badge);
                    }
                } else if (existing) {
                    existing.remove();
                }
            });
        } catch {
            // ignore
        }
    }

    function applyRoomSettingsFallback(payload) {
        if (!payload || typeof payload !== 'object') return;
        try {
            const roomDisplay = String(payload.room_display_name || '').trim();
            if (roomDisplay) {
                const topRoomTitle = document.getElementById('vixo_private_room_title');
                const topRoomInlineTitle = document.getElementById('vixo_private_room_title_inline');
                if (topRoomTitle) topRoomTitle.textContent = roomDisplay;
                if (topRoomInlineTitle) topRoomInlineTitle.textContent = roomDisplay;
            }
        } catch {
            // ignore
        }

        try {
            const descWrap = document.getElementById('vixo_public_room_description_wrap');
            const descEl = document.getElementById('vixo_public_room_description');
            if (descWrap && descEl) {
                const desc = String(payload.room_description || '').trim();
                descEl.textContent = desc;
                descWrap.classList.toggle('hidden', !desc);
            }
        } catch {
            // ignore
        }

        try {
            const code = String(payload.room_code || '').trim();
            if (code) {
                const roomCodeButtons = Array.from(document.querySelectorAll('[data-room-code-copy]'));
                roomCodeButtons.forEach((el) => {
                    try {
                        el.textContent = code;
                        el.setAttribute('data-room-code-copy', code);
                    } catch {
                        // ignore
                    }
                });
            }
        } catch {
            // ignore
        }

        try {
            const mediaAllowed = !!payload.allow_media_uploads;
            window.__vixoMediaUploadsAllowed = mediaAllowed;
            const uploadBtn = document.getElementById('chat_upload_btn');
            const fileInput = document.getElementById('chat_file_input');
            const uploadAux = document.getElementById('chat_upload_aux');
            if (uploadBtn) {
                uploadBtn.disabled = !mediaAllowed;
                uploadBtn.classList.toggle('hidden', !mediaAllowed);
            }
            if (fileInput) fileInput.disabled = !mediaAllowed;
            if (uploadAux) uploadAux.classList.toggle('hidden', !mediaAllowed);
        } catch {
            // ignore
        }

        try {
            const settingsAdminOnly = document.getElementById('vixo_settings_admin_only');
            const settingsMediaAllowed = document.getElementById('vixo_settings_media_allowed');
            const settingsSlowMode = document.getElementById('vixo_settings_slow_mode');
            const settingsDescription = document.getElementById('vixo_settings_room_description');
            const settingsName = document.getElementById('vixo_settings_room_name');
            if (settingsAdminOnly) settingsAdminOnly.checked = !!payload.only_admins_can_send;
            if (settingsMediaAllowed) settingsMediaAllowed.checked = !!payload.allow_media_uploads;
            if (settingsSlowMode) settingsSlowMode.value = String(parseInt(payload.slow_mode_seconds || 0, 10) || 0);
            if (settingsDescription && typeof payload.room_description === 'string') settingsDescription.value = payload.room_description;
            if (settingsName && typeof payload.room_display_name === 'string' && payload.room_display_name) settingsName.value = payload.room_display_name;
        } catch {
            // ignore
        }
    }

    function setAdminOnlyFallback(enabled, admins) {
        try {
            const adminIds = new Set();
            (Array.isArray(admins) ? admins : []).forEach((a) => {
                const uid = parseInt((a && a.id) || 0, 10) || 0;
                if (uid > 0) adminIds.add(uid);
            });
            const amAdmin = currentUserId > 0 && adminIds.has(currentUserId);
            if (amAdmin) return;

            const on = !!enabled;
            const mediaAllowed = (window.__vixoMediaUploadsAllowed !== false);

            const composerRow = document.getElementById('chat_composer_row');
            const composerForm = document.getElementById('chat_message_form');
            const composerBar = document.getElementById('chat_composer_bar');
            const adminOnlyRow = document.getElementById('chat_admin_only_row');
            const notMemberRow = document.getElementById('chat_not_member_row');
            const uploadAux = document.getElementById('chat_upload_aux');
            const input = document.getElementById('id_body');
            const sendBtn = document.getElementById('chat_send_btn');
            const uploadBtn = document.getElementById('chat_upload_btn');
            const emojiBtn = document.getElementById('emoji_btn');
            const gifBtn = document.getElementById('gif_btn');
            const fileInput = document.getElementById('chat_file_input');

            if (adminOnlyRow) adminOnlyRow.classList.toggle('hidden', !on);
            if (notMemberRow) notMemberRow.classList.add('hidden');
            if (composerRow) composerRow.classList.toggle('hidden', on);
            if (composerForm) composerForm.classList.toggle('hidden', on);
            if (composerBar) composerBar.classList.toggle('hidden', on);
            if (uploadAux) uploadAux.classList.toggle('hidden', on || !mediaAllowed);

            if (input) input.disabled = on;
            if (sendBtn) sendBtn.disabled = on;
            if (emojiBtn) emojiBtn.disabled = on;
            if (gifBtn) gifBtn.disabled = on;
            if (uploadBtn) {
                uploadBtn.disabled = on || !mediaAllowed;
                uploadBtn.classList.toggle('hidden', on || !mediaAllowed);
            }
            if (fileInput) fileInput.disabled = on || !mediaAllowed;
        } catch {
            // ignore
        }
    }

    function connect() {
        try {
            // Prevent overlapping connections/reconnect storms.
            if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
                return;
            }
        } catch {
            // ignore
        }

        try {
            if (socket && socket.close) socket.close();
        } catch {
            // ignore
        }

        socket = new WebSocket(wsUrl);

        socket.onopen = function () {
            wsConnected = true;
            stopPolling();
            __wsReconnectAttempt = 0;
            if (__wsReconnectTimer) {
                clearTimeout(__wsReconnectTimer);
                __wsReconnectTimer = null;
            }
            updateLastIdFromDom();
            if (document.visibilityState === 'visible') sendReadAck(lastId);
            // On initial load/room switch, start at the latest message.
            forceScrollToBottomNow();

            __startWsHeartbeat();

            // Ask server for active challenge state (private chats only; server will no-op otherwise).
            try {
                socket.send(JSON.stringify({ type: 'challenge_state' }));
            } catch {
                // ignore
            }
        };

        socket.onmessage = function (event) {
            let payload;
            try {
                payload = JSON.parse(event.data);
            } catch {
                // Ignore unexpected non-JSON frames
                return;
            }

            if (payload.type === 'chat_message' && payload.html) {
                // De-dupe/reconcile WS echo for the same message.
                try {
                    const nonce = payload.client_nonce ? String(payload.client_nonce) : '';
                    if (nonce) {
                        // Drop duplicate frames for the same message (can happen with reconnects).
                        if (__seenChatNonces.has(nonce)) return;
                        __seenChatNonces.set(nonce, Date.now());

                        // Best-effort prune.
                        if (__seenChatNonces.size > 400) {
                            const cutoff = Date.now() - 60_000;
                            for (const [k, t] of __seenChatNonces) {
                                if (t < cutoff || __seenChatNonces.size > 350) __seenChatNonces.delete(k);
                                else break;
                            }
                        }

                        const pending = __pendingByNonce.get(nonce);
                        if (pending) {
                            __pendingByNonce.delete(nonce);

                            // Replies are often sent while scrolled up; always jump to latest for your own send.
                            // (The send handler sets this too, but keep it armed in case it was toggled.)
                            window.__forceNextChatScroll = true;

                            __enqueueIncomingRender({
                                kind: 'replace',
                                pendingEl: pending,
                                html: payload.html,
                                forceScroll: true,
                                showPrivateJump: false,
                            });
                        } else {
                            __enqueueIncomingRender({
                                kind: 'append',
                                html: payload.html,
                                forceScroll: !!window.__forceNextChatScroll,
                                showPrivateJump: !window.__forceNextChatScroll,
                            });
                        }
                    } else {
                        __enqueueIncomingRender({
                            kind: 'append',
                            html: payload.html,
                            forceScroll: !!window.__forceNextChatScroll,
                            showPrivateJump: !window.__forceNextChatScroll,
                        });
                    }
                } catch {
                    // ignore
                }
                return;
            }

            if (payload.type === 'challenge_event' && payload.html) {
                __enqueueIncomingRender({
                    kind: 'append',
                    html: payload.html,
                    challengeState: payload.state || null,
                    forceScroll: !!window.__forceNextChatScroll,
                    showPrivateJump: false,
                });
                return;
            }

            if (payload.type === 'challenge_state' && payload.state) {
                setChallengeState(payload.state);
                return;
            }

            if (payload.type === 'read_receipt') {
                const readerId = parseInt(payload.reader_id || 0, 10) || 0;
                const lastReadId = parseInt(payload.last_read_id || 0, 10) || 0;
                if (readerId && readerId !== currentUserId) {
                    lastOtherReadId = Math.max(lastOtherReadId || 0, lastReadId || 0);
                    applyReadTicks(lastReadId);
                }
                return;
            }

            if (payload.type === 'one_time_seen' && payload.message_id) {
                const authorId = parseInt(payload.author_id || 0, 10) || 0;
                if (authorId && authorId === currentUserId) {
                    const mid = parseInt(payload.message_id || 0, 10) || 0;
                    const msgEl = mid ? document.getElementById(`msg-${mid}`) : null;
                    const slot = msgEl && msgEl.querySelector ? msgEl.querySelector('[data-one-time-sender-status]') : null;
                    if (slot) {
                        const viewerName = (payload.viewer_name || 'Someone').trim() || 'Someone';
                        slot.innerHTML = `
                            <div class="flex items-center gap-2">
                                <span class="inline-flex h-2 w-2 rounded-full bg-emerald-400 motion-safe:animate-pulse" aria-hidden="true"></span>
                                <span class="font-semibold">Disappearing image was seen</span>
                                <span class="text-emerald-200/60">•</span>
                                <span class="truncate text-emerald-200/80">${viewerName}</span>
                            </div>
                        `;
                        try { slot.classList.remove('hidden'); } catch {}
                        try { slot.classList.remove('opacity-0', 'translate-y-1'); } catch {}
                        try { slot.classList.add('opacity-100'); } catch {}
                        // Gentle entrance animation.
                        try {
                            slot.style.opacity = '0';
                            slot.style.transform = 'translateY(4px)';
                            slot.style.transition = 'opacity 220ms ease, transform 220ms ease';
                            requestAnimationFrame(() => {
                                try { slot.style.opacity = '1'; } catch {}
                                try { slot.style.transform = 'translateY(0)'; } catch {}
                            });
                        } catch {}
                    }
                }
                return;
            }

            if (payload.type === 'typing') {
                handleTypingEvent(payload);
                return;
            }

            if (payload.type === 'pong') {
                // keepalive ack (no UI)
                return;
            }

            if (payload.type === 'cooldown') {
                const seconds = parseInt(payload.seconds || payload.retry_after || payload.muted_seconds || 0, 10) || 0;
                if (seconds > 0 && typeof startSendCooldown === 'function') startSendCooldown(seconds);
                return;
            }

            if (payload.type === 'member_mute_updated') {
                const targetUserId = parseInt(payload.target_user_id || 0, 10) || 0;
                if (targetUserId && targetUserId === currentUserId) {
                    if (payload.unmuted) startSendCooldown(0);
                    else startSendCooldown(parseInt(payload.seconds || 0, 10) || 0);
                }
                return;
            }

            if (payload.type === 'verify_required') {
                showVerifyRequired(payload.reason || 'Verify your email to continue chatting.');
                return;
            }

            if (payload.type === 'message_update' && payload.message_id && payload.html) {
                const el = document.getElementById(`msg-${payload.message_id}`);
                if (el) {
                    el.outerHTML = payload.html;
                    const replaced = document.getElementById(`msg-${payload.message_id}`);
                    hydrateLocalTimes(replaced || document);
                    try {
                        if (replaced) applyConsecutiveHeaderGroupingWindow(replaced);
                        else applyConsecutiveHeaderGrouping(messagesEl);
                    } catch {}
                    applyReadTicks(lastOtherReadId);
                }
                return;
            }

            if (payload.type === 'message_delete' && payload.message_id) {
                const el = document.getElementById(`msg-${payload.message_id}`);
                if (el) vixoAnimateRemoveMessage(el);
                return;
            }

            if (payload.type === 'reactions' && payload.message_id && payload.html) {
                const el = document.getElementById(`reactions-${payload.message_id}`);
                if (el) {
                    el.outerHTML = payload.html;
                }
                return;
            }

            if (payload.type === 'online_count' && typeof payload.online_count !== 'undefined') {
                __setOnlineCount(payload.online_count);
            }

            if (payload.type === 'call_invite') {
                if (!window.__hasGlobalCallInvite) {
                    showIncomingCall(payload);
                }
            }

            if (payload.type === 'call_control') {
                if (payload.action === 'end' || payload.action === 'decline') {
                    endCallPopup(payload.action === 'decline' ? 'Call declined' : 'Call ended');
                }
            }

            if (payload.type === 'waiting_list_updated') {
                try {
                    if (typeof window.__vixoWaitingListRealtime === 'function') {
                        window.__vixoWaitingListRealtime(payload.count || 0);
                    }
                } catch {
                    // ignore
                }
                return;
            }

            if (payload.type === 'not_member') {
                if (typeof window.__vixoSetNotMember === 'function') {
                    window.__vixoSetNotMember(true);
                }
                try {
                    if (typeof window.__vixoShowRemovedModal === 'function') {
                        window.__vixoShowRemovedModal(payload.message || 'You have been removed from the group by an admin.');
                    }
                } catch {
                    // ignore
                }
                return;
            }

            if (payload.type === 'member_removed') {
                const removedUserId = parseInt(payload.removed_user_id || payload.removedUserId || payload.user_id || 0, 10) || 0;
                if (removedUserId) removeMemberRowById(removedUserId);
                updateMembersCountBadge(payload.member_count, -1);

                if (!removedUserId || removedUserId === currentUserId) {
                    if (typeof window.__vixoSetNotMember === 'function') {
                        window.__vixoSetNotMember(true);
                    }
                    if (typeof window.__vixoShowRemovedModal === 'function') {
                        window.__vixoShowRemovedModal(payload.message || 'You have been removed from the group by an admin.');
                    }
                }
                return;
            }

            if (payload.type === 'member_left') {
                const userId = parseInt(payload.user_id || 0, 10) || 0;
                if (userId) removeMemberRowById(userId);
                updateMembersCountBadge(payload.member_count, -1);
                return;
            }

            if (payload.type === 'member_added') {
                updateMembersCountBadge(payload.member_count, 1);
                try {
                    upsertMemberRow(payload.member || {});
                } catch {
                    // ignore
                }
                return;
            }

            if (payload.type === 'room_settings') {
                applyRoomSettingsFallback(payload);
                try {
                    if (typeof window.__vixoApplyRoomSettings === 'function') {
                        window.__vixoApplyRoomSettings(payload);
                    }
                } catch {
                    // ignore
                }

                try {
                    if (Array.isArray(payload.admins)) {
                        applyAdminBadges(payload.admins);
                    }
                } catch {
                    // ignore
                }

                if (typeof window.__vixoSetAdminOnly === 'function') {
                    window.__vixoSetAdminOnly(!!payload.only_admins_can_send, payload.admins);
                } else {
                    setAdminOnlyFallback(!!payload.only_admins_can_send, payload.admins);
                }
                return;
            }

            if (payload.type === 'admin_only') {
                if (typeof window.__vixoSetAdminOnly === 'function') {
                    window.__vixoSetAdminOnly(true, payload.admins);
                }
                if (typeof window.__vixoShowAdminOnlyPopup === 'function') {
                    window.__vixoShowAdminOnlyPopup();
                }
                return;
            }

            if (payload.type === 'admin_role_removed') {
                const demotedUserId = parseInt(payload.demoted_user_id || 0, 10) || 0;
                if (demotedUserId && demotedUserId === currentUserId && typeof window.__vixoShowAdminRemovedPopup === 'function') {
                    window.__vixoShowAdminRemovedPopup(payload.message || 'You have been removed from admin.');
                }
                return;
            }

            if (payload.type === 'call_presence') {
                // UI-only: keep the call popup participant list in sync.
                const action = (payload.action || 'join');
                const username = payload.username || '';

                // Only care when a call popup is open.
                if (!callActive) return;

                if (username === currentUsername) {
                    if (action === 'leave') setParticipant('me', 'Left', '—');
                    else setParticipant('me', 'In call', 'On call');
                    return;
                }

                if (otherUsername && username === otherUsername) {
                    if (action === 'leave') setParticipant('other', 'Left', '—');
                    else setParticipant('other', 'In call', 'On call');
                    return;
                }
            }

            if (payload.type === 'error' && payload.code === 'links_not_allowed') {
                __popup('Links not allowed', payload.message || 'Links are only allowed in private chats.');
                return;
            }
        };

        socket.onclose = function () {
            wsConnected = false;
            __stopWsHeartbeat();
            startPolling();
            __scheduleWsReconnect();
        };

        socket.onerror = function () {
            // Don't flip to disconnected on transient errors; `onclose` will handle it.
        };
    }

    // Init challenge controls (if present in this room).
    try {
        initChallengeControls();
    } catch {
        // ignore
    }

    function isNearBottom() {
        try {
            if (typeof window.__isChatNearBottom === 'function') {
                return !!window.__isChatNearBottom();
            }
            const el = document.getElementById('chat_container');
            if (!el) return true;
            return (el.scrollHeight - (el.scrollTop + el.clientHeight)) <= 140;
        } catch {
            return true;
        }
    }

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible') return;
        updateLastIdFromDom();
        if (isNearBottom()) sendReadAck(lastId);

        // If the socket was dropped while tab was hidden, reconnect quickly on return.
        try {
            if (!__wsIsOpen()) __scheduleWsReconnect();
        } catch {
            // ignore
        }
    });

    window.addEventListener('focus', () => {
        updateLastIdFromDom();
        if (isNearBottom()) sendReadAck(lastId);
    });

    // Use query-by-id here to avoid referencing `chatContainer` before it's defined later in this file.
    const __chatContainerForRead = document.getElementById('chat_container');
    if (__chatContainerForRead) {
        __chatContainerForRead.addEventListener('scroll', () => {
            if (!isNearBottom()) return;
            updateLastIdFromDom();
            if (document.visibilityState === 'visible') sendReadAck(lastId);
        }, { passive: true });
    }

    // Ensure correct position on initial render.
    // chat.js is often injected after DOMContentLoaded (via chat_loader.js),
    // so we must also run this immediately when DOM is already ready.
    function __initChatInitialRender() {
        if (__initChatInitialRender.__didRun) return;
        __initChatInitialRender.__didRun = true;

        updateLastIdFromDom();
        hydrateLocalTimes(document);
        applyConsecutiveHeaderGrouping(messagesEl);
        applyReadTicks(lastOtherReadId);
        safeScrollToBottom();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', __initChatInitialRender, { once: true });
    } else {
        __initChatInitialRender();
    }

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') maybeAckReadIfVisible();
    });
    window.addEventListener('focus', () => {
        maybeAckReadIfVisible();
    });

    (function initReadAckOnScroll() {
        const chatContainer = document.getElementById('chat_container');
        if (!chatContainer) return;
        let timer = null;
        chatContainer.addEventListener('scroll', () => {
            if (timer) window.clearTimeout(timer);
            timer = window.setTimeout(() => {
                try {
                    const remaining = chatContainer.scrollHeight - (chatContainer.scrollTop + chatContainer.clientHeight);
                    if (remaining <= 80) maybeAckReadIfVisible();
                } catch {
                    // ignore
                }
            }, 120);
        }, { passive: true });
    })();

    (function initPinnedBannerCollapse() {
        const chatContainer = document.getElementById('chat_container');
        const banner = document.getElementById('pinned_banner');
        const full = document.getElementById('pinned_full');
        const fullInner = document.getElementById('pinned_full_inner');
        const collapsed = document.getElementById('pinned_collapsed');
        const label = document.getElementById('pinned_label');
        const toggle = document.getElementById('pinned_toggle');
        if (!chatContainer || !banner || !full || !fullInner || !collapsed) return;

        let forceExpanded = false;

        function setExpanded(expanded) {
            // Expanded: show full content, hide collapsed line.
            // Collapsed: show collapsed line, animate full content closed.
            const durationMs = 300;

            if (expanded) {
                // Ensure collapsed is visible during transition (fade out), then hide.
                if (!collapsed.classList.contains('hidden')) {
                    collapsed.style.opacity = '0';
                    window.setTimeout(() => {
                        collapsed.classList.add('hidden');
                    }, 180);
                }

                full.classList.remove('hidden');
                full.style.opacity = '1';

                // Start from 0 height if currently collapsed.
                if (String(full.style.height || '') === '0px') {
                    full.style.height = '0px';
                }

                const target = fullInner.scrollHeight;
                // Force a reflow so height transition triggers.
                void full.offsetHeight;
                full.style.height = `${target}px`;

                window.setTimeout(() => {
                    // After transition, let it size naturally.
                    full.style.height = 'auto';
                }, durationMs);
            } else {
                // Show collapsed (fade in)
                collapsed.classList.remove('hidden');
                // Force reflow for opacity.
                void collapsed.offsetHeight;
                collapsed.style.opacity = '1';

                // Collapse full: from auto -> px -> 0
                const current = fullInner.scrollHeight;
                full.style.height = `${current}px`;
                full.style.opacity = '1';
                void full.offsetHeight;
                full.style.height = '0px';
                full.style.opacity = '0';

                window.setTimeout(() => {
                    full.classList.add('hidden');
                    // Keep height at 0px for next expand start.
                    full.style.height = '0px';
                }, durationMs);
            }

            if (label) {
                if (expanded) label.classList.remove('hidden');
                else label.classList.add('hidden');
            }

            if (toggle) {
                toggle.setAttribute('aria-expanded', String(expanded));
            }
        }

        function sync() {
            const scrolled = (chatContainer.scrollTop || 0) > 12;
            const shouldBeCollapsed = scrolled && !forceExpanded;
            setExpanded(!shouldBeCollapsed);
        }

        chatContainer.addEventListener('scroll', sync, { passive: true });

        if (toggle) {
            toggle.addEventListener('click', () => {
                const scrolled = (chatContainer.scrollTop || 0) > 12;
                // If user is at top, we always consider it expanded.
                if (!scrolled) {
                    forceExpanded = false;
                    sync();
                    return;
                }

                forceExpanded = !forceExpanded;
                sync();
            });
        }

        // initial state
        sync();
    })();

    // -------- Reactions (WhatsApp style click popup) --------
    function closeAllReactionPickers() {
        document.querySelectorAll('[data-reaction-picker]').forEach((el) => {
            el.classList.add('hidden');
        });
    }

    document.addEventListener('click', function (e) {
        const toggleBtn = e.target.closest('[data-reaction-toggle]');
        const emojiBtn = e.target.closest('[data-react-emoji]');

        if (toggleBtn) {
            e.preventDefault();
            e.stopPropagation();
            const messageId = toggleBtn.dataset.messageId;
            if (!messageId) return;
            const picker = document.querySelector(`[data-reaction-picker][data-message-id="${messageId}"]`);
            if (!picker) return;
            const willOpen = picker.classList.contains('hidden');
            closeAllReactionPickers();
            if (willOpen) picker.classList.remove('hidden');
            return;
        }

        if (emojiBtn) {
            e.preventDefault();
            e.stopPropagation();
            const messageId = emojiBtn.dataset.messageId;
            const emoji = emojiBtn.dataset.emoji;
            if (!messageId || !emoji) return;
            closeAllReactionPickers();
            const url = messageReactUrlTemplate.replace('/0/', `/${messageId}/`);
            const params = new URLSearchParams();
            params.set('emoji', emoji);
            fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': (typeof getCookie === 'function' ? getCookie('csrftoken') : ''),
                },
                body: params,
            }).catch(() => {});
            return;
        }

        // Outside click closes pickers
        closeAllReactionPickers();
    });

    function closeAllMessageMenus(exceptMenu) {
        const menus = document.querySelectorAll('[data-message-menu]');
        menus.forEach((menu) => {
            if (exceptMenu && menu === exceptMenu) return;
            menu.classList.add('hidden');
            const toggle = menu.parentElement ? menu.parentElement.querySelector('[data-message-menu-toggle]') : null;
            if (toggle) toggle.setAttribute('aria-expanded', 'false');

            const msg = menu.closest ? menu.closest('.vixo-msg') : null;
            const actions = msg ? msg.querySelector('[data-msg-actions]') : null;
            try {
                if (actions && msg && !msg.matches(':hover')) {
                    actions.classList.add('opacity-0', 'pointer-events-none');
                    actions.classList.remove('opacity-100', 'pointer-events-auto');
                }
            } catch {
                // ignore
            }
        });
    }

    // Toggle actions menu on 3-dots click (not hover)
    document.addEventListener('click', function (e) {
        const toggle = e.target && e.target.closest ? e.target.closest('[data-message-menu-toggle]') : null;
        const insideMenu = e.target && e.target.closest ? e.target.closest('[data-message-menu]') : null;

        if (toggle) {
            e.preventDefault();
            e.stopPropagation();

            const wrapper = toggle.parentElement;
            const menu = wrapper ? wrapper.querySelector('[data-message-menu]') : null;
            if (!menu) return;

            const willOpen = menu.classList.contains('hidden');
            closeAllMessageMenus(willOpen ? menu : null);

            if (willOpen) {
                menu.classList.remove('hidden');
                toggle.setAttribute('aria-expanded', 'true');
            } else {
                menu.classList.add('hidden');
                toggle.setAttribute('aria-expanded', 'false');
            }
            return;
        }

        // Clicks inside menu should not close it
        if (insideMenu) return;

        // Click anywhere else closes menus
        closeAllMessageMenus();
    }, true);

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeAllMessageMenus();
    }, true);

    // -------- Message Copy/Edit/Delete (actions menu) --------
    document.addEventListener('click', async function (e) {
        const copyBtn = e.target.closest('[data-copy-message]');
        const editBtn = e.target.closest('[data-edit-message]');
        const delBtn = e.target.closest('[data-delete-message]');

        if (!copyBtn && !editBtn && !delBtn) return;
        e.preventDefault();
        e.stopPropagation();

        const actionBtn = (copyBtn || editBtn || delBtn);
        const messageId = actionBtn && actionBtn.dataset ? actionBtn.dataset.messageId : '';

        // Close any open message menu after choosing an action
        closeAllMessageMenus();

        if (copyBtn) {
            const text = (copyBtn.dataset.messageText || '').toString();
            const trimmed = text.trim();
            if (trimmed.startsWith('[GIF]')) {
                try {
                    if (window.showToast) window.showToast('Copy is disabled for GIF messages.');
                } catch {
                    // ignore
                }
                return;
            }
            if (!trimmed) {
                try {
                    if (window.showToast) window.showToast('Nothing to copy.');
                } catch {
                    // ignore
                }
                return;
            }

            const ok = await copyToClipboard(text);
            try {
                if (window.showToast) window.showToast(ok ? 'Message copied.' : 'Copy failed.');
            } catch {
                // ignore
            }
            return;
        }

        if (!messageId) return;

        if (editBtn) {
            const body = editBtn.dataset.messageBody || '';
            startEditingMessage(messageId, body);
            return;
        }

        if (delBtn) {
            const url = messageDeleteUrlTemplate.replace('/0/', `/${messageId}/`);
            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': (typeof getCookie === 'function' ? getCookie('csrftoken') : ''),
                    },
                    body: new URLSearchParams(),
                });

                // Animate immediately on success; WS echo will be a no-op for already-removed elements.
                if (resp && resp.ok) {
                    const el = document.getElementById(`msg-${messageId}`);
                    if (el) vixoAnimateRemoveMessage(el);
                }
            } catch {
                // ignore
            }
        }
    });

    function ensureIncomingContainer() {
        let c = document.getElementById('incoming-call-container');
        if (c) return c;
        c = document.createElement('div');
        c.id = 'incoming-call-container';
        c.className = 'fixed top-24 right-6 z-50 w-[min(24rem,calc(100vw-3rem))] space-y-3';
        document.body.appendChild(c);
        return c;
    }

    function showIncomingCall(payload) {
        const container = ensureIncomingContainer();
        const from = payload.from_username || 'Someone';
        const type = (payload.call_type || 'voice').toLowerCase() === 'video' ? 'video' : 'voice';

        playIncomingRing();

        const toast = document.createElement('div');
        toast.className = 'pointer-events-auto flex items-start gap-3 rounded-xl border border-gray-800 bg-gray-900/90 px-4 py-3 text-sm text-gray-100 shadow-lg shadow-black/20';
        toast.innerHTML = `
                <div class="mt-0.5 h-2.5 w-2.5 flex-none rounded-full bg-emerald-400"></div>
                <div class="flex-1">
                    <div class="font-semibold">Incoming ${type === 'video' ? 'video' : 'voice'} call</div>
                    <div class="text-gray-300 text-xs mt-0.5">from ${from}</div>
                    <div class="mt-3 flex gap-2">
                        <button type="button" data-accept class="text-xs bg-emerald-500 hover:bg-emerald-600 text-white px-3 py-1.5 rounded-lg transition-colors">Accept</button>
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
        toast.querySelector('[data-close]')?.addEventListener('click', removeToast);
        toast.querySelector('[data-accept]')?.addEventListener('click', async () => {
            stopIncomingRing();
            window.__hasGlobalCallInvite = true;
            removeToast();
            await openCallPopup(type, 'callee');
        });
        toast.querySelector('[data-decline]')?.addEventListener('click', async () => {
            try {
                const body = new URLSearchParams();
                body.set('action', 'decline');
                body.set('type', type);
                await fetch(callEventUrl, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': (typeof getCookie === 'function' ? getCookie('csrftoken') : ''),
                    },
                    body,
                });
            } catch {
                // ignore
            }
            removeToast();
        });
        setTimeout(removeToast, 15000);

        container.appendChild(toast);
    }

    // --- Call popup (no separate page) ---
    const callPopupEl = document.getElementById('call_popup');
    const callPopupHeaderEl = document.getElementById('call_popup_header');
    const callPopupTitleEl = document.getElementById('call_popup_title');
    const callPopupSubtitleEl = document.getElementById('call_popup_subtitle');
    const callPopupStatusEl = document.getElementById('call_popup_status');
    const callPopupVideoEl = document.getElementById('call_popup_video');
    const callLocalEl = document.getElementById('call_local_player');
    const callRemoteEl = document.getElementById('call_remote_player');
    const callMicBtn = document.getElementById('call_popup_mic');
    const callCamBtn = document.getElementById('call_popup_cam');
    const callSwitchBtn = document.getElementById('call_popup_switch');
    const callEndBtn = document.getElementById('call_popup_end');

    const callPartMeAvatarEl = document.getElementById('call_part_me_avatar');
    const callPartMeNameEl = document.getElementById('call_part_me_name');
    const callPartMeStateEl = document.getElementById('call_part_me_state');
    const callPartMeBadgeEl = document.getElementById('call_part_me_badge');

    const callPartOtherAvatarEl = document.getElementById('call_part_other_avatar');
    const callPartOtherNameEl = document.getElementById('call_part_other_name');
    const callPartOtherStateEl = document.getElementById('call_part_other_state');
    const callPartOtherBadgeEl = document.getElementById('call_part_other_badge');

    let callActive = false;
    let callTypeActive = null;
    let callRoleActive = null;
    let callClient = null;
    let localTracks = { audio: null, video: null };

    let callMicEnabled = true;
    let callCamEnabled = true;

    function syncCallControlVisibility() {
        const isVideo = callTypeActive === 'video';
        if (callCamBtn) callCamBtn.style.display = isVideo ? '' : 'none';
        if (callSwitchBtn) callSwitchBtn.style.display = isVideo ? '' : 'none';
    }

    function syncCallControlLabels() {
        if (callMicBtn) callMicBtn.textContent = callMicEnabled ? 'Mute' : 'Unmute';
        if (callCamBtn) callCamBtn.textContent = callCamEnabled ? 'Cam Off' : 'Cam On';
    }

    // Remote audio can be blocked by autoplay policies (Chrome/Safari). Keep refs to retry on user gesture.
    const callRemoteAudioTracks = new Map(); // uid -> audioTrack
    let callAudioPlaybackBlocked = false;

    function tryPlayCallRemoteAudio() {
        let playedAny = false;
        for (const track of callRemoteAudioTracks.values()) {
            if (!track) continue;
            try {
                track.play();
                playedAny = true;
            } catch {
                // still blocked
            }
        }
        if (playedAny) {
            callAudioPlaybackBlocked = false;
            setCallStatus('In call');
        }
    }

    document.addEventListener('pointerdown', () => {
        if (!callAudioPlaybackBlocked) return;
        tryPlayCallRemoteAudio();
    }, { passive: true });

    function initCallParticipantsUi() {
        try {
            if (callPartMeNameEl) callPartMeNameEl.textContent = 'You';
            if (callPartMeAvatarEl) callPartMeAvatarEl.src = meAvatarUrl || '';

            if (callPartOtherNameEl) callPartOtherNameEl.textContent = otherDisplayName || otherUsername || 'Participant';
            if (callPartOtherAvatarEl) callPartOtherAvatarEl.src = otherAvatarUrl || '';
        } catch {
            // ignore
        }
    }

    function setParticipant(which, stateText, badgeText) {
        const state = stateText || '';
        const badge = badgeText || '—';
        if (which === 'me') {
            if (callPartMeStateEl) callPartMeStateEl.textContent = state;
            if (callPartMeBadgeEl) callPartMeBadgeEl.textContent = badge;
            return;
        }
        if (which === 'other') {
            if (callPartOtherStateEl) callPartOtherStateEl.textContent = state;
            if (callPartOtherBadgeEl) callPartOtherBadgeEl.textContent = badge;
        }
    }

    initCallParticipantsUi();

    function setCallStatus(text) {
        if (callPopupStatusEl) callPopupStatusEl.textContent = text || '';
        if (callPopupSubtitleEl) callPopupSubtitleEl.textContent = text || '';
    }

    function getPublicCallErrorMessage(error) {
        const raw = String((error && error.message) ? error.message : (error || '')).toLowerCase();
        if (raw.includes('permission') || raw.includes('notallowed') || raw.includes('denied')) {
            return 'Microphone/camera permission is required.';
        }
        if (raw.includes('device') || raw.includes('camera') || raw.includes('microphone') || raw.includes('track')) {
            return 'Could not access your mic/camera. Please check device settings.';
        }
        return 'Could not start call. Please try again.';
    }

    function showCallPopup() {
        if (!callPopupEl) return;
        callPopupEl.classList.remove('hidden');
    }

    function hideCallPopup() {
        if (!callPopupEl) return;
        callPopupEl.classList.add('hidden');
    }

    async function fetchAgoraToken() {
        const res = await fetch(tokenUrl, { credentials: 'same-origin' });

        // Handle rate limit cleanly.
        if (res.status === 429) {
            const retryAfter = Number(res.headers.get('Retry-After') || '10');
            throw new Error(`Rate limited. Try again in ${Number.isFinite(retryAfter) ? retryAfter : 10}s.`);
        }

        let data = null;
        try {
            data = await res.json();
        } catch {
            // Some servers return HTML on errors; include a short hint.
            const text = await res.text().catch(() => '');
            const hint = (text || '').slice(0, 140).replace(/\s+/g, ' ').trim();
            throw new Error(!res.ok ? `Token request failed (${res.status}). ${hint}` : 'Token response was not JSON.');
        }

        if (!res.ok || (data && data.error)) {
            throw new Error((data && data.error) ? String(data.error) : `Token request failed (${res.status}).`);
        }
        return data;
    }

    function getCsrf() {
        try { return (typeof getCookie === 'function' ? getCookie('csrftoken') : ''); } catch { return ''; }
    }

    async function announcePresence(action, uid, type) {
        try {
            const body = new URLSearchParams();
            body.set('action', action);
            body.set('type', type);
            body.set('uid', String(uid || 0));
            await fetch(presenceUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': getCsrf(),
                },
                body,
            });
        } catch {
            // ignore
        }
    }

    async function postCallEvent(action, type) {
        try {
            const body = new URLSearchParams();
            body.set('action', action);
            body.set('type', type);
            await fetch(callEventUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': getCsrf(),
                },
                body,
            });
        } catch {
            // ignore
        }
    }

    async function openCallPopup(type, role) {
        if (callActive) return;
        callActive = true;
        callTypeActive = (type || 'voice');
        callRoleActive = (role || 'caller');

        initCallParticipantsUi();
        setParticipant('me', 'Connecting…', '…');
        setParticipant('other', 'Waiting…', '…');

        showCallPopup();
        if (callPopupTitleEl) callPopupTitleEl.textContent = callTypeActive === 'video' ? 'Video call' : 'Voice call';
        setCallStatus('Connecting…');

        callMicEnabled = true;
        callCamEnabled = true;
        syncCallControlVisibility();
        syncCallControlLabels();

        if (callPopupVideoEl) {
            if (callTypeActive === 'video') {
                callPopupVideoEl.classList.remove('hidden');
                callPopupVideoEl.classList.add('grid');
            } else {
                callPopupVideoEl.classList.add('hidden');
                callPopupVideoEl.classList.remove('grid');
            }
        }

        try {
            const { token, uid, channel, app_id } = await fetchAgoraToken();
            if (!app_id) throw new Error('Agora is not configured (missing AGORA_APP_ID).');

            callClient = AgoraRTC.createClient({ mode: 'rtc', codec: 'vp8' });

            callClient.on('user-joined', () => {
                if (callPopupSubtitleEl) {
                    callPopupSubtitleEl.textContent = otherUsername ? `${otherUsername} joined` : 'User joined';
                }
                setParticipant('other', 'Joined', 'On call');
            });

            callClient.on('user-published', async (user, mediaType) => {
                await callClient.subscribe(user, mediaType);
                if (mediaType === 'video' && callRemoteEl) {
                    try { user.videoTrack.play(callRemoteEl); } catch {}
                }
                if (mediaType === 'audio') {
                    try {
                        callRemoteAudioTracks.set(String(user.uid), user.audioTrack);
                        user.audioTrack.play();
                    } catch {
                        callAudioPlaybackBlocked = true;
                        setCallStatus('Tap anywhere to enable audio');
                    }
                }
                setCallStatus('In call');
                setParticipant('other', 'In call', 'On call');
            });

            callClient.on('user-left', () => {
                setCallStatus('Waiting…');
                setParticipant('other', 'Left', '—');
            });

            await callClient.join(app_id, channel, token, uid);
            await announcePresence('join', uid, callTypeActive);

            setParticipant('me', 'In call', 'On call');

            if (callRoleActive === 'caller') {
                await postCallEvent('start', callTypeActive);
            }

            localTracks.audio = await AgoraRTC.createMicrophoneAudioTrack({ AEC: true, AGC: true, ANS: true });
            if (callTypeActive === 'video') {
                localTracks.video = await AgoraRTC.createCameraVideoTrack();
                if (callLocalEl) {
                    try { localTracks.video.play(callLocalEl); } catch {}
                }
                await callClient.publish([localTracks.audio, localTracks.video]);
            } else {
                await callClient.publish([localTracks.audio]);
            }

            setCallStatus('In call');
        } catch (e) {
            try { console.error('Call popup start failed:', e); } catch {}
            setCallStatus(getPublicCallErrorMessage(e));

            // Allow retry without refresh.
            try {
                if (localTracks.video) {
                    try { localTracks.video.stop(); } catch {}
                    try { localTracks.video.close(); } catch {}
                }
                if (localTracks.audio) {
                    try { localTracks.audio.stop(); } catch {}
                    try { localTracks.audio.close(); } catch {}
                }
            } catch {}
            try {
                if (callClient) {
                    try { await callClient.leave(); } catch {}
                }
            } catch {}

            callClient = null;
            localTracks = { audio: null, video: null };
            callActive = false;
            callTypeActive = null;
            callRoleActive = null;
            setParticipant('me', 'Waiting…', '—');
            setParticipant('other', 'Waiting…', '—');
        }
    }

    async function endCallPopup(reason) {
        const hadActiveCall = !!callActive;
        try {
            if (reason) setCallStatus(reason);
            // Broadcast end marker (only once is fine; server dedupes)
            if (hadActiveCall && callTypeActive) await postCallEvent('end', callTypeActive);
        } catch {}

        if (!hadActiveCall) {
            callClient = null;
            localTracks = { audio: null, video: null };
            callActive = false;
            callTypeActive = null;
            callRoleActive = null;
            setParticipant('me', 'Waiting…', '—');
            setParticipant('other', 'Waiting…', '—');
            hideCallPopup();
            return;
        }

        try {
            callRemoteAudioTracks.clear();
            callAudioPlaybackBlocked = false;
        } catch {}

        try {
            if (localTracks.video) {
                try { localTracks.video.stop(); } catch {}
                try { localTracks.video.close(); } catch {}
            }
            if (localTracks.audio) {
                try { localTracks.audio.stop(); } catch {}
                try { localTracks.audio.close(); } catch {}
            }
        } catch {}

        try {
            if (callClient) {
                try { await callClient.leave(); } catch {}
            }
        } catch {}

        callClient = null;
        localTracks = { audio: null, video: null };
        callActive = false;
        callTypeActive = null;
        callRoleActive = null;
        setParticipant('me', 'Waiting…', '—');
        setParticipant('other', 'Waiting…', '—');
        hideCallPopup();
    }

    if (callEndBtn) {
        callEndBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            endCallPopup('Call ended');
        });
    }

    window.addEventListener('beforeunload', (e) => {
        if (!callActive) return;
        const msg = 'Call will end if you reload or leave this page.';
        e.preventDefault();
        e.returnValue = msg;
        return msg;
    });

    if (callMicBtn) {
        callMicBtn.addEventListener('click', async (e) => {
            try {
                e.preventDefault();
                e.stopPropagation();
            } catch {}
            try {
                if (!localTracks.audio) {
                    setCallStatus('Mic not ready yet');
                    return;
                }
                callMicEnabled = !callMicEnabled;
                await localTracks.audio.setEnabled(callMicEnabled);
                syncCallControlLabels();
                setCallStatus(callMicEnabled ? 'Mic on' : 'Mic muted');
            } catch {
                setCallStatus('Failed to toggle mic');
            }
        });
    }

    if (callCamBtn) {
        callCamBtn.addEventListener('click', async (e) => {
            try {
                e.preventDefault();
                e.stopPropagation();
            } catch {}
            try {
                if (callTypeActive !== 'video') return;
                if (!localTracks.video) {
                    setCallStatus('Camera not ready yet');
                    return;
                }
                callCamEnabled = !callCamEnabled;
                await localTracks.video.setEnabled(callCamEnabled);
                syncCallControlLabels();
                setCallStatus(callCamEnabled ? 'Camera on' : 'Camera off');
            } catch {
                setCallStatus('Failed to toggle camera');
            }
        });
    }

    if (callSwitchBtn) {
        callSwitchBtn.addEventListener('click', async (e) => {
            try {
                e.preventDefault();
                e.stopPropagation();
            } catch {}
            try {
                if (callTypeActive !== 'video') return;
                if (!localTracks.video) {
                    setCallStatus('Camera not ready yet');
                    return;
                }
                const cams = await AgoraRTC.getCameras();
                if (!cams || cams.length < 2) {
                    setCallStatus('No alternate camera found');
                    return;
                }
                const currentLabel = (typeof localTracks.video.getTrackLabel === 'function') ? localTracks.video.getTrackLabel() : '';
                let idx = cams.findIndex((c) => c && c.label && currentLabel && c.label === currentLabel);
                if (idx < 0) idx = 0;
                const next = cams[(idx + 1) % cams.length];
                if (!next || !next.deviceId) {
                    setCallStatus('No alternate camera found');
                    return;
                }
                await localTracks.video.setDevice(next.deviceId);
                setCallStatus('Switched camera');
            } catch {
                setCallStatus('Failed to switch camera');
            }
        });
    }

    // Draggable popup
    (function () {
        if (!callPopupEl || !callPopupHeaderEl) return;
        let dragging = false;
        let offsetX = 0;
        let offsetY = 0;

        function stopDrag(e) {
            if (!dragging) return;
            dragging = false;
            try {
                if (e && typeof e.pointerId !== 'undefined') {
                    callPopupHeaderEl.releasePointerCapture(e.pointerId);
                }
            } catch {}
        }

        callPopupHeaderEl.addEventListener('pointerdown', (e) => {
            // Don't start dragging when clicking the End button (or any interactive element).
            const interactive = e.target && e.target.closest ? e.target.closest('button, a, input, select, textarea') : null;
            if (interactive) return;
            // Only left-click for mouse pointers.
            if (typeof e.button === 'number' && e.button !== 0) return;
            dragging = true;
            try { callPopupHeaderEl.setPointerCapture(e.pointerId); } catch {}
            const rect = callPopupEl.getBoundingClientRect();
            offsetX = e.clientX - rect.left;
            offsetY = e.clientY - rect.top;
        });

        callPopupHeaderEl.addEventListener('pointermove', (e) => {
            if (!dragging) return;
            const left = Math.max(8, Math.min(window.innerWidth - callPopupEl.offsetWidth - 8, e.clientX - offsetX));
            const top = Math.max(8, Math.min(window.innerHeight - callPopupEl.offsetHeight - 8, e.clientY - offsetY));
            callPopupEl.style.left = `${left}px`;
            callPopupEl.style.top = `${top}px`;
            callPopupEl.style.right = 'auto';
            callPopupEl.style.bottom = 'auto';
        });

        callPopupHeaderEl.addEventListener('pointerup', (e) => {
            stopDrag(e);
        });

        callPopupHeaderEl.addEventListener('pointercancel', (e) => {
            stopDrag(e);
        });

        // Safety: if pointerup happens outside header, still stop dragging.
        window.addEventListener('pointerup', stopDrag, true);
        window.addEventListener('pointercancel', stopDrag, true);
    })();

    // When clicking call buttons, notify the other member first, then open popup.
    document.addEventListener('click', async function (e) {
        const a = e.target && e.target.closest ? e.target.closest('[data-call-btn]') : null;
        if (!a) return;
        e.preventDefault();

        const type = a.getAttribute('data-call-type') || 'voice';
        try {
            const body = new URLSearchParams();
            body.set('type', type);
            await fetch(inviteUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': (typeof getCookie === 'function' ? getCookie('csrftoken') : ''),
                },
                body,
            });
        } catch {
            // ignore
        }
        await openCallPopup(type, 'caller');
    }, true);

    async function poll() {
        // Fallback: if websocket isn't connected, poll for new messages
        if (__wsIsOpen()) {
            wsConnected = true;
            return;
        }
        wsConnected = false;
        if (__pollInFlight) return;
        __pollInFlight = true;
        try {
            try {
                if (document.visibilityState === 'hidden') return;
            } catch {
                // ignore
            }
            updateLastIdFromDom();
            const res = await fetch(`${pollUrl}?after=${lastId}`, {
                credentials: 'same-origin',
                headers: { 'X-Vixo-No-Loading': '1' },
            });
            if (!res.ok) return;
            const data = await res.json();
            if (data && typeof data.online_count !== 'undefined') {
                __setOnlineCount(data.online_count);
            }
            if (data && data.messages_html) {
                const __wasNearBottom = isNearBottom();
                const emptyEl = document.getElementById('empty_state');
                if (emptyEl) emptyEl.remove();
                if (messagesEl && messagesEl.classList.contains('hidden')) {
                    messagesEl.classList.remove('hidden');
                }
                messagesEl.insertAdjacentHTML('beforeend', data.messages_html);
                hydrateLocalTimes(messagesEl);
                applyConsecutiveHeaderGrouping(messagesEl);
                updateLastIdFromDom();
                if (__chatAutoScrollEnabled && __wasNearBottom) forceScrollToBottomNow();
            }
            if (data && typeof data.last_id !== 'undefined') {
                const newLast = parseInt(String(data.last_id), 10);
                if (!Number.isNaN(newLast) && newLast > lastId) lastId = newLast;
            }
        } catch {
            // ignore
        } finally {
            __pollInFlight = false;
        }
    }

    // Initial load: ensure we land on the latest message.
    // (On first render we are not "near bottom", so guarded autoscroll would do nothing.)
    (function initialScrollToLatest() {
        if (window.__didInitialChatScroll) return;
        window.__didInitialChatScroll = true;

        // Hide chat until we've snapped to bottom to avoid the “starts at top then scrolls down” effect.
        // (Visibility is controlled via the template-added class.)
        hardScrollToBottom();
        revealChatContainer();

        // Run a few times to handle layout/avatars loading.
        try {
            requestAnimationFrame(() => {
                forceScrollToBottomNow();
                revealChatContainer();
                requestAnimationFrame(() => {
                    forceScrollToBottomNow();
                    revealChatContainer();
                });
            });
        } catch {
            // ignore
        }
        setTimeout(() => { forceScrollToBottomNow(); revealChatContainer(); }, 0);
        setTimeout(() => { forceScrollToBottomNow(); revealChatContainer(); }, 120);
        setTimeout(() => { forceScrollToBottomNow(); revealChatContainer(); }, 320);
    })();

    startPolling();
    connect();

    function clearReply() {
        if (replyToIdInput) replyToIdInput.value = '';
        if (replyBar) replyBar.classList.add('hidden');
        if (replyBarAuthor) replyBarAuthor.textContent = '';
        if (replyBarPreview) replyBarPreview.textContent = '';
    }

    function normalizeReplyPreview(text) {
        const collapsed = String(text || '').replace(/\s+/g, ' ').trim();
        if (!collapsed) return '';
        if (collapsed.length <= 160) return collapsed;
        return `${collapsed.slice(0, 160)}…`;
    }

    if (replyBarCancel) {
        replyBarCancel.addEventListener('click', function () {
            clearReply();
            if (input) input.focus();
        });
    }

    // Click "Reply" on a message bubble
    document.addEventListener('click', function (e) {
        const btn = e.target && e.target.closest ? e.target.closest('[data-reply-button]') : null;
        if (!btn) return;

        const msgId = btn.getAttribute('data-reply-to-id') || '';
        const author = btn.getAttribute('data-reply-author') || '';
        const preview = normalizeReplyPreview(btn.getAttribute('data-reply-preview') || '');

        if (replyToIdInput) replyToIdInput.value = msgId;
        if (replyBarAuthor) replyBarAuthor.textContent = author;
        if (replyBarPreview) replyBarPreview.textContent = preview;
        if (replyBar) replyBar.classList.remove('hidden');
        if (input) input.focus();
    }, true);

    // Click replied-to snippet to jump to original
    function __flashReplyTarget(msgEl) {
        if (!msgEl) return;
        const row = (msgEl.closest && msgEl.closest('.vixo-msg')) || msgEl;
        if (!row) return;

        const existing = row.querySelector('[data-reply-highlight]');
        if (existing) {
            try { existing.remove(); } catch {}
        }

        const overlay = document.createElement('div');
        overlay.setAttribute('data-reply-highlight', '1');
        overlay.className = 'absolute inset-x-0 -inset-y-1 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 pointer-events-none';
        row.insertBefore(overlay, row.firstChild);

        setTimeout(() => {
            try { overlay.remove(); } catch {}
        }, 1600);
    }

    document.addEventListener('click', function (e) {
        const jump = e.target && e.target.closest ? e.target.closest('[data-scroll-to]') : null;
        if (!jump) return;
        const targetId = jump.getAttribute('data-scroll-to');
        if (!targetId) return;
        const el = document.getElementById(targetId);
        if (!el) return;
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Flash highlight so it's obvious which message was referenced.
        setTimeout(() => { __flashReplyTarget(el); }, 220);
    }, true);

    (function initImageViewer() {
        // Click any <img data-image-viewer> to open zoomable viewer.
        // Supports: pinch-zoom (mobile), wheel-zoom (desktop), drag-to-pan, double-tap/dblclick to toggle zoom.
        const isIOS = () => {
            try {
                return /iPad|iPhone|iPod/.test(navigator.userAgent || '') && !window.MSStream;
            } catch {
                return false;
            }
        };

        let overlay = null;
        let stage = null;
        let pan = null;
        let img = null;
        let hint = null;
        let closeBtn = null;

        let scale = 1;
        let tx = 0;
        let ty = 0;
        const MIN_SCALE = 1;
        const MAX_SCALE = 4;

        // touch state
        let touchMode = '';
        let startDist = 0;
        let startScale = 1;
        let startTx = 0;
        let startTy = 0;
        let startX = 0;
        let startY = 0;
        let lastTapAt = 0;

        function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

        function apply() {
            if (!pan || !img) return;
            pan.style.transform = `translate3d(${tx}px, ${ty}px, 0)`;
            img.style.transform = `scale(${scale})`;
            img.style.cursor = scale > 1 ? 'grab' : 'auto';
        }

        function reset() {
            scale = 1;
            tx = 0;
            ty = 0;
            apply();
        }

        function ensure() {
            if (overlay) return;

            overlay = document.createElement('div');
            overlay.id = 'vixo_image_viewer';
            overlay.className = 'fixed inset-0 z-[90] hidden';
            overlay.innerHTML = `
                <div data-iv-backdrop class="absolute inset-0 bg-black/70"></div>
                <button type="button" data-iv-close class="absolute z-20 top-3 right-3 sm:top-5 sm:right-5 h-10 w-10 rounded-full bg-gray-900/70 border border-gray-700 text-gray-100 hover:bg-gray-800/80 transition" aria-label="Close">
                    <span aria-hidden="true">×</span>
                </button>
                <div data-iv-stage class="absolute inset-0 flex items-center justify-center p-3 sm:p-6">
                    <div data-iv-pan class="max-w-full max-h-full" style="transform: translate3d(0,0,0);">
                        <img data-iv-img class="max-w-[95vw] max-h-[85vh] object-contain select-none" draggable="false" style="transform: scale(1); transform-origin: center center;" />
                    </div>
                </div>
                <div data-iv-hint class="absolute z-20 bottom-4 left-1/2 -translate-x-1/2 text-[11px] text-gray-100/80 bg-gray-900/60 border border-gray-800 rounded-full px-3 py-1.5">
                    Pinch/scroll to zoom • Double tap to reset
                </div>
            `;
            document.body.appendChild(overlay);

            stage = overlay.querySelector('[data-iv-stage]');
            pan = overlay.querySelector('[data-iv-pan]');
            img = overlay.querySelector('[data-iv-img]');
            hint = overlay.querySelector('[data-iv-hint]');
            closeBtn = overlay.querySelector('[data-iv-close]');

            // Prevent browser gestures while interacting.
            if (stage) stage.style.touchAction = 'none';

            function close() {
                overlay.classList.add('hidden');
                if (!isIOS()) document.body.classList.remove('overflow-hidden');
                if (img) img.src = '';
                reset();
            }

            closeBtn?.addEventListener('click', close);
            overlay.addEventListener('click', (e) => {
                if (e.target && e.target.closest && e.target.closest('[data-iv-close]')) return;
                const backdrop = e.target && e.target.closest ? e.target.closest('[data-iv-backdrop]') : null;
                if (backdrop) close();
            });

            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && overlay && !overlay.classList.contains('hidden')) close();
            });

            // Zoom with wheel (desktop)
            stage?.addEventListener('wheel', (e) => {
                if (!overlay || overlay.classList.contains('hidden')) return;
                e.preventDefault();
                const delta = e.deltaY;
                const factor = delta < 0 ? 1.12 : 0.9;
                const next = clamp(scale * factor, MIN_SCALE, MAX_SCALE);
                if (next === scale) return;
                scale = next;
                if (scale <= 1) {
                    tx = 0;
                    ty = 0;
                }
                apply();
            }, { passive: false });

            // Double click to toggle zoom
            stage?.addEventListener('dblclick', (e) => {
                if (!overlay || overlay.classList.contains('hidden')) return;
                e.preventDefault();
                if (scale > 1) {
                    reset();
                } else {
                    scale = 2.5;
                    apply();
                }
            });

            // Touch: pinch + pan + double tap
            stage?.addEventListener('touchstart', (e) => {
                if (!overlay || overlay.classList.contains('hidden')) return;
                if (!e.touches) return;

                // double tap
                if (e.touches.length === 1) {
                    const now = Date.now();
                    if (now - lastTapAt < 280) {
                        e.preventDefault();
                        if (scale > 1) {
                            reset();
                        } else {
                            scale = 2.5;
                            apply();
                        }
                        lastTapAt = 0;
                        return;
                    }
                    lastTapAt = now;
                }

                if (e.touches.length === 2) {
                    touchMode = 'pinch';
                    const dx = e.touches[0].clientX - e.touches[1].clientX;
                    const dy = e.touches[0].clientY - e.touches[1].clientY;
                    startDist = Math.hypot(dx, dy);
                    startScale = scale;
                    startTx = tx;
                    startTy = ty;
                    e.preventDefault();
                    return;
                }

                if (e.touches.length === 1 && scale > 1) {
                    touchMode = 'pan';
                    startX = e.touches[0].clientX;
                    startY = e.touches[0].clientY;
                    startTx = tx;
                    startTy = ty;
                    e.preventDefault();
                }
            }, { passive: false });

            stage?.addEventListener('touchmove', (e) => {
                if (!overlay || overlay.classList.contains('hidden')) return;
                if (!e.touches) return;

                if (touchMode === 'pinch' && e.touches.length === 2) {
                    const dx = e.touches[0].clientX - e.touches[1].clientX;
                    const dy = e.touches[0].clientY - e.touches[1].clientY;
                    const dist = Math.hypot(dx, dy);
                    if (!startDist) return;
                    const next = clamp(startScale * (dist / startDist), MIN_SCALE, MAX_SCALE);
                    scale = next;
                    if (scale <= 1) {
                        tx = 0;
                        ty = 0;
                    } else {
                        tx = startTx;
                        ty = startTy;
                    }
                    apply();
                    e.preventDefault();
                    return;
                }

                if (touchMode === 'pan' && e.touches.length === 1 && scale > 1) {
                    const dx = e.touches[0].clientX - startX;
                    const dy = e.touches[0].clientY - startY;
                    tx = startTx + dx;
                    ty = startTy + dy;
                    apply();
                    e.preventDefault();
                }
            }, { passive: false });

            stage?.addEventListener('touchend', () => {
                touchMode = '';
                startDist = 0;
            }, { passive: true });

            // Mouse pan (desktop)
            let mouseDown = false;
            stage?.addEventListener('mousedown', (e) => {
                if (!overlay || overlay.classList.contains('hidden')) return;
                if (scale <= 1) return;
                mouseDown = true;
                startX = e.clientX;
                startY = e.clientY;
                startTx = tx;
                startTy = ty;
                try { e.preventDefault(); } catch {}
            });
            window.addEventListener('mousemove', (e) => {
                if (!mouseDown) return;
                if (!overlay || overlay.classList.contains('hidden')) return;
                if (scale <= 1) return;
                tx = startTx + (e.clientX - startX);
                ty = startTy + (e.clientY - startY);
                apply();
            });
            window.addEventListener('mouseup', () => { mouseDown = false; });

            // Hide hint after a moment
            setTimeout(() => {
                try { hint?.classList.add('opacity-0'); } catch {}
            }, 1800);
        }

        function openWith(src, alt) {
            ensure();
            if (!overlay || !img) return;
            img.src = src;
            img.alt = alt || 'Image';
            overlay.classList.remove('hidden');
            // We can lock scroll safely here (no inputs), but avoid iOS quirks.
            if (!isIOS()) document.body.classList.add('overflow-hidden');
            reset();
            // show hint each open
            try {
                hint?.classList.remove('opacity-0');
                setTimeout(() => { try { hint?.classList.add('opacity-0'); } catch {} }, 1600);
            } catch {}
        }

        document.addEventListener('click', function (e) {
            const el = e.target && e.target.closest ? e.target.closest('img[data-image-viewer]') : null;
            if (!el) return;
            const src = el.getAttribute('src') || '';
            if (!src) return;
            e.preventDefault();
            e.stopPropagation();
            openWith(src, el.getAttribute('alt') || 'Image');
        }, true);
    })();

    (function initOneTimeView() {
        // Handles one-time photos:
        // - Hidden bubble is rendered in HTML.
        // - Clicking POSTs to server to record this viewer as having opened it.
        // - Client shows photo with an animated countdown, then removes the message for this viewer.

        const countdownTimers = new WeakMap();

        function getCsrf() {
            try { return (typeof getCookie === 'function' ? getCookie('csrftoken') : ''); } catch { return ''; }
        }

        function renderExpired(container) {
            if (!container) return;
            try {
                container.innerHTML = '<div class="rounded-2xl border border-gray-700 bg-gray-900/40 px-4 py-4 text-sm text-gray-200" data-one-time-expired>Photo expired</div>';
            } catch {}
        }

        function removeMessageForViewer(container) {
            const msg = container && container.closest ? (container.closest('.vixo-msg') || container) : container;
            if (!msg) return;
            try {
                msg.style.transition = 'opacity 200ms ease, transform 200ms ease';
                msg.style.opacity = '0';
                msg.style.transform = 'translateY(-4px)';
            } catch {}
            window.setTimeout(() => {
                try { msg.remove(); } catch {}
            }, 220);
        }

        function clearCountdown(container) {
            const prev = countdownTimers.get(container);
            if (!prev) return;
            try { window.clearTimeout(prev.timeoutId); } catch {}
            try { window.clearInterval(prev.intervalId); } catch {}
            countdownTimers.delete(container);
        }

        function startCountdown(container, seconds, expiresAtSec) {
            if (!container) return;
            clearCountdown(container);

            const endMs = ((expiresAtSec && expiresAtSec > 0) ? expiresAtSec : (Math.floor(Date.now() / 1000) + seconds)) * 1000;
            let remaining = Math.max(0, Math.ceil((endMs - Date.now()) / 1000));
            if (remaining <= 0) {
                removeMessageForViewer(container);
                return;
            }

            const label = container.querySelector('[data-one-time-remaining]');
            const progress = container.querySelector('[data-one-time-progress]');
            if (label) label.textContent = String(remaining);

            // Animate progress bar from full -> empty.
            try {
                if (progress) {
                    progress.style.width = '100%';
                    progress.style.transition = `width ${remaining}s linear`;
                    requestAnimationFrame(() => {
                        try { progress.style.width = '0%'; } catch {}
                    });
                }
            } catch {}

            const intervalId = window.setInterval(() => {
                remaining = Math.max(0, Math.ceil((endMs - Date.now()) / 1000));
                if (label) label.textContent = String(remaining);
            }, 250);

            const timeoutId = window.setTimeout(() => {
                clearCountdown(container);
                removeMessageForViewer(container);
            }, remaining * 1000);

            countdownTimers.set(container, { intervalId, timeoutId });
        }

        async function openOneTime(btn) {
            const container = btn.closest('[data-one-time-container]') || btn.parentElement;
            if (!container) return;

            const url = btn.getAttribute('data-one-time-open-url') || '';
            const fileUrl = btn.getAttribute('data-one-time-file-url') || '';
            const fallbackSeconds = parseInt(btn.getAttribute('data-one-time-seconds') || '0', 10) || 0;
            if (!url || !fileUrl) return;

            btn.disabled = true;
            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'X-CSRFToken': getCsrf(),
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                });

                const data = await resp.json().catch(() => null);
                if (!resp.ok || !data || !data.ok) {
                    renderExpired(container);
                    return;
                }

                const seconds = parseInt(data.seconds || fallbackSeconds || '0', 10) || fallbackSeconds || 0;
                const expiresAt = parseInt(data.expires_at || '0', 10) || 0;

                container.innerHTML = `
                    <div class="relative">
                        <img class="w-full h-auto rounded-lg cursor-zoom-in" src="${fileUrl}" alt="Image" loading="lazy" data-image-viewer />
                        <div class="absolute inset-0 pointer-events-none">
                            <div class="absolute top-2 left-2 inline-flex items-center gap-2 rounded-full bg-black/60 border border-white/10 px-2.5 py-1 text-[11px] text-white">
                                <span data-one-time-remaining>${seconds}</span><span>s</span>
                            </div>
                            <div class="absolute bottom-0 left-0 right-0 h-1 bg-white/10 rounded-b-lg overflow-hidden">
                                <div data-one-time-progress class="h-full bg-emerald-400/80"></div>
                            </div>
                        </div>
                    </div>
                `;

                startCountdown(container, seconds, expiresAt);
            } catch {
                try { btn.disabled = false; } catch {}
            }
        }

        document.addEventListener('click', (e) => {
            const btn = e.target && e.target.closest ? e.target.closest('[data-one-time-open-btn]') : null;
            if (!btn) return;
            e.preventDefault();
            e.stopPropagation();
            openOneTime(btn);
        }, true);
    })();

    (function initGifPicker() {
        if (window.__vixoGifPickerInitDone) return;
        const gifsAllowed = !!cfg.gifsAllowed;
        const apiKey = String(cfg.giphyApiKey || '').trim();
        const limit = parseInt(cfg.giphyLimit || '30', 10) || 30;

        if (!gifsAllowed || !apiKey) return;

        const btn = document.getElementById('gif_btn');
        const panel = document.getElementById('gif_panel');
        const closeBtn = document.getElementById('gif_close');
        const searchInput = document.getElementById('gif_search');
        const statusEl = document.getElementById('gif_status');
        const resultsEl = document.getElementById('gif_results');
        const form = document.getElementById('chat_message_form');
        const input = document.getElementById('id_body');

        if (!btn || !panel || !searchInput || !resultsEl || !form || !input) return;

        let open = false;
        let debounceId = null;
        let activeReq = 0;
        let hasLoadedInitial = false;

        function scheduleReposition() {
            if (!open) return;
            // Let layout settle (images, fonts) then reposition.
            window.setTimeout(() => { try { positionPanel(); } catch {} }, 0);
            window.setTimeout(() => { try { positionPanel(); } catch {} }, 60);
            window.setTimeout(() => { try { positionPanel(); } catch {} }, 220);
        }

        function positionPanel() {
            if (!panel || !btn) return;
            if (panel.classList.contains('hidden')) return;

            // Desktop: CSS (`sm:absolute ... sm:bottom-full ...`) handles stable positioning.
            // JS positioning on desktop caused the perceived "hover drift" when transforms/images load.
            try {
                if (window.matchMedia && window.matchMedia('(min-width: 640px)').matches) {
                    panel.style.left = '';
                    panel.style.right = '';
                    panel.style.top = '';
                    panel.style.bottom = '';
                    panel.style.display = '';
                    panel.style.visibility = '';
                    return;
                }
            } catch {}

            // Ensure we have measurable dimensions.
            const prevVis = panel.style.visibility;
            panel.style.visibility = 'hidden';
            panel.style.display = 'block';

            const panelRect = panel.getBoundingClientRect();
            const panelW = panelRect.width || 384;
            const panelH = panelRect.height || 320;
            const btnRect = btn.getBoundingClientRect();

            const padding = 12;
            const gap = 10;

            // Right-align to button, clamp to viewport.
            let left = btnRect.right - panelW;
            left = Math.max(padding, Math.min(left, window.innerWidth - panelW - padding));

            // Prefer above button; if not enough room, place below.
            const canPlaceAbove = (btnRect.top - panelH - gap) >= padding;

            panel.style.left = `${Math.round(left)}px`;
            panel.style.right = 'auto';

            if (canPlaceAbove) {
                // Anchor using TOP above the button so late-loading images don't push it down.
                let top = btnRect.top - gap - panelH;
                top = Math.max(padding, Math.min(top, window.innerHeight - panelH - padding));
                panel.style.top = `${Math.round(top)}px`;
                panel.style.bottom = 'auto';
            } else {
                let top = btnRect.bottom + gap;
                top = Math.max(padding, Math.min(top, window.innerHeight - panelH - padding));
                panel.style.top = `${Math.round(top)}px`;
                panel.style.bottom = 'auto';
            }

            panel.style.visibility = prevVis || '';
        }

        function setPanelOpen(next) {
            open = !!next;
            if (open) {
                panel.classList.remove('hidden');
                // Place it immediately (without flicker).
                try { panel.style.visibility = 'hidden'; } catch {}
                positionPanel();
                requestAnimationFrame(() => {
                    try {
                        panel.classList.remove('opacity-0', 'scale-95', 'pointer-events-none');
                        panel.classList.add('opacity-100', 'scale-100', 'pointer-events-auto');
                    } catch {}
                    try { panel.style.visibility = ''; } catch {}
                });
                try { searchInput.focus(); } catch {}
            } else {
                try {
                    panel.classList.add('opacity-0', 'scale-95', 'pointer-events-none');
                    panel.classList.remove('opacity-100', 'scale-100', 'pointer-events-auto');
                } catch {}
                window.setTimeout(() => {
                    if (!open) {
                        try { panel.classList.add('hidden'); } catch {}
                    }
                }, 160);
            }
        }

        function renderStatus(text) {
            if (!statusEl) return;
            statusEl.textContent = String(text || '');
        }

        function renderResults(items) {
            resultsEl.innerHTML = '';
            if (!items || !items.length) {
                resultsEl.innerHTML = '<div class="col-span-2 text-xs text-gray-400">No GIFs found.</div>';
                return;
            }
            const frag = document.createDocumentFragment();
            for (const it of items) {
                const images = it && it.images ? it.images : null;
                const url = images && images.fixed_width && images.fixed_width.url ? String(images.fixed_width.url) : '';
                const thumb = images && images.fixed_width_small && images.fixed_width_small.url ? String(images.fixed_width_small.url) : url;
                if (!url) continue;
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'relative overflow-hidden rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 transition';
                b.setAttribute('data-gif-url', url);
                b.innerHTML = `<img src="${__escapeHtml(thumb)}" alt="GIF" class="w-full h-28 object-cover" loading="lazy" decoding="async" />`;
                frag.appendChild(b);
            }
            resultsEl.appendChild(frag);

            // Reposition after thumbnails load to prevent perceived drift.
            try {
                resultsEl.querySelectorAll('img').forEach((img) => {
                    img.addEventListener('load', scheduleReposition, { once: true });
                    img.addEventListener('error', scheduleReposition, { once: true });
                });
            } catch {}

            scheduleReposition();
        }

        async function search(q) {
            const query = String(q || '').trim();
            if (!query) {
                renderStatus('Trending GIFs');
                if (!hasLoadedInitial) {
                    await loadTrending();
                }
                return;
            }

            const reqId = ++activeReq;
            renderStatus('Searching...');
            try {
                const url = `https://api.giphy.com/v1/gifs/search?q=${encodeURIComponent(query)}&api_key=${encodeURIComponent(apiKey)}&limit=${encodeURIComponent(String(limit))}`;
                const resp = await fetch(url, { method: 'GET' });
                const data = await resp.json().catch(() => null);
                if (reqId !== activeReq) return;
                const items = data && Array.isArray(data.data) ? data.data : [];
                renderStatus(items.length ? `Results: ${items.length}` : 'No results');
                renderResults(items);
            } catch {
                if (reqId !== activeReq) return;
                renderStatus('Failed to load GIFs.');
                resultsEl.innerHTML = '<div class="col-span-2 text-xs text-red-300">Could not reach Giphy.</div>';
            }
        }

        async function loadTrending() {
            const reqId = ++activeReq;
            renderStatus('Loading trending...');
            try {
                const url = `https://api.giphy.com/v1/gifs/trending?api_key=${encodeURIComponent(apiKey)}&limit=${encodeURIComponent(String(limit))}`;
                const resp = await fetch(url, { method: 'GET' });
                const data = await resp.json().catch(() => null);
                if (reqId !== activeReq) return;
                const items = data && Array.isArray(data.data) ? data.data : [];
                hasLoadedInitial = true;
                renderStatus(items.length ? 'Trending GIFs' : 'No trending GIFs');
                renderResults(items);
            } catch {
                if (reqId !== activeReq) return;
                renderStatus('Failed to load GIFs.');
                resultsEl.innerHTML = '<div class="col-span-2 text-xs text-red-300">Could not reach Giphy.</div>';
            }
        }

        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const next = !open;
            setPanelOpen(next);
            if (next) {
                // Show something immediately.
                const q = String(searchInput.value || '').trim();
                if (!q) loadTrending();
                scheduleReposition();
            }
        });
        if (closeBtn) closeBtn.addEventListener('click', (e) => { e.preventDefault(); setPanelOpen(false); });

        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            if (!open) return;
            setPanelOpen(false);
        }, true);

        // Close on outside click.
        document.addEventListener('click', (e) => {
            if (!open) return;
            const inside = e.target && e.target.closest ? e.target.closest('#gif_panel, #gif_btn') : null;
            if (!inside) setPanelOpen(false);
        }, true);

        // Keep anchored when the page/layout changes.
        window.addEventListener('resize', () => { if (open) positionPanel(); }, { passive: true });
        window.addEventListener('scroll', () => { if (open) positionPanel(); }, true);

        // Reposition on pointer hover (user mentioned hover causes drift).
        try {
            panel.addEventListener('pointerenter', scheduleReposition, { passive: true });
            panel.addEventListener('pointermove', () => { if (open) positionPanel(); }, { passive: true });
        } catch {}

        searchInput.addEventListener('input', () => {
            if (debounceId) window.clearTimeout(debounceId);
            debounceId = window.setTimeout(() => search(searchInput.value), 250);
        });

        resultsEl.addEventListener('click', (e) => {
            const btn = e.target && e.target.closest ? e.target.closest('[data-gif-url]') : null;
            if (!btn) return;
            const url = String(btn.getAttribute('data-gif-url') || '').trim();
            if (!url) return;

            const gifBody = `[GIF] ${url}`;
            setPanelOpen(false);

            // Private chats: send instantly without showing the GIF body in the input.
            // We temporarily set the value for the submit handler, then restore immediately.
            const prevValue = input.value;
            if (typeof __linksAllowed !== 'undefined' && __linksAllowed) {
                try {
                    input.value = gifBody;
                    if (form.requestSubmit) form.requestSubmit();
                    else {
                        const send = document.getElementById('chat_send_btn');
                        if (send) send.click();
                    }
                } catch {
                    // ignore
                } finally {
                    try { input.value = prevValue; } catch {}
                }
                return;
            }

            // Non-private: keep the old UX.
            input.value = gifBody;
            try {
                if (form.requestSubmit) form.requestSubmit();
                else {
                    const send = document.getElementById('chat_send_btn');
                    if (send) send.click();
                }
            } catch {}
        });

        // Initial state
        renderStatus('Trending GIFs');
        resultsEl.innerHTML = '<div class="col-span-2 text-xs text-gray-400">Opening…</div>';
    })();

    (function initGifHoverPlayback() {
        // Only affects GIF messages rendered as <video data-gif-player>.
        // Behavior:
        // - Not autoplay
        // - Hover -> play up to 6 times then stop
        // - Scroll -> stop immediately

        const container = document.getElementById('chat_container') || document;
        const isTouchMode = (() => {
            try {
                if (window.matchMedia && window.matchMedia('(hover: none) and (pointer: coarse)').matches) return true;
            } catch {}
            try {
                if (navigator && typeof navigator.maxTouchPoints === 'number' && navigator.maxTouchPoints > 0) return true;
            } catch {}
            return false;
        })();

        const maxLoopsDefault = 6;
        const maxLoopsTouch = 5;
        const state = new WeakMap();
        let scrollStopAt = 0;

        function now() { return Date.now(); }

        function isVisible(el) {
            try {
                const r = el.getBoundingClientRect();
                return r.bottom > 0 && r.right > 0 && r.top < (window.innerHeight || 0) && r.left < (window.innerWidth || 0);
            } catch {
                return true;
            }
        }

        function fallbackToImg(video) {
            try {
                const gifUrl = video.getAttribute('data-gif-url') || '';
                if (!gifUrl) return;
                const img = document.createElement('img');
                img.className = video.className || 'w-full h-auto rounded-lg';
                img.src = gifUrl;
                img.alt = 'GIF';
                img.loading = 'lazy';
                img.decoding = 'async';
                video.replaceWith(img);
            } catch {}
        }

        function ensure(video) {
            if (!video || state.has(video)) return;

            const st = {
                active: false,
                loops: 0,
                maxLoops: isTouchMode
                    ? maxLoopsTouch
                    : (parseInt(video.getAttribute('data-gif-loops') || String(maxLoopsDefault), 10) || maxLoopsDefault),
                inCycle: false,
                cooldownUntil: 0,
            };
            state.set(video, st);

            try {
                video.autoplay = false;
                video.loop = false;
                video.muted = true;
                video.playsInline = true;
            } catch {}

            function stop(resetToStart) {
                try { video.pause(); } catch {}
                st.inCycle = false;
                if (resetToStart) {
                    try { video.currentTime = 0; } catch {}
                }
            }

            async function playOnce() {
                try {
                    if (!isVisible(video)) return;
                    await video.play();
                } catch {
                    // ignore (autoplay policy etc)
                }
            }

            function startCycle() {
                const t = now();
                if (t < st.cooldownUntil) return;
                if (!st.active) return;
                if (!isVisible(video)) return;

                st.loops = 0;
                st.inCycle = true;
                try { video.currentTime = 0; } catch {}
                playOnce();
            }

            video.addEventListener('ended', () => {
                if (!state.has(video)) return;
                // Stop if user scrolled recently.
                if (now() - scrollStopAt < 350) {
                    stop(true);
                    st.active = false;
                    return;
                }
                if (!st.active) {
                    stop(true);
                    return;
                }

                st.loops += 1;
                if (st.loops >= st.maxLoops) {
                    stop(true);
                    st.active = false;
                    return;
                }

                // Replay
                try { video.currentTime = 0; } catch {}
                playOnce();
            });

            video.addEventListener('error', () => fallbackToImg(video), { once: true });

            if (!isTouchMode) {
                video.addEventListener('pointerenter', () => {
                    st.active = true;
                    startCycle();
                });
                video.addEventListener('pointerleave', () => {
                    st.active = false;
                    stop(true);
                });
                video.addEventListener('pointermove', () => {
                    // If scroll stopped playback while cursor stayed on top, moving cursor should restart.
                    if (!st.active) return;
                    if (st.inCycle) return;
                    startCycle();
                }, { passive: true });
            } else {
                // Mobile: tap to play (5 loops) then stop. Tap again restarts.
                video.addEventListener('click', (e) => {
                    try { e.preventDefault(); e.stopPropagation(); } catch {}
                    if (st.inCycle) {
                        st.active = false;
                        stop(true);
                        return;
                    }
                    st.active = true;
                    startCycle();
                }, true);
            }

            // If it leaves viewport, stop.
            try {
                const obs = new IntersectionObserver((entries) => {
                    for (const en of entries) {
                        if (en.target !== video) continue;
                        if (!en.isIntersecting) stop(true);
                    }
                }, { threshold: 0.1 });
                obs.observe(video);
            } catch {}
        }

        function scan(root) {
            const r = root || document;
            try {
                r.querySelectorAll('video[data-gif-player]').forEach((v) => ensure(v));
            } catch {}
        }

        function stopAllFromScroll() {
            scrollStopAt = now();
            try {
                document.querySelectorAll('video[data-gif-player]').forEach((v) => {
                    const st = state.get(v);
                    if (st) st.cooldownUntil = now() + 250;
                    if (st) st.active = false;
                    try { v.pause(); } catch {}
                    try { v.currentTime = 0; } catch {}
                    if (st) st.inCycle = false;
                });
            } catch {}
        }

        scan(document);

        // Stop on scroll (user asked).
        try {
            container.addEventListener('scroll', stopAllFromScroll, { passive: true });
        } catch {}
        try {
            window.addEventListener('scroll', stopAllFromScroll, { passive: true });
        } catch {}

        // New messages inserted: scan them.
        const messages = document.getElementById('chat_messages');
        if (messages && typeof MutationObserver !== 'undefined') {
            const mo = new MutationObserver((mutations) => {
                for (const m of mutations) {
                    for (const node of m.addedNodes || []) {
                        if (!(node instanceof HTMLElement)) continue;
                        scan(node);
                    }
                }
            });
            try { mo.observe(messages, { childList: true, subtree: true }); } catch {}
        }
    })();

    (function initMobileSidebarToggle() {
        const mobileNav = document.getElementById('chat_mobile_nav');
        const sidebar = document.getElementById('chat_sidebar');
        const panel = document.getElementById('chat_sidebar_panel');
        const openBtn = document.getElementById('chat_sidebar_open');
        const closeBtn = document.getElementById('chat_sidebar_close');
        const mobileTabChat = document.getElementById('chat_mobile_tab_chat');
        const mobileTabGroups = document.getElementById('chat_mobile_tab_groups');
        const mobileTabProfile = document.getElementById('chat_mobile_tab_profile');
        if (!sidebar || !panel) return;

        const isMobile = () => !window.matchMedia('(min-width: 1024px)').matches;
        const isIOS = () => {
            try {
                return /iPad|iPhone|iPod/.test(navigator.userAgent || '') && !window.MSStream;
            } catch {
                return false;
            }
        };

        const overlayClasses = [
            'fixed', 'inset-0', 'z-50',
            'flex', 'items-stretch', 'justify-stretch',
            'bg-gray-900/60'
        ];

        function setMobileTab(tab) {
            if (!mobileTabChat || !mobileTabGroups) return;
            const groupsActive = tab === 'groups';
            if (mobileNav) {
                mobileNav.dataset.activeTab = tab === 'groups' ? 'groups' : (tab === 'profile' ? 'profile' : 'chat');
            }
            mobileTabGroups.classList.toggle('is-active', groupsActive);
            mobileTabGroups.classList.toggle('text-gray-100', groupsActive);
            mobileTabGroups.classList.toggle('text-gray-300', !groupsActive);

            mobileTabChat.classList.toggle('is-active', !groupsActive);
            mobileTabChat.classList.toggle('text-gray-100', !groupsActive);
            mobileTabChat.classList.toggle('text-gray-300', groupsActive);

            if (mobileTabProfile) {
                const profileActive = tab === 'profile';
                mobileTabProfile.classList.toggle('is-active', profileActive);
                mobileTabProfile.classList.toggle('text-gray-100', profileActive);
                mobileTabProfile.classList.toggle('text-gray-300', !profileActive);
            }
        }

        function setGroupsScrollLock(locked) {
            try {
                document.documentElement.classList.toggle('vixo-mobile-groups-open', !!locked);
            } catch {}
            try {
                document.body.classList.toggle('vixo-mobile-groups-open', !!locked);
            } catch {}
        }

        function closeSidebar() {
            if (!isMobile()) return;
            sidebar.classList.add('hidden');
            sidebar.classList.remove(...overlayClasses);
            if (!isIOS()) document.body.classList.remove('overflow-hidden');
            setGroupsScrollLock(false);
            setMobileTab('chat');
        }

        function openSidebar() {
            if (!isMobile()) return;
            sidebar.classList.remove('hidden');
            sidebar.classList.add(...overlayClasses);
            // iOS Safari: scroll-lock via overflow-hidden can break input focus/typing in fixed overlays.
            if (!isIOS()) document.body.classList.add('overflow-hidden');
            setGroupsScrollLock(true);
            setMobileTab('groups');
        }

        let lastMobile = isMobile();
        function sync(force) {
            const nowMobile = isMobile();
            if (!force && nowMobile === lastMobile) return;
            lastMobile = nowMobile;

            if (!nowMobile) {
                sidebar.classList.remove('hidden');
                sidebar.classList.remove(...overlayClasses);
                if (!isIOS()) document.body.classList.remove('overflow-hidden');
                setGroupsScrollLock(false);
                return;
            }
            // Only auto-close when we actually switch into mobile mode (not on iOS keyboard resize).
            closeSidebar();
        }

        if (openBtn) {
            openBtn.addEventListener('click', openSidebar);
        }
        if (closeBtn) {
            closeBtn.addEventListener('click', closeSidebar);
        }

        if (mobileTabGroups) {
            mobileTabGroups.addEventListener('click', () => {
                openSidebar();
            });
        }

        if (mobileTabChat) {
            mobileTabChat.addEventListener('click', () => {
                closeSidebar();
            });
        }

        if (mobileTabProfile) {
            mobileTabProfile.addEventListener('pointerdown', () => {
                setMobileTab('profile');
            });
        }

        sidebar.addEventListener('click', (e) => {
            if (e.target === sidebar) {
                closeSidebar();
                return;
            }

            const link = e.target && e.target.closest ? e.target.closest('a') : null;
            if (!link) return;
            closeSidebar();
        });

        // Use media-query change instead of window resize (iOS keyboard opens/closes fire resize events).
        const mq = window.matchMedia('(min-width: 1024px)');
        const onMq = () => sync(true);
        try {
            mq.addEventListener('change', onMq);
        } catch {
            try { mq.addListener(onMq); } catch {}
        }

        sync(true);
        setMobileTab('chat');

        try {
            const params = new URLSearchParams(window.location.search || '');
            const initialTab = String(params.get('tab') || '').toLowerCase();
            if (initialTab === 'groups' && isMobile()) {
                openSidebar();
            }

            if (initialTab === 'groups') {
                params.delete('tab');
                const nextQuery = params.toString();
                const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}${window.location.hash || ''}`;
                window.history.replaceState({}, '', nextUrl);
            }
        } catch {
            // ignore
        }

        // Desktop safety: if something accidentally left the page scroll-locked,
        // unlock it so the user can reach the footer.
        try {
            window.setTimeout(() => {
                if (isMobile()) return;

                const body = document.body;
                if (!body || !body.classList.contains('overflow-hidden')) return;

                // Only unlock when no known overlay is visible.
                const globalModal = document.getElementById('global_modal_root');
                const modalOpen = !!(globalModal && !globalModal.classList.contains('hidden') && (globalModal.innerHTML || '').trim().length);

                const sidebarOverlayOpen = sidebar.classList.contains('fixed') || sidebar.classList.contains('inset-0');
                const challengeDrawer = document.getElementById('challenge_drawer');
                const challengeOpen = !!(challengeDrawer && !challengeDrawer.classList.contains('pointer-events-none') && !challengeDrawer.classList.contains('opacity-0'));

                if (!modalOpen && !sidebarOverlayOpen && !challengeOpen) {
                    body.classList.remove('overflow-hidden');
                }
            }, 250);
        } catch {
            // ignore
        }
    })();

    (function initCodeRoomWaitingList() {
        const btn = document.getElementById('code_room_waiting_btn');
        const panel = document.getElementById('code_room_waiting_panel');
        const body = document.getElementById('code_room_waiting_body');
        const closeBtn = document.getElementById('code_room_waiting_close');
        const badge = document.getElementById('code_room_waiting_badge');
        if (!btn || !panel || !body) return;

        let lastRealtimeCount = 0;
        try {
            lastRealtimeCount = Math.max(0, parseInt(String(badge && badge.textContent ? badge.textContent : '0'), 10) || 0);
        } catch {
            lastRealtimeCount = 0;
        }

        const listUrl = btn.getAttribute('data-waiting-list-url') || '';
        const admitUrl = btn.getAttribute('data-waiting-admit-url') || '';

        const getCsrf = () => {
            try { return (typeof getCookie === 'function' ? getCookie('csrftoken') : ''); } catch { return ''; }
        };

        function setBadge(n) {
            if (!badge) return;
            const count = Math.max(0, parseInt(String(n ?? 0), 10) || 0);
            if (count <= 0) {
                badge.textContent = '0';
                badge.style.display = 'none';
                return;
            }
            badge.textContent = String(count);
            badge.style.display = 'flex';
        }

        function renderEmpty(text) {
            body.innerHTML = `<div class="text-xs text-gray-400 px-2 py-3">${__escapeHtml(text || 'No one is waiting.')}</div>`;
        }

        function renderList(items) {
            if (!Array.isArray(items) || items.length === 0) {
                renderEmpty('No one is waiting.');
                return;
            }

            body.innerHTML = '';
            for (const u of items) {
                const row = document.createElement('div');
                row.className = 'flex items-center gap-2 px-2 py-2 rounded-xl hover:bg-gray-800/40';

                const avatar = document.createElement('div');
                avatar.className = 'h-8 w-8 rounded-full bg-gray-800 overflow-hidden flex-none';
                const av = String(u && u.avatar ? u.avatar : '').trim();
                if (av) {
                    avatar.innerHTML = `<img src="${__escapeHtml(av)}" alt="" class="h-full w-full object-cover" />`;
                }

                const meta = document.createElement('div');
                meta.className = 'min-w-0 flex-1';
                const display = String((u && u.display) || (u && u.username) || 'User');
                const username = String((u && u.username) || '');
                meta.innerHTML = `
                    <div class="text-xs font-semibold text-gray-100 truncate">${__escapeHtml(display)}</div>
                    <div class="text-[11px] text-gray-400 truncate">@${__escapeHtml(username)}</div>
                `;

                const admit = document.createElement('button');
                admit.type = 'button';
                admit.className = 'text-[11px] bg-emerald-600 hover:bg-emerald-700 text-white px-2.5 py-1.5 rounded-lg transition-colors flex-none';
                admit.textContent = 'Admit';
                admit.setAttribute('data-admit-user', String(u && u.id ? u.id : ''));

                row.appendChild(avatar);
                row.appendChild(meta);
                row.appendChild(admit);
                body.appendChild(row);
            }
        }

        let refreshing = false;
        async function refresh() {
            if (!listUrl) return;
            if (refreshing) return;
            refreshing = true;
            try {
                body.innerHTML = '<div class="text-xs text-gray-400 px-2 py-3">Loading…</div>';
                const r = await fetch(listUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                const data = await r.json();
                if (!data || !data.ok) {
                    renderEmpty('Failed to load.');
                    setBadge(0);
                    return;
                }
                setBadge(data.count || 0);
                renderList(data.pending || []);
            } catch {
                renderEmpty('Network issue.');
            } finally {
                refreshing = false;
            }
        }

        // Realtime hook: used by websocket events to keep the waiting list live.
        try {
            window.__vixoWaitingListRealtime = (count) => {
                let n = 0;
                try {
                    n = Math.max(0, parseInt(String(count ?? 0), 10) || 0);
                    setBadge(n);
                } catch {
                    // ignore
                }
                try {
                    if (n > lastRealtimeCount) playWaitingFollowSound();
                    lastRealtimeCount = n;
                } catch {
                    // ignore
                }
                try {
                    if (!panel.classList.contains('hidden')) refresh();
                } catch {
                    // ignore
                }
            };
        } catch {
            // ignore
        }

        function open() {
            panel.classList.remove('hidden');
            refresh();
        }

        function close() {
            panel.classList.add('hidden');
        }

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

        body.addEventListener('click', async (e) => {
            const t = e.target && e.target.closest ? e.target.closest('[data-admit-user]') : null;
            if (!t) return;
            const userId = t.getAttribute('data-admit-user') || '';
            if (!userId) return;
            if (!admitUrl) return;

            t.disabled = true;
            try {
                const r = await fetch(admitUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': getCsrf(),
                    },
                    body: JSON.stringify({ user_id: parseInt(userId, 10) }),
                });
                const data = await r.json().catch(() => ({}));
                if (!r.ok || !data || !data.ok) {
                    // Keep UI simple; just refresh to reflect server state.
                }
            } catch {
                // ignore
            } finally {
                t.disabled = false;
                refresh();
            }
        }, true);
    })();
})();
