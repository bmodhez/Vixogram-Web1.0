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
        try { els.bar.style.width = '0%'; } catch {}
        try { if (els.text) els.text.textContent = '0%'; } catch {}
        try { els.root.classList.remove('hidden'); } catch {}
        try { if (els.pill) els.pill.classList.remove('hidden'); } catch {}

        let start = null;
        const durationMs = 950; // feels like a "0→100" loader

        const tick = (ts) => {
            if (!start) start = ts;
            const t = Math.min(1, (ts - start) / durationMs);

            // Ease-out so it slows near the end.
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

            // Only show loader when user is actually navigating via these links.
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

        // Show loader on actual submit (login/signup).
        document.addEventListener('submit', function (e) {
            if (!isAuthPage()) return;
            const form = e.target;
            if (!form || form.tagName !== 'FORM') return;

            // Only for account forms (avoid interfering with other pages using vixo-auth-page).
            const action = (form.getAttribute('action') || '').toLowerCase();
            if (action && !action.includes('/accounts/')) return;

            // If we've already delayed once, allow the submit to proceed.
            if (form.dataset && form.dataset.vixoSubmitDelayed === '1') return;

            // Preserve which button initiated the submit.
            // allauth relies on the submit button name (e.g. action_send).
            const submitter = e.submitter || form.__vixoLastSubmitter || null;

            // If another handler (e.g., reCAPTCHA v3) prevents default, don't start progress yet.
            if (e.defaultPrevented) return;
            showAuthProgress();

            // Signup success animation: slide the card up + fade before redirect.
            // We can't know server success synchronously, so we animate on submit for signup.
            const isSignup = action.includes('/accounts/signup');
            if (isSignup) {
                try {
                    const card = form.closest('.vixo-auth-card');
                    if (card) card.classList.add('vixo-auth-card--success-leave');
                } catch {}
                try { document.body.classList.add('vixo-page-leave'); } catch {}
            }

            // Give the browser a moment to paint the loader before navigation.
            // Without this, fast POSTs can navigate away before any visual change appears.
            try {
                e.preventDefault();
                if (form.dataset) form.dataset.vixoSubmitDelayed = '1';
                window.setTimeout(function () {
                    try {
                        if (typeof form.requestSubmit === 'function') {
                            // Use requestSubmit(submitter) so the button name/value is included.
                            if (submitter && submitter.form === form) form.requestSubmit(submitter);
                            else form.requestSubmit();
                        } else {
                            // Fallback: mimic submitter by injecting a hidden input.
                            try {
                                const name = submitter && submitter.getAttribute ? (submitter.getAttribute('name') || '') : '';
                                const value = submitter && submitter.getAttribute ? (submitter.getAttribute('value') || '') : '';
                                if (name) {
                                    const tmp = document.createElement('input');
                                    tmp.type = 'hidden';
                                    tmp.name = name;
                                    tmp.value = value;
                                    form.appendChild(tmp);
                                    form.submit();
                                    form.removeChild(tmp);
                                } else {
                                    form.submit();
                                }
                            } catch {
                                try { form.submit(); } catch {}
                            }
                        }
                    } catch {
                        try { form.submit(); } catch {}
                    }
                }, isSignup ? 260 : 120);
            } catch {
                // ignore
            }
        }, true);

        // Start loader as early as possible (click on submit button).
        document.addEventListener('click', function (e) {
            if (!isAuthPage()) return;
            const btn = e.target && e.target.closest ? e.target.closest('button[type="submit"], input[type="submit"]') : null;
            if (!btn) return;
            const form = btn.form;
            if (!form) return;
            const action = (form.getAttribute('action') || '').toLowerCase();
            if (action && !action.includes('/accounts/')) return;
            try { form.__vixoLastSubmitter = btn; } catch {}
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
