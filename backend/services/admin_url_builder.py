from __future__ import annotations

import re
from urllib.parse import urlparse

_ADMIN_BASES = {
    "us": "https://intercomrades.intercom.com/admin",
    "eu": "https://intercomrades.eu.intercom.com/admin",
    "au": "https://intercomrades.au.intercom.com/admin",
}


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
            return f"{admin_base}/workflows?app_id={app_id}&workflow_id={item_id}"

    if url_type == "custom_action":
        item_id = _find_resource_id(parts, "actions") or _find_resource_id(parts, "custom-action") or _find_resource_id(parts, "custom_actions")
        if item_id:
            return f"{admin_base}/custom_actions?app_id={app_id}&custom_action_id={item_id}"

    if url_type == "article":
        item_id = _find_resource_id(parts, "articles")
        if item_id:
            return f"{admin_base}/articles?app_id={app_id}&article_id={item_id}"

    if url_type == "help_center":
        item_id = _find_resource_id(parts, "articles")
        if item_id:
            return f"{admin_base}/articles?app_id={app_id}&article_id={item_id}"

    # Resource types beyond the url_type enum — detected from path structure
    for resource, param in [
        ("procedures", "procedure_id"),
        ("series", "series_id"),
        ("reports", "report_id"),
        ("users", "user_id"),
        ("companies", "company_id"),
    ]:
        item_id = _find_resource_id(parts, resource)
        if item_id:
            return f"{admin_base}/{resource}?app_id={app_id}&{param}={item_id}"

    # Outbound: messages, tours, custom-bots, posts, etc.
    if "outbound" in parts:
        outbound_idx = parts.index("outbound")
        remaining = parts[outbound_idx + 1:]
        if len(remaining) >= 2:
            outbound_type = remaining[0]
            outbound_id = remaining[1]
            return f"{admin_base}/outbound/{outbound_type}?app_id={app_id}&id={outbound_id}"
        elif len(remaining) == 1:
            return f"{admin_base}/outbound?app_id={app_id}"

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
            return f"{admin_base}/workflows?app_id={app_id}&workflow_id={remaining[1]}"
        elif len(remaining) >= 1:
            return f"{admin_base}/operator/{remaining[0]}?app_id={app_id}"

    # Generic fallback — best effort with app_id
    return f"{admin_base}/?app_id={app_id}"
