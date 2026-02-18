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

    function installFloatingAuthBubbles() {
        if (!isAuthPage()) return;

        const root = document.querySelector('[data-vixo-floating-bubbles]');
        if (!root) return;

        const pageType = (root.getAttribute('data-vixo-floating-bubbles') || '').toLowerCase();
        const bubbleSets = {
            login: [
                { name: 'Aarav', text: 'Bro room kholo, hot tea spill hai ☕🔥' },
                { name: 'Kiara', text: 'Who online rn? Meme drop incoming 😭✨' },
                { name: 'Rhea', text: 'Mood off tha, yaha aake vibe set ho gayi 💜' },
                { name: 'Dev', text: 'No cap, ye app pe convo level max hai 🚀' },
                { name: 'Ishaan', text: 'Late night gang assemble? 2-min mein aaya 👀' },
                { name: 'Naina', text: 'Aaj ka playlist drop karo, chill room banaate 🎧' },
                { name: 'Rudra', text: 'Office se nikla, ab thoda bakchodi mode on 😌' },
                { name: 'Sana', text: 'Study break pe hoon, koi quick convo karega?' },
                { name: 'Vihaan', text: 'Mere paas ek savage meme hai, ready ho jao 😂' },
                { name: 'Myra', text: 'Yaha ke log legit wholesome hain, love it 💫' },
                { name: 'Kabir', text: 'Game night plan? Team banani hai abhi 🎮' },
                { name: 'Anvi', text: 'Rain + coffee + random chat = perfect combo ☔' },
                { name: 'Yash', text: 'Kaun kaun abhi online hai? ping karo jaldi' },
                { name: 'Trisha', text: 'Vent karna tha, yaha aake halka feel hua 🤍' },
                { name: 'Abeer', text: 'Ek line mein apna mood batao, chalo thread banaye' },
                { name: 'Zoya', text: 'New dp kisne dekhi? honest ratings allowed 😭' },
                { name: 'Kian', text: 'Aaj ka hot take: pineapple pizza overrated hai' },
                { name: 'Mahi', text: 'Ghost mat karo yaar, convo interesting ho raha tha' },
                { name: 'Reyansh', text: 'Night owls check-in. Kaun kaun जाग रहा?' },
                { name: 'Inaaya', text: 'Mujhe ek funny reel bhejo, mood boost chahiye' },
                { name: 'Arjun', text: 'Quick poll: chai ya coffee? votes abhi ☕' },
                { name: 'Siya', text: 'Random strangers se best advice milta hai fr' },
                { name: 'Laksh', text: 'Voice room khol du? text se zyada maza aayega' },
                { name: 'Tara', text: 'Aaj ka win share karo, small bhi chalega ✨' },
                { name: 'Rohan', text: 'Coding se break liya, ab thoda gossip time' },
                { name: 'Aisha', text: 'Kal ka episode dekha? spoilers controlled pls 😭' },
                { name: 'Nivaan', text: 'Mere cat ne keyboard pe walk karke poem likh di' },
                { name: 'Prisha', text: 'Sunset pics drop karo, timeline pretty banate 🌇' },
                { name: 'Advik', text: 'Yeh app pe random chats unexpectedly elite hain' },
                { name: 'Meher', text: 'Tum log itne fast reply kaise karte ho omg' },
                { name: 'Harsh', text: 'Aaj ka gym update: skipped. Meme therapy done 💀' },
                { name: 'Kavya', text: 'Serious question: best late-night snack kya hai?' },
                { name: 'Dhruv', text: 'Kal interview hai, confidence booster bhejo pls' },
                { name: 'Ira', text: 'Koi journaling karta hai? tips do na 📓' },
                { name: 'Parth', text: 'Mic on karo bhai, story half pe mat chhodo' },
                { name: 'Anaya', text: 'Yaha ki energy alag hi soothing lagti hai 🌙' },
                { name: 'Vivaan', text: 'Mujhe ek roast chahiye, halka wala only 😅' },
                { name: 'Ritika', text: 'Aaj gratitude list me Vixogram bhi add hua 💜' },
                { name: 'Krish', text: 'Travel plans discuss kare? budget hacks chahiye' },
                { name: 'Aditi', text: 'Kaun indie music sunta hai? recommendations do' },
                { name: 'Manav', text: 'Thread idea: best life hack under 100 rupees' },
                { name: 'Shanaya', text: 'Yeh chat room mujhe daily reset de deta hai' },
                { name: 'Om', text: 'Aaj kis cheez pe hasi aayi? share karo sab' },
                { name: 'Pihu', text: 'Main introvert hoon but yaha bolne ka mann karta' },
                { name: 'Samar', text: 'Koi football fans hai? match discussion live' },
                { name: 'Aanya', text: 'Good people + good vibes = yahi space 😌' },
                { name: 'Raghav', text: 'One word check-in: burnt, calm, hype, or sleepy?' },
                { name: 'Kiara', text: 'New meme folder bana liya, ab flood aayega 😂' },
                { name: 'Ishita', text: 'Aaj self-care kiya kya? पानी पी लो reminder 💧' },
                { name: 'Neel', text: 'Koi book suggestion de do jo boring na ho' },
                { name: 'Samaira', text: 'Life update tiny: aaj finally overthinking kam hua' },
                { name: 'Atharv', text: 'Photo dump ke liye caption ideas bhejo yaar' },
                { name: 'Diya', text: 'Wholesome threads yaha gold mine hote hain ✨' },
                { name: 'Agastya', text: 'Kaun coding seekh raha? accountability partner?' },
                { name: 'Ruhani', text: 'Yaar aaj ka weather aur chat vibe dono dreamy' },
                { name: 'Tanmay', text: 'Mere jokes pe hasi mandatory hai, warning ⚠️' },
                { name: 'Navya', text: 'Ek compliment drop karo next person ke liye 💜' },
                { name: 'Jai', text: 'Weekend plan cancel? idhar aa jao, room alive hai' },
                { name: 'Esha', text: 'Yaha pe strangers bhi comfort zone ban jaate' },
                { name: 'Aditya', text: 'Chalo rapid-fire: fav app, song, snack, go!' },
                { name: 'Mishti', text: 'Aaj ka affirmation: slow progress bhi progress 🌱' },
            ],
            signup: [
                { name: 'Mahi', text: 'First day and already besties? iconic fr 💅' },
                { name: 'Kabir', text: 'Yaha chats lowkey addictive hain ngl 😮‍💨' },
                { name: 'Zoya', text: 'New account, new era. Let’s vibe 🎧⚡' },
                { name: 'Yuv', text: 'POV: random room joined and chaos started 😂' },
                { name: 'Anya', text: 'Glow-up arc starts with one message ✨📲' },
                { name: 'Rhea', text: 'Signup kiya aur first room mein full laughter मिला' },
                { name: 'Arjun', text: 'Naya account, zero pressure, full fun scene 😎' },
                { name: 'Tia', text: 'Yaha strangers bhi quickly dost ban jaate hain' },
                { name: 'Vihaan', text: 'First hello bola aur 20 replies aa gaye 😭' },
                { name: 'Meera', text: 'Mujhe laga awkward hoga, but vibe smooth निकली' },
                { name: 'Rudra', text: 'Account banao aur seedha meme lane me aa jao' },
                { name: 'Aisha', text: 'No judgment chats = instant comfort zone 🤍' },
                { name: 'Kunal', text: 'Signup ke baad boredom officially खत्म' },
                { name: 'Sana', text: 'Yaha pe daily mini happiness mil jati hai' },
                { name: 'Parth', text: 'One profile, endless random conversations 🔥' },
                { name: 'Naina', text: 'Main shy thi, ab yaha nonstop bolti hoon 😂' },
                { name: 'Dev', text: 'Join karo bhai, room energy crazy achhi hai' },
                { name: 'Ira', text: 'First week and already my favorite app ban gaya' },
                { name: 'Abeer', text: 'Signup took 1 min, laughs lasted all night' },
                { name: 'Prisha', text: 'Safe, fun, and real convos. rare combo fr' },
                { name: 'Neel', text: 'Mere random questions ka bhi yaha answer milta' },
                { name: 'Diya', text: 'Join karte hi welcome vibes mil gayi 🌸' },
                { name: 'Laksh', text: 'Naye log, naye jokes, same chill mood 😌' },
                { name: 'Anvi', text: 'Yaha pe awkward silence naam ki cheez nahi' },
                { name: 'Om', text: 'Profile banate hi late-night squad mil gaya' },
                { name: 'Kiara', text: 'Best decision: “Create account” pe click करना' },
                { name: 'Yash', text: 'Maine try kiya, ab friends list full speed se badh rahi' },
                { name: 'Myra', text: 'Fresh start chahiye? yahi se begin karo ✨' },
                { name: 'Rohan', text: 'First day pe hi roast bhi mila, pyaar bhi मिला' },
                { name: 'Aanya', text: 'Signup simple, conversations top tier 💜' },
                { name: 'Krish', text: 'Yaha ka humor level mujhe roz wapas kheechta hai' },
                { name: 'Esha', text: 'New user ho? tension mat lo, sab friendly hain' },
                { name: 'Manav', text: 'Mere jaise introvert ke liye perfect starter space' },
                { name: 'Pihu', text: 'One post dala aur logon ne genuine replies diye' },
                { name: 'Jai', text: 'Yaha aa ke doomscrolling aadhi ho gayi सच में' },
                { name: 'Kavya', text: 'Real conversations without fake flex, loved it' },
                { name: 'Atharv', text: 'Kaafi clean UI aur smooth chat flow. respect' },
                { name: 'Ritika', text: 'Nayi jagah thi but feel hua jaise old friends' },
                { name: 'Tanmay', text: 'Sign up karo aur apna corner instantly set karo' },
                { name: 'Ziva', text: 'Mera comfort thread yahi pe start hua था' },
                { name: 'Aditya', text: 'Random room join karke best convo mil gaya' },
                { name: 'Shanaya', text: 'Is app pe daily check-in ab routine ban gaya' },
                { name: 'Agastya', text: 'Naye account pe bhi community warm लगती है' },
                { name: 'Raghav', text: 'Kaun kehta new apps boring hote? yaha toh नहीं' },
                { name: 'Samaira', text: 'Mood swing days me yahi pe balance milta hai' },
                { name: 'Harsh', text: 'Join today, laugh today. simple formula 😄' },
                { name: 'Trisha', text: 'Start small—hi likho, baaki flow ho jayega' },
                { name: 'Nivaan', text: 'Profile photo set and boom—conversation started' },
                { name: 'Ruhani', text: 'This place feels light, kind, and honestly fun' },
                { name: 'Samar', text: 'Gaming se leke poetry tak sab mil jaata yaha' },
                { name: 'Ishita', text: 'Meri first post pe itna pyaar expected nahi tha' },
                { name: 'Aditi', text: 'New account made, social battery restored 🔋' },
                { name: 'Vivaan', text: 'Ek baar join kiya toh daily aaoge, bet' },
                { name: 'Inaaya', text: 'Yaha pe positivity ka filter default on lagta' },
                { name: 'Dhruv', text: 'Users real lagte, chats natural lagti—win win' },
                { name: 'Tara', text: 'Mera safe meme zone finally mil gaya 🫶' },
                { name: 'Reyansh', text: 'Signup ka best part: zero awkward onboarding' },
                { name: 'Navya', text: 'Aaj join kiya, kal tak sab naam yaad ho गए' },
                { name: 'Kian', text: 'No spam vibes, just people and good talks' },
                { name: 'Mishti', text: 'One tap signup, many wholesome moments 🌈' },
                { name: 'Advik', text: 'Ab jab bhi free hota hoon, seedha idhar aata' },
            ],
        };

        const messages = bubbleSets[pageType];
        if (!Array.isArray(messages) || messages.length < 5) return;

        const desktopPositions = [
            { left: '8%', top: '23%' },
            { left: '28%', top: '15%' },
            { left: '36%', top: '34%' },
            { left: '16%', top: '46%' },
            { left: '34%', top: '56%' },
        ];

        const mobilePositions = [
            { left: '6%', top: '16%' },
            { left: '30%', top: '9%' },
            { left: '44%', top: '24%' },
            { left: '10%', top: '36%' },
            { left: '36%', top: '42%' },
        ];

        const isMobile = () => window.matchMedia && window.matchMedia('(max-width: 767px)').matches;
        const VISIBLE_MS = 2150;
        const TRANSITION_MS = 260;
        const LOOP_DELAY_MS = 130;
        let activeBubble = null;
        let animationTimer = 0;
        let sequenceIndex = 0;

        function createBubble(item, position) {
            const bubble = document.createElement('div');
            bubble.className = 'vixo-auth-bubble';
            bubble.style.setProperty('--bubble-left', position.left);
            bubble.style.setProperty('--bubble-top', position.top);

            const name = document.createElement('span');
            name.className = 'vixo-auth-bubble__name';
            name.textContent = item.name;

            const text = document.createElement('span');
            text.className = 'vixo-auth-bubble__text';
            text.textContent = item.text;

            bubble.appendChild(name);
            bubble.appendChild(text);
            return bubble;
        }

        function clearSequenceTimer() {
            if (!animationTimer) return;
            window.clearTimeout(animationTimer);
            animationTimer = 0;
        }

        function renderSequenceStep() {
            const positions = isMobile() ? mobilePositions : desktopPositions;
            const slot = positions[sequenceIndex % positions.length];
            const item = messages[sequenceIndex % 5];

            if (activeBubble && activeBubble.parentNode) {
                activeBubble.classList.remove('is-visible');
                const stale = activeBubble;
                window.setTimeout(function () {
                    if (stale.parentNode) {
                        try { stale.parentNode.removeChild(stale); } catch {}
                    }
                }, TRANSITION_MS + 10);
            }

            const bubble = createBubble(item, slot);
            root.appendChild(bubble);

            requestAnimationFrame(function () {
                bubble.classList.add('is-visible');
            });
            activeBubble = bubble;

            sequenceIndex = (sequenceIndex + 1) % 5;
            clearSequenceTimer();
            animationTimer = window.setTimeout(renderSequenceStep, VISIBLE_MS + TRANSITION_MS + LOOP_DELAY_MS);
        }

        renderSequenceStep();

        window.addEventListener('resize', function () {
            if (!activeBubble) return;
            const positions = isMobile() ? mobilePositions : desktopPositions;
            const lastIndex = (sequenceIndex + 4) % 5;
            const slot = positions[lastIndex % positions.length];
            activeBubble.style.setProperty('--bubble-left', slot.left);
            activeBubble.style.setProperty('--bubble-top', slot.top);
        });

        document.addEventListener('visibilitychange', function () {
            if (!document.hidden) {
                clearSequenceTimer();
                renderSequenceStep();
            }
        });
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

    installFloatingAuthBubbles();
    installPageSwapTransitions();
})();
