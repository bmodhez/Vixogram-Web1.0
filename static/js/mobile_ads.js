(function () {
  'use strict';

  function readJsonScript(id) {
    try {
      const el = document.getElementById(id);
      if (!el) return null;
      const raw = (el.textContent || el.innerText || '').trim();
      if (!raw) return null;
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  function nowMs() {
    return Date.now();
  }

  function isMobileWidth() {
    try {
      return window.matchMedia && window.matchMedia('(max-width: 767px)').matches;
    } catch {
      return (window.innerWidth || 0) < 768;
    }
  }

  function isSlowNetwork() {
    try {
      const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
      if (!c) return false;
      if (c.saveData) return true;
      const t = String(c.effectiveType || '').toLowerCase();
      return t === 'slow-2g' || t === '2g';
    } catch {
      return false;
    }
  }

  function storageGet(key) {
    try {
      const v = sessionStorage.getItem(key);
      if (v != null) return v;
    } catch {}
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  function storageSet(key, value) {
    try { sessionStorage.setItem(key, value); } catch {}
    try { localStorage.setItem(key, value); } catch {}
  }

  function storageRemove(key) {
    try { sessionStorage.removeItem(key); } catch {}
    try { localStorage.removeItem(key); } catch {}
  }

  function hasScrolledOnce() {
    return storageGet('vixo_ads_has_scrolled') === '1';
  }

  function markScrolledOnce() {
    storageSet('vixo_ads_has_scrolled', '1');
  }

  function getChatroomName() {
    const chatCfg = readJsonScript('vixo-chat-config') || {};
    return String(chatCfg.chatroomName || '').trim();
  }

  function isKeyboardOpen() {
    // Heuristic: on mobile, visualViewport shrinks when keyboard is open.
    try {
      if (!isMobileWidth()) return false;
      const vv = window.visualViewport;
      if (!vv) {
        const ae = document.activeElement;
        if (!ae) return false;
        const tag = (ae.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea') return true;
        return false;
      }
      const heightDiff = (window.innerHeight || 0) - (vv.height || 0);
      if (heightDiff > 140) return true;
      if ((vv.offsetTop || 0) > 80) return true;
      return false;
    } catch {
      return false;
    }
  }

  function initTypingTracker() {
    const input = document.getElementById('id_body');
    if (!input) return;

    let timer = null;
    const setTyping = () => {
      storageSet('vixo_ads_typing', '1');
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => storageSet('vixo_ads_typing', '0'), 1200);
    };

    input.addEventListener('input', setTyping);
    input.addEventListener('keydown', setTyping);
    input.addEventListener('focus', () => storageSet('vixo_ads_typing', '1'));
    input.addEventListener('blur', () => storageSet('vixo_ads_typing', '0'));
  }

  function isUserTyping() {
    return storageGet('vixo_ads_typing') === '1';
  }

  function shouldRenderChatList(baseCfg) {
    if (!baseCfg || !baseCfg.mobileAdsEnabled) return false;
    if (!isMobileWidth()) return false;
    if (isKeyboardOpen()) return false;
    if (isUserTyping()) return false;
    if (isSlowNetwork()) return false;
    return true;
  }

  function shouldRenderChatFeed(baseCfg) {
    // Keep feed ads extra conservative to avoid distraction.
    if (!baseCfg || !baseCfg.mobileAdsEnabled) return false;
    if (!isMobileWidth()) return false;
    if (!hasScrolledOnce()) return false;
    if (isKeyboardOpen()) return false;
    if (isUserTyping()) return false;
    if (isSlowNetwork()) return false;
    return true;
  }

  function makeChatListAdCard(ad, index) {
    const wrap = document.createElement('div');
    wrap.id = `vixo_chat_list_ad_${index}`;
    wrap.setAttribute('data-vixo-ad', 'chat-list');
    wrap.className = 'mt-2 mb-2 rounded-xl border border-gray-800 bg-gray-900/40 px-3 py-3';

    const label = document.createElement('div');
    label.className = 'flex items-start justify-between gap-2';

    const advertiser = (ad && ad.advertiser) ? String(ad.advertiser).trim() : '';

    const title = document.createElement('div');
    title.className = 'text-sm font-semibold text-gray-200';
    title.textContent = (ad && ad.title) ? ad.title : (advertiser || 'Sponsored');

    const sponsored = document.createElement('div');
    sponsored.className = 'text-[10px] font-semibold text-gray-400/90';
    sponsored.textContent = advertiser ? 'Ad' : 'Sponsored';

    label.appendChild(title);
    label.appendChild(sponsored);

    const body = document.createElement('div');
    body.className = 'mt-1 text-xs text-gray-300';
    body.textContent = (ad && ad.body) ? ad.body : '';

    const imageUrl = (ad && ad.imageUrl) ? String(ad.imageUrl).trim() : '';
    let img = null;
    if (imageUrl) {
      img = document.createElement('img');
      img.src = imageUrl;
      img.alt = advertiser ? `${advertiser} ad` : 'Advertisement';
      img.loading = 'lazy';
      img.decoding = 'async';
      img.className = 'mt-2 w-full rounded-lg border border-gray-800 bg-gray-950/30';
    }

    const ctaRow = document.createElement('div');
    ctaRow.className = 'mt-2 flex items-center justify-end';

    const ctaUrl = (ad && ad.ctaUrl) ? String(ad.ctaUrl).trim() : '';
    if (ctaUrl) {
      const btn = document.createElement('a');
      btn.href = ctaUrl;
      btn.target = '_blank';
      btn.className = 'inline-flex items-center justify-center rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-3 py-2 transition-colors';
      btn.textContent = (ad && ad.ctaText) ? ad.ctaText : 'Learn more';
      btn.setAttribute('rel', 'noopener noreferrer sponsored');
      ctaRow.appendChild(btn);
    }

    wrap.appendChild(label);
    if (body.textContent) wrap.appendChild(body);
    if (img) wrap.appendChild(img);
    if (ctaRow.childNodes.length) wrap.appendChild(ctaRow);

    return wrap;
  }

  function makeChatFeedAdCard(ad) {
    const outer = document.createElement('div');
    outer.id = 'vixo_chat_feed_ad';
    outer.setAttribute('data-vixo-ad', 'chat-feed');
    outer.className = 'w-full flex justify-center';

    const card = document.createElement('div');
    card.className = 'w-full max-w-[90%] sm:max-w-[75%] lg:max-w-[65%] rounded-2xl border border-gray-800 bg-gray-900/40 px-4 py-3 text-center';

    const advertiser = (ad && ad.advertiser) ? String(ad.advertiser).trim() : '';

    const label = document.createElement('div');
    label.className = 'text-[11px] font-semibold text-gray-400';
    label.textContent = advertiser ? `Ad · ${advertiser}` : 'Sponsored message';

    const title = document.createElement('div');
    title.className = 'mt-1 text-sm font-semibold text-gray-100';
    title.textContent = (ad && ad.title) ? ad.title : (advertiser || 'Sponsored');

    const body = document.createElement('div');
    body.className = 'mt-1 text-xs text-gray-300';
    body.textContent = (ad && ad.body) ? ad.body : '';

    const imageUrl = (ad && ad.imageUrl) ? String(ad.imageUrl).trim() : '';
    let img = null;
    if (imageUrl) {
      img = document.createElement('img');
      img.src = imageUrl;
      img.alt = advertiser ? `${advertiser} ad` : 'Advertisement';
      img.loading = 'lazy';
      img.decoding = 'async';
      img.className = 'mt-3 w-full rounded-xl border border-gray-800 bg-gray-950/30';
    }

    const cta = document.createElement('div');
    cta.className = 'mt-2 flex items-center justify-center';

    const ctaUrl = (ad && ad.ctaUrl) ? String(ad.ctaUrl).trim() : '';
    if (ctaUrl) {
      const btn = document.createElement('a');
      btn.href = ctaUrl;
      btn.target = '_blank';
      btn.className = 'inline-flex items-center justify-center rounded-lg bg-gray-800 hover:bg-gray-700 text-white text-xs font-semibold px-3 py-2 transition-colors';
      btn.textContent = (ad && ad.ctaText) ? ad.ctaText : 'Open';
      btn.setAttribute('rel', 'noopener noreferrer sponsored');
      cta.appendChild(btn);
    }

    card.appendChild(label);
    card.appendChild(title);
    if (body.textContent) card.appendChild(body);
    if (img) card.appendChild(img);
    if (cta.childNodes.length) card.appendChild(cta);

    outer.appendChild(card);
    return outer;
  }

  function chatListAllowed() {
    const ts = parseInt(storageGet('vixo_ads_chat_list_shown_at') || '0', 10) || 0;
    // once per session OR re-show after 10 minutes
    return !ts || (nowMs() - ts) >= 10 * 60 * 1000;
  }

  function markChatListShown() {
    storageSet('vixo_ads_chat_list_shown_at', String(nowMs()));
  }

  function chatFeedAllowed(roomName) {
    if (!roomName) return false;
    const key = `vixo_ads_chat_feed_shown_at:${roomName}`;
    const ts = parseInt(storageGet(key) || '0', 10) || 0;
    // Max 1 per room, cooldown 15 minutes
    return !ts || (nowMs() - ts) >= 15 * 60 * 1000;
  }

  function markChatFeedShown(roomName) {
    if (!roomName) return;
    const key = `vixo_ads_chat_feed_shown_at:${roomName}`;
    storageSet(key, String(nowMs()));
  }

  function injectChatListAds(baseCfg) {
    try {
      const panel = document.querySelector('[data-chat-list]') || document.getElementById('chat_sidebar_panel');
      if (!panel) return;
      if (panel.getAttribute('data-vixo-chat-list-ads-injected') === '1') return;
      if (!chatListAllowed()) return;

      const ad = (baseCfg.mobileAds && baseCfg.mobileAds.chatList) || {};

      // Target group-chat items only (mobile request: after every 3 groups).
      // Fallback to all chat list items if template markers are missing.
      let items = Array.from(panel.querySelectorAll('[data-chat-list-item][data-chat-list-scope="group"]'));
      if (!items.length) {
        items = Array.from(panel.querySelectorAll('[data-chat-list-item]'))
          .filter((el) => !el.closest('[data-chat-pinned]'));
      }

      if (items.length < 3) return;

      const interval = 3;
      let adIndex = 0;
      for (let n = interval; n <= items.length; n += interval) {
        const afterEl = items[n - 1];
        if (!afterEl) continue;

        const card = makeChatListAdCard(ad, adIndex++);

        // Keep markup valid-ish: if we're inside a UL, insert as a LI.
        const ul = afterEl.closest('ul');
        if (ul) {
          const li = document.createElement('li');
          li.setAttribute('data-vixo-ad', 'chat-list');
          li.className = 'list-none';
          li.appendChild(card);

          const anchorLi = afterEl.closest('li');
          if (anchorLi && anchorLi.parentNode) {
            anchorLi.insertAdjacentElement('afterend', li);
          } else {
            afterEl.insertAdjacentElement('afterend', li);
          }
        } else {
          const anchorLi = afterEl.closest('li') || afterEl;
          anchorLi.insertAdjacentElement('afterend', card);
        }
      }

      panel.setAttribute('data-vixo-chat-list-ads-injected', '1');
      markChatListShown();
    } catch {
      // silently skip
    }
  }

  function injectChatFeedAd(baseCfg) {
    try {
      const ul = document.getElementById('chat_messages');
      if (!ul) return;
      if (document.getElementById('vixo_chat_feed_ad')) return;

      const roomName = getChatroomName();
      if (!chatFeedAllowed(roomName)) return;

      // Count only real message nodes.
      const messageNodes = Array.from(ul.children)
        .filter((n) => n && n.nodeType === 1 && (n.hasAttribute('data-message-id') || n.querySelector && n.querySelector('[data-message-id]')));

      const total = messageNodes.length;
      if (total < 25) return; // must have >= 25 messages

      // Do not place near latest messages: keep at least 10 messages below the ad.
      if (total < 35) return;

      // Choose a stable insert point between 25..30.
      const seed = roomName ? roomName.length : 0;
      const offset = (seed % 6); // 0..5
      let insertAfterIndex = 24 + offset; // after 25..30th (0-based)
      const maxInsertAfter = Math.max(0, total - 11); // ensure 10 messages below
      if (insertAfterIndex > maxInsertAfter) insertAfterIndex = maxInsertAfter;

      const afterNode = messageNodes[insertAfterIndex];
      if (!afterNode) return;

      const ad = (baseCfg.mobileAds && baseCfg.mobileAds.chatFeed) || {};
      const card = makeChatFeedAdCard(ad);

      afterNode.insertAdjacentElement('afterend', card);
      markChatFeedShown(roomName);
    } catch {
      // silently skip
    }
  }

  function syncVisibility() {
    try {
      const feedAd = document.getElementById('vixo_chat_feed_ad');
      const baseCfg = readJsonScript('vixo-config') || {};

      const okList = shouldRenderChatList(baseCfg);
      const okFeed = shouldRenderChatFeed(baseCfg);

      const listAds = Array.from(document.querySelectorAll('[data-vixo-ad="chat-list"]'));
      listAds.forEach((el) => { el.style.display = okList ? '' : 'none'; });
      if (feedAd) feedAd.style.display = okFeed ? '' : 'none';

      if (okList) injectChatListAds(baseCfg);
      if (okFeed) injectChatFeedAd(baseCfg);
    } catch {
      // ignore
    }
  }

  function initScrollTracking() {
    const mark = () => {
      if (!hasScrolledOnce()) markScrolledOnce();
    };

    const attach = (el) => {
      if (!el) return;
      el.addEventListener('scroll', mark, { passive: true });
    };

    attach(window);
    attach(document);
    attach(document.documentElement);
    attach(document.body);
    attach(document.getElementById('chat_container'));
    attach(document.getElementById('chat_sidebar_panel'));
    // Also listen to touchmove to capture scroll on some mobile browsers.
    document.addEventListener('touchmove', mark, { passive: true });
  }

  function init() {
    const baseCfg = readJsonScript('vixo-config') || {};
    if (!baseCfg || !baseCfg.mobileAdsEnabled) return;

    initScrollTracking();
    initTypingTracker();

    // React to viewport changes (keyboard open/close)
    try {
      if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', syncVisibility);
        window.visualViewport.addEventListener('scroll', syncVisibility);
      }
    } catch {}

    window.addEventListener('resize', syncVisibility);
    window.addEventListener('orientationchange', syncVisibility);
    document.addEventListener('focusin', syncVisibility);
    document.addEventListener('focusout', syncVisibility);

    // Run after first paint.
    requestAnimationFrame(syncVisibility);

    // Also re-run after HTMX swaps/new messages.
    document.body.addEventListener('htmx:afterSwap', () => requestAnimationFrame(syncVisibility));
    document.body.addEventListener('htmx:afterRequest', () => requestAnimationFrame(syncVisibility));

    // New messages via websocket are inserted directly; poll visibility periodically (lightweight).
    setInterval(() => {
      if (!document.hidden) syncVisibility();
    }, 3000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
