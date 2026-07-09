"""Path redaction for API-facing diagnostic strings.

The dashboard API never exposes raw parquet paths, run folders, drive letters or
any other deployment internals (dashboard_data_contract.md's read-only boundary;
dashboard_api_contract.md §8). The core lineage validator
(:mod:`src.dashboard.lineage`) deliberately formats verbose, path-carrying
warnings — those are useful when running the pipeline locally. This module is
the **projection-layer** filter applied on the way out to the wire.

The transformation is deliberately narrow: it removes path-shaped tokens and
leaves everything else byte-identical, so a warning keeps its component name and
its failure class ("no run directory", "manifest lacks explicit behaviour
provenance", …). Run ids are public — they are served as ``/meta.runId`` — and
contain no path separators, so no pattern below can match one.
"""

from __future__ import annotations

import re

#: Stand-in for any elided filesystem path.
REDACTED = "[redacted path]"

# A path token runs until whitespace or a character that reliably terminates one
# in the validator's f-strings (`;`, `,`, `)`, quotes).
_TOKEN = r"[^\s;,)'\"]*"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    # C:\Users\... or C:/Users/...
    re.compile(rf"[A-Za-z]:[\\/]{_TOKEN}"),
    # UNC: \\server\share\...
    re.compile(rf"\\\\{_TOKEN}"),
    # POSIX absolute: /home/ci/injexcore/data/... . The lookbehind keeps the
    # separator in run-id pairs ("remat-v1-.../20260612T124909Z") from matching:
    # there, the slash follows a word character.
    re.compile(r"(?<![\w.])/(?:[\w.\-]+/)+[\w.\-]*"),
    # Repo-relative: data/..., ./src/..., runs\..., configs/...
    re.compile(
        rf"(?:\.{{1,2}}[\\/])?(?:data|runs|src|apps|configs|tests|docs)[\\/]{_TOKEN}"
    ),
    # Residual: any token carrying a backslash, or a bare artifact filename.
    re.compile(r"\S*\\\S*"),
    re.compile(r"\S+\.(?:parquet|json|joblib|csv|yaml|yml)\b"),
)


def _replace(match: re.Match[str]) -> str:
    """Elide the path but hand back sentence punctuation it greedily swallowed."""
    trailing = len(match.group(0)) - len(match.group(0).rstrip("."))
    return REDACTED + "." * trailing


def redact_paths(text: str) -> str:
    """Replace filesystem paths in ``text`` with :data:`REDACTED`.

    Idempotent, and a no-op on path-free text — the four provenance warnings the
    canonical chain actually emits pass through unchanged.
    """
    for pattern in _PATTERNS:
        text = pattern.sub(_replace, text)
    return text
