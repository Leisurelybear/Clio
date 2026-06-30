"""StrEnum compatibility module for Python < 3.11."""

try:
    from enum import StrEnum
except ImportError:
    # Python < 3.11 compatibility
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef,misc]  # noqa: UP042
        pass
