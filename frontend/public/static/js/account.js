(function () {
    function getProgressEls() {
        try {
            const root = document.getElementById('vixo-auth-progress');
            if (!root) return null;
            return {
                root,
                bar: document.getElementById('vixo-auth-progress-bar'),
                pill: document.getElementById('vixo-auth-progress-pill'),
                text: document.getElementById('vixo-auth-progress-text'),
            };
        } catch {
            return null;
        }
    }

    let progressRunning = false;
    function showAuthProgress() {
        if (progressRunning) return;
        if (!isAuthPage()) return;
        const els = getProgressEls();
        if (!els || !els.root || !els.bar) return;

        progressRunning = true;
        try { els.root.classList.remove('hidden'); } catch {}
        try { if (els.pill) els.pill.classList.remove('hidden'); } catch {}

        let start = null;
        const durationMs = 950;

        const tick = (ts) => {
            if (!start) start = ts;
            const t = Math.min(1, (ts - start) / durationMs);
            const eased = 1 - Math.pow(1 - t, 2.2);
            const pct = Math.max(0, Math.min(100, Math.round(eased * 100)));

            try { els.bar.style.width = pct + '%'; } catch {}
            try { if (els.text) els.text.textContent = pct + '%'; } catch {}

            if (t < 1) {
                requestAnimationFrame(tick);
            }
        };

        try { requestAnimationFrame(tick); } catch {}
    }

    function isAuthPage() {
        try {
            return document.body && document.body.classList.contains('vixo-auth-page');
        } catch {
            return false;
        }
    }

    function runEnterAnimation() {
        if (!isAuthPage()) return;
        try {
            document.body.classList.remove('vixo-page-leave');
            document.body.classList.add('vixo-page-enter');
            // Two RAFs ensures the class is applied before removing.
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    try { document.body.classList.remove('vixo-page-enter'); } catch {}
                });
            });
        } catch {
            // ignore
        }
    }

    function isSameOriginHref(href) {
        try {
            const u = new URL(href, window.location.href);
            return u.origin === window.location.origin;
        } catch {
            return false;
        }
    }

    function shouldHandleLinkClick(e, a) {
        if (!a) return false;
        const href = a.getAttribute('href') || '';
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return false;
        if (a.hasAttribute('download') || a.getAttribute('target') === '_blank') return false;
        if (e.defaultPrevented) return false;
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return false;
        if (e.button && e.button !== 0) return false;
        return isSameOriginHref(href);
    }

    function installPageSwapTransitions() {
        if (!isAuthPage()) return;

        // Fade-in on initial load.
        runEnterAnimation();

        // Fade-in when coming back via bfcache.
        window.addEventListener('pageshow', function () {
            runEnterAnimation();
        });

        document.addEventListener('click', function (e) {
            if (!isAuthPage()) return;
            const a = e.target && e.target.closest ? e.target.closest('a') : null;
            if (!a) return;

            // Only animate swaps between auth pages (signin/signup and related account pages).
            const href = a.getAttribute('href') || '';
            if (!/\/accounts\/(login|signup)\/?/i.test(href)) return;
            if (!shouldHandleLinkClick(e, a)) return;

            e.preventDefault();

            showAuthProgress();
            try {
                document.body.classList.add('vixo-page-leave');
            } catch {
                window.location.href = href;
                return;
            }
            window.setTimeout(function () {
                window.location.href = href;
            }, 170);
        }, true);

        document.addEventListener('submit', function (e) {
            if (!isAuthPage()) return;
            const form = e.target;
            if (!form || form.tagName !== 'FORM') return;

            const action = (form.getAttribute('action') || '').toLowerCase();
            if (action && !action.includes('/accounts/')) return;
            if (e.defaultPrevented) return;
            showAuthProgress();
        }, true);
    }

    // Allauth "Email addresses" page: add a friendly placeholder.
    try {
        const el = document.getElementById('id_email');
        if (el && !el.getAttribute('placeholder')) {
            el.setAttribute('placeholder', 'you@example.com');
        }
    } catch {
        // ignore
    }

    // If add-email submit succeeded, clear the input on next load.
    try {
        const forms = document.querySelectorAll('form[action$="/accounts/email/"]');
        forms.forEach((form) => {
            form.addEventListener('submit', function (e) {
                const submitter = e.submitter || form.__vixoLastSubmitter || null;
                if (!submitter || !submitter.getAttribute) return;
                const name = (submitter.getAttribute('name') || '').toLowerCase();
                if (name === 'action_add') {
                    sessionStorage.setItem('vixo:clear_add_email', '1');
                } else if (name === 'action_send' || name === 'action_primary' || name === 'action_remove') {
                    // Clear stale add-email errors/values after other actions.
                    sessionStorage.setItem('vixo:clear_add_email_force', '1');
                }
            }, true);
        });

        const el = document.getElementById('id_email');
        if (el) {
            const form = el.closest('form');
            const hasError = !!(form && form.querySelector('.text-red-400, .errorlist, .error'));
            const shouldClear = sessionStorage.getItem('vixo:clear_add_email') === '1'
                || sessionStorage.getItem('vixo:clear_add_email_force') === '1';
            if (shouldClear) {
                if (!hasError || sessionStorage.getItem('vixo:clear_add_email_force') === '1') {
                    el.value = '';
                    // Hide stale error text if present.
                    if (form) {
                        const err = form.querySelector('.text-red-400');
                        if (err) err.textContent = '';
                    }
                }
                sessionStorage.removeItem('vixo:clear_add_email');
                sessionStorage.removeItem('vixo:clear_add_email_force');
            }
        }
    } catch {
        // ignore
    }

    // Lucide icon hydration (used on login/signup forms).
    try {
        if (window.lucide && typeof window.lucide.createIcons === 'function') {
            window.lucide.createIcons();
        }
    } catch {
        // ignore
    }

    // Password show/hide toggle is initialized globally in vixogram.js.
    // Keep account.js lean to avoid duplicate event handlers.

    installPageSwapTransitions();
})();
