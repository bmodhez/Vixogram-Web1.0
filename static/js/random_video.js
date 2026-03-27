(function () {
    function syncViewportLayout() {
        const topbar = document.querySelector('.vixo-topbar');
        const topbarHeight = topbar ? Math.ceil(topbar.getBoundingClientRect().height) : 72;
        document.documentElement.style.setProperty('--vixo-rv-topbar-h', `${topbarHeight}px`);
    }

    syncViewportLayout();
    window.addEventListener('resize', syncViewportLayout, { passive: true });

    function parseConfig() {
        try {
            const el = document.getElementById('rv-config');
            if (!el) return { wsPath: '/ws/random-video/' };
            return JSON.parse(el.textContent || '{}') || { wsPath: '/ws/random-video/' };
        } catch {
            return { wsPath: '/ws/random-video/' };
        }
    }

    const config = parseConfig();
    const SEARCH_WAIT_TIMEOUT_MS = 25000;
    const MATCH_CONNECT_DELAY_MS = 7000;
    const MATCH_CONNECT_DELAY_SECONDS = Math.max(1, Math.floor(MATCH_CONNECT_DELAY_MS / 1000));
    const VIDEO_MAX_WIDTH = 640;
    const VIDEO_MAX_HEIGHT = 360;
    const VIDEO_IDEAL_FPS = 15;

    function videoConstraints(deviceId) {
        const constraints = {
            width: { ideal: VIDEO_MAX_WIDTH, max: VIDEO_MAX_WIDTH },
            height: { ideal: VIDEO_MAX_HEIGHT, max: VIDEO_MAX_HEIGHT },
            frameRate: { ideal: VIDEO_IDEAL_FPS, max: 24 },
        };
        if (deviceId) {
            constraints.deviceId = { exact: String(deviceId) };
        }
        return constraints;
    }

    let ws = null;
    let pc = null;
    let localStream = null;
    let remoteStream = null;
    let connectWatchdog = 0;
    let started = false;
    let matched = false;
    let micEnabled = true;
    let camEnabled = true;
    let waitingDotsTimer = 0;
    let waitingDotsCount = 3;
    let remoteRevealTimer = 0;
    let waitingRetryTimer = 0;
    let retryDelayOverrideMs = 0;
    let matchedConnectTimer = 0;
    let matchedConnectCountdownTimer = 0;
    let pendingSignals = [];
    let typingStopTimer = 0;
    let sentTypingState = false;
    let welcomeContinueHandler = null;

    const els = {
        localVideo: document.getElementById('rv_local_video'),
        remoteVideo: document.getElementById('rv_remote_video'),
        remotePlaceholder: document.getElementById('rv_remote_placeholder'),
        remoteIdle: document.getElementById('rv_remote_idle'),
        remoteWaiting: document.getElementById('rv_remote_waiting'),
        remoteStartBtn: document.getElementById('rv_remote_start_btn'),
        remoteRetryBtn: document.getElementById('rv_remote_retry_btn'),
        waitingText: document.getElementById('rv_waiting_text'),
        waitingDots: document.getElementById('rv_waiting_dots'),
        connectionState: document.getElementById('rv_connection_state'),
        status: document.getElementById('rv_status'),
        online: document.getElementById('rv_online'),
        connectBtn: document.getElementById('rv_connect_btn'),
        nextBtn: document.getElementById('rv_next_btn'),
        endBtn: document.getElementById('rv_end_btn'),
        deviceBtn: document.getElementById('rv_device_btn'),
        chatWrap: document.getElementById('rv_chat_wrap'),
        statusPanel: document.getElementById('rv_status_panel'),
        chatMessages: document.getElementById('rv_chat_messages'),
        chatForm: document.getElementById('rv_chat_form'),
        chatInput: document.getElementById('rv_chat_input'),
        typingIndicator: document.getElementById('rv_typing_indicator'),
        deviceModal: document.getElementById('rv_device_modal'),
        deviceBackdrop: document.getElementById('rv_device_backdrop'),
        cameraSelect: document.getElementById('rv_camera_select'),
        micSelect: document.getElementById('rv_mic_select'),
        deviceApplyBtn: document.getElementById('rv_device_apply'),
        deviceCloseBtn: document.getElementById('rv_device_close'),
        chatPromoModal: document.getElementById('rv_chat_promo_modal'),
        chatPromoBackdrop: document.getElementById('rv_chat_promo_backdrop'),
        chatPromoLaterBtn: document.getElementById('rv_chat_promo_later'),
        welcomeModal: document.getElementById('rv_welcome_modal'),
        welcomeBackdrop: document.getElementById('rv_welcome_backdrop'),
        welcomeContinueBtn: document.getElementById('rv_welcome_continue'),
        warnBtn: document.getElementById('rv_warn_btn'),
        warnModal: document.getElementById('rv_warn_modal'),
        warnBackdrop: document.getElementById('rv_warn_backdrop'),
        warnInput: document.getElementById('rv_warn_input'),
        warnCancelBtn: document.getElementById('rv_warn_cancel'),
        warnSendBtn: document.getElementById('rv_warn_send'),
        warnAlertModal: document.getElementById('rv_warn_alert_modal'),
        warnAlertBackdrop: document.getElementById('rv_warn_alert_backdrop'),
        warnAlertTitle: document.getElementById('rv_warn_alert_title'),
        warnAlertMessage: document.getElementById('rv_warn_alert_message'),
        warnAlertOkBtn: document.getElementById('rv_warn_alert_ok'),
    };

    function isSuperuser() {
        return !!config.isSuperuser;
    }

    function closeWarnModal() {
        if (!els.warnModal) return;
        els.warnModal.classList.add('hidden');
        els.warnModal.setAttribute('aria-hidden', 'true');
    }

    function openWarnModal() {
        if (!els.warnModal) return;
        els.warnModal.classList.remove('hidden');
        els.warnModal.setAttribute('aria-hidden', 'false');
        if (els.warnInput) {
            els.warnInput.focus();
        }
    }

    function closeWarnAlertModal() {
        if (!els.warnAlertModal) return;
        els.warnAlertModal.classList.add('hidden');
        els.warnAlertModal.setAttribute('aria-hidden', 'true');
    }

    function openWarnAlertModal(sender, message) {
        if (!els.warnAlertModal) return;
        if (els.warnAlertTitle) {
            els.warnAlertTitle.textContent = String(sender || 'Vixogram');
        }
        if (els.warnAlertMessage) {
            els.warnAlertMessage.textContent = String(message || '').trim();
        }
        els.warnAlertModal.classList.remove('hidden');
        els.warnAlertModal.setAttribute('aria-hidden', 'false');
    }

    function closeWelcomeModal() {
        if (!els.welcomeModal) return;
        els.welcomeModal.classList.add('hidden');
        els.welcomeModal.setAttribute('aria-hidden', 'true');
        welcomeContinueHandler = null;
    }

    function openWelcomeModal(onContinue) {
        if (typeof onContinue === 'function') {
            onContinue();
        }
    }

    function closeChatPromoModal() {
        if (!els.chatPromoModal) return;
        els.chatPromoModal.classList.add('hidden');
        els.chatPromoModal.setAttribute('aria-hidden', 'true');
        try { window.sessionStorage.setItem('vixo.rv.chatPromoDismissed', '1'); } catch {}
    }

    function openChatPromoModal() {
        if (!els.chatPromoModal) return;
        try {
            if (window.sessionStorage.getItem('vixo.rv.chatPromoDismissed') === '1') {
                return;
            }
        } catch {}
        els.chatPromoModal.classList.remove('hidden');
        els.chatPromoModal.setAttribute('aria-hidden', 'false');
    }

    function setStatus(text) {
        if (els.status) els.status.textContent = text;
    }

    function setConnectionState(text, isConnected) {
        if (!els.connectionState) return;
        els.connectionState.textContent = text;
        els.connectionState.classList.toggle('text-emerald-300', !!isConnected);
        els.connectionState.classList.toggle('text-gray-300', !isConnected);
    }

    function setOnline(text) {
        if (els.online) els.online.textContent = text;
    }

    function showRemotePlaceholder(show) {
        if (!els.remotePlaceholder) return;
        els.remotePlaceholder.style.display = show ? '' : 'none';
    }

    function setRemoteVideoVisible(isVisible) {
        if (!els.remoteVideo) return;
        els.remoteVideo.style.visibility = isVisible ? 'visible' : 'hidden';
        els.remoteVideo.style.opacity = isVisible ? '1' : '0';
    }

    function stopWaitingDots() {
        if (waitingDotsTimer) {
            window.clearInterval(waitingDotsTimer);
            waitingDotsTimer = 0;
        }
        waitingDotsCount = 3;
        if (els.waitingDots) {
            els.waitingDots.textContent = '...';
        }
    }

    function startWaitingDots() {
        if (!els.waitingDots || waitingDotsTimer) return;
        waitingDotsCount = 3;
        els.waitingDots.textContent = '...';
        waitingDotsTimer = window.setInterval(() => {
            waitingDotsCount = (waitingDotsCount % 3) + 1;
            els.waitingDots.textContent = '.'.repeat(waitingDotsCount);
        }, 450);
    }

    function clearRemoteRevealTimer() {
        if (remoteRevealTimer) {
            window.clearTimeout(remoteRevealTimer);
            remoteRevealTimer = 0;
        }
    }

    function clearWaitingRetryTimer() {
        if (waitingRetryTimer) {
            window.clearTimeout(waitingRetryTimer);
            waitingRetryTimer = 0;
        }
    }

    function clearMatchedConnectTimer() {
        if (matchedConnectTimer) {
            window.clearTimeout(matchedConnectTimer);
            matchedConnectTimer = 0;
        }
    }

    function clearMatchedConnectCountdownTimer() {
        if (matchedConnectCountdownTimer) {
            window.clearInterval(matchedConnectCountdownTimer);
            matchedConnectCountdownTimer = 0;
        }
    }

    function startMatchedConnectCountdown() {
        clearMatchedConnectCountdownTimer();
        let secondsLeft = MATCH_CONNECT_DELAY_SECONDS;
        setStatus(`Match found. Connecting in ${secondsLeft} seconds...`);

        matchedConnectCountdownTimer = window.setInterval(() => {
            secondsLeft -= 1;
            if (secondsLeft <= 0) {
                clearMatchedConnectCountdownTimer();
                return;
            }
            setStatus(`Match found. Connecting in ${secondsLeft} seconds...`);
        }, 1000);
    }

    function setRetryVisible(show) {
        if (!els.remoteRetryBtn) return;
        els.remoteRetryBtn.classList.toggle('hidden', !show);
        if (els.waitingText) {
            els.waitingText.classList.toggle('hidden', !!show);
        }
    }

    function isRetryVisible() {
        return !!(els.remoteRetryBtn && !els.remoteRetryBtn.classList.contains('hidden'));
    }

    function enterRetryMode(message) {
        started = false;
        matched = false;
        clearWaitingRetryTimer();
        stopWaitingDots();
        setRetryVisible(true);
        setStatus(message || 'No stranger available right now. Press Retry to search again.');
        setConnectionState('Not connected', false);
        setOnline('Ready');
    }

    function scheduleRetryVisibility() {
        if (waitingRetryTimer || isRetryVisible()) return;
        const retryDelayMs = retryDelayOverrideMs > 0 ? retryDelayOverrideMs : SEARCH_WAIT_TIMEOUT_MS;
        retryDelayOverrideMs = 0;
        setRetryVisible(false);
        waitingRetryTimer = window.setTimeout(() => {
            waitingRetryTimer = 0;
            if (started && !matched) {
                sendWs({ action: 'skip' });
                enterRetryMode('No stranger available right now. Press Retry to search again.');
            }
        }, retryDelayMs);
    }

    function scheduleRemoteReveal() {
        clearRemoteRevealTimer();
        remoteRevealTimer = window.setTimeout(() => {
            setRemotePlaceholderMode('hidden');
        }, 4000);
    }

    function setRemotePlaceholderMode(mode) {
        if (mode === 'hidden') {
            stopWaitingDots();
            clearWaitingRetryTimer();
            setRetryVisible(false);
            setRemoteVideoVisible(true);
            showRemotePlaceholder(false);
            return;
        }

        if (els.remoteVideo) {
            try { els.remoteVideo.pause(); } catch {}
            try { els.remoteVideo.srcObject = null; } catch {}
        }
        remoteStream = null;
        setRemoteVideoVisible(false);
        showRemotePlaceholder(true);

        if (els.remoteIdle) {
            els.remoteIdle.classList.toggle('hidden', mode !== 'idle');
        }
        if (els.remoteWaiting) {
            els.remoteWaiting.classList.toggle('hidden', mode !== 'waiting');
        }

        if (mode === 'waiting') {
            startWaitingDots();
            scheduleRetryVisibility();
        } else {
            stopWaitingDots();
            clearWaitingRetryTimer();
            setRetryVisible(false);
        }
    }

    function setChatVisible(show) {
        if (!els.chatWrap) return;
        if (show) {
            els.chatWrap.classList.remove('hidden');
            if (els.statusPanel) {
                els.statusPanel.classList.add('hidden');
            }
        } else {
            els.chatWrap.classList.add('hidden');
            if (els.statusPanel) {
                els.statusPanel.classList.remove('hidden');
            }
        }
    }

    function setControlsStarted(isStarted) {
        if (els.connectBtn) {
            els.connectBtn.classList.toggle('is-hidden', !!isStarted);
            els.connectBtn.classList.toggle('is-visible', !isStarted);
            els.connectBtn.disabled = !!isStarted;
        }
        if (els.endBtn) {
            els.endBtn.classList.toggle('is-hidden', !isStarted);
            els.endBtn.classList.toggle('is-visible', !!isStarted);
            els.endBtn.disabled = !isStarted;
        }
    }

    function escapeHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function appendChatMessage(message, mine) {
        if (!els.chatMessages) return;
        const safe = escapeHtml(message).trim();
        if (!safe) return;
        let isLightTheme = false;
        try {
            const root = document.documentElement;
            isLightTheme = root.classList.contains('theme-light') || String(root.getAttribute('data-theme') || '').toLowerCase() === 'light';
        } catch {
            // ignore
        }

        const bubbleClass = mine
            ? (isLightTheme
                ? 'bg-white/55 text-slate-900 border border-white/70 shadow-[0_8px_24px_rgba(15,23,42,0.10)] backdrop-blur-md'
                : 'bg-cyan-400/16 text-cyan-50 border border-cyan-300/30 shadow-[0_10px_24px_rgba(34,211,238,0.16)] backdrop-blur-md')
            : (isLightTheme
                ? 'bg-white/45 text-slate-900 border border-slate-200/85 shadow-[0_8px_24px_rgba(15,23,42,0.08)] backdrop-blur-md'
                : 'bg-slate-700/35 text-slate-100 border border-slate-500/35 shadow-[0_10px_24px_rgba(2,6,23,0.32)] backdrop-blur-md');

        const row = document.createElement('div');
        row.className = `mb-1.5 flex ${mine ? 'justify-end' : 'justify-start'}`;
        row.innerHTML = `<div class="w-fit max-w-[86%] sm:max-w-[72%] rounded-xl px-3 py-2 whitespace-pre-wrap break-all leading-relaxed ${bubbleClass}" style="overflow-wrap:anywhere;max-height:11.5rem;overflow-y:auto;">${safe}</div>`;
        els.chatMessages.appendChild(row);
        els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
    }

    function clearChatMessages() {
        if (!els.chatMessages) return;
        els.chatMessages.innerHTML = '';
    }

    function resetChatForNewStranger(hideChat) {
        clearChatMessages();
        setTypingIndicator(false);
        stopTyping();
        if (els.chatInput) {
            els.chatInput.value = '';
        }
        if (hideChat) {
            setChatVisible(false);
        }
    }

    function setTypingIndicator(show) {
        if (!els.typingIndicator) return;
        els.typingIndicator.classList.toggle('hidden', !show);
    }

    function sendTypingState(isTyping) {
        const next = !!isTyping;
        if (sentTypingState === next) return;
        sentTypingState = next;
        sendWs({ action: 'typing', typing: next });
    }

    function clearTypingStopTimer() {
        if (!typingStopTimer) return;
        window.clearTimeout(typingStopTimer);
        typingStopTimer = 0;
    }

    function stopTyping() {
        clearTypingStopTimer();
        sendTypingState(false);
    }

    function handleLocalTypingInput() {
        if (!matched || !els.chatInput) {
            stopTyping();
            return;
        }

        const hasText = String(els.chatInput.value || '').trim().length > 0;
        if (!hasText) {
            stopTyping();
            return;
        }

        sendTypingState(true);
        clearTypingStopTimer();
        typingStopTimer = window.setTimeout(() => {
            typingStopTimer = 0;
            stopTyping();
        }, 1500);
    }

    function wsUrl(path) {
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${window.location.host}${path}`;
    }

    function sendWs(payload) {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        ws.send(JSON.stringify(payload || {}));
    }

    function hasActivePeerConnection() {
        if (!pc) return false;
        const state = String(pc.connectionState || '').toLowerCase();
        return state === 'connected' || state === 'connecting';
    }

    function getIceServers() {
        const fallback = [{ urls: 'stun:stun.l.google.com:19302' }];
        const configured = config && Array.isArray(config.iceServers) ? config.iceServers : [];
        const normalized = configured
            .map((entry) => {
                if (!entry || typeof entry !== 'object') return null;
                const urls = entry.urls;
                const username = entry.username;
                const credential = entry.credential;
                if (!urls || (typeof urls !== 'string' && !Array.isArray(urls))) return null;
                const server = { urls };
                if (typeof username === 'string' && username) server.username = username;
                if (typeof credential === 'string' && credential) server.credential = credential;
                return server;
            })
            .filter(Boolean);
        return normalized.length ? normalized : fallback;
    }

    async function ensureLocalStream() {
        if (localStream) return localStream;
        localStream = await navigator.mediaDevices.getUserMedia({
            video: videoConstraints(''),
            audio: true,
        });
        localStream.getAudioTracks().forEach((track) => {
            track.enabled = micEnabled;
        });
        localStream.getVideoTracks().forEach((track) => {
            track.enabled = camEnabled;
        });
        if (els.localVideo) {
            els.localVideo.srcObject = localStream;
            try { els.localVideo.play(); } catch {}
        }
        return localStream;
    }

    async function applySignalToPc(data) {
        if (!pc || !data) return;

        const description = data.description;
        const candidate = data.candidate;

        if (description) {
            await pc.setRemoteDescription(new RTCSessionDescription(description));
            if (description.type === 'offer') {
                const answer = await pc.createAnswer();
                await pc.setLocalDescription(answer);
                sendWs({
                    action: 'signal',
                    data: {
                        description: pc.localDescription,
                    },
                });
            }
            return;
        }

        if (candidate) {
            try {
                await pc.addIceCandidate(new RTCIceCandidate(candidate));
            } catch {
                // ignore race conditions
            }
        }
    }

    async function flushPendingSignals() {
        if (!pc || !pendingSignals.length) return;
        const queued = pendingSignals.slice();
        pendingSignals = [];
        for (const item of queued) {
            await applySignalToPc(item);
        }
    }

    function getTrackDeviceId(track) {
        if (!track) return '';
        try {
            const settings = track.getSettings ? track.getSettings() : null;
            return (settings && settings.deviceId) ? String(settings.deviceId) : '';
        } catch {
            return '';
        }
    }

    function closeDeviceModal() {
        if (!els.deviceModal) return;
        els.deviceModal.classList.add('hidden');
        els.deviceModal.setAttribute('aria-hidden', 'true');
    }

    function openDeviceModal() {
        if (!els.deviceModal) return;
        els.deviceModal.classList.remove('hidden');
        els.deviceModal.setAttribute('aria-hidden', 'false');
    }

    async function populateDeviceOptions() {
        if (!els.cameraSelect || !els.micSelect) return;

        try {
            await ensureLocalStream();
        } catch {
            // continue; device list may still be available with limited labels
        }

        let devices = [];
        try {
            devices = await navigator.mediaDevices.enumerateDevices();
        } catch {
            devices = [];
        }

        const cameras = devices.filter((d) => d && d.kind === 'videoinput');
        const microphones = devices.filter((d) => d && d.kind === 'audioinput');

        const currentCamId = getTrackDeviceId(localStream && localStream.getVideoTracks()[0]);
        const currentMicId = getTrackDeviceId(localStream && localStream.getAudioTracks()[0]);

        els.cameraSelect.innerHTML = '';
        cameras.forEach((device, index) => {
            const option = document.createElement('option');
            option.value = String(device.deviceId || '');
            option.textContent = device.label || `Camera ${index + 1}`;
            if (option.value && option.value === currentCamId) {
                option.selected = true;
            }
            els.cameraSelect.appendChild(option);
        });

        els.micSelect.innerHTML = '';
        microphones.forEach((device, index) => {
            const option = document.createElement('option');
            option.value = String(device.deviceId || '');
            option.textContent = device.label || `Microphone ${index + 1}`;
            if (option.value && option.value === currentMicId) {
                option.selected = true;
            }
            els.micSelect.appendChild(option);
        });

        if (!els.cameraSelect.value && currentCamId) {
            els.cameraSelect.value = currentCamId;
        }
        if (!els.micSelect.value && currentMicId) {
            els.micSelect.value = currentMicId;
        }
    }

    async function applySelectedDevices() {
        const cameraDeviceId = (els.cameraSelect && els.cameraSelect.value) ? String(els.cameraSelect.value) : '';
        const micDeviceId = (els.micSelect && els.micSelect.value) ? String(els.micSelect.value) : '';

        const constraints = {
            video: videoConstraints(cameraDeviceId),
            audio: micDeviceId ? { deviceId: { exact: micDeviceId } } : true,
        };

        let nextStream;
        try {
            nextStream = await navigator.mediaDevices.getUserMedia(constraints);
        } catch {
            setStatus('Unable to switch camera/microphone. Check permissions and device availability.');
            return;
        }

        const nextVideoTrack = nextStream.getVideoTracks()[0] || null;
        const nextAudioTrack = nextStream.getAudioTracks()[0] || null;

        if (nextVideoTrack) nextVideoTrack.enabled = camEnabled;
        if (nextAudioTrack) nextAudioTrack.enabled = micEnabled;

        if (pc) {
            const senders = pc.getSenders ? pc.getSenders() : [];
            senders.forEach((sender) => {
                if (!sender || !sender.track) return;
                if (sender.track.kind === 'video' && nextVideoTrack) {
                    try { sender.replaceTrack(nextVideoTrack); } catch {}
                }
                if (sender.track.kind === 'audio' && nextAudioTrack) {
                    try { sender.replaceTrack(nextAudioTrack); } catch {}
                }
            });
        }

        const previousStream = localStream;
        localStream = nextStream;
        if (els.localVideo) {
            els.localVideo.srcObject = localStream;
        }

        if (previousStream) {
            previousStream.getTracks().forEach((track) => {
                try { track.stop(); } catch {}
            });
        }

        setStatus('Camera and microphone updated.');
        closeDeviceModal();
    }

    function clearPeerConnection() {
        clearMatchedConnectTimer();
        clearMatchedConnectCountdownTimer();

        if (connectWatchdog) {
            window.clearTimeout(connectWatchdog);
            connectWatchdog = 0;
        }

        if (pc) {
            try { pc.ontrack = null; } catch {}
            try { pc.onicecandidate = null; } catch {}
            try { pc.onconnectionstatechange = null; } catch {}
            try { pc.close(); } catch {}
        }
        pc = null;
        pendingSignals = [];

        remoteStream = null;
        clearRemoteRevealTimer();
        if (els.remoteVideo) els.remoteVideo.srcObject = null;
        setRemotePlaceholderMode(started ? 'waiting' : 'idle');
    }

    async function makePeerConnection(offerer) {
        clearPeerConnection();
        const stream = await ensureLocalStream();

        pc = new RTCPeerConnection({
            iceServers: getIceServers(),
        });

        stream.getTracks().forEach((track) => {
            pc.addTrack(track, stream);
        });

        pc.ontrack = (event) => {
            const [first] = event.streams || [];
            if (!first) return;
            remoteStream = first;
            if (els.remoteVideo) {
                els.remoteVideo.srcObject = remoteStream;
                try { els.remoteVideo.play(); } catch {}
            }
            setRemotePlaceholderMode('hidden');
        };

        pc.onicecandidate = (event) => {
            if (!event.candidate) return;
            sendWs({
                action: 'signal',
                data: {
                    candidate: event.candidate,
                },
            });
        };

        pc.onconnectionstatechange = () => {
            const state = (pc && pc.connectionState) || '';
            if (state === 'connected') {
                if (connectWatchdog) {
                    window.clearTimeout(connectWatchdog);
                    connectWatchdog = 0;
                }
                setStatus('Connected with a random user.');
                setConnectionState('Connected', true);
                setOnline('Live now');
                setRemotePlaceholderMode('hidden');
                setChatVisible(true);
            } else if (state === 'failed' || state === 'disconnected') {
                matched = false;
                resetChatForNewStranger(true);
                setStatus('Connection failed due to network restrictions. Try switching WiFi or mobile data.');
                setConnectionState('Not connected', false);
                sendWs({ action: 'skip' });
            }
        };

        connectWatchdog = window.setTimeout(() => {
            const state = (pc && pc.connectionState) || '';
            if (state !== 'connected') {
                matched = false;
                resetChatForNewStranger(true);
                setStatus('Connection failed due to network restrictions. Try switching WiFi or mobile data.');
                setConnectionState('Not connected', false);
                sendWs({ action: 'skip' });
            }
        }, 10000);

        if (offerer) {
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            sendWs({
                action: 'signal',
                data: {
                    description: pc.localDescription,
                },
            });
        }

        await flushPendingSignals();
    }

    async function handleSignal(data) {
        if (!data) return;
        if (!pc) {
            pendingSignals.push(data);
            return;
        }

        await applySignalToPc(data);
    }

    function startMatching() {
        clearMatchedConnectTimer();
        clearMatchedConnectCountdownTimer();
        clearWaitingRetryTimer();
        setRetryVisible(false);
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            setStatus('Signaling not ready. Reconnecting…');
            setConnectionState('Not connected', false);
            connectSocket();
            return;
        }
        sendWs({ action: 'start' });
        setStatus('Searching random user…');
        setConnectionState('Searching…', false);
        setOnline('Matching…');
        started = true;
        setControlsStarted(true);
        setRemotePlaceholderMode('waiting');
    }

    function stopAll() {
        clearMatchedConnectTimer();
        clearMatchedConnectCountdownTimer();
        started = false;
        matched = false;
        sendWs({ action: 'skip' });
        clearPeerConnection();
        resetChatForNewStranger(true);
        setStatus('Session ended. Press Start to begin again.');
        setConnectionState('Not connected', false);
        setOnline('Offline');
        setControlsStarted(false);
        setRemotePlaceholderMode('idle');
    }

    function connectSocket() {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
            return;
        }

        ws = new WebSocket(wsUrl(config.wsPath || '/ws/random-video/'));

        ws.addEventListener('open', () => {
            setOnline('Ready');
            if (started) {
                sendWs({ action: 'start' });
            }
        });

        ws.addEventListener('close', () => {
            setOnline('Disconnected');
            clearPeerConnection();
            if (started) {
                window.setTimeout(connectSocket, 1200);
            }
        });

        ws.addEventListener('message', async (event) => {
            let payload = {};
            try {
                payload = JSON.parse(event.data || '{}');
            } catch {
                payload = {};
            }

            const type = String(payload.type || '');
            if (type === 'ready') {
                setOnline('Ready');
                return;
            }
            if (type === 'rejected') {
                sendWs({ action: 'skip' });
                enterRetryMode('Too many users right now. Press Retry to search again.');
                setRemotePlaceholderMode('waiting');
                return;
            }
            if (type === 'waiting') {
                if (matched || hasActivePeerConnection()) {
                    return;
                }
                if (!started) {
                    if (isRetryVisible()) {
                        enterRetryMode('No stranger available right now. Press Retry to search again.');
                        setRemotePlaceholderMode('waiting');
                        return;
                    }
                    setRemotePlaceholderMode('idle');
                    return;
                }
                matched = false;
                resetChatForNewStranger(true);
                setStatus('Searching random user…');
                setConnectionState('Searching…', false);
                setRemotePlaceholderMode('waiting');
                return;
            }
            if (type === 'matched') {
                if (!started) {
                    sendWs({ action: 'skip' });
                    setRemotePlaceholderMode(isRetryVisible() ? 'waiting' : 'idle');
                    return;
                }
                matched = true;
                setChatVisible(false);
                resetChatForNewStranger(true);
                const offerer = !!payload.offerer;
                startMatchedConnectCountdown();
                setConnectionState('Connecting…', false);
                setOnline('Connecting…');
                setRemotePlaceholderMode('waiting');
                setRetryVisible(false);
                clearMatchedConnectTimer();
                matchedConnectTimer = window.setTimeout(async () => {
                    matchedConnectTimer = 0;
                    clearMatchedConnectCountdownTimer();
                    if (!started || !matched) {
                        return;
                    }
                    try {
                        await makePeerConnection(offerer);
                    } catch {
                        setStatus('Camera or microphone unavailable. Please allow permissions and retry.');
                        setConnectionState('Not connected', false);
                        sendWs({ action: 'skip' });
                    }
                }, MATCH_CONNECT_DELAY_MS);
                return;
            }
            if (type === 'signal') {
                await handleSignal(payload.data || {});
                return;
            }
            if (type === 'peer_left') {
                if (!started) {
                    setRemotePlaceholderMode(isRetryVisible() ? 'waiting' : 'idle');
                    return;
                }
                matched = false;
                setTypingIndicator(false);
                resetChatForNewStranger(true);
                clearPeerConnection();
                setStatus('Stranger left. Finding next user…');
                setConnectionState('Searching…', false);
                setRemotePlaceholderMode('waiting');
                if (started) {
                    sendWs({ action: 'start' });
                }
                return;
            }
            if (type === 'chat_message') {
                setTypingIndicator(false);
                appendChatMessage(payload.message || '', false);
                return;
            }
            if (type === 'typing') {
                setTypingIndicator(!!payload.typing && matched);
                return;
            }
            if (type === 'report_ack') {
                setStatus('Report submitted. Finding a new user…');
                sendWs({ action: 'skip' });
                return;
            }
            if (type === 'warn_sent') {
                setStatus('Warning sent to user.');
                return;
            }
            if (type === 'warn_denied') {
                setStatus('Only superuser can send warnings.');
                return;
            }
            if (type === 'warn_failed') {
                setStatus('Could not send warning right now.');
                return;
            }
            if (type === 'admin_warning') {
                const msg = String(payload.message || '').trim();
                if (msg) {
                    openWarnAlertModal(payload.sender || 'Vixogram', msg);
                }
                return;
            }
        });
    }

    function init() {
        if (!els.connectBtn || !els.nextBtn || !els.endBtn) return;

        const requestStart = () => {
            started = true;
            startMatching();
        };

        const requestStartWithWelcome = () => {
            requestStart();
        };

        connectSocket();
        setConnectionState('Not connected', false);
        setStatus('Press Start Video Chat to begin random matching.');
        setControlsStarted(false);
        setRemotePlaceholderMode('idle');
        ensureLocalStream().catch(() => {
            setStatus('Camera preview unavailable. Please allow camera access and refresh.');
        });

        els.connectBtn.addEventListener('click', () => {
            requestStartWithWelcome();
        });

        if (els.remoteStartBtn) {
            els.remoteStartBtn.addEventListener('click', () => {
                requestStartWithWelcome();
            });
        }

        if (els.remoteRetryBtn) {
            els.remoteRetryBtn.addEventListener('click', () => {
                sendWs({ action: 'skip' });
                retryDelayOverrideMs = SEARCH_WAIT_TIMEOUT_MS;
                requestStart();
            });
        }

        els.nextBtn.addEventListener('click', () => {
            if (!started) {
                started = true;
            }
            clearMatchedConnectTimer();
            matched = false;
            retryDelayOverrideMs = SEARCH_WAIT_TIMEOUT_MS;
            clearWaitingRetryTimer();
            setRetryVisible(false);
            resetChatForNewStranger(true);
            sendWs({ action: 'skip' });
            setStatus('Searching random user…');
            setConnectionState('Searching…', false);
            setOnline('Matching…');
            setControlsStarted(true);
            setRemotePlaceholderMode('waiting');
        });

        els.endBtn.addEventListener('click', () => {
            stopAll();
        });

        if (els.deviceBtn) {
            els.deviceBtn.addEventListener('click', async () => {
                await populateDeviceOptions();
                openDeviceModal();
            });
        }

        if (els.deviceApplyBtn) {
            els.deviceApplyBtn.addEventListener('click', () => {
                applySelectedDevices();
            });
        }

        if (els.deviceCloseBtn) {
            els.deviceCloseBtn.addEventListener('click', () => {
                closeDeviceModal();
            });
        }

        if (els.deviceBackdrop) {
            els.deviceBackdrop.addEventListener('click', () => {
                closeDeviceModal();
            });
        }

        if (els.chatPromoLaterBtn) {
            els.chatPromoLaterBtn.addEventListener('click', () => {
                closeChatPromoModal();
            });
        }

        if (els.chatPromoBackdrop) {
            els.chatPromoBackdrop.addEventListener('click', () => {
                closeChatPromoModal();
            });
        }

        if (els.welcomeContinueBtn) {
            els.welcomeContinueBtn.addEventListener('click', () => {
                const handler = welcomeContinueHandler;
                closeWelcomeModal();
                if (typeof handler === 'function') {
                    handler();
                }
            });
        }

        if (els.welcomeBackdrop) {
            els.welcomeBackdrop.addEventListener('click', () => {
                closeWelcomeModal();
            });
        }

        if (isSuperuser()) {
            if (els.warnBtn) {
                els.warnBtn.addEventListener('click', () => {
                    if (!matched) {
                        setStatus('Warn karne ke liye pehle user se connected hona zaruri hai.');
                        return;
                    }
                    openWarnModal();
                });
            }

            if (els.warnCancelBtn) {
                els.warnCancelBtn.addEventListener('click', () => {
                    closeWarnModal();
                });
            }

            if (els.warnBackdrop) {
                els.warnBackdrop.addEventListener('click', () => {
                    closeWarnModal();
                });
            }

            if (els.warnSendBtn) {
                els.warnSendBtn.addEventListener('click', () => {
                    if (!matched) {
                        setStatus('User disconnected. Warning send nahi hua.');
                        return;
                    }
                    const warnMessage = String((els.warnInput && els.warnInput.value) || '').trim();
                    if (!warnMessage) {
                        setStatus('Warning message likho.');
                        if (els.warnInput) els.warnInput.focus();
                        return;
                    }
                    sendWs({ action: 'warn', message: warnMessage });
                    if (els.warnInput) {
                        els.warnInput.value = '';
                    }
                    closeWarnModal();
                });
            }
        }

        if (els.warnAlertOkBtn) {
            els.warnAlertOkBtn.addEventListener('click', () => {
                closeWarnAlertModal();
            });
        }

        if (els.warnAlertBackdrop) {
            els.warnAlertBackdrop.addEventListener('click', () => {
                closeWarnAlertModal();
            });
        }

        document.addEventListener('keydown', (event) => {
            const isCtrlB = (event.ctrlKey || event.metaKey)
                && !event.altKey
                && String(event.key || '').toLowerCase() === 'b';

            if (isCtrlB) {
                event.preventDefault();
                if (event.repeat) return;
                if (started) {
                    stopAll();
                } else {
                    requestStartWithWelcome();
                }
                return;
            }

            if (event.key === 'Escape') {
                closeDeviceModal();
                closeChatPromoModal();
                closeWelcomeModal();
                closeWarnModal();
                closeWarnAlertModal();
            }
        });

        window.setTimeout(() => {
            openChatPromoModal();
        }, 180000);

        if (els.chatForm && els.chatInput) {
            els.chatForm.addEventListener('submit', (event) => {
                event.preventDefault();
                if (!matched) return;
                const message = String(els.chatInput.value || '').trim();
                if (!message) return;
                stopTyping();
                sendWs({ action: 'chat', message });
                appendChatMessage(message, true);
                els.chatInput.value = '';
            });

            els.chatInput.addEventListener('input', () => {
                handleLocalTypingInput();
            });

            els.chatInput.addEventListener('blur', () => {
                stopTyping();
            });
        }

        setChatVisible(false);

        window.addEventListener('beforeunload', () => {
            stopWaitingDots();
            stopTyping();
            try { stopAll(); } catch {}
            try { if (ws) ws.close(); } catch {}
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
