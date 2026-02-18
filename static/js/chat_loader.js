(function () {
    function onReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn, { once: true });
        } else {
            fn();
        }
    }

    async function main() {


        onReady(() => {
            const s = document.createElement('script');
            s.src = '/static/js/chat.js?v=20260218b';
            // Dynamic scripts execute asynchronously by default; ensure predictable ordering.
            s.async = false;
            document.head.appendChild(s);
        });
    }

    main();
})();
