(function () {
    function __escapeHtml(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
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

    const cfg = (window.__vixo_chat_config && typeof window.__vixo_chat_config === 'object')
        ? window.__vixo_chat_config
        : (readJsonScript('vixo-chat-config') || {});

    function initSidebarSectionCollapse() {
        const toggles = document.querySelectorAll('[data-vixo-collapse-toggle][data-vixo-collapse-key]');
        if (!toggles || !toggles.length) return;

        function storageKey(k) {
            return `vixo_sidebar_section_collapsed:${String(k || '')}`;
        }

        function setCollapsed(key, collapsed) {
            const body = document.querySelector(`[data-vixo-collapse-body][data-vixo-collapse-key="${CSS.escape(String(key))}"]`);
            const toggle = document.querySelector(`[data-vixo-collapse-toggle][data-vixo-collapse-key="${CSS.escape(String(key))}"]`);
            if (!body || !toggle) return;

            const chevron = toggle.querySelector('[data-vixo-collapse-chevron]');
            if (collapsed) {
                body.classList.add('hidden');
                toggle.setAttribute('aria-expanded', 'false');
                if (chevron) chevron.style.transform = 'rotate(-90deg)';
            } else {
                body.classList.remove('hidden');
                toggle.setAttribute('aria-expanded', 'true');
                if (chevron) chevron.style.transform = '';
            }
        }

        function loadInitialState(key) {
            try {
                const v = window.localStorage.getItem(storageKey(key));
                return v === '1';
            } catch {
                return false;
            }
        }

        toggles.forEach((btn) => {
            const key = btn.getAttribute('data-vixo-collapse-key') || '';
            if (!key) return;

            // Initial
            const collapsed = loadInitialState(key);
            setCollapsed(key, collapsed);

            btn.addEventListener('click', () => {
                const body = document.querySelector(`[data-vixo-collapse-body][data-vixo-collapse-key="${CSS.escape(String(key))}"]`);
                if (!body) return;
                const isCollapsed = body.classList.contains('hidden');
                const nextCollapsed = !isCollapsed;
                setCollapsed(key, nextCollapsed);
                try {
                    window.localStorage.setItem(storageKey(key), nextCollapsed ? '1' : '0');
                } catch {
                    // ignore
                }
            });
        });
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

        // If the server rendered the blocked state, the form doesn't exist.
        // On unblock, reload to restore the form.
        if (!form) {
            if (!normalized) {
                try { window.location.reload(); } catch {}
            }
            return;
        }

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

    // Realtime block/unblock (admin action)
    window.addEventListener('chat:block_status', (e) => {
        const d = e && e.detail ? e.detail : {};
        applyChatBlockedUI(!!d.blocked, { allowPopup: true });
    });

    // Initialize from embedded config (if present)
    if (typeof cfg.chatBlocked !== 'undefined') {
        // Initialize UI silently (no popups on load).
        applyChatBlockedUI(!!cfg.chatBlocked, { allowPopup: false });
    }

    // --- Mobile chat message actions (swipe + long-press) ---
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

    // Swipe left to reply; long-press to reveal reply/+ / ⋮
    // Prevent horizontal scrolling during the gesture to avoid mobile overflow/side space.
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
            if (!__isMobileChatViewport()) return;
            try { closeAllReactionPickers(); } catch {}
            try { closeAllMessageMenus(); } catch {}
            openMessageActionBar(msg);
        }, 520);
    }, { passive: true });

    document.addEventListener('touchmove', function(e) {
        if (touchTimer) clearTimeout(touchTimer);
        if (!touchActiveMsg) return;
        if (e.touches.length !== 1) return;

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

        if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) && dx < 0 && dt < 400) {
            closeAllMessageActionBars();
            const replyBtn = msg.querySelector('[data-reply-button]');
            if (replyBtn) replyBtn.click();
        }
    }, { passive: true });

    document.addEventListener('touchcancel', function() {
        if (touchTimer) clearTimeout(touchTimer);
        touchActiveMsg = null;
    }, { passive: true });

    document.addEventListener('click', function (e) {
        if (!__isMobileChatViewport()) return;
        const keep = e.target && e.target.closest
            ? e.target.closest('.vixo-msg.vixo-actions-open [data-msg-actions], .vixo-msg.vixo-actions-open [data-message-menu]')
            : null;
        if (keep) return;
        closeAllMessageActionBars();
    }, true);

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
                        close();
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
                    close();
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
            setUploadingState(false);
        });

        document.body.addEventListener('htmx:responseError', (e) => {
            if (!e || !e.target) return;
            if (e.target !== form) return;
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

    // Explicit marker from server after a file upload; ensure the file chooser is cleared.
    document.body.addEventListener('chatFileUploaded', () => {
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

    // If server rate-limits message sends (429), show a countdown on the Send button.
    let sendCooldownTimer = null;
    function startSendCooldown(seconds) {
        const btn = document.getElementById('chat_send_btn');
        const input = document.getElementById('id_body');
        if (!btn || !input) return;

        if (!btn.dataset.originalText) {
            btn.dataset.originalText = (btn.textContent || 'Send').trim();
        }

        let remaining = Math.max(1, Number(seconds || 1));
        btn.disabled = true;
        input.disabled = true;

        const tick = () => {
            btn.textContent = `Wait ${remaining}s`;
            remaining -= 1;
            if (remaining < 0) {
                window.clearInterval(sendCooldownTimer);
                sendCooldownTimer = null;
                btn.disabled = false;
                input.disabled = false;
                btn.textContent = btn.dataset.originalText || 'Send';
                try { input.focus(); } catch (e) {}
            }
        };

        if (sendCooldownTimer) window.clearInterval(sendCooldownTimer);
        tick();
        sendCooldownTimer = window.setInterval(tick, 1000);
    }

    // When a file is selected, switch the main form to upload mode.
    (function setupUploadModeSwitcher() {
        const msgForm = document.getElementById('chat_message_form');
        const fileInput = document.getElementById('chat_file_input');
        const uploadBtn = document.getElementById('chat_upload_btn');
        const captionInput = document.getElementById('chat_file_caption');
        const msgInput = (msgForm && msgForm.querySelector('[name="body"]')) || document.getElementById('id_body');

        const modal = document.getElementById('upload_modal');
        const modalBackdrop = document.getElementById('upload_modal_backdrop');
        const modalClose = document.getElementById('upload_modal_close');
        const modalCancel = document.getElementById('upload_modal_cancel');
        const modalSend = document.getElementById('upload_modal_send');
        const modalImg = document.getElementById('upload_modal_img');
        const modalVideo = document.getElementById('upload_modal_video');
        const modalCaption = document.getElementById('upload_modal_caption');
        const modalHint = document.getElementById('upload_modal_hint');

        if (!msgForm || !fileInput) return;

        let cropper = null;
        let previewUrl = null;
        let modalOpen = false;

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

        function closeModal(opts) {
            const options = opts || {};
            modalOpen = false;
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
            if (modal) modal.classList.add('hidden');

            if (options.clearFile) {
                if (captionInput) captionInput.value = '';
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
                cleanupCropper();
                modalImg.classList.add('hidden');
                modalVideo.classList.add('hidden');
                if (modalHint) modalHint.textContent = 'Preview unavailable for this file type.';
            }

            modal.classList.remove('hidden');
        }

        function syncUploadMode() {
            const hasFile = !!(fileInput.files && fileInput.files.length);
            if (!hasFile) {
                if (captionInput) captionInput.value = '';
                return;
            }

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
                            // fallback to original file
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

        if (__containsLink(text || '')) {
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
    const onlineCountEl = document.getElementById('online-count');

    // Chat input behavior:
    // - Enter: send
    // - Shift+Enter: new line
    // Note: when the mention panel is open, Enter is used to select a mention.
    if (form && input) {
        input.addEventListener('keydown', function (e) {
            if (e.key !== 'Enter') return;
            if (e.shiftKey) return;
            if (e.isComposing) return;

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
        typingIndicatorEl.classList.remove('hidden');
        typingIndicatorTextEl.textContent = `${names.join(', ')} typing...`;
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
                            updateLastIdFromDom();
                        }
                        window.__forceNextChatScroll = true;
                        try { __chatAutoScrollEnabled = true; } catch {}
                        forceScrollToBottomNow();
                    }

                    // Reset UI after send
                    if (input) input.value = '';
                    if (typedMsInput) typedMsInput.value = '';
                    if (replyToIdInput) replyToIdInput.value = '';
                    if (replyBar) replyBar.classList.add('hidden');
                    if (replyBarPreview) replyBarPreview.textContent = '';
                    if (replyBarAuthor) replyBarAuthor.textContent = '';
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
                if (!__linksAllowed && __containsLink(body)) {
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

                                const safe = __escapeHtml(body).replace(/\n/g, '<br>');
                                const pendingHtml = `
<div data-pending="1" data-client-nonce="${clientNonce}" class="vixo-msg group relative w-full flex justify-end opacity-90">
    <div class="flex flex-col items-end max-w-[90%] sm:max-w-[75%] lg:max-w-[65%]">
        <div class="flex items-end gap-2">
            <div data-message-bubble class="relative px-4 py-3 rounded-2xl shadow-sm shadow-black/20 backdrop-blur-md bg-gradient-to-r from-purple-500 via-indigo-500 to-sky-500 text-white vixo-keep-white rounded-tr-none border border-white/10">
                <div class="text-[15px] sm:text-[16px] leading-relaxed text-white/95 vixo-keep-white">${safe}</div>
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
            if (input) input.value = '';
            if (typedMsInput) typedMsInput.value = '';
            if (replyToIdInput) replyToIdInput.value = '';
            if (replyBar) replyBar.classList.add('hidden');
            if (replyBarPreview) replyBarPreview.textContent = '';
            if (replyBarAuthor) replyBarAuthor.textContent = '';
            // Don't auto-scroll here; we scroll once when the server echoes back.
            // if (typeof scrollToBottom === 'function') {
            //     scrollToBottom({ force: true, behavior: 'auto' });
            // }
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
    let __wsReconnectTimer = null;
    let __pollTimer = null;

    function __wsIsOpen() {
        try {
            return !!(socket && socket.readyState === WebSocket.OPEN);
        } catch {
            return false;
        }
    }

    function startPolling() {
        if (__pollTimer) return;
        __pollTimer = setInterval(poll, 1200);
    }

    function stopPolling() {
        if (!__pollTimer) return;
        try { clearInterval(__pollTimer); } catch {}
        __pollTimer = null;
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

        const panel = document.getElementById('challenge_drawer_panel');
        let __drawerCloseTimer = null;

        function openDrawer() {
            if (__drawerCloseTimer) {
                clearTimeout(__drawerCloseTimer);
                __drawerCloseTimer = null;
            }
            drawer.classList.remove('opacity-0', 'pointer-events-none');
            document.body.classList.add('overflow-hidden');
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
        const nodes = container.querySelectorAll ? container.querySelectorAll('time[data-dt]') : [];
        if (!nodes || !nodes.length) return;

        const timeFmt = new Intl.DateTimeFormat(undefined, {
            hour: '2-digit',
            minute: '2-digit',
        });
        const fullFmt = new Intl.DateTimeFormat(undefined, {
            dateStyle: 'medium',
            timeStyle: 'short',
        });

        nodes.forEach((el) => {
            const iso = el.getAttribute('data-dt');
            if (!iso) return;
            const d = new Date(iso);
            if (Number.isNaN(d.getTime())) return;

            el.textContent = timeFmt.format(d);
            // Hover tooltip for clarity across dates/timezones
            el.setAttribute('title', fullFmt.format(d));
            if (!el.getAttribute('datetime')) el.setAttribute('datetime', iso);
        });
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

    function connect() {
        try {
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
            if (__wsReconnectTimer) {
                clearTimeout(__wsReconnectTimer);
                __wsReconnectTimer = null;
            }
            updateLastIdFromDom();
            if (document.visibilityState === 'visible') sendReadAck(lastId);
            // On initial load/room switch, start at the latest message.
            forceScrollToBottomNow();

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
                try {
                    const nonce = payload.client_nonce ? String(payload.client_nonce) : '';
                    if (nonce) {
                        if (__seenChatNonces.has(nonce)) return;
                        __seenChatNonces.set(nonce, Date.now());

                        if (__seenChatNonces.size > 400) {
                            const cutoff = Date.now() - 60_000;
                            for (const [k, t] of __seenChatNonces) {
                                if (t < cutoff || __seenChatNonces.size > 350) __seenChatNonces.delete(k);
                                else break;
                            }
                        }

                        const pending = __pendingByNonce.get(nonce);
                        if (pending) {
                            try {
                                const wasAtBottom = messagesEl && messagesEl.lastElementChild === pending;
                                pending.style.visibility = 'hidden';
                                pending.insertAdjacentHTML('afterend', payload.html);
                                const newEl = pending.nextElementSibling;
                                pending.remove();
                                if (newEl) newEl.style.visibility = 'visible';
                                if (wasAtBottom) window.__forceNextChatScroll = false;
                            } catch {}
                            __pendingByNonce.delete(nonce);
                        } else {
                            messagesEl.insertAdjacentHTML('beforeend', payload.html);
                        }
                    } else {
                        messagesEl.insertAdjacentHTML('beforeend', payload.html);
                    }
                } catch {
                    // ignore
                }
                const emptyEl = document.getElementById('empty_state');
                if (emptyEl) emptyEl.remove();
                if (messagesEl && messagesEl.classList.contains('hidden')) {
                    messagesEl.classList.remove('hidden');
                }
                hydrateLocalTimes(messagesEl);
                updateLastIdFromDom();
                const shouldForce = !!window.__forceNextChatScroll || (!!__chatAutoScrollEnabled && isNearBottom());
                if (window.__forceNextChatScroll) {
                    window.__forceNextChatScroll = false;
                    __chatAutoScrollEnabled = true;
                }
                if (shouldForce) {
                    forceScrollToBottomNow();
                    __hidePrivateNewMsgJump();
                } else {
                    // Only in private chats (button exists): show an Instagram-like jump-to-latest indicator.
                    __showPrivateNewMsgJump();
                }
                if (document.visibilityState === 'visible') sendReadAck(lastId);
                return;
            }

            if (payload.type === 'challenge_event' && payload.html) {
                const emptyEl = document.getElementById('empty_state');
                if (emptyEl) emptyEl.remove();
                if (messagesEl && messagesEl.classList.contains('hidden')) {
                    messagesEl.classList.remove('hidden');
                }
                messagesEl.insertAdjacentHTML('beforeend', payload.html);
                hydrateLocalTimes(messagesEl);
                applyConsecutiveHeaderGrouping(messagesEl);
                updateLastIdFromDom();
                if (payload.state) setChallengeState(payload.state);
                const shouldForce = !!window.__forceNextChatScroll || (!!__chatAutoScrollEnabled && isNearBottom());
                if (window.__forceNextChatScroll) {
                    window.__forceNextChatScroll = false;
                    __chatAutoScrollEnabled = true;
                }
                if (shouldForce) forceScrollToBottomNow();
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

            if (payload.type === 'typing') {
                handleTypingEvent(payload);
                return;
            }

            if (payload.type === 'message_update' && payload.message_id && payload.html) {
                const el = document.getElementById(`msg-${payload.message_id}`);
                if (el) {
                    el.outerHTML = payload.html;
                    hydrateLocalTimes(document);
                    applyReadTicks(lastOtherReadId);
                }
                return;
            }

            if (payload.type === 'message_delete' && payload.message_id) {
                const el = document.getElementById(`msg-${payload.message_id}`);
                if (el) el.remove();
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
                if (onlineCountEl) onlineCountEl.textContent = payload.online_count;
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
            startPolling();
            // Simple reconnect
            if (!__wsReconnectTimer) {
                __wsReconnectTimer = setTimeout(() => {
                    __wsReconnectTimer = null;
                    connect();
                }, 1000);
            }
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

    // Ensure correct position on initial render
    document.addEventListener('DOMContentLoaded', function () {
        updateLastIdFromDom();
        hydrateLocalTimes(document);
        applyReadTicks(lastOtherReadId);
        safeScrollToBottom();
    });

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

    // -------- Message Edit/Delete (actions menu) --------
    document.addEventListener('click', async function (e) {
        const editBtn = e.target.closest('[data-edit-message]');
        const delBtn = e.target.closest('[data-delete-message]');

        if (!editBtn && !delBtn) return;
        e.preventDefault();
        e.stopPropagation();

        const messageId = (editBtn || delBtn).dataset.messageId;
        if (!messageId) return;

        // Close any open message menu after choosing an action
        closeAllMessageMenus();

        if (editBtn) {
            const body = editBtn.dataset.messageBody || '';
            startEditingMessage(messageId, body);
            return;
        }

        if (delBtn) {
            const url = messageDeleteUrlTemplate.replace('/0/', `/${messageId}/`);
            try {
                await fetch(url, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': (typeof getCookie === 'function' ? getCookie('csrftoken') : ''),
                    },
                    body: new URLSearchParams(),
                });
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
            setCallStatus('Error: ' + (e && e.message ? e.message : String(e)));

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
        if (!callActive) return;
        try {
            if (reason) setCallStatus(reason);
            // Broadcast end marker (only once is fine; server dedupes)
            if (callTypeActive) await postCallEvent('end', callTypeActive);
        } catch {}

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
        try {
            updateLastIdFromDom();
            const res = await fetch(`${pollUrl}?after=${lastId}`, { credentials: 'same-origin' });
            if (!res.ok) return;
            const data = await res.json();
            if (data && typeof data.online_count !== 'undefined') {
                if (onlineCountEl) onlineCountEl.textContent = data.online_count;
            }
            if (data && data.messages_html) {
                const emptyEl = document.getElementById('empty_state');
                if (emptyEl) emptyEl.remove();
                if (messagesEl && messagesEl.classList.contains('hidden')) {
                    messagesEl.classList.remove('hidden');
                }
                messagesEl.insertAdjacentHTML('beforeend', data.messages_html);
                hydrateLocalTimes(messagesEl);
                updateLastIdFromDom();
                if (__chatAutoScrollEnabled) forceScrollToBottomNow();
            }
            if (data && typeof data.last_id !== 'undefined') {
                const newLast = parseInt(String(data.last_id), 10);
                if (!Number.isNaN(newLast) && newLast > lastId) lastId = newLast;
            }
        } catch {
            // ignore
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
        const preview = btn.getAttribute('data-reply-preview') || '';

        if (replyToIdInput) replyToIdInput.value = msgId;
        if (replyBarAuthor) replyBarAuthor.textContent = author;
        if (replyBarPreview) replyBarPreview.textContent = preview;
        if (replyBar) replyBar.classList.remove('hidden');
        if (input) input.focus();
    }, true);

    // Click replied-to snippet to jump to original
    document.addEventListener('click', function (e) {
        const jump = e.target && e.target.closest ? e.target.closest('[data-scroll-to]') : null;
        if (!jump) return;
        const targetId = jump.getAttribute('data-scroll-to');
        if (!targetId) return;
        const el = document.getElementById(targetId);
        if (!el) return;
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
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

    (function initMobileSidebarToggle() {
        const sidebar = document.getElementById('chat_sidebar');
        const panel = document.getElementById('chat_sidebar_panel');
        const openBtn = document.getElementById('chat_sidebar_open');
        const closeBtn = document.getElementById('chat_sidebar_close');
        if (!sidebar || !panel || !openBtn || !closeBtn) return;

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
            'flex', 'items-start', 'justify-center',
            'bg-gray-900/60', 'p-4', 'pt-20'
        ];

        function closeSidebar() {
            if (!isMobile()) return;
            sidebar.classList.add('hidden');
            sidebar.classList.remove(...overlayClasses);
            if (!isIOS()) document.body.classList.remove('overflow-hidden');
        }

        function openSidebar() {
            if (!isMobile()) return;
            sidebar.classList.remove('hidden');
            sidebar.classList.add(...overlayClasses);
            // iOS Safari: scroll-lock via overflow-hidden can break input focus/typing in fixed overlays.
            if (!isIOS()) document.body.classList.add('overflow-hidden');
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
                return;
            }
            // Only auto-close when we actually switch into mobile mode (not on iOS keyboard resize).
            closeSidebar();
        }

        openBtn.addEventListener('click', openSidebar);
        closeBtn.addEventListener('click', closeSidebar);

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
    })();
})();
