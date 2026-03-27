from __future__ import annotations

import html
import re

from django import template
from django.utils.safestring import mark_safe


# Conservative @mention pattern: @username (letters, numbers, underscore, dot, dash)
_MENTION_RE = re.compile(r"(^|\s)@(?P<name>[A-Za-z0-9_.-]{1,32})\b")


register = template.Library()


_URL_TOKEN_RE = re.compile(
    r"((?:https?:\/\/|www\.)[^\s<]+|(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?:\/[^\s<]*)?)",
    flags=re.IGNORECASE,
)
_MARKDOWN_LINK_RE = re.compile(
    r"\[(?P<label>[^\]\n]{1,80})\]\((?P<url>(?:https?:\/\/|www\.)[^\s)]+)\)",
    flags=re.IGNORECASE,
)


def _normalize_link_href(raw_url: str) -> str:
    value = str(raw_url or '').strip()
    if not value:
        return ''
    if re.match(r'^https?://', value, flags=re.IGNORECASE):
        return value
    return f"https://{value}"


def _strip_url_trailing_punct(token: str) -> tuple[str, str]:
    value = str(token or '')
    suffix = ''
    while value and value[-1] in '),.;!?':
        suffix = value[-1] + suffix
        value = value[:-1]
    return value, suffix


def _linkify_plain_segment(text: str) -> str:
    if not text:
        return ''

    out = []
    cursor = 0
    for match in _URL_TOKEN_RE.finditer(text):
        start, end = match.span()
        token = match.group(0) or ''
        url_token, suffix = _strip_url_trailing_punct(token)
        if not url_token:
            continue

        if start > cursor:
            out.append(html.escape(text[cursor:start]))

        href = html.escape(_normalize_link_href(url_token), quote=True)
        label = html.escape(url_token)
        out.append(
            f'<a href="{href}" target="_blank" rel="noopener noreferrer nofollow">{label}</a>'
        )
        if suffix:
            out.append(html.escape(suffix))
        cursor = end

    if cursor < len(text):
        out.append(html.escape(text[cursor:]))

    return ''.join(out)


@register.filter(name='highlight_mentions')
def highlight_mentions(value):
    """Wrap @mentions in a styled span.

    IMPORTANT: Use together with |escape before this filter.
    """
    if value is None:
        return ''

    text = str(value)

    def _repl(m):
        prefix = m.group(1) or ''
        name = (m.group('name') or '').strip()
        if not name:
            return m.group(0)
        return (
            f"{prefix}"
            f"<span class=\"font-bold text-yellow-300\">@{name}</span>"
        )

    return mark_safe(_MENTION_RE.sub(_repl, text))


@register.filter(name='rich_announcement')
def rich_announcement(value):
    """Render banner text with support for named links.

    Supported format for custom label links:
    [Your Text](https://example.com)

    Plain URLs are still auto-linkified.
    """
    if value is None:
        return ''

    text = str(value)
    out = []
    cursor = 0

    for match in _MARKDOWN_LINK_RE.finditer(text):
        start, end = match.span()
        if start > cursor:
            out.append(_linkify_plain_segment(text[cursor:start]))

        label = (match.group('label') or '').strip()
        url = (match.group('url') or '').strip()
        if label and url:
            href = html.escape(_normalize_link_href(url), quote=True)
            out.append(
                f'<a href="{href}" target="_blank" rel="noopener noreferrer nofollow">{html.escape(label)}</a>'
            )
        else:
            out.append(html.escape(match.group(0) or ''))
        cursor = end

    if cursor < len(text):
        out.append(_linkify_plain_segment(text[cursor:]))

    return mark_safe(''.join(out))


def _split_query(url: str) -> tuple[str, str]:
    if not url:
        return '', ''
    s = str(url)
    if '?' not in s:
        return s, ''
    base, q = s.split('?', 1)
    return base, ('?' + q) if q else ''


@register.filter(name='giphy_mp4_url')
def giphy_mp4_url(url):
    """Best-effort conversion from a Giphy GIF URL to a MP4 URL.

    We store GIF URLs in messages. MP4 allows pausing/playing on hover.
    Giphy generally supports the same path with .mp4.
    """
    if not url:
        return ''
    base, q = _split_query(str(url).strip())
    if base.lower().endswith('.gif'):
        return base[:-4] + '.mp4' + q
    return base + q


@register.filter(name='giphy_still_url')
def giphy_still_url(url):
    """Best-effort conversion from a Giphy GIF URL to a *still* preview.

    Used as a poster/thumbnail so GIFs don't animate until hovered.
    """
    if not url:
        return ''
    base, q = _split_query(str(url).strip())

    lower = base.lower()
    if lower.endswith('/giphy.gif'):
        return base[:-9] + 'giphy_s.gif' + q

    m = re.search(r"/(\d+w)\.gif$", base, flags=re.IGNORECASE)
    if m:
        size = m.group(1)
        return re.sub(r"/(\d+w)\.gif$", f"/{size}_s.gif", base, flags=re.IGNORECASE) + q

    # Fallback: return original.
    return base + q
