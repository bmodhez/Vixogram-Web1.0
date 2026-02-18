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

    const cfg = (window.__vixo_call_config && typeof window.__vixo_call_config === 'object')
        ? window.__vixo_call_config
        : (readJsonScript('vixo-call-config') || {});

    const callType = String(cfg.callType || 'voice');
    const channel = String(cfg.channel || '');
    const callRole = String(cfg.callRole || '');
    const currentUsername = String(cfg.currentUsername || '');
    const tokenUrl = String(cfg.tokenUrl || '');
    const presenceUrl = String(cfg.presenceUrl || '');
    const callEventUrl = String(cfg.callEventUrl || '');
    const memberUsernames = Array.isArray(cfg.memberUsernames) ? cfg.memberUsernames : [];

    if (!channel || !tokenUrl) return;

    const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${wsScheme}://${window.location.host}/ws/chatroom/${channel}`;

    const phaseEl = document.getElementById('call-phase');
    const countEl = document.getElementById('participants-count');
    const namesEl = document.getElementById('participants-names');
    const freeLimitTimerEl = document.getElementById('free-limit-timer');
    const freeLimitPopupEl = document.getElementById('free-limit-popup');
    const loadingEl = document.getElementById('call-loading');
    const loadingTextEl = document.getElementById('call-loading-text');

    const statusEl = document.getElementById('call-status');
    const setStatus = (t) => { if (statusEl) statusEl.textContent = t; };
    const setPhase = (t) => { if (phaseEl) phaseEl.textContent = t; };

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

    const endBackEl = document.getElementById('call_end_back');

    let joinedUid = null;
    let endEventSent = false;

    function showLoading(text) {
        if (!loadingEl) return;
        if (loadingTextEl) loadingTextEl.textContent = text || 'Loading…';
        loadingEl.classList.remove('hidden');
        loadingEl.classList.add('flex');
    }

    function hideLoading() {
        if (!loadingEl) return;
        loadingEl.classList.add('hidden');
        loadingEl.classList.remove('flex');
    }

    // --- Free call limit ---
    // Voice: 4 min, Video: 2 min (server can override + provides remaining seconds)
    const DEFAULT_FREE_LIMIT_SECONDS = (callType === 'video') ? 2 * 60 : 4 * 60;
    let freeLimitSeconds = DEFAULT_FREE_LIMIT_SECONDS;
    let freeSecondsLeftInitial = DEFAULT_FREE_LIMIT_SECONDS;
    let freeLimitDeadlineMs = null;
    let freeLimitInterval = null;
    let freeLimitStarted = false;

    function formatMMSS(totalSeconds) {
        const s = Math.max(0, Number(totalSeconds || 0));
        const mm = String(Math.floor(s / 60)).padStart(2, '0');
        const ss = String(Math.floor(s % 60)).padStart(2, '0');
        return `${mm}:${ss}`;
    }

    function setFreeLimitTimer(secondsLeft) {
        if (!freeLimitTimerEl) return;
        freeLimitTimerEl.textContent = formatMMSS(secondsLeft);
    }

    function showFreeLimitPopup({ title = null, body = null, showUpgrade = null } = {}) {
        if (!freeLimitPopupEl) return;

        try {
            const titleEl = document.getElementById('call-modal-title');
            const bodyEl = document.getElementById('call-modal-body');
            const upgradeEl = document.getElementById('call-modal-upgrade');
            if (titleEl && title) titleEl.textContent = String(title);
            if (bodyEl && body) bodyEl.textContent = String(body);
            if (upgradeEl && typeof showUpgrade === 'boolean') {
                upgradeEl.style.display = showUpgrade ? '' : 'none';
            }
        } catch {
            // ignore
        }

        freeLimitPopupEl.classList.remove('hidden');
        freeLimitPopupEl.classList.add('flex');
    }

    function stopFreeLimitCountdown() {
        if (freeLimitInterval) {
            clearInterval(freeLimitInterval);
            freeLimitInterval = null;
        }
    }

    function startFreeLimitCountdown() {
        if (freeLimitStarted) return;
        freeLimitStarted = true;

        let warnedTenSeconds = false;

        const startSeconds = Math.max(0, Math.min(freeLimitSeconds, Number(freeSecondsLeftInitial || 0)));
        freeLimitDeadlineMs = Date.now() + (startSeconds * 1000);
        setFreeLimitTimer(startSeconds);

        freeLimitInterval = setInterval(() => {
            const remainingMs = Math.max(0, freeLimitDeadlineMs - Date.now());
            const remainingSeconds = Math.ceil(remainingMs / 1000);
            setFreeLimitTimer(remainingSeconds);

            if (!warnedTenSeconds && remainingSeconds <= 10 && remainingSeconds > 0) {
                warnedTenSeconds = true;
                toast('10 seconds left');
                beep();
            }

            if (remainingSeconds <= 0) {
                stopFreeLimitCountdown();
                // End call and show upsell modal + redirect to pricing.
                showFreeLimitPopup({
                    title: 'Want to talk more on calls?',
                    body: 'Buy the premium to continue calling.',
                    showUpgrade: true,
                });
                const pricingUrl = String(cfg.pricingUrl || '/pricing');
                hangupAndExit('Free limit reached', { redirectDelayMs: 900, redirectUrl: pricingUrl, sendEndEvent: true });
            }
        }, 250);
    }

    // Set initial display so user always sees the limit.
    setFreeLimitTimer(freeSecondsLeftInitial);

    const client = AgoraRTC.createClient({ mode: 'rtc', codec: 'vp8' });

    let localTracks = { audio: null, video: null };

    // Remote audio can be blocked by autoplay policies; keep references to retry on user gesture.
    const remoteAudioTracks = new Map(); // uid -> audioTrack
    let audioPlaybackBlocked = false;

    function tryPlayAllRemoteAudio() {
        let playedAny = false;
        for (const track of remoteAudioTracks.values()) {
            if (!track) continue;
            try {
                track.play();
                playedAny = true;
            } catch {
                // still blocked
            }
        }
        if (playedAny) {
            audioPlaybackBlocked = false;
            setStatus('Connected (audio playing)');
        }
    }

    // uid -> username (UI only)
    const participants = new Map();
    // Represent self separately so we don't create a duplicate remote tile.
    participants.set('me', 'You');

    // Remote video containers (uid -> { cardEl, playerEl, labelEl })
    const remoteCards = new Map();
    // Voice participant cards (uid -> { cardEl, labelEl })
    const voiceCards = new Map();

    function getVideoGrid() {
        return document.getElementById('video-grid');
    }

    function getVoiceGrid() {
        return document.getElementById('voice-grid');
    }

    function ensureLocalTile() {
        if (callType === 'video') {
            const grid = getVideoGrid();
            if (!grid) return;
            if (document.getElementById('local-player')) return;

            const card = document.createElement('div');
            card.className = 'rounded-lg border border-gray-800 bg-black/20 p-2';

            const label = document.createElement('div');
            label.className = 'text-[11px] text-gray-400 mb-2 truncate';
            label.textContent = 'You';

            const player = document.createElement('div');
            player.id = 'local-player';
            player.className = 'w-full aspect-video bg-black/40 rounded-md overflow-hidden';

            card.appendChild(label);
            card.appendChild(player);
            grid.appendChild(card);
        } else {
            const grid = getVoiceGrid();
            if (!grid) return;
            if (document.getElementById('local-voice-tile')) return;

            const card = document.createElement('div');
            card.id = 'local-voice-tile';
            card.className = 'rounded-lg border border-gray-800 bg-black/20 p-3';

            const label = document.createElement('div');
            label.className = 'text-sm text-gray-200 font-semibold truncate';
            label.textContent = 'You';

            const sub = document.createElement('div');
            sub.className = 'text-xs text-gray-500 mt-1';
            sub.textContent = 'Connected';

            card.appendChild(label);
            card.appendChild(sub);
            grid.appendChild(card);
        }
    }

    function setParticipantsUi() {
        try {
            const names = Array.from(participants.values()).filter(Boolean);
            if (countEl) countEl.textContent = String(names.length);
            if (namesEl) namesEl.textContent = names.join(', ');
        } catch {
            // ignore
        }
    }

    function toast(message, { timeoutMs = 2200 } = {}) {
        try {
            const toastEl = document.getElementById('call-toast');
            const toastTextEl = document.getElementById('call-toast-text');
            if (!toastEl || !toastTextEl) return;
            toastTextEl.textContent = String(message || '');
            toastEl.classList.remove('hidden');
            toastEl.classList.add('flex');
            window.clearTimeout(toast._t);
            toast._t = window.setTimeout(() => {
                try {
                    toastEl.classList.add('hidden');
                    toastEl.classList.remove('flex');
                } catch {}
            }, Math.max(250, Number(timeoutMs || 0)));
        } catch {
            // ignore
        }
    }

    let userGestureSeen = false;
    function beep() {
        if (!userGestureSeen) return;
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtx) return;
            const ctx = new AudioCtx();
            const o = ctx.createOscillator();
            const g = ctx.createGain();
            o.type = 'sine';
            o.frequency.value = 880;
            g.gain.value = 0.06;
            o.connect(g);
            g.connect(ctx.destination);
            o.start();
            window.setTimeout(() => {
                try { o.stop(); } catch {}
                try { ctx.close(); } catch {}
            }, 180);
        } catch {
            // ignore
        }
    }

    function addParticipant(uid, username) {
        const key = String(uid);
        const name = username || `User ${key}`;
        participants.set(key, name);
        setParticipantsUi();

        if (callType === 'video') {
            const grid = getVideoGrid();
            if (!grid) return;

            if (remoteCards.has(key)) return;

            const card = document.createElement('div');
            card.className = 'rounded-lg border border-gray-800 bg-black/20 p-2';

            const label = document.createElement('div');
            label.className = 'text-[11px] text-gray-400 mb-2 truncate';
            label.textContent = name;

            const player = document.createElement('div');
            player.id = `remote-player-${key}`;
            player.className = 'w-full aspect-video bg-black/40 rounded-md overflow-hidden';

            card.appendChild(label);
            card.appendChild(player);
            grid.appendChild(card);

            remoteCards.set(key, { cardEl: card, playerEl: player, labelEl: label });
        } else {
            const grid = getVoiceGrid();
            if (!grid) return;

            if (voiceCards.has(key)) return;

            const card = document.createElement('div');
            card.className = 'rounded-lg border border-gray-800 bg-black/20 p-3';

            const label = document.createElement('div');
            label.className = 'text-sm text-gray-200 font-semibold truncate';
            label.textContent = name;

            const sub = document.createElement('div');
            sub.className = 'text-xs text-gray-500 mt-1';
            sub.textContent = 'Connected';

            card.appendChild(label);
            card.appendChild(sub);
            grid.appendChild(card);

            voiceCards.set(key, { cardEl: card, labelEl: label });
        }
    }

    function removeParticipant(uid) {
        const key = String(uid);
        participants.delete(key);
        setParticipantsUi();

        if (remoteCards.has(key)) {
            try { remoteCards.get(key).cardEl.remove(); } catch {}
            remoteCards.delete(key);
        }
        if (voiceCards.has(key)) {
            try { voiceCards.get(key).cardEl.remove(); } catch {}
            voiceCards.delete(key);
        }
    }

    function getCsrf() {
        try { return (typeof getCookie === 'function' ? getCookie('csrftoken') : ''); } catch { return ''; }
    }

    async function announcePresence(action, uid) {
        try {
            const body = new URLSearchParams();
            body.set('action', action);
            body.set('type', callType);
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

    async function postCallEvent(action) {
        try {
            const body = new URLSearchParams();
            body.set('action', action);
            body.set('type', callType);
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

    async function postCallEventKeepalive(action) {
        try {
            const body = new URLSearchParams();
            body.set('action', action);
            body.set('type', callType);
            await fetch(callEventUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': getCsrf(),
                },
                body,
                keepalive: true,
            });
        } catch {
            // ignore
        }
    }

    async function announcePresenceKeepalive(action, uid) {
        try {
            const body = new URLSearchParams();
            body.set('action', action);
            body.set('type', callType);
            body.set('uid', String(uid || 0));
            await fetch(presenceUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': getCsrf(),
                },
                body,
                keepalive: true,
            });
        } catch {
            // ignore
        }
    }

    function sendEndEventBestEffort() {
        if (endEventSent) return;
        endEventSent = true;
        // Best-effort: end call for everyone + mark presence leave.
        try { postCallEventKeepalive('end'); } catch {}
        try { announcePresenceKeepalive('leave', joinedUid); } catch {}
    }

    async function fetchAgoraToken() {
        const url = (() => {
            try {
                const u = new URL(tokenUrl, window.location.origin);
                u.searchParams.set('type', callType);
                return u.toString();
            } catch {
                // Fallback if tokenUrl isn't absolute
                const sep = tokenUrl.includes('?') ? '&' : '?';
                return `${tokenUrl}${sep}type=${encodeURIComponent(callType)}`;
            }
        })();

        const res = await fetch(url, { credentials: 'same-origin' });

        if (res.status === 429) {
            const retryAfter = Number(res.headers.get('Retry-After') || '10');
            throw new Error(`Rate limited. Try again in ${Number.isFinite(retryAfter) ? retryAfter : 10}s.`);
        }

        let data = null;
        try {
            data = await res.json();
        } catch {
            const text = await res.text().catch(() => '');
            const hint = (text || '').slice(0, 140).replace(/\s+/g, ' ').trim();
            throw new Error(!res.ok ? `Token request failed (${res.status}). ${hint}` : 'Token response was not JSON.');
        }

        if (!res.ok || (data && data.error)) {
            const err = (data && data.error) ? String(data.error) : `Token request failed (${res.status}).`;
            if (String(err) === 'free_limit_reached') {
                showFreeLimitPopup({
                    title: 'Want to talk more on calls?',
                    body: 'Buy the premium to continue calling.',
                    showUpgrade: true,
                });
                const pricingUrl = String(cfg.pricingUrl || '/pricing');
                window.setTimeout(() => {
                    try { window.location.href = pricingUrl; } catch {}
                }, 900);
            }
            throw new Error(err);
        }

        // Server-provided free timer values.
        try {
            const fl = Number(data.free_limit_seconds);
            const left = Number(data.free_seconds_left);
            if (Number.isFinite(fl) && fl > 0) freeLimitSeconds = Math.max(0, Math.floor(fl));
            if (Number.isFinite(left)) freeSecondsLeftInitial = Math.max(0, Math.min(freeLimitSeconds, Math.floor(left)));
            setFreeLimitTimer(freeSecondsLeftInitial);
        } catch {
            // ignore
        }
        return data;
    }

    async function hangupAndExit(reason, { redirectDelayMs = 0, redirectUrl = null, sendEndEvent = false } = {}) {
        try {
            if (reason) setStatus(reason);
        } catch {}

        try {
            if (sendEndEvent) {
                endEventSent = true;
                await postCallEvent('end');
            }
        } catch {}

        try {
            await announcePresence('leave', joinedUid);
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
            await client.leave();
        } catch {}

        const targetUrl = redirectUrl ? String(redirectUrl) : (cfg.backUrl || '/');
        if (redirectDelayMs > 0) {
            setTimeout(() => {
                try { window.location.href = targetUrl; } catch {}
            }, redirectDelayMs);
        } else {
            try { window.location.href = targetUrl; } catch {}
        }
    }

    // --- WebSocket presence/control ---
    let socket = null;
    let __wsReconnectTimer = null;
    let __wsReconnectAttempt = 0;

    const __WS_RECONNECT_BASE_MS = 900;
    const __WS_RECONNECT_FACTOR = 1.7;
    const __WS_RECONNECT_MAX_MS = 30_000;

    function __scheduleWsReconnect() {
        if (__wsReconnectTimer) return;

        const attempt = Math.min(30, Math.max(0, __wsReconnectAttempt || 0));
        __wsReconnectAttempt = attempt + 1;

        if (attempt >= 4) {
            try {
                window.__vixoCallWsWarned = window.__vixoCallWsWarned || false;
                if (!window.__vixoCallWsWarned) {
                    window.__vixoCallWsWarned = true;
                    toast('Connection issue. Retrying…', { timeoutMs: 3500 });
                }
            } catch {}
        }

        let delay = Math.min(
            __WS_RECONNECT_MAX_MS,
            Math.round(__WS_RECONNECT_BASE_MS * Math.pow(__WS_RECONNECT_FACTOR, attempt))
        );

        // Jitter
        delay = Math.round(delay * (0.7 + Math.random() * 0.6));
        try { if (document.visibilityState === 'hidden') delay = Math.max(delay, 5000); } catch {}

        __wsReconnectTimer = setTimeout(() => {
            __wsReconnectTimer = null;
            connectWs();
        }, delay);
    }

    function handleCallControl(payload) {
        if (!payload) return;
        if (payload.chatroom_name && String(payload.chatroom_name) !== String(channel)) return;
        if (payload.action === 'end' || payload.action === 'decline') {
            const isDecline = payload.action === 'decline';
            showFreeLimitPopup({
                title: isDecline ? 'Call declined' : 'Call ended',
                body: isDecline ? 'The other user declined the call.' : 'The call has ended.',
                showUpgrade: false,
            });
            hangupAndExit(isDecline ? 'Call declined' : 'Call ended', { redirect: false, sendEndEvent: false });
        }
    }

    function connectWs() {
        try {
            if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
        } catch {}

        try {
            if (socket && socket.close) socket.close();
        } catch {}

        try {
            socket = new WebSocket(wsUrl);
        } catch {
            __scheduleWsReconnect();
            return;
        }

        socket.onopen = function () {
            __wsReconnectAttempt = 0;
            if (__wsReconnectTimer) {
                try { clearTimeout(__wsReconnectTimer); } catch {}
                __wsReconnectTimer = null;
            }
        };

        socket.onmessage = function (event) {
            let payload;
            try {
                payload = JSON.parse(event.data);
            } catch {
                return;
            }

            if (payload.type === 'call_control') {
                handleCallControl(payload);
            }
        };

        socket.onclose = function () {
            __scheduleWsReconnect();
        };
    }

    connectWs();

    // Also listen for global notify WS call control events.
    window.addEventListener('call:control', (e) => {
        try { handleCallControl(e && e.detail ? e.detail : null); } catch {}
    });

    // --- Agora lifecycle ---
    (async function start() {
        ensureLocalTile();
        showLoading('Connecting…');
        setPhase('Connecting…');

        try {
            const { token, uid, channel: chan, app_id } = await fetchAgoraToken();
            if (!app_id) throw new Error('Agora is not configured (missing AGORA_APP_ID).');

            client.on('user-joined', (user) => {
                if (String(user.uid) === String(uid)) return;
                addParticipant(user.uid, null);
                startFreeLimitCountdown();
            });

            client.on('user-left', (user) => {
                removeParticipant(user.uid);
            });

            client.on('user-published', async (user, mediaType) => {
                // Some browsers emit user-published before user-joined.
                if (String(user.uid) !== String(uid)) {
                    addParticipant(user.uid, null);
                }

                await client.subscribe(user, mediaType);

                if (mediaType === 'video' && callType === 'video') {
                    const card = remoteCards.get(String(user.uid));
                    if (card && card.playerEl && user.videoTrack) {
                        try { user.videoTrack.play(card.playerEl); } catch {}
                    }
                }

                if (mediaType === 'audio' && user.audioTrack) {
                    remoteAudioTracks.set(String(user.uid), user.audioTrack);
                    try {
                        user.audioTrack.play();
                    } catch {
                        audioPlaybackBlocked = true;
                        setStatus('Tap anywhere to enable audio');
                        toast('Tap anywhere to enable audio');
                    }
                }

                setPhase('In call');
                hideLoading();
                startFreeLimitCountdown();
            });

            client.on('user-unpublished', (user, mediaType) => {
                if (mediaType === 'audio') {
                    remoteAudioTracks.delete(String(user.uid));
                }
            });

            await client.join(app_id, chan || channel, token, uid);
            joinedUid = uid;
            await announcePresence('join', uid);

            if (callRole === 'caller') {
                await postCallEvent('start');
            }

            // Warm participants list (UI only)
            setParticipantsUi();
            for (const name of memberUsernames) {
                if (name && name !== currentUsername) {
                    // don't add duplicates; these are just names
                }
            }

            localTracks.audio = await AgoraRTC.createMicrophoneAudioTrack({ AEC: true, AGC: true, ANS: true });
            if (callType === 'video') {
                localTracks.video = await AgoraRTC.createCameraVideoTrack();
                try {
                    const localPlayer = document.getElementById('local-player');
                    if (localPlayer) localTracks.video.play(localPlayer);
                } catch {}
                await client.publish([localTracks.audio, localTracks.video]);
            } else {
                await client.publish([localTracks.audio]);
            }

            hideLoading();
            setPhase('In call');
            setStatus('Connected');
        } catch (e) {
            hideLoading();
            setPhase('Error');
            try { console.error('Call page start failed:', e); } catch {}
            setStatus(getPublicCallErrorMessage(e));
        }
    })();

    // Retry audio on user gesture if blocked
    document.addEventListener('pointerdown', () => {
        userGestureSeen = true;
        if (!audioPlaybackBlocked) return;
        tryPlayAllRemoteAudio();
    }, { passive: true });

    // --- Controls ---
    const btnMic = document.getElementById('btn-mic');
    const btnCam = document.getElementById('btn-cam');
    const btnSwitchCam = document.getElementById('btn-switch-cam');
    const btnEnd = document.getElementById('btn-end');

    let micEnabled = true;
    let camEnabled = true;

    function syncControlVisibility() {
        if (btnCam) btnCam.style.display = (callType === 'video') ? '' : 'none';
        if (btnSwitchCam) btnSwitchCam.style.display = (callType === 'video') ? '' : 'none';
    }

    function syncControlLabels() {
        if (btnMic) btnMic.textContent = micEnabled ? 'Mute' : 'Unmute';
        if (btnCam) btnCam.textContent = camEnabled ? 'Camera Off' : 'Camera On';
    }

    syncControlVisibility();
    syncControlLabels();

    if (btnMic) {
        btnMic.addEventListener('click', async () => {
            try {
                if (!localTracks.audio) {
                    toast('Mic not ready yet');
                    return;
                }
                micEnabled = !micEnabled;
                await localTracks.audio.setEnabled(micEnabled);
                syncControlLabels();
                toast(micEnabled ? 'Mic on' : 'Mic muted');
            } catch {
                toast('Failed to toggle mic');
            }
        });
    }

    if (btnCam) {
        btnCam.addEventListener('click', async () => {
            try {
                if (callType !== 'video') return;
                if (!localTracks.video) {
                    toast('Camera not ready yet');
                    return;
                }
                camEnabled = !camEnabled;
                await localTracks.video.setEnabled(camEnabled);
                syncControlLabels();
                toast(camEnabled ? 'Camera on' : 'Camera off');
            } catch {
                toast('Failed to toggle camera');
            }
        });
    }

    if (btnSwitchCam) {
        btnSwitchCam.addEventListener('click', async () => {
            try {
                if (callType !== 'video') return;
                if (!localTracks.video) {
                    toast('Camera not ready yet');
                    return;
                }
                const cams = await AgoraRTC.getCameras();
                if (!cams || cams.length < 2) {
                    toast('No alternate camera found');
                    return;
                }
                const currentLabel = (typeof localTracks.video.getTrackLabel === 'function') ? localTracks.video.getTrackLabel() : '';
                let idx = cams.findIndex((c) => c && c.label && currentLabel && c.label === currentLabel);
                if (idx < 0) idx = 0;
                const next = cams[(idx + 1) % cams.length];
                if (!next || !next.deviceId) {
                    toast('No alternate camera found');
                    return;
                }
                await localTracks.video.setDevice(next.deviceId);
                toast('Switched camera');
            } catch {
                toast('Failed to switch camera');
            }
        });
    }

    if (btnEnd) {
        btnEnd.addEventListener('click', () => {
            hangupAndExit('Call ended', { redirectDelayMs: 0, sendEndEvent: true });
        });
    }

    window.addEventListener('beforeunload', (e) => {
        const hasActiveCall = (joinedUid !== null) || !!localTracks.audio || !!localTracks.video;
        if (!hasActiveCall) return;
        sendEndEventBestEffort();
        const msg = 'Call will end if you reload or leave this page.';
        e.preventDefault();
        e.returnValue = msg;
        return msg;
    });

    // When user leaves the call page, ensure remote side ends too.
    window.addEventListener('pagehide', () => {
        sendEndEventBestEffort();
    });

    if (endBackEl) {
        endBackEl.addEventListener('click', (e) => {
            // Prevent raw navigation; hangup will redirect to backUrl.
            try {
                e.preventDefault();
                e.stopPropagation();
            } catch {}
            hangupAndExit('Call ended', { redirectDelayMs: 0, sendEndEvent: true });
        });
    }
})();
