"""API error hierarchy → serialized as {"error": {"code", "message"}} responses.

Matches the approved contract error envelope: LINEAGE_INVALID / ARTIFACT_UNREADABLE
= 503 (fail closed); INTERNAL = 500 (the ApiError base default).
"""

from __future__ import annotations


class ApiError(Exception):
    """Base API error. Subclasses set status_code / code / message."""

    status_code: int = 500
    code: str = "INTERNAL"
    message: str = "Internal server error."

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class LineageInvalidError(ApiError):
    status_code = 503
    code = "LINEAGE_INVALID"
    message = "Dashboard lineage validation failed."


class ArtifactUnreadableError(ApiError):
    status_code = 503
    code = "ARTIFACT_UNREADABLE"
    message = "A required artifact could not be read."
