// Realtime presence + follow-list modal.
// This file can be used on a full profile page and inside the HTMX profile modal.
(function () {
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

    function getCfg() {
        return (window.__vixo_profile_config || readJsonScript('vixo-profile-config') || {});
    }

    let presenceSocket = null;
    let presenceSocketUrl = '';
    let presenceReconnectTimer = null;

    function clearPresenceTimers() {
        try { if (presenceReconnectTimer) clearTimeout(presenceReconnectTimer); } catch {}
        presenceReconnectTimer = null;
    }

    function closePresenceSocket() {
        clearPresenceTimers();
        try {
            if (presenceSocket) {
                presenceSocket.onclose = null;
                presenceSocket.onmessage = null;
                presenceSocket.close();
            }
        } catch {}
        presenceSocket = null;
        presenceSocketUrl = '';
    }

    function setPresenceUi(online, isDnd) {
        const dot = document.getElementById('presence_dot');
        const text = document.getElementById('presence_text');
        if (!dot || !text) return;
        const dnd = !!isDnd;
        dot.classList.toggle('bg-red-500', dnd);
        dot.classList.toggle('bg-emerald-400', !dnd && !!online);
        dot.classList.toggle('bg-gray-500', !dnd && !online);
        text.textContent = dnd ? 'DND' : (online ? 'Online' : 'Offline');
    }

    function initPresence(cfg) {
        const dot = document.getElementById('presence_dot');
        const text = document.getElementById('presence_text');
        if (!dot || !text) {
            // Presence UI not on this page/modal.
            closePresenceSocket();
            return;
        }

        const isDnd = !!cfg.presenceIsDnd;
        if (typeof cfg.presenceOnline === 'boolean') {
            setPresenceUi(cfg.presenceOnline, isDnd);
        }

        const profileUsername = String(cfg.profileUsername || '');
        if (!cfg.presenceWsEnabled || !profileUsername) {
            closePresenceSocket();
            return;
        }

        const wsScheme = (window.location.protocol === 'https:') ? 'wss' : 'ws';
        const wsUrl = `${wsScheme}://${window.location.host}/ws/presence/${encodeURIComponent(profileUsername)}/`;

        // Already connected to the right target.
        if (presenceSocket && presenceSocketUrl === wsUrl && presenceSocket.readyState === WebSocket.OPEN) {
            return;
        }

        // Switch target (or reconnect).
        closePresenceSocket();
        presenceSocketUrl = wsUrl;

        const connect = () => {
            clearPresenceTimers();
            try {
                presenceSocket = new WebSocket(wsUrl);
            } catch {
                presenceSocket = null;
                return;
            }

            presenceSocket.onmessage = (event) => {
                let payload;
                try { payload = JSON.parse(event.data); } catch { return; }
                if (payload && payload.type === 'presence') {
                    if (typeof payload.online === 'boolean') setPresenceUi(payload.online, isDnd);
                }
            };

            presenceSocket.onclose = () => {
                // Basic reconnect (only while tab is visible)
                try {
                    if (document.visibilityState === 'hidden') return;
                } catch {}
                presenceReconnectTimer = setTimeout(connect, 1200);
            };
        };

        connect();
    }

    function initFollowListModal(cfg) {
        const modal = document.getElementById('follow_modal');
        const titleEl = document.getElementById('follow_modal_title');
        const closeBtn = document.getElementById('follow_modal_close');
        const bodyEl = document.getElementById('follow_modal_body');
        const followersEl = document.getElementById('followers_count_value');
        const followingEl = document.getElementById('following_count_value');
        if (!modal || !titleEl || !closeBtn || !bodyEl) return;

        const profileUsername = String((cfg && cfg.profileUsername) || '');
        const isOwner = !!(cfg && cfg.isOwner);

        const open = ({ kind, url }) => {
            modal.dataset.kind = kind;
            modal.dataset.baseUrl = url;
            modal.dataset.full = '0';
            modal.dataset.profileUsername = profileUsername;

            if (kind === 'following') titleEl.textContent = isOwner ? 'Your followings' : 'Following';
            else titleEl.textContent = isOwner ? 'Your followers' : 'Followers';

            modal.classList.remove('hidden');
            modal.setAttribute('aria-hidden', 'false');
            bodyEl.innerHTML = '<div class="text-sm text-gray-400">Loading...</div>';

            try {
                if (window.htmx && typeof window.htmx.ajax === 'function') {
                    window.htmx.ajax('GET', url, { target: '#follow_modal_body', swap: 'innerHTML' });
                }
            } catch {}
        };

        const close = () => {
            modal.classList.add('hidden');
            modal.setAttribute('aria-hidden', 'true');
        };

        closeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            close();
        });
        modal.addEventListener('click', (e) => {
            if (e.target === modal || e.target === modal.firstElementChild) close();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !modal.classList.contains('hidden')) close();
        });

        document.addEventListener('click', (e) => {
            const btn = e.target && e.target.closest ? e.target.closest('[data-follow-modal]') : null;
            if (!btn) return;
            const kind = btn.getAttribute('data-follow-modal');
            const url = btn.getAttribute('data-url');
            if (!kind || !url) return;
            e.preventDefault();
            open({ kind, url });
        }, true);

        document.body.addEventListener('htmx:afterSwap', (e) => {
            try {
                const target = e && e.detail && e.detail.target;
                if (!target || target.id !== 'follow_modal_body') return;
                const state = document.getElementById('follow_modal_state');
                if (!state) return;
                modal.dataset.kind = state.getAttribute('data-kind') || (modal.dataset.kind || '');
                modal.dataset.full = state.getAttribute('data-full') || (modal.dataset.full || '0');
            } catch {}
        });

        document.body.addEventListener('followChanged', (e) => {
            try {
                const detail = (e && e.detail) ? e.detail : {};
                if (!detail || detail.profile_username !== profileUsername) return;

                if (followersEl && typeof detail.followers_count === 'number') followersEl.textContent = String(detail.followers_count);
                if (followingEl && typeof detail.following_count === 'number') followingEl.textContent = String(detail.following_count);

                if (modal.classList.contains('hidden')) return;
                const kind = (modal.dataset.kind || '');
                if (kind !== 'following' && kind !== 'followers') return;
                const baseUrl = modal.dataset.baseUrl || '';
                if (!baseUrl) return;

                const isFull = (modal.dataset.full || '0') === '1';
                const url = isFull ? (baseUrl + '?full=1') : baseUrl;
                if (window.htmx && typeof window.htmx.ajax === 'function') {
                    window.htmx.ajax('GET', url, { target: '#follow_modal_body', swap: 'innerHTML' });
                }
            } catch {}
        });
    }

    function initMyProfileToggle() {
        const toggleBtn = document.querySelector('[data-profile-overview-toggle]');
        const section = document.getElementById('profile_overview_section');
        const quickMenu = document.getElementById('profile_menu');
        const stateEl = toggleBtn ? toggleBtn.querySelector('[data-profile-overview-state]') : null;
        if (!toggleBtn || !section) return;

        const hash = String(window.location.hash || '').toLowerCase();
        const shouldOpenOptionsFirst = (hash === '' || hash === '#profile_menu');
        if (shouldOpenOptionsFirst) {
            section.classList.add('hidden');
        }

        const setState = () => {
            const expanded = !section.classList.contains('hidden');
            toggleBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            if (stateEl) stateEl.textContent = expanded ? 'Hide' : 'Show';
        };

        setState();

        if (shouldOpenOptionsFirst && quickMenu) {
            try { quickMenu.scrollIntoView({ behavior: 'auto', block: 'start' }); } catch {}
        }

        toggleBtn.addEventListener('click', () => {
            section.classList.toggle('hidden');
            setState();
            const expanded = !section.classList.contains('hidden');
            if (expanded) {
                try { section.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch {}
            }
        });
    }

    let followModalInitDone = false;
    function initFollowListModalOnce(cfg) {
        if (followModalInitDone) return;
        // Only relevant for full profile page (modal fragment doesn't include follow list modal).
        const modal = document.getElementById('follow_modal');
        if (!modal) return;
        followModalInitDone = true;
        initFollowListModal(cfg);
    }

    function initAll() {
        const cfg = getCfg();
        initMyProfileToggle();
        initFollowListModalOnce(cfg);
        initPresence(cfg);
    }

    // Initial page load.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }

    // HTMX modal swaps (profile modal opens inside #global_modal_root).
    // Use `document` (not `document.body`) so this works even if the script loads in <head>.
    document.addEventListener('htmx:afterSwap', (e) => {
        try {
            const target = e && e.detail && e.detail.target;
            if (!target) return;
            if (target.id !== 'global_modal_root') return;
            initAll();
        } catch {}
    });
})();
