"""全局常量，统一管理，避免重复定义。"""

# 视频文件发现（扫描目录用，支持更多格式）
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}

# 视频服务端播放（仅浏览器可直接播放的格式，用于 Range 请求）
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}
