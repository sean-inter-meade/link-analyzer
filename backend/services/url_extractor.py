from __future__ import annotations

import re
from datetime import datetime

from backend.models import ConversationMessage

_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'\)]+")
_ANCHOR_RE = re.compile(
    r'<a\s[^>]*href=["\'](?P<url>https?://[^"\']+)["\'][^>]*>(?P<text>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


class UrlExtractor:
    def extract(self, messages: list[ConversationMessage]) -> list[dict]:
        results: list[dict] = []

        for msg in messages:
            anchors = {m.group("url"): m for m in _ANCHOR_RE.finditer(msg.body_text)}
            seen_urls: set[str] = set()
            url_entries: list[tuple[int, dict]] = []

            for match in _URL_RE.finditer(msg.body_text):
                url = match.group()
                if url.startswith("www."):
                    url = "https://" + url
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                anchor_match = anchors.get(url)
                anchor_text: str | None = None
                if anchor_match:
                    anchor_text = re.sub(r"<[^>]+>", "", anchor_match.group("text")).strip()

                start = match.start()
                end = match.end()
                before = msg.body_text[max(0, start - 100) : start]
                after = msg.body_text[end : end + 100]
                surrounding = (before + after).strip()

                url_entries.append(
                    (
                        start,
                        {
                            "url": url,
                            "message_id": msg.id,
                            "message_author_type": msg.author_type.value,
                            "message_created_at": msg.created_at,
                            "anchor_text": anchor_text,
                            "surrounding_text": surrounding,
                            "is_bare_url": self._is_bare(msg.body_text, seen_urls),
                        },
                    )
                )

            url_entries.sort(key=lambda e: e[0])
            results.extend(entry for _, entry in url_entries)

        results.sort(key=lambda r: (r["message_created_at"], 0))
        return results

    @staticmethod
    def _is_bare(body: str, urls: set[str]) -> bool:
        stripped = body
        for url in urls:
            stripped = stripped.replace(url, "")
        return len(stripped.strip()) < 10
