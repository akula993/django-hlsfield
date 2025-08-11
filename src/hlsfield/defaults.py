# Безопасный доступ к settings
try:
    from django.conf import settings as _settings
    _CONFIGURED = getattr(_settings, "configured", False)
except Exception:
    _settings = None
    _CONFIGURED = False

def _get(name, default):
    if _CONFIGURED and _settings is not None:
        try:
            return getattr(_settings, name, default)
        except Exception:
            return default
    return default

FFPROBE = _get("HLSFIELD_FFPROBE", "ffprobe")
FFMPEG  = _get("HLSFIELD_FFMPEG", "ffmpeg")

DEFAULT_LADDER = _get("HLSFIELD_DEFAULT_LADDER", [
    {"height": 240,  "v_bitrate": 300,  "a_bitrate": 64},
    {"height": 360,  "v_bitrate": 800,  "a_bitrate": 96},
    {"height": 480,  "v_bitrate": 1200, "a_bitrate": 96},
    {"height": 720,  "v_bitrate": 2500, "a_bitrate": 128},
    {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
])
SEGMENT_DURATION = int(_get("HLSFIELD_SEGMENT_DURATION", 6))

# Хочешь nested по дефолту? поставь "nested"
SIDECAR_LAYOUT   = _get("HLSFIELD_SIDECAR_LAYOUT", "nested")  # "nested" | "flat"
PREVIEW_FILENAME = _get("HLSFIELD_PREVIEW_FILENAME", "preview.jpg")
META_FILENAME    = _get("HLSFIELD_META_FILENAME", "meta.json")
HLS_SUBDIR       = _get("HLSFIELD_HLS_SUBDIR", "hls")

# Автоподстановка upload_to: глобальный тумблер + dotted path
USE_DEFAULT_UPLOAD_TO = bool(_get("HLSFIELD_USE_DEFAULT_UPLOAD_TO", True))
DEFAULT_UPLOAD_TO_PATH = _get("HLSFIELD_DEFAULT_UPLOAD_TO", None)



DASH_SUBDIR = _get("HLSFIELD_DASH_SUBDIR", "dash")
ADAPTIVE_SUBDIR = _get("HLSFIELD_ADAPTIVE_SUBDIR", "adaptive")

# Конфигурация для DASH
DASH_SEGMENT_DURATION = int(_get("HLSFIELD_DASH_SEGMENT_DURATION", 4))  # DASH обычно использует более короткие сегменты
DASH_USE_TEMPLATE = bool(_get("HLSFIELD_DASH_USE_TEMPLATE", True))
DASH_USE_TIMELINE = bool(_get("HLSFIELD_DASH_USE_TIMELINE", True))

# Фоллбэк-реализация upload_to (если dotted-path не задан)
import os, uuid
def default_upload_to(instance, filename: str) -> str:
    stem, ext = os.path.splitext(filename)
    folder = uuid.uuid4().hex[:8]
    return f"videos/{folder}/{stem}{ext}"
