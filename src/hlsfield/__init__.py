"""
🎬 django-hlsfield - Django адаптивное видео с HLS/DASH стримингом

Автоматическое создание адаптивного видео для Django проектов.
Поддерживает HLS, DASH, превью, метаданные и Celery интеграцию.

Основные возможности:
- VideoField - базовое поле с метаданными
- HLSVideoField - HTTP Live Streaming
- DASHVideoField - MPEG-DASH адаптивный стрим
- AdaptiveVideoField - HLS + DASH одновременно
- Готовые HTML5 плееры
- Celery фоновая обработка
- Поддержка любых storage backends

Пример использования:
    from hlsfield import HLSVideoField

    class Movie(models.Model):
        title = models.CharField(max_length=200)
        video = HLSVideoField(
            upload_to="movies/",
            hls_playlist_field="hls_master"
        )
        hls_master = models.CharField(max_length=500, null=True, blank=True)

Автор: akula993
Лицензия: MIT
GitHub: https://github.com/akula993/django-hlsfield
"""

# Версия пакета (семантическое версионирование)
__version__ = "1.0.6"

# Метаданные пакета
__title__ = "django-hlsfield"
__description__ = "Django VideoField + HLS/DASH adaptive streaming with automatic transcoding"
__url__ = "https://github.com/akula993/django-hlsfield"
__author__ = "akula993"
__author_email__ = "akula993@gmail.com"
__license__ = "MIT"
__copyright__ = "Copyright 2025 akula993"

# Статус разработки
__status__ = "Production/Stable"

from django.core.exceptions import ImproperlyConfigured

# Исключения для обработки ошибок
from .exceptions import (
    HLSFieldError,
    FFmpegError,
    FFmpegNotFoundError,
    InvalidVideoError,
    TranscodingError,
    StorageError,
    ConfigurationError,
)
# Основные поля (главный API)
from .fields import (
    VideoField,
    VideoFieldFile,
    HLSVideoField,
    HLSVideoFieldFile,
    DASHVideoField,
    DASHVideoFieldFile,
    AdaptiveVideoField,
    AdaptiveVideoFieldFile,
)
# Валидация и утилиты
from .fields import (
    validate_ladder,
    get_optimal_ladder_for_resolution,
)
# Вспомогательные функции
from .helpers import (
    video_upload_to,
    get_video_upload_path,
    generate_video_id,
)

# ==============================================================================
# ОСНОВНЫЕ ИМПОРТЫ
# ==============================================================================

# ==============================================================================
# ЭКСПОРТЫ ПАКЕТА
# ==============================================================================

# Основной API - поля для использования в models.py
__all__ = [
    # === ОСНОВНЫЕ ПОЛЯ ===
    "VideoField",  # Базовое видео поле с метаданными
    "HLSVideoField",  # HTTP Live Streaming
    "DASHVideoField",  # MPEG-DASH адаптивный стрим
    "AdaptiveVideoField",  # HLS + DASH одновременно
    # === FILE OBJECTS ===
    "VideoFieldFile",  # Файловый объект для VideoField
    "HLSVideoFieldFile",  # Файловый объект для HLSVideoField
    "DASHVideoFieldFile",  # Файловый объект для DASHVideoField
    "AdaptiveVideoFieldFile",  # Файловый объект для AdaptiveVideoField
    # === УТИЛИТЫ ===
    "validate_ladder",  # Валидация лестницы качеств
    "get_optimal_ladder_for_resolution",  # Генерация оптимальной лестницы
    "video_upload_to",  # Функция upload_to
    "get_video_upload_path",  # Генерация путей для видео
    "generate_video_id",  # Генерация уникальных ID
    # === ИСКЛЮЧЕНИЯ ===
    "HLSFieldError",  # Базовое исключение пакета
    "FFmpegError",  # Ошибки FFmpeg
    "FFmpegNotFoundError",  # FFmpeg не найден
    "InvalidVideoError",  # Некорректный видеофайл
    "TranscodingError",  # Ошибки транскодинга
    "StorageError",  # Ошибки storage
    "ConfigurationError",  # Ошибки конфигурации
    # === МЕТАДАННЫЕ ===
    "__version__",  # Версия пакета
]


# ==============================================================================
# УСЛОВНЫЕ ИМПОРТЫ (для дополнительных функций)
# ==============================================================================


def _get_streaming_views():
    """Ленивый импорт streaming views"""
    try:
        from .streaming import SecureStreamingView, ProtectedHLSView

        return {
            "SecureStreamingView": SecureStreamingView,
            "ProtectedHLSView": ProtectedHLSView,
        }
    except ImportError:
        return {}

def _get_analytics():
    """Ленивый импорт аналитики"""
    try:
        from .views import VideoAnalyticsView
        return {
            "VideoAnalyticsView": VideoAnalyticsView,
        }
    except ImportError:
        return {}


# ==============================================================================
# МАГИЧЕСКИЕ МЕТОДЫ ДЛЯ ДИНАМИЧЕСКИХ ИМПОРТОВ
# ==============================================================================


def __getattr__(name: str):
    """
    Динамический импорт модулей при первом обращении.

    Позволяет импортировать дополнительные компоненты только при необходимости:
    - from hlsfield import SecureStreamingView
    - from hlsfield import VideoAnalyticsView
    """

    # Продвинутые поля (проверяем существование модуля)
    if name in ["SmartAdaptiveVideoField", "ProgressiveVideoField"]:
        try:
            from . import smart_fields

            if hasattr(smart_fields, name):
                return getattr(smart_fields, name)
        except ImportError:
            pass

    # Streaming views
    if name in ["SecureStreamingView", "ProtectedHLSView"]:
        try:
            from . import streaming

            if hasattr(streaming, name):
                return getattr(streaming, name)
        except ImportError:
            pass

    # Views
    if name in ["VideoAnalyticsView", "VideoStatusView"]:
        try:
            from . import views

            if hasattr(views, name):
                return getattr(views, name)
        except ImportError:
            pass

    # Задачи Celery
    if name.endswith("_task") or name.startswith("build_"):
        try:
            from . import tasks

            if hasattr(tasks, name):
                return getattr(tasks, name)
        except ImportError:
            pass

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__():
    """Возвращает список доступных атрибутов для автокомплита"""

    base_attrs = __all__.copy()

    # Добавляем streaming views если доступны
    base_attrs.extend(_get_streaming_views().keys())

    # Добавляем аналитику если доступна
    base_attrs.extend(_get_analytics().keys())

    # Добавляем основные настройки
    base_attrs.extend(
        [
            "DEFAULT_LADDER",
            "SEGMENT_DURATION",
            "FFMPEG",
            "FFPROBE",
            "MOBILE_LADDER",
            "PREMIUM_LADDER",
        ]
    )

    return sorted(base_attrs)


# ==============================================================================
# ПРОВЕРКИ СОВМЕСТИМОСТИ
# ==============================================================================


def check_django_version():
    """Проверяет совместимость с версией Django"""
    try:
        import django
        from packaging import version

        django_version_str = "{}.{}".format(*django.VERSION[:2])
        django_version = version.parse(django_version_str)
        min_version = version.parse("4.2")

        if django_version < min_version:
            import warnings

            warnings.warn(
                f"django-hlsfield requires Django 4.2+, you have {django.get_version()}",
                UserWarning,
                stacklevel=2,
            )
    except ImportError:
        pass


def check_python_version():
    """Проверяет совместимость с версией Python"""
    import sys

    if sys.version_info < (3, 10):
        import warnings

        warnings.warn(
            f"django-hlsfield requires Python 3.10+, you have {sys.version}",
            UserWarning,
            stacklevel=2,
        )


# Выполняем проверки при импорте (только в development)
try:
    from django.conf import settings

    if getattr(settings, "DEBUG", False):
        check_django_version()
        check_python_version()
except (ImportError, ImproperlyConfigured):
    # Django еще не настроен
    pass

# ==============================================================================
# ИНФОРМАЦИЯ О ПАКЕТЕ ДЛЯ ИНСТРУМЕНТОВ
# ==============================================================================

# Информация для setuptools/pip
package_info = {
    "name": __title__,
    "version": __version__,
    "description": __description__,
    "url": __url__,
    "author": __author__,
    "author_email": __author_email__,
    "license": __license__,
    "status": __status__,
}

# Классификаторы для PyPI
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Framework :: Django",
    "Framework :: Django :: 4.2",
    "Framework :: Django :: 5.0",
    "Framework :: Django :: 5.1",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Internet :: WWW/HTTP",
    "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    "Topic :: Multimedia :: Video",
    "Topic :: Multimedia :: Video :: Conversion",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Environment :: Web Environment",
    "Natural Language :: English",
    "Natural Language :: Russian",
]

# Ключевые слова для поиска
keywords = [
    "django",
    "video",
    "hls",
    "dash",
    "streaming",
    "adaptive",
    "ffmpeg",
    "transcoding",
    "celery",
    "html5",
    "player",
    "multimedia",
    "webdev",
]

# ==============================================================================
# DJANGO APPS REGISTRY
# ==============================================================================

# Автоматическая конфигурация Django app
default_app_config = "hlsfield.apps.HLSFieldConfig"

# ==============================================================================
# ЗАВЕРШАЮЩЕЕ СООБЩЕНИЕ
# ==============================================================================

# При первом импорте показываем краткую информацию (только в DEBUG)
try:
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured

    if getattr(settings, "DEBUG", False):
        import sys

        if "runserver" in sys.argv or "shell" in sys.argv:
            print(f"🎬 {__title__} v{__version__} loaded")
except (ImportError, ImproperlyConfigured, AttributeError):
    pass
