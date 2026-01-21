import random
import re
import unicodedata
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ChatChallenge, ChatGroup


VOWELS_RE = re.compile(r"[aeiou]", re.IGNORECASE)

LOW_EFFORT_SET = {
    'ok', 'okay', 'k', 'kk', 'k.',
    'idk', "i don't know", 'dont know',
    'lol', 'lmao', 'lmfao',
    'hmm', 'hm', 'hmmm',
    'yes', 'no', 'nah', 'yep',
    'fine', 'good',
}

REPEATED_CHAR_RE = re.compile(r"^(.)\1{5,}$", re.DOTALL)


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _normalize_cmp(s: str) -> str:
    """Normalize for loose comparisons (case + common apostrophe variants)."""
    s = _normalize_text(s).lower()
    # Normalize curly quotes to straight for matching.
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    return s


def _is_low_effort_answer(text: str, *, min_len: int = 10) -> bool:
    s = _normalize_text(text).lower()
    if len(s) < int(min_len):
        return True
    if s in LOW_EFFORT_SET:
        return True
    # e.g., "ok ok ok" / "lol lol" etc.
    tokens = [t for t in re.split(r"\W+", s) if t]
    if tokens and len(tokens) <= 3:
        if all(t in LOW_EFFORT_SET for t in tokens):
            return True
    return False


def _is_repeated_or_meaningless(text: str) -> bool:
    s = _normalize_text(text)
    if not s:
        return True
    # "aaaaaa" / "!!!!!!" / "هههههه" etc.
    if REPEATED_CHAR_RE.match(s):
        return True
    # Very low character diversity for longer strings.
    if len(s) >= 12:
        uniq = len(set(s))
        if uniq <= 3:
            return True
        if (uniq / max(1, len(s))) < 0.18:
            return True
    return False


# A pragmatic emoji check: allow common emoji codepoint blocks plus emoji joiners/modifiers.
_EMOJI_RANGES = [
    (0x1F300, 0x1FAFF),  # Misc Symbols and Pictographs + Supplemental
    (0x2600, 0x26FF),    # Misc symbols
    (0x2700, 0x27BF),    # Dingbats
    (0xFE00, 0xFE0F),    # Variation selectors
    (0x1F1E6, 0x1F1FF),  # Flags
]


def _is_emoji_char(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    if ch == "\u200d":  # ZWJ
        return True
    if 0x1F3FB <= cp <= 0x1F3FF:  # skin tone
        return True
    for a, b in _EMOJI_RANGES:
        if a <= cp <= b:
            return True
    return False


def _is_emoji_only(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False

    # Quick reject: any letters/digits -> not emoji-only.
    for ch in s:
        if ch.isalnum() or ch == "_":
            return False

    for ch in s:
        if ch.isspace():
            continue
        # Some punctuation often appears accidentally; treat as rule-break.
        if not _is_emoji_char(ch):
            # Also allow characters that are categorized as "Symbol, Other".
            try:
                if unicodedata.category(ch) == "So":
                    continue
            except Exception:
                pass
            return False
    return True


_MEME_TEMPLATES = [
    {
        "prompt": "Finish the meme: Me: I'll sleep early tonight. Also me at 3AM: ____",
        "answer": "just one more reel",
    },
    {
        "prompt": "Finish the meme: When you say 'I'm fine' but you're actually ____",
        "answer": "not fine",
    },
    {
        "prompt": "Finish the meme: When the WiFi stops working and you suddenly ____",
        "answer": "remember life",
    },
]

_TRUTH_PROMPTS = [
    "Who was the last person you stalked?",
    "Which friend are you secretly jealous of?",
    "What lie do you tell the most?",
    "Whose screenshots do you still have?",
    "Worst crush you ever had?",
    "Which message did you purposely ignore?",
    "What part of your personality is fake?",
    "Do you still remember an ex’s number?",
    "Your biggest insecurity?",
    "A thought about a friend you’ll never say out loud?",
    "What do you overthink about at night?",
    "What do you flex that you don’t actually have?",
    "Who ghosted you last?",
    "Your most toxic trait?",
    "Who did you leave on “seen” intentionally?",
    "Worst DM you’ve ever sent?",
    "What type of people do you hate instantly?",
    "Have you ever used someone emotionally?",
    "What regret hits you randomly?",
    "A secret only you know about someone here?",
    "Which app wastes most of your time?",
    "Who do you trust the least in your friend group?",
    "When was the last time you cried?",
    "Your most embarrassing phase?",
    "What scares you the most?",
    "Have you ever hurt someone on purpose?",
    "Your darkest (safe) thought?",
    "Where do you fake confidence?",
    "Who do you have muted right now?",
    "What makes you lose your temper fast?",
    "Who’s talent makes you jealous?",
    "Your image vs reality difference?",
    "When did you last feel like a failure?",
    "What are you really bad at?",
    "Which friend feels boring now?",
    "Something you pretend not to care about?",
    "What do people misunderstand about you?",
    "Who do you secretly miss?",
    "Worst habit you hide?",
    "Something you’re ashamed of liking?",
    "What drains your energy the most?",
    "Who do you compare yourself to?",
    "A goal you’re scared you won’t reach?",
    "Something you fake laugh at?",
    "What makes you feel lonely?",
    "Who do you wish noticed you more?",
    "A truth you avoid accepting?",
    "Something you overthink way too much?",
    "Who disappoints you the most?",
    "What would you change about yourself instantly?",
    "Who do you pretend to like but don’t?",
    "What notification are you waiting for right now?",
    "What’s the pettiest thing you’ve done?",
    "Who do you secretly want to replace in your life?",
    "What’s something you’re tired of explaining?",
    "Who has the most power over your mood?",
    "What compliment do you fake accepting?",
    "What’s your “I’m fine” lie?",
    "Who do you wish would text you first?",
    "What’s your biggest red flag in relationships?",
    "What do you miss that you’ll never get back?",
    "What’s something you’re scared people will find out?",
    "Who do you low-key compete with?",
    "What part of your life feels stuck?",
    "What’s something you hate admitting?",
    "Who do you avoid on purpose?",
    "What memory still makes you cringe?",
    "What’s your emotional weakness?",
    "Who do you feel misunderstood by?",
    "What drains you even when you pretend it doesn’t?",
    "What do you overthink after sending messages?",
    "What promise did you break to yourself?",
    "Who do you wish you never met?",
    "What do you hide behind jokes?",
    "What’s something you silently judge people for?",
]


def _tod_get_prev_state(group: ChatGroup) -> dict:
    """Fetch the most recent truth-or-dare state for this room.

    We persist the deck in ChatChallenge.meta so we can avoid repeats across
    separate challenges without a schema change.
    """
    try:
        prev = (
            ChatChallenge.objects.filter(group=group, kind=ChatChallenge.KIND_TRUTH_OR_DARE)
            .order_by("-created")
            .only("id", "meta")
            .first()
        )
    except Exception:
        prev = None
    meta = dict(getattr(prev, "meta", None) or {})
    return {
        "truth_deck": list(meta.get("tod_truth_deck") or []),
        "truth_idx": int(meta.get("tod_truth_idx") or 0),
        "dare_deck": list(meta.get("tod_dare_deck") or []),
        "dare_idx": int(meta.get("tod_dare_idx") or 0),
    }


def _tod_next_truth(group: ChatGroup) -> tuple[str, list[str], int]:
    state = _tod_get_prev_state(group)
    deck = list(state.get("truth_deck") or [])
    idx = int(state.get("truth_idx") or 0)

    if not deck or idx >= len(deck):
        deck = list(_TRUTH_PROMPTS)
        random.shuffle(deck)
        idx = 0

    prompt = deck[idx]
    idx += 1
    return prompt, deck, idx


def _tod_next_dare(group: ChatGroup) -> tuple[dict, list[dict], int]:
    """Deck-based dare selection (non-repeating until exhausted).

    For now it uses the existing small dare list; when you provide a bigger
    list we can expand it the same way as Truth.
    """
    state = _tod_get_prev_state(group)
    deck = list(state.get("dare_deck") or [])
    idx = int(state.get("dare_idx") or 0)

    # Persist dare deck as list of dicts.
    if not deck or idx >= len(deck):
        deck = list(_DARE_RULES)
        random.shuffle(deck)
        idx = 0

    dare = deck[idx]
    idx += 1
    return dare, deck, idx

_DARE_PROMPTS = [
    "Dare: Your next message must be ALL CAPS.",
    "Dare: Your next message must include the word 'PINEAPPLE'.",
    "Dare: Your next message must include at least 3 emojis.",
]

_DARE_RULES = [
    {"prompt": "Dare: Send the 😶 emoji.", "rule": {"type": "contains_emoji", "value": "😶"}},
    {"prompt": "Dare: Type one insecurity — no explanation.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Change your status to “I overthink a lot” for 5 mins.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Send a “…” message.", "rule": {"type": "equals", "value": "..."}},
    {"prompt": "Dare: Drop a 🖤 in chat and don’t explain.", "rule": {"type": "contains_emoji", "value": "🖤"}},
    {"prompt": "Dare: Type your mood in ONE word.", "rule": {"type": "one_word"}},
    {"prompt": "Dare: Send the last emoji you used.", "rule": {"type": "emoji_only"}},
    {"prompt": "Dare: Type “I’m not okay lol” and stop.", "rule": {"type": "equals", "value": "i'm not okay lol"}},
    {"prompt": "Dare: Send a song lyric that hits too hard.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Type the first name that comes to mind.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Send “we need to talk” then go silent.", "rule": {"type": "equals", "value": "we need to talk"}},
    {"prompt": "Dare: React 👀 to the last message you see.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Type something you miss (one word).", "rule": {"type": "one_word"}},
    {"prompt": "Dare: Send a dark meme line (text only).", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Type “I’m tired” and nothing else.", "rule": {"type": "equals", "value": "i'm tired"}},
    {"prompt": "Dare: Send the 🥀 emoji.", "rule": {"type": "contains_emoji", "value": "🥀"}},
    {"prompt": "Dare: Confess a harmless habit in one line.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Type “don’t ask” and stop.", "rule": {"type": "equals", "value": "don't ask"}},
    {"prompt": "Dare: Drop a skull emoji 💀.", "rule": {"type": "contains_emoji", "value": "💀"}},
    {"prompt": "Dare: Type the last thing you Googled.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Send a message with only punctuation.", "rule": {"type": "punctuation_only"}},
    {"prompt": "Dare: Type “that hurt” without context.", "rule": {"type": "equals", "value": "that hurt"}},
    {"prompt": "Dare: Send a random voice note (2 sec).", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Change nickname to “overthinker” for 5 mins.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Type your current vibe in lowercase.", "rule": {"type": "lowercase"}},
    {"prompt": "Dare: Send “lol okay” and disappear.", "rule": {"type": "equals", "value": "lol okay"}},
    {"prompt": "Dare: Type a sentence starting with “sometimes I…”.", "rule": {"type": "starts_with", "value": "sometimes i"}},
    {"prompt": "Dare: Send the 🫠 emoji.", "rule": {"type": "contains_emoji", "value": "🫠"}},
    {"prompt": "Dare: Type a word that describes your life rn.", "rule": {"type": "one_word"}},
    {"prompt": "Dare: Send “idk anymore”.", "rule": {"type": "equals", "value": "idk anymore"}},
    {"prompt": "Dare: Type one thing you’re avoiding.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Send a message with only numbers.", "rule": {"type": "numbers_only"}},
    {"prompt": "Dare: Type “I shouldn’t have said that”.", "rule": {"type": "equals", "value": "i shouldn't have said that"}},
    {"prompt": "Dare: Drop a 🌓 emoji.", "rule": {"type": "contains_emoji", "value": "🌓"}},
    {"prompt": "Dare: Send “anyway” randomly.", "rule": {"type": "equals", "value": "anyway"}},
    {"prompt": "Dare: Type one red flag about yourself.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Send a message using only emojis.", "rule": {"type": "emoji_only"}},
    {"prompt": "Dare: Type “this is awkward”.", "rule": {"type": "equals", "value": "this is awkward"}},
    {"prompt": "Dare: Send “bruh”.", "rule": {"type": "equals", "value": "bruh"}},
    {"prompt": "Dare: Type one thing you want but can’t have.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Send a sad emoji without explanation.", "rule": {"type": "emoji_only"}},
    {"prompt": "Dare: Type “moving on”.", "rule": {"type": "equals", "value": "moving on"}},
    {"prompt": "Dare: Send “I felt that”.", "rule": {"type": "equals", "value": "i felt that"}},
    {"prompt": "Dare: Type a single letter.", "rule": {"type": "single_letter"}},
    {"prompt": "Dare: Send “noted.”", "rule": {"type": "equals", "value": "noted."}},
    {"prompt": "Dare: Type “hmm”.", "rule": {"type": "equals", "value": "hmm"}},
    {"prompt": "Dare: Send a text, delete it immediately.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Type “don’t read into this”.", "rule": {"type": "equals", "value": "don't read into this"}},
    {"prompt": "Dare: Send the 🔕 emoji.", "rule": {"type": "contains_emoji", "value": "🔕"}},
    {"prompt": "Dare: Type “it is what it is”.", "rule": {"type": "equals", "value": "it is what it is"}},
    {"prompt": "Dare: Type “I’m mentally tired” and stop.", "rule": {"type": "equals", "value": "i'm mentally tired"}},
    {"prompt": "Dare: Send 🫥 to the chat.", "rule": {"type": "contains_emoji", "value": "🫥"}},
    {"prompt": "Dare: Drop a single word that hurts.", "rule": {"type": "one_word"}},
    {"prompt": "Dare: Type “I remember that” with no context.", "rule": {"type": "equals", "value": "i remember that"}},
    {"prompt": "Dare: Send a message, then immediately say “ignore that”.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Type one thing you fear losing.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Send the 🕳️ emoji.", "rule": {"type": "contains_emoji", "value": "🕳️"}},
    {"prompt": "Dare: Type “this feels weird”.", "rule": {"type": "equals", "value": "this feels weird"}},
    {"prompt": "Dare: Send a lowercase confession (one line).", "rule": {"type": "lowercase"}},
    {"prompt": "Dare: Type “I miss it” and disappear.", "rule": {"type": "equals", "value": "i miss it"}},
    {"prompt": "Dare: Send “nah I’m good” randomly.", "rule": {"type": "equals", "value": "nah i'm good"}},
    {"prompt": "Dare: Drop a 🧠 emoji.", "rule": {"type": "contains_emoji", "value": "🧠"}},
    {"prompt": "Dare: Type one word you hate hearing.", "rule": {"type": "one_word"}},
    {"prompt": "Dare: Send “okay sure” and go silent.", "rule": {"type": "equals", "value": "okay sure"}},
    {"prompt": "Dare: Type a sentence starting with “low-key…”.", "rule": {"type": "starts_with", "value": "low-key"}},
    {"prompt": "Dare: Send 🪦 without context.", "rule": {"type": "contains_emoji", "value": "🪦"}},
    {"prompt": "Dare: Type “don’t make this deep”.", "rule": {"type": "equals", "value": "don't make this deep"}},
    {"prompt": "Dare: Send a message using only dots.", "rule": {"type": "only_dots"}},
    {"prompt": "Dare: Type “I’m over it”.", "rule": {"type": "equals", "value": "i'm over it"}},
    {"prompt": "Dare: Drop a 🌑 emoji.", "rule": {"type": "contains_emoji", "value": "🌑"}},
    {"prompt": "Dare: Type one thing you need right now.", "rule": {"type": "any_nonempty"}},
    {"prompt": "Dare: Send “this isn’t funny anymore”.", "rule": {"type": "equals", "value": "this isn't funny anymore"}},
    {"prompt": "Dare: Type “I should sleep”.", "rule": {"type": "equals", "value": "i should sleep"}},
    {"prompt": "Dare: Send a message with only symbols.", "rule": {"type": "symbols_only"}},
    {"prompt": "Dare: Type “nothing feels the same”.", "rule": {"type": "equals", "value": "nothing feels the same"}},
]


@dataclass
class ChallengeCheckResult:
    allowed: bool
    reason: str = ""
    ended: bool = False


def get_active_challenge(group: ChatGroup) -> ChatChallenge | None:
    return (
        ChatChallenge.objects.filter(group=group, status=ChatChallenge.STATUS_ACTIVE)
        .order_by("-started_at")
        .first()
    )


def _members(group: ChatGroup) -> list[int]:
    try:
        return list(group.members.values_list("id", flat=True))
    except Exception:
        return []


def _participants_from_meta(group: ChatGroup, meta: dict) -> list[int]:
    """Return the user IDs that should be considered participants for this challenge.

    Prefer the persisted meta['participants'] (captured at start) to avoid counting
    offline/non-participating members as automatic losers.
    """
    raw = meta.get('participants') if isinstance(meta, dict) else None
    if isinstance(raw, (list, tuple)) and raw:
        try:
            ids = [int(x) for x in raw if int(x) > 0]
            return sorted(set(ids))
        except Exception:
            pass
    return _members(group)


def start_challenge(group: ChatGroup, created_by, kind: str) -> ChatChallenge:
    if not getattr(group, "is_private", False):
        raise ValueError("Challenges are only available in private chats.")

    kind = (kind or "").strip().lower()
    if kind not in ChatChallenge.KIND_CHOICES_DICT:
        raise ValueError("Unknown challenge.")

    with transaction.atomic():
        # Prevent double-start races.
        ChatGroup.objects.select_for_update().filter(pk=group.pk).exists()
        active = get_active_challenge(group)
        if active:
            raise ValueError("A challenge is already active in this chat.")

        now = timezone.now()

        # MVP: fixed 30s duration for all challenges.
        duration = timedelta(seconds=30)
        prompt = ""
        meta: dict = {
            "losers": [],
            "winners": [],
            "counts": {},
            "completed": {},
            "min_len": 10,
            "ended_notified": False,
            "ended_kind": "",
        }

        # Track participants at start to avoid counting offline members as losers.
        try:
            created_by_id = int(getattr(created_by, 'id', created_by) or 0)
        except Exception:
            created_by_id = 0
        participants: set[int] = set()
        try:
            participants |= set(int(x) for x in group.users_online.values_list('id', flat=True) if int(x) > 0)
        except Exception:
            pass
        if created_by_id > 0:
            participants.add(created_by_id)
        meta['participants'] = sorted(participants)

        if kind == ChatChallenge.KIND_TIME_ATTACK:
            duration = timedelta(seconds=30)
            meta["target_messages"] = 3
            prompt = "Time attack: send 3 messages in 30 seconds."

        if kind == ChatChallenge.KIND_FINISH_MEME:
            tpl = random.choice(_MEME_TEMPLATES)
            # For MVP (no AI), judge by validity (min length + not spam). First valid reply wins.
            prompt = tpl["prompt"] + "\n(First valid reply wins. Be creative!)"

        if kind == ChatChallenge.KIND_TRUTH_OR_DARE:
            # Randomly pick truth or dare.
            pick_truth = bool(random.randint(0, 1))
            if pick_truth:
                truth, truth_deck, truth_idx = _tod_next_truth(group)
                prompt = f"Truth: {truth}\n(Answer meaningfully. No spam.)"
                meta["tod_mode"] = "truth"
                meta["tod_truth_deck"] = truth_deck
                meta["tod_truth_idx"] = truth_idx
            else:
                dare, dare_deck, dare_idx = _tod_next_dare(group)
                prompt = dare["prompt"]
                meta["tod_mode"] = "dare"
                meta["dare_rule"] = dare.get("rule")
                meta["tod_dare_deck"] = dare_deck
                meta["tod_dare_idx"] = dare_idx

            # Always persist whichever deck state we have so the next challenge
            # can continue from the latest state (even if this one was "dare").
            if "tod_truth_deck" not in meta:
                prev = _tod_get_prev_state(group)
                if prev.get("truth_deck"):
                    meta["tod_truth_deck"] = prev.get("truth_deck")
                    meta["tod_truth_idx"] = int(prev.get("truth_idx") or 0)
            if "tod_dare_deck" not in meta:
                prev = _tod_get_prev_state(group)
                if prev.get("dare_deck"):
                    meta["tod_dare_deck"] = prev.get("dare_deck")
                    meta["tod_dare_idx"] = int(prev.get("dare_idx") or 0)

        if kind == ChatChallenge.KIND_EMOJI_ONLY:
            prompt = "Emoji-only mode: for 30 seconds, only emojis allowed. Any text = instant lose."

        if kind == ChatChallenge.KIND_NO_VOWELS:
            prompt = "No-vowels challenge: A, E, I, O, U are banned for 30 seconds. Any vowel = instant lose."

        ends_at = now + duration

        return ChatChallenge.objects.create(
            group=group,
            kind=kind,
            status=ChatChallenge.STATUS_ACTIVE,
            created_by=created_by,
            prompt=prompt,
            started_at=now,
            ends_at=ends_at,
            meta=meta,
        )


def cancel_challenge(ch: ChatChallenge) -> ChatChallenge:
    if not ch or ch.status != ChatChallenge.STATUS_ACTIVE:
        return ch

    meta = dict(getattr(ch, "meta", None) or {})
    meta["winners"] = []
    meta["losers"] = []
    meta["ended_kind"] = "cancelled"
    ch.meta = meta
    ch.status = ChatChallenge.STATUS_CANCELLED
    ch.ended_at = timezone.now()
    ch.save(update_fields=["meta", "status", "ended_at"])
    return ch


def _set_loser(ch: ChatChallenge, user_id: int) -> None:
    meta = dict(getattr(ch, "meta", None) or {})
    losers = set(meta.get("losers") or [])
    if user_id:
        losers.add(int(user_id))
    meta["losers"] = sorted(losers)
    ch.meta = meta


def _mark_completed(ch: ChatChallenge, user_id: int) -> None:
    meta = dict(getattr(ch, "meta", None) or {})
    completed = dict(meta.get("completed") or {})
    if user_id:
        completed[str(int(user_id))] = True
    meta["completed"] = completed
    ch.meta = meta


def _inc_count(ch: ChatChallenge, user_id: int) -> None:
    meta = dict(getattr(ch, "meta", None) or {})
    counts = dict(meta.get("counts") or {})
    key = str(int(user_id))
    counts[key] = int(counts.get(key) or 0) + 1
    meta["counts"] = counts
    ch.meta = meta


def end_if_expired(ch: ChatChallenge) -> bool:
    if not ch or ch.status != ChatChallenge.STATUS_ACTIVE:
        return False
    if ch.ends_at and timezone.now() >= ch.ends_at:
        end_challenge(ch)
        return True
    return False


def end_challenge(ch: ChatChallenge) -> ChatChallenge:
    if not ch or ch.status != ChatChallenge.STATUS_ACTIVE:
        return ch
    meta = dict(getattr(ch, "meta", None) or {})

    member_ids = _participants_from_meta(ch.group, meta)
    losers = set(meta.get("losers") or [])

    winners = [uid for uid in member_ids if uid and uid not in losers]

    # Truth or dare: must reply at least once.
    if ch.kind == ChatChallenge.KIND_TRUTH_OR_DARE:
        completed = dict(meta.get("completed") or {})
        # Completed means "passed validation".
        losers = set(int(uid) for uid in member_ids if str(int(uid)) not in completed)
        winners = [uid for uid in member_ids if uid and uid not in losers]
        meta["losers"] = sorted(losers)

    # Time attack: must send N messages.
    if ch.kind == ChatChallenge.KIND_TIME_ATTACK:
        target = int(meta.get("target_messages") or 3)
        counts = dict(meta.get("counts") or {})
        losers = set(int(uid) for uid in member_ids if int(counts.get(str(int(uid))) or 0) < target)
        winners = [uid for uid in member_ids if uid and uid not in losers]
        meta["losers"] = sorted(losers)

    meta["winners"] = sorted(int(x) for x in winners)
    ch.meta = meta
    meta["ended_kind"] = "completed"
    ch.status = ChatChallenge.STATUS_COMPLETED
    ch.ended_at = timezone.now()
    ch.save(update_fields=["meta", "status", "ended_at"])
    return ch


def check_message(ch: ChatChallenge, user_id: int, body: str) -> ChallengeCheckResult:
    if not ch or ch.status != ChatChallenge.STATUS_ACTIVE:
        return ChallengeCheckResult(allowed=True)

    # End before validating.
    if end_if_expired(ch):
        return ChallengeCheckResult(allowed=True, ended=True)

    uid = int(user_id or 0)
    meta = dict(getattr(ch, "meta", None) or {})
    losers = set(meta.get("losers") or [])
    if uid in losers:
        # Already lost; allow messages but do not count.
        return ChallengeCheckResult(allowed=True)

    text = (body or "").strip()
    min_len = int(meta.get("min_len") or 10)

    if ch.kind == ChatChallenge.KIND_EMOJI_ONLY:
        if not _is_emoji_only(text):
            _set_loser(ch, uid)
            ch.save(update_fields=["meta"])
            return ChallengeCheckResult(allowed=False, reason="Emoji-only mode: text not allowed.")
        return ChallengeCheckResult(allowed=True)

    if ch.kind == ChatChallenge.KIND_NO_VOWELS:
        if VOWELS_RE.search(text or ""):
            _set_loser(ch, uid)
            ch.save(update_fields=["meta"])
            return ChallengeCheckResult(allowed=False, reason="No-vowels challenge: vowel detected.")
        return ChallengeCheckResult(allowed=True)

    if ch.kind == ChatChallenge.KIND_TRUTH_OR_DARE:
        mode = str(meta.get("tod_mode") or "").strip().lower()
        if mode == 'truth':
            if _is_low_effort_answer(text, min_len=min_len) or _is_repeated_or_meaningless(text):
                _set_loser(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=False, reason=f"Truth answer must be meaningful (≥{min_len} chars).")
            _mark_completed(ch, uid)
            ch.save(update_fields=["meta"])
            return ChallengeCheckResult(allowed=True)

        if mode == 'dare':
            rule = dict(meta.get('dare_rule') or {})
            rtype = str(rule.get('type') or '').strip().lower()
            if rtype == 'any_nonempty':
                if not _normalize_text(text):
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: message required.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'equals':
                expected = _normalize_cmp(str(rule.get('value') or ''))
                got = _normalize_cmp(text)
                if expected and got != expected:
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: exact text required.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'starts_with':
                expected = _normalize_cmp(str(rule.get('value') or ''))
                got = _normalize_cmp(text)
                if expected and not got.startswith(expected):
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: text must start with required phrase.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'one_word':
                s = _normalize_text(text)
                tokens = [t for t in re.split(r"\s+", s) if t]
                if len(tokens) != 1:
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: must be exactly one word.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'lowercase':
                s = _normalize_text(text)
                if not s or s != s.lower():
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: must be lowercase.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'single_letter':
                s = _normalize_text(text)
                if len(s) != 1 or not s.isalpha():
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: must be a single letter.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'numbers_only':
                s = _normalize_text(text)
                if not s or not s.isdigit():
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: numbers only.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'punctuation_only':
                s = (text or '').strip()
                if not s:
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: punctuation required.")
                ok = True
                for c in s:
                    if c.isspace():
                        continue
                    if c.isalnum() or c == '_':
                        ok = False
                        break
                if not ok:
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: punctuation only.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'symbols_only':
                s = (text or '').strip()
                if not s:
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: symbols required.")
                ok = True
                for c in s:
                    if c.isspace():
                        continue
                    if c.isalnum() or c == '_':
                        ok = False
                        break
                if not ok:
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: symbols only.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'only_dots':
                s = (text or '').strip()
                if not s or any((c not in {'.', '…'} and not c.isspace()) for c in s):
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: dots only.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'emoji_only':
                if not _is_emoji_only(text):
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: emojis only.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'contains_emoji':
                needle = str(rule.get('value') or '').strip()
                if not needle or needle not in text:
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: required emoji missing.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'all_caps':
                letters = ''.join([c for c in text if c.isalpha()])
                if not letters or text != text.upper():
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason="Dare failed: message must be ALL CAPS.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'contains':
                needle = str(rule.get('value') or '').strip().lower()
                if not needle or needle not in text.lower():
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason=f"Dare failed: must include '{needle}'.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)
            if rtype == 'min_emojis':
                target = int(rule.get('value') or 3)
                emoji_count = 0
                for c in text:
                    if _is_emoji_char(c) and not c.isspace() and c != '\u200d':
                        emoji_count += 1
                if emoji_count < target:
                    _set_loser(ch, uid)
                    ch.save(update_fields=["meta"])
                    return ChallengeCheckResult(allowed=False, reason=f"Dare failed: need ≥{target} emojis.")
                _mark_completed(ch, uid)
                ch.save(update_fields=["meta"])
                return ChallengeCheckResult(allowed=True)

            # Unknown dare rule -> treat as fail-safe allow.
            _mark_completed(ch, uid)
            ch.save(update_fields=["meta"])
            return ChallengeCheckResult(allowed=True)

        # If mode missing, require meaningful response.
        if _is_low_effort_answer(text, min_len=min_len) or _is_repeated_or_meaningless(text):
            _set_loser(ch, uid)
            ch.save(update_fields=["meta"])
            return ChallengeCheckResult(allowed=False, reason=f"Answer must be meaningful (≥{min_len} chars).")
        _mark_completed(ch, uid)
        ch.save(update_fields=["meta"])
        return ChallengeCheckResult(allowed=True)

    if ch.kind == ChatChallenge.KIND_TIME_ATTACK:
        _inc_count(ch, uid)
        ch.save(update_fields=["meta"])
        return ChallengeCheckResult(allowed=True)

    if ch.kind == ChatChallenge.KIND_FINISH_MEME:
        if _is_low_effort_answer(text, min_len=min_len) or _is_repeated_or_meaningless(text):
            _set_loser(ch, uid)
            ch.save(update_fields=["meta"])
            return ChallengeCheckResult(allowed=False, reason=f"Reply must be meaningful (≥{min_len} chars).")

        # First valid reply wins immediately.
        member_ids = _participants_from_meta(ch.group, meta)
        meta["winners"] = [uid]
        meta["losers"] = [x for x in member_ids if x and int(x) != uid]
        meta["ended_kind"] = "completed"
        ch.meta = meta
        ch.status = ChatChallenge.STATUS_COMPLETED
        ch.ended_at = timezone.now()
        ch.save(update_fields=["meta", "status", "ended_at"])
        return ChallengeCheckResult(allowed=True, ended=True)

    return ChallengeCheckResult(allowed=True)


def get_win_loss_totals(
    user_id: int,
    *,
    group: ChatGroup | None = None,
    private_only: bool = True,
) -> dict:
    """Return aggregated challenge results for a user.

    We count wins/losses based on the persisted `meta['winners']`/`meta['losers']`
    lists on COMPLETED challenges.
    """
    uid = int(user_id or 0)
    if uid <= 0:
        return {'wins': 0, 'losses': 0, 'completed': 0}

    qs = ChatChallenge.objects.filter(status=ChatChallenge.STATUS_COMPLETED)
    if group is not None:
        qs = qs.filter(group=group)
    elif private_only:
        qs = qs.filter(group__is_private=True)

    wins = 0
    losses = 0
    completed = 0

    for meta in qs.values_list('meta', flat=True):
        if not isinstance(meta, dict):
            continue
        completed += 1
        winners = meta.get('winners') or []
        losers = meta.get('losers') or []
        if uid in winners:
            wins += 1
        if uid in losers:
            losses += 1

    return {'wins': wins, 'losses': losses, 'completed': completed}


def challenge_public_state(ch: ChatChallenge | None) -> dict:
    if not ch:
        return {"active": False}
    meta = dict(getattr(ch, "meta", None) or {})
    return {
        "active": ch.status == ChatChallenge.STATUS_ACTIVE,
        "id": ch.id,
        "kind": ch.kind,
        "prompt": ch.prompt,
        "started_at": int(ch.started_at.timestamp()) if ch.started_at else 0,
        "ends_at": int(ch.ends_at.timestamp()) if ch.ends_at else 0,
        "status": ch.status,
        "ended_kind": str(meta.get('ended_kind') or ''),
        "losers": list(meta.get("losers") or []),
        "winners": list(meta.get("winners") or []),
    }
