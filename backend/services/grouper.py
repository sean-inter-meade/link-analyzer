from __future__ import annotations

from collections import defaultdict

from backend.models import AnalysisSummary, ExampleStatus, ExtractedLink, LinkGroup

_STATUS_ORDER = [
    ExampleStatus.BROKEN_EXAMPLE.value,
    ExampleStatus.WORKING_EXAMPLE.value,
    ExampleStatus.NEUTRAL_OR_UNKNOWN.value,
]


class Grouper:
    def group_by_status(
        self, links: list[ExtractedLink]
    ) -> tuple[AnalysisSummary, list[LinkGroup]]:
        buckets: dict[str, list[ExtractedLink]] = defaultdict(list)
        for link in links:
            buckets[link.example_status].append(link)

        groups = [
            LinkGroup(example_status=status, items=buckets[status])
            for status in _STATUS_ORDER
            if status in buckets
        ]

        summary = AnalysisSummary(
            working_count=len(buckets.get(ExampleStatus.WORKING_EXAMPLE.value, [])),
            broken_count=len(buckets.get(ExampleStatus.BROKEN_EXAMPLE.value, [])),
            unknown_count=len(buckets.get(ExampleStatus.NEUTRAL_OR_UNKNOWN.value, [])),
        )

        return summary, groups

    def group_by_type(self, links: list[ExtractedLink]) -> list[LinkGroup]:
        buckets: dict[str, list[ExtractedLink]] = defaultdict(list)
        for link in links:
            buckets[link.url_type].append(link)

        return [
            LinkGroup(example_status=url_type, items=items)
            for url_type, items in sorted(buckets.items())
        ]

    def group_nested(self, links: list[ExtractedLink]) -> list[dict]:
        outer: dict[str, dict[str, list[ExtractedLink]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for link in links:
            outer[link.example_status][link.url_type].append(link)

        result: list[dict] = []
        for status in _STATUS_ORDER:
            if status not in outer:
                continue
            type_groups = [
                {"url_type": url_type, "items": items}
                for url_type, items in sorted(outer[status].items())
            ]
            result.append({"example_status": status, "groups": type_groups})

        return result
