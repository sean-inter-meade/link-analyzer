from __future__ import annotations

import re
from urllib.parse import urlparse

ADMIN_BASE = "https://intercomrades.intercom.com/admin"


def _extract_app_id(path_parts: list[str]) -> str | None:
    try:
        apps_idx = path_parts.index("apps")
        if apps_idx + 1 < len(path_parts):
            return path_parts[apps_idx + 1]
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

    app_id = _extract_app_id(parts)
    if not app_id:
        return None

    if url_type == "conversation":
        item_id = _find_resource_id(parts, "conversations") or _find_resource_id(parts, "conversation")
        if item_id:
            return f"{ADMIN_BASE}/conversations?app_id={app_id}&conversation_id={item_id}"

    if url_type == "workflow":
        item_id = _find_resource_id(parts, "workflows") or _find_resource_id(parts, "custom-bots")
        if item_id:
            return f"{ADMIN_BASE}/workflows?app_id={app_id}&workflow_id={item_id}"

    if url_type == "custom_action":
        item_id = _find_resource_id(parts, "actions") or _find_resource_id(parts, "custom-action") or _find_resource_id(parts, "custom_actions")
        if item_id:
            return f"{ADMIN_BASE}/custom_actions?app_id={app_id}&custom_action_id={item_id}"

    if url_type == "article":
        item_id = _find_resource_id(parts, "articles")
        if item_id:
            return f"{ADMIN_BASE}/articles?app_id={app_id}&article_id={item_id}"

    if url_type == "help_center":
        item_id = _find_resource_id(parts, "articles")
        if item_id:
            return f"{ADMIN_BASE}/articles?app_id={app_id}&article_id={item_id}"

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
            return f"{ADMIN_BASE}/{resource}?app_id={app_id}&{param}={item_id}"

    # Outbound: messages, tours, custom-bots, posts, etc.
    if "outbound" in parts:
        outbound_idx = parts.index("outbound")
        remaining = parts[outbound_idx + 1:]
        if len(remaining) >= 2:
            outbound_type = remaining[0]
            outbound_id = remaining[1]
            return f"{ADMIN_BASE}/outbound/{outbound_type}?app_id={app_id}&id={outbound_id}"
        elif len(remaining) == 1:
            return f"{ADMIN_BASE}/outbound?app_id={app_id}"

    # Settings pages — no resource ID, just link to the settings section
    if "settings" in parts:
        settings_idx = parts.index("settings")
        section = "/".join(parts[settings_idx:])
        return f"{ADMIN_BASE}/{section}?app_id={app_id}"

    # Operator section (workflows, task bots, etc.)
    if "operator" in parts:
        operator_idx = parts.index("operator")
        remaining = parts[operator_idx + 1:]
        if len(remaining) >= 2:
            return f"{ADMIN_BASE}/workflows?app_id={app_id}&workflow_id={remaining[1]}"
        elif len(remaining) >= 1:
            return f"{ADMIN_BASE}/operator/{remaining[0]}?app_id={app_id}"

    # Generic fallback — best effort with app_id
    return f"{ADMIN_BASE}/?app_id={app_id}"
