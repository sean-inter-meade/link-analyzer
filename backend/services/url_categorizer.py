from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import yaml

from backend.models import UrlType

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "url_patterns.yaml"


class UrlCategorizer:
    def __init__(self) -> None:
        with open(_CONFIG_PATH) as f:
            data = yaml.safe_load(f)
        self._rules: list[dict] = data.get("rules", [])

    def categorize(self, url: str) -> str:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        path = parsed.path or ""

        for rule in self._rules:
            hostnames: list[str] = rule.get("hostnames") or []
            paths: list[str] = rule.get("paths") or []

            hostname_match = any(h in hostname for h in hostnames)
            path_match = any(p in path for p in paths)

            if hostnames and hostname_match:
                return rule["url_type"]
            if paths and path_match:
                return rule["url_type"]
            # Catch-all: empty hostnames and empty paths means match everything
            if not hostnames and not paths:
                return rule["url_type"]

        return UrlType.OTHER.value
