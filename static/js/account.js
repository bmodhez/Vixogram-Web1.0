(function () {
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
