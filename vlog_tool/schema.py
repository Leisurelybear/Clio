"""Centralized artifact schema versioning for generated JSON artifacts.

Usage::

    from vlog_tool.schema import add_schema_version, check_schema_version

    data = {"key": "value"}
    add_schema_version(data)
    write_json(data, path)

    # When reading back:
    loaded = json.loads(path.read_text())
    check_schema_version(loaded, label="analysis")
"""

from __future__ import annotations

import logging

ARTIFACT_SCHEMA_VERSION = 2
"""Current schema version for all generated JSON artifacts.

Incremented when the schema of any artifact changes in a backward-incompatible way.
Version 1 was the initial implicit schema (no _schema_version field).
Version 2 was the first explicit version (added _schema_version field).
"""

logger = logging.getLogger("vlog_tool.schema")


def add_schema_version(data: dict) -> dict:
    """Add ``_schema_version`` to *data* in-place and return it for chaining."""
    data["_schema_version"] = ARTIFACT_SCHEMA_VERSION
    return data


def check_schema_version(data: dict, label: str = "artifact") -> bool:
    """Check that *data*'s ``_schema_version`` matches the current version.

    Logs a warning on mismatch but does not raise — the caller decides
    how to handle it.

    Returns True if the version matches (or if the data has no version field),
    False if there is a mismatch.
    """
    v = data.get("_schema_version")
    if v is None:
        # No version field — assume v1 (legacy data)
        if ARTIFACT_SCHEMA_VERSION > 1:
            logger.warning("%s has no _schema_version — assuming v1 (current v%s)", label, ARTIFACT_SCHEMA_VERSION)
        return True
    if v != ARTIFACT_SCHEMA_VERSION:
        logger.warning("%s schema v%s != current v%s", label, v, ARTIFACT_SCHEMA_VERSION)
        return False
    return True
