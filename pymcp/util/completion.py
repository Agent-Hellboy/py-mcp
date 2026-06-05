"""Helpers for MCP completion/complete suggestion ranking and pagination."""

from __future__ import annotations

import re

_COMPLETION_PAGE_SIZE = 100
_TEMPLATE_VARIABLE_PATTERN = re.compile(r"\{([^}]+)\}")


def extract_template_variables(uri_template: str) -> list[str]:
    return _TEMPLATE_VARIABLE_PATTERN.findall(uri_template)


def completion_candidates_from_argument(argument: dict[str, object]) -> list[str]:
    completion = argument.get("completion")
    if isinstance(completion, list):
        return [str(value) for value in completion]

    schema = argument.get("schema")
    if isinstance(schema, dict):
        enum = schema.get("enum")
        if isinstance(enum, list):
            return [str(value) for value in enum]

    return []


def rank_completions(candidates: list[str], prefix: str) -> list[str]:
    if not candidates:
        return []

    normalized_prefix = prefix.casefold()
    if not normalized_prefix:
        return sorted(candidates, key=str.casefold)

    prefix_matches = [value for value in candidates if value.casefold().startswith(normalized_prefix)]
    if prefix_matches:
        return sorted(prefix_matches, key=lambda value: (len(value), value.casefold()))

    substring_matches = [value for value in candidates if normalized_prefix in value.casefold()]
    return sorted(substring_matches, key=lambda value: (len(value), value.casefold()))


def paginate_completions(
    values: list[str],
    *,
    limit: int = _COMPLETION_PAGE_SIZE,
) -> tuple[list[str], int, bool]:
    total = len(values)
    page = values[:limit]
    return page, total, total > limit


def build_completion_result(values: list[str], *, prefix: str) -> dict[str, object]:
    ranked = rank_completions(values, prefix)
    page, total, has_more = paginate_completions(ranked)
    return {
        "values": page,
        "total": total,
        "hasMore": has_more,
    }


__all__ = [
    "build_completion_result",
    "completion_candidates_from_argument",
    "extract_template_variables",
    "paginate_completions",
    "rank_completions",
]
