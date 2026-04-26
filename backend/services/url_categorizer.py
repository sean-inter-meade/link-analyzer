from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse, parse_qs

import yaml

from backend.models import UrlType

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "url_patterns.yaml"

_STANDALONE_PARAMS = {"standalone", "overview"}


class UrlCategorizer:
    def __init__(self) -> None:
        with open(_CONFIG_PATH) as f:
            data = yaml.safe_load(f)
        self._rules: list[dict] = data.get("rules", [])

    def categorize(self, url: str) -> str:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        path = parsed.path or ""
        query = parse_qs(parsed.query)

        # standalone=1 or overview=1 on any Intercom app domain → excluded
        is_intercom_app = hostname.startswith("app.") and ("intercom.com" in hostname or "intercom.io" in hostname)
        if is_intercom_app:
            if any(param in query for param in _STANDALONE_PARAMS):
                if any(p in path for p in ("-overview", "/overview", "/home")):
                    return UrlType.EXCLUDED.value

        for rule in self._rules:
            hostnames: list[str] = rule.get("hostnames") or []
            paths: list[str] = rule.get("paths") or []
            url_type = rule["url_type"]

            hostname_match = any(h in hostname for h in hostnames)
            path_match = any(p in path for p in paths)

            # Excluded rules require BOTH hostname and path to match
            if url_type == "excluded":
                if hostname_match and path_match:
                    return url_type
                continue

            if hostnames and paths:
                if hostname_match and path_match:
                    return url_type
            elif hostnames:
                if hostname_match:
                    return url_type
            elif paths:
                if path_match:
                    return url_type
            else:
                return url_type

        return UrlType.OTHER.value
