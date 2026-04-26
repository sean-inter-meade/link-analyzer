from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs

_ADMIN_BASES = {
    "us": "https://intercomrades.intercom.com/admin",
    "eu": "https://intercomrades.eu.intercom.com/admin",
    "au": "https://intercomrades.au.intercom.com/admin",
}

_OUTBOUND_SUBTYPE_KEYWORDS = (
    "tour", "email", "chat", "push", "checklists", "sms",
    "carousel", "custom-bot", "broadcast", "discord-broadcast",
    "tooltips", "whatsapp", "news-items",
)

_ID_RE = re.compile(r"^\d+$")


def _detect_region(hostname: str) -> str:
    if ".eu." in hostname:
        return "eu"
    if ".au." in hostname:
        return "au"
    return "us"


def _extract_app_id(path_parts: list[str]) -> str | None:
    # Standard format: /a/apps/{app_id}/...
    # Inbox format:    /a/inbox/{app_id}/...
    for prefix in ("apps", "inbox"):
        try:
            idx = path_parts.index(prefix)
            if idx + 1 < len(path_parts):
                candidate = path_parts[idx + 1]
                # "inbox" appears twice in inbox URLs — the app_id is the
                # non-keyword segment immediately after the first match
                if candidate not in ("admin", "inbox", "conversation", "conversations"):
                    return candidate
        except ValueError:
            continue
    return None


def _find_numeric_id(path_parts: list[str], after_keyword: str) -> str | None:
    try:
        idx = path_parts.index(after_keyword)
        for candidate in path_parts[idx + 1:]:
            if _ID_RE.match(candidate):
                return candidate
    except ValueError:
        pass
    return None


def _find_resource_id(path_parts: list[str], after_keyword: str) -> str | None:
    try:
        idx = path_parts.index(after_keyword)
        if idx + 1 < len(path_parts):
            candidate = path_parts[idx + 1]
            if candidate not in ("edit", "show", "new", ""):
                return candidate
    except ValueError:
        pass
    return None


def build_admin_url(original_url: str, url_type: str) -> str | None:
    parsed = urlparse(original_url)
    path = parsed.path.strip("/")
    parts = path.split("/")
    hostname = parsed.hostname or ""
    query = parse_qs(parsed.query)

    app_id = _extract_app_id(parts)
    if not app_id:
        return None

    region = _detect_region(hostname)
    admin_base = _ADMIN_BASES[region]

    if url_type == "conversation":
        item_id = _find_resource_id(parts, "conversations") or _find_resource_id(parts, "conversation")
        if item_id:
            return f"{admin_base}/conversations?app_id={app_id}&conversation_id={item_id}"

    if url_type == "workflow":
        item_id = _find_resource_id(parts, "workflows") or _find_resource_id(parts, "custom-bots")
        if item_id:
            return f"{admin_base}/rulesets/{item_id}"

    if url_type == "custom_action":
        item_id = (
            _find_resource_id(parts, "custom-action")
            or _find_resource_id(parts, "custom_actions")
            or _find_numeric_id(parts, "custom-actions")
            or _find_resource_id(parts, "actions")
        )
        if item_id:
            return f"{admin_base}/custom_actions/{item_id}?app_id={app_id}"

    if url_type == "procedure":
        item_id = _find_numeric_id(parts, "procedures")
        if item_id:
            return f"{admin_base}/fin_procedures/{item_id}?app_id={app_id}"

    if url_type == "guidance":
        item_id = _find_numeric_id(parts, "guidance")
        if item_id:
            return f"{admin_base}/rulesets/{item_id}"

    if url_type == "article":
        item_id = _find_resource_id(parts, "articles")
        if item_id:
            return f"{admin_base}/articles/{item_id}"

    if url_type == "help_center":
        item_id = _find_resource_id(parts, "articles")
        if item_id:
            return f"{admin_base}/articles/{item_id}"

    if url_type == "knowledge_hub":
        content_id = query.get("activeContentId", [None])[0]
        if content_id:
            return f"{admin_base}/knowledge-hub?app_id={app_id}&activeContentId={content_id}"
        folder_id = _find_resource_id(parts, "folder")
        if folder_id:
            return f"{admin_base}/knowledge-hub/folder/{folder_id}?app_id={app_id}"

    if url_type == "outbound":
        for keyword in _OUTBOUND_SUBTYPE_KEYWORDS:
            item_id = _find_numeric_id(parts, keyword)
            if item_id:
                return f"{admin_base}/rulesets/{item_id}"
        if "all" in parts:
            return f"{admin_base}/outbound/all?app_id={app_id}"

    if url_type == "series":
        item_id = _find_numeric_id(parts, "series")
        if item_id:
            return f"{admin_base}/rulesets/{item_id}"

    if url_type == "report":
        item_id = _find_numeric_id(parts, "report")
        if item_id:
            return f"{admin_base}/reports/{item_id}?app_id={app_id}"
        return f"{admin_base}/reports?app_id={app_id}"

    if url_type == "user":
        item_id = _find_resource_id(parts, "users")
        if item_id:
            return f"{admin_base}/users/{item_id}?app_id={app_id}"

    if url_type == "company":
        item_id = _find_resource_id(parts, "companies")
        if item_id:
            return f"{admin_base}/companies/{item_id}?app_id={app_id}"

    # Settings pages — no resource ID, just link to the settings section
    if "settings" in parts:
        settings_idx = parts.index("settings")
        section = "/".join(parts[settings_idx:])
        return f"{admin_base}/{section}?app_id={app_id}"

    # Operator section (workflows, task bots, etc.)
    if "operator" in parts:
        operator_idx = parts.index("operator")
        remaining = parts[operator_idx + 1:]
        if len(remaining) >= 2:
            return f"{admin_base}/rulesets/{remaining[1]}"
        elif len(remaining) >= 1:
            return f"{admin_base}/operator/{remaining[0]}?app_id={app_id}"

    # Generic fallback — best effort with app_id
    return f"{admin_base}/?app_id={app_id}"
