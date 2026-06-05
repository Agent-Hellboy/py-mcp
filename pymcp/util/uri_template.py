"""URI template matching for MCP resource templates."""

from __future__ import annotations

import re


def compile_uri_template(uri_template: str) -> re.Pattern[str]:
    """Compile an MCP URI template with ``{variable}`` placeholders into a matcher."""

    parts = re.split(r"\{([^}]+)\}", uri_template)
    regex_parts = ["^"]
    index = 0
    while index < len(parts):
        if index % 2 == 0:
            regex_parts.append(re.escape(parts[index]))
        else:
            name = parts[index]
            has_suffix = index + 1 < len(parts) and parts[index + 1]
            if has_suffix:
                regex_parts.append(f"(?P<{name}>[^/]+)")
            else:
                regex_parts.append(f"(?P<{name}>.+)")
        index += 1
    regex_parts.append("$")
    return re.compile("".join(regex_parts))


def match_uri_template(uri_template: str, uri: str) -> dict[str, str] | None:
    """Match ``uri`` against ``uri_template`` and return captured variables."""

    matcher = compile_uri_template(uri_template)
    match = matcher.match(uri)
    if match is None:
        return None
    return {key: value for key, value in match.groupdict().items() if value is not None}


__all__ = ["compile_uri_template", "match_uri_template"]
