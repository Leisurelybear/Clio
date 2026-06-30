from clio._str_enum import StrEnum


class WhisperModelSize(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE_V3 = "large-v3"


class WhisperLang(StrEnum):
    ZH = "zh"
    EN = "en"
    AUTO = "auto"


class WhisperDevice(StrEnum):
    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"
