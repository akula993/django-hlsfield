"""
🎬 Django HLS Video Fields - Основные поля для работы с адаптивным видео

Этот модуль содержит все основные поля для интеграции адаптивного видео в Django:
- VideoField: базовое поле с метаданными и превью
- HLSVideoField: автоматическое создание HLS стримов
- DASHVideoField: DASH адаптивный стриминг
- AdaptiveVideoField: HLS + DASH одновременно

Автор: akula993
Лицензия: MIT
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from importlib import import_module
from pathlib import Path
from typing import Any, Optional

from django.core.files.base import File
from django.db import models
from django.utils import timezone

from . import defaults, utils
from .exceptions import InvalidVideoError, StorageError, FFmpegNotFoundError

# Настройка логирования
logger = logging.getLogger(__name__)

# Константы для backward compatibility
META_SUFFIX = "_meta.json"
PREVIEW_SUFFIX = "_preview.jpg"


# ==============================================================================
# БАЗОВЫЙ КЛАСС ДЛЯ РАБОТЫ С ВИДЕОФАЙЛАМИ
# ==============================================================================


class VideoFieldFile(models.fields.files.FieldFile):
    """
    Расширенный FieldFile для работы с видеофайлами.

    Обеспечивает:
    - Извлечение метаданных (длительность, разрешение)
    - Создание превью кадров
    - Гибкую структуру sidecar файлов (nested/flat)
    - Безопасную обработку ошибок
    """

    def _base_key(self) -> str:
        """Базовое имя файла без расширения"""
        base, _ext = os.path.splitext(self.name)
        return base

    def _sidecar_dir_key(self) -> str:
        """Ключ директории для nested layout"""
        return self._base_key()

    def _meta_key(self) -> str:
        """Ключ для файла метаданных"""
        field: VideoField = self.field

        if field.sidecar_layout == "nested":
            return f"{self._sidecar_dir_key()}/{field.meta_filename}"
        return f"{self._base_key()}{META_SUFFIX}"

    def _preview_key(self) -> str:
        """Ключ для файла превью"""
        field: VideoField = self.field

        if field.sidecar_layout == "nested":
            return f"{self._sidecar_dir_key()}/{field.preview_filename}"
        return f"{self._base_key()}{PREVIEW_SUFFIX}"

    def metadata(self) -> dict:
        """
        Получает метаданные видео.

        Сначала пробует получить из полей модели, если настроены.
        Иначе читает из JSON sidecar файла.

        Returns:
            dict: Словарь с метаданными видео
        """
        field: VideoField = self.field
        inst = self.instance

        # Проверяем настроены ли поля модели для метаданных
        have_model_fields = any(
            [field.duration_field, field.width_field, field.height_field, field.preview_field]
        )

        if have_model_fields:
            out = {}

            if field.duration_field:
                dur = getattr(inst, field.duration_field, None)
                if isinstance(dur, dt.timedelta):
                    out["duration_seconds"] = int(dur.total_seconds())

            if field.width_field:
                width = getattr(inst, field.width_field, None)
                if width:
                    out["width"] = width

            if field.height_field:
                height = getattr(inst, field.height_field, None)
                if height:
                    out["height"] = height

            if field.preview_field:
                preview = getattr(inst, field.preview_field, None)
                if preview:
                    out["preview_name"] = preview

            return out

        # Читаем из JSON файла
        try:
            with self.storage.open(self._meta_key(), "r") as fh:
                return json.loads(fh.read())
        except Exception as e:
            logger.debug(f"Could not read metadata from {self._meta_key()}: {e}")
            return {}

    def preview_url(self) -> Optional[str]:
        """
        Получает URL превью изображения.

        Returns:
            Optional[str]: URL превью или None если не найдено
        """
        field: VideoField = self.field
        inst = self.instance

        # Сначала проверяем поле модели
        if field.preview_field:
            preview_name = getattr(inst, field.preview_field, None)
            if preview_name:
                try:
                    return self.storage.url(preview_name)
                except Exception as e:
                    logger.warning(f"Could not get URL for preview {preview_name}: {e}")

        # Проверяем sidecar превью файл
        try:
            preview_key = self._preview_key()
            if self.storage.exists(preview_key):
                return self.storage.url(preview_key)
        except Exception as e:
            logger.debug(f"Could not check preview file existence: {e}")

        return None

    def master_url(self) -> Optional[str]:
        """
        Получает URL master плейлиста для HLS.

        Returns:
            Optional[str]: URL master.m3u8 или None
        """
        field = self.field
        inst = self.instance

        # Проверяем есть ли поле для HLS плейлиста
        playlist_field = getattr(field, "hls_playlist_field", None)
        if playlist_field:
            playlist_name = getattr(inst, playlist_field, None)
            if playlist_name:
                try:
                    return self.storage.url(playlist_name)
                except Exception as e:
                    logger.warning(f"Could not get URL for HLS playlist {playlist_name}: {e}")

        return None

    def dash_url(self) -> Optional[str]:
        """
        Получает URL DASH манифеста.

        Returns:
            Optional[str]: URL manifest.mpd или None
        """
        field = self.field
        inst = self.instance

        # Проверяем есть ли поле для DASH манифеста
        manifest_field = getattr(field, "dash_manifest_field", None)
        if manifest_field:
            manifest_name = getattr(inst, manifest_field, None)
            if manifest_name:
                try:
                    return self.storage.url(manifest_name)
                except Exception as e:
                    logger.warning(f"Could not get URL for DASH manifest {manifest_name}: {e}")

        return None

    def save(self, name: str, content: File, save: bool = True):
        """
        Сохраняет видеофайл и запускает обработку.

        Args:
            name: Имя файла
            content: Содержимое файла
            save: Сохранять ли модель автоматически
        """
        try:
            # Валидируем файл перед сохранением
            self._validate_file(content)

            # Сохраняем через родительский класс
            super().save(name, content, save)

            field: VideoField = self.field
            inst = self.instance

            # Проверяем нужно ли обрабатывать видео
            if not getattr(field, "process_on_save", True):
                logger.debug(f"Video processing disabled for field {field.name}")
                return

            # Запускаем обработку видео
            self._process_video_metadata(field, inst)

        except Exception as e:
            logger.error(f"Error saving video file {name}: {e}")

            # Очищаем при критических ошибках
            if isinstance(e, (InvalidVideoError, FFmpegNotFoundError)):
                self._cleanup_on_error()

            raise

    def _validate_file(self, content: File):
        """Валидация загружаемого видеофайла"""

        # Проверяем размер
        if hasattr(content, "size") and content.size:
            max_size = getattr(defaults, "MAX_FILE_SIZE", 2 * 1024**3)  # 2GB
            if content.size > max_size:
                raise InvalidVideoError(f"File too large: {content.size} bytes (max: {max_size})")

            if content.size < 1000:  # Минимум 1KB
                raise InvalidVideoError("File too small to be a valid video")

        # Проверяем расширение
        if hasattr(content, "name") and content.name:
            ext = Path(content.name).suffix.lower()
            allowed_exts = getattr(
                defaults,
                "ALLOWED_EXTENSIONS",
                [".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".mkv"],
            )

            if ext not in allowed_exts:
                raise InvalidVideoError(f"Unsupported file extension: {ext}")

    def _process_video_metadata(self, field: VideoField, inst):
        """Обрабатывает метаданные видео"""

        try:
            with utils.tempdir() as td:
                logger.info(f"Processing video metadata for {self.name}")

                # Загружаем файл локально для обработки
                local_path = utils.pull_to_local(self.storage, self.name, td)

                # Извлекаем метаданные через FFprobe
                try:
                    info = utils.ffprobe_streams(local_path)
                    v_stream, a_stream = utils.pick_video_audio_streams(info)

                    meta = {}

                    # Длительность из format секции
                    if fmt := info.get("format"):
                        try:
                            duration = float(fmt.get("duration", 0))
                            if duration > 0:
                                meta["duration_seconds"] = int(duration)
                        except (ValueError, TypeError):
                            logger.warning("Could not parse video duration")

                    # Разрешение из видео потока
                    if v_stream:
                        try:
                            width = int(v_stream.get("width", 0))
                            height = int(v_stream.get("height", 0))
                            if width > 0 and height > 0:
                                meta["width"] = width
                                meta["height"] = height
                        except (ValueError, TypeError):
                            logger.warning("Could not parse video dimensions")

                    # Сохраняем метаданные в поля модели
                    self._save_metadata_to_model(field, inst, meta)

                except Exception as e:
                    logger.error(f"Metadata extraction failed: {e}")
                    # Продолжаем без метаданных

                # Создаем превью кадр
                self._create_preview(field, inst, local_path, td)

                # Обновляем timestamp обработки
                if hasattr(inst, "video_processed_at"):
                    setattr(inst, "video_processed_at", timezone.now())

        except Exception as e:
            logger.error(f"Video processing failed for {self.name}: {e}")

            # Устанавливаем статус ошибки
            if hasattr(inst, "processing_status"):
                setattr(inst, "processing_status", f"error: {str(e)[:100]}")

            # Критические ошибки прерывают процесс
            if isinstance(e, (InvalidVideoError, FFmpegNotFoundError)):
                raise

    def _save_metadata_to_model(self, field: VideoField, inst, meta: dict):
        """Сохраняет метаданные в поля модели"""

        try:
            # Длительность
            if field.duration_field and "duration_seconds" in meta:
                duration = dt.timedelta(seconds=meta["duration_seconds"])
                setattr(inst, field.duration_field, duration)

            # Размеры
            if field.width_field and "width" in meta:
                setattr(inst, field.width_field, meta["width"])

            if field.height_field and "height" in meta:
                setattr(inst, field.height_field, meta["height"])

        except Exception as e:
            logger.warning(f"Failed to save metadata to model fields: {e}")

    def _create_preview(self, field: VideoField, inst, local_path: Path, temp_dir: Path):
        """Создает превью изображение из видео"""

        try:
            preview_tmp = temp_dir / "preview.jpg"

            # Извлекаем кадр в указанное время
            utils.extract_preview(local_path, preview_tmp, at_sec=field.preview_at)

            if preview_tmp.exists() and preview_tmp.stat().st_size > 100:
                # Сохраняем в storage
                preview_key = self._preview_key()

                with preview_tmp.open("rb") as fh:
                    saved_path = self.storage.save(preview_key, fh)

                # Обновляем поле модели
                if field.preview_field:
                    setattr(inst, field.preview_field, saved_path)

                # Добавляем в метаданные JSON файла если нет полей модели
                if not any(
                    [
                        field.duration_field,
                        field.width_field,
                        field.height_field,
                        field.preview_field,
                    ]
                ):
                    meta = {"preview_name": saved_path}
                    try:
                        from io import StringIO

                        payload = json.dumps(meta, ensure_ascii=False)
                        self.storage.save(self._meta_key(), StringIO(payload))
                    except Exception as e:
                        logger.warning(f"Could not save metadata JSON: {e}")

                logger.info(f"Preview created: {saved_path}")
            else:
                logger.warning("Preview extraction produced empty or invalid file")

        except Exception as e:
            logger.warning(f"Preview creation failed: {e}")
            # Не прерываем процесс из-за превью

    def _cleanup_on_error(self):
        """Очистка при ошибках сохранения"""

        try:
            if self.name and self.storage.exists(self.name):
                self.storage.delete(self.name)
                logger.info(f"Cleaned up failed upload: {self.name}")
        except Exception as e:
            logger.warning(f"Failed to cleanup file {self.name}: {e}")


# ==============================================================================
# БАЗОВОЕ ВИДЕО ПОЛЕ
# ==============================================================================


class VideoField(models.FileField):
    """
    Базовое поле для работы с видеофайлами.

    Возможности:
    - Автоматическое извлечение метаданных (длительность, разрешение)
    - Создание превью кадра из видео
    - Гибкие настройки sidecar файлов
    - Интеграция с Django admin
    - Автоматический upload_to

    Пример использования:
        video = VideoField(
            upload_to="videos/",
            duration_field="duration",      # поле для длительности
            width_field="width",            # поле для ширины
            height_field="height",          # поле для высоты
            preview_field="preview_image",  # поле для пути к превью
            preview_at=5.0,                 # время извлечения превью (сек)
        )
    """

    attr_class = VideoFieldFile

    def __init__(
        self,
        *args,
        # Поля модели для автозаполнения метаданных
        duration_field: str | None = None,
        width_field: str | None = None,
        height_field: str | None = None,
        preview_field: str | None = None,
        # Настройки обработки
        preview_at: float = 3.0,
        process_on_save: bool = True,
        # Настройки файловой структуры
        sidecar_layout: str | None = None,  # "flat" | "nested"
        preview_filename: str | None = None,  # имя для nested
        meta_filename: str | None = None,  # имя для nested
        # Автоматический upload_to
        use_default_upload_to: bool | None = None,
        **kwargs: Any,
    ):

        # ============================================================================
        # АВТО-ЛОГИКА upload_to
        # ============================================================================

        explicit_upload_to = kwargs.get("upload_to", None)
        has_explicit = bool(explicit_upload_to)

        # Если поле не получило явный upload_to - применяем дефолт
        if not has_explicit:
            use_flag = (
                defaults.USE_DEFAULT_UPLOAD_TO
                if use_default_upload_to is None
                else bool(use_default_upload_to)
            )

            if use_flag:
                # Пробуем получить функцию из настроек
                upload_to_func = None

                if hasattr(defaults, "DEFAULT_UPLOAD_TO_PATH") and defaults.DEFAULT_UPLOAD_TO_PATH:
                    try:
                        module_path, func_name = defaults.DEFAULT_UPLOAD_TO_PATH.rsplit(".", 1)
                        module = import_module(module_path)
                        upload_to_func = getattr(module, func_name)
                    except Exception as e:
                        logger.warning(f"Could not import upload_to function: {e}")

                # Используем функцию из настроек или встроенную
                kwargs["upload_to"] = upload_to_func or defaults.default_upload_to

        # Инициализируем родительский FileField
        super().__init__(*args, **kwargs)

        # Сохраняем параметры обработки
        self.duration_field = duration_field
        self.width_field = width_field
        self.height_field = height_field
        self.preview_field = preview_field
        self.preview_at = preview_at
        self.process_on_save = process_on_save

        # Настройки файловой структуры
        self.sidecar_layout = sidecar_layout or defaults.SIDECAR_LAYOUT
        self.preview_filename = preview_filename or defaults.PREVIEW_FILENAME
        self.meta_filename = meta_filename or defaults.META_FILENAME

    def deconstruct(self):
        """Декомпозиция поля для Django migrations"""
        name, path, args, kwargs = super().deconstruct()

        # Добавляем наши специфические параметры
        if self.duration_field is not None:
            kwargs["duration_field"] = self.duration_field
        if self.width_field is not None:
            kwargs["width_field"] = self.width_field
        if self.height_field is not None:
            kwargs["height_field"] = self.height_field
        if self.preview_field is not None:
            kwargs["preview_field"] = self.preview_field
        if self.preview_at != 3.0:
            kwargs["preview_at"] = self.preview_at
        if not self.process_on_save:
            kwargs["process_on_save"] = self.process_on_save
        if self.sidecar_layout != defaults.SIDECAR_LAYOUT:
            kwargs["sidecar_layout"] = self.sidecar_layout
        if self.preview_filename != defaults.PREVIEW_FILENAME:
            kwargs["preview_filename"] = self.preview_filename
        if self.meta_filename != defaults.META_FILENAME:
            kwargs["meta_filename"] = self.meta_filename

        return name, path, args, kwargs


# ==============================================================================
# HLS VIDEO FIELD - HTTP LIVE STREAMING
# ==============================================================================


class HLSVideoFieldFile(VideoFieldFile):
    """FieldFile для HLS видео с дополнительной логикой обработки"""

    def save(self, name: str, content: File, save: bool = True):
        """Сохраняет файл и запускает HLS обработку"""

        # Сначала выполняем базовую обработку (метаданные, превью)
        super().save(name, content, save)

        field: HLSVideoField = self.field
        inst = self.instance

        # Проверяем нужно ли запускать HLS транскодинг
        if not getattr(field, "hls_on_save", True):
            logger.debug("HLS processing disabled for this field")
            return

        # Если у объекта еще нет pk - отложим HLS обработку до post_save
        if getattr(inst, "pk", None) is None:
            setattr(inst, f"__hls_pending__{field.attname}", True)
            logger.debug("Deferring HLS processing until instance has PK")
            return

        # Запускаем HLS транскодинг
        field._trigger_hls(inst)


class HLSVideoField(VideoField):
    """
    Поле для автоматического создания HLS (HTTP Live Streaming) адаптивного видео.

    Создает:
    - Несколько представлений разного качества (360p, 720p, 1080p etc.)
    - Master плейлист (master.m3u8) со ссылками на все качества
    - TS сегменты для каждого качества
    - Поддержка настраиваемой лестницы качеств

    Пример использования:
        video = HLSVideoField(
            upload_to="videos/",
            hls_playlist_field="hls_master",  # поле для хранения пути к master.m3u8
            ladder=[                          # кастомная лестница качеств
                {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
                {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
                {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
            ],
            segment_duration=6,               # длительность TS сегментов в секундах
        )
        hls_master = models.CharField(max_length=500, null=True, blank=True)
    """

    attr_class = HLSVideoFieldFile

    def __init__(
        self,
        *args,
        hls_playlist_field: str | None = None,
        hls_base_subdir: str | None = None,
        ladder: list[dict] | None = None,
        segment_duration: int | None = None,
        hls_on_save: bool = True,
        **kwargs: Any,
    ):

        # Инициализируем базовое VideoField
        super().__init__(*args, **kwargs)

        # HLS специфичные параметры
        self.hls_playlist_field = hls_playlist_field
        self.hls_base_subdir = hls_base_subdir or defaults.HLS_SUBDIR
        self.ladder = ladder or defaults.DEFAULT_LADDER.copy()
        self.segment_duration = segment_duration or defaults.SEGMENT_DURATION
        self.hls_on_save = hls_on_save

    def contribute_to_class(self, cls, name, **kwargs):
        """Интеграция поля в модель Django"""

        super().contribute_to_class(cls, name, **kwargs)
        self.attname = name

        # Подключаем post_save сигнал для отложенной HLS обработки
        from django.db.models.signals import post_save

        def _hls_post_save_handler(sender, instance, created, **kw):
            """Обработчик post_save для HLS транскодинга"""

            pending_attr = f"__hls_pending__{name}"

            if getattr(instance, pending_attr, False):
                # Убираем флаг отложенной обработки
                setattr(instance, pending_attr, False)

                try:
                    self._trigger_hls(instance)
                except Exception as e:
                    # Логируем ошибку но не ломаем сохранение модели
                    logger.error(f"HLS processing failed in post_save: {e}")

        # Подключаем сигнал к конкретной модели
        post_save.connect(_hls_post_save_handler, sender=cls, weak=False)

    def _trigger_hls(self, instance):
        """Запускает HLS транскодинг через Celery или синхронно"""

        try:
            # Пробуем использовать Celery задачу
            from .tasks import build_hls_for_field, build_hls_for_field_sync

            if hasattr(build_hls_for_field, "delay"):
                # Celery доступен - запускаем асинхронно
                logger.info(
                    f"Starting HLS transcoding (async) for {instance._meta.label}:{instance.pk}"
                )
                task = build_hls_for_field.delay(instance._meta.label, instance.pk, self.attname)

                # Сохраняем task ID если есть соответствующее поле
                if hasattr(instance, "hls_task_id"):
                    setattr(instance, "hls_task_id", task.id)
            else:
                # Celery недоступен - запускаем синхронно
                logger.info(
                    f"Starting HLS transcoding (sync) for {instance._meta.label}:{instance.pk}"
                )
                build_hls_for_field_sync(instance._meta.label, instance.pk, self.attname)

        except ImportError:
            # Модуль tasks не найден - используем синхронную функцию
            from .tasks import build_hls_for_field_sync

            logger.info(
                f"Starting HLS transcoding (fallback) for {instance._meta.label}:{instance.pk}"
            )
            build_hls_for_field_sync(instance._meta.label, instance.pk, self.attname)

    def deconstruct(self):
        """Декомпозиция для migrations"""
        name, path, args, kwargs = super().deconstruct()

        if self.hls_playlist_field is not None:
            kwargs["hls_playlist_field"] = self.hls_playlist_field
        if self.hls_base_subdir != defaults.HLS_SUBDIR:
            kwargs["hls_base_subdir"] = self.hls_base_subdir
        if self.ladder != defaults.DEFAULT_LADDER:
            kwargs["ladder"] = self.ladder
        if self.segment_duration != defaults.SEGMENT_DURATION:
            kwargs["segment_duration"] = self.segment_duration
        if not self.hls_on_save:
            kwargs["hls_on_save"] = self.hls_on_save

        return name, path, args, kwargs


# ==============================================================================
# DASH VIDEO FIELD - DYNAMIC ADAPTIVE STREAMING
# ==============================================================================


class DASHVideoFieldFile(VideoFieldFile):
    """FieldFile для DASH видео"""

    def dash_url(self) -> Optional[str]:
        """Получает URL DASH манифеста"""
        field: DASHVideoField = self.field
        inst = self.instance

        manifest_field = getattr(field, "dash_manifest_field", None)
        if manifest_field:
            manifest_name = getattr(inst, manifest_field, None)
            if manifest_name:
                try:
                    return self.storage.url(manifest_name)
                except Exception as e:
                    logger.warning(f"Could not get DASH manifest URL: {e}")
        return None

    def save(self, name: str, content: File, save: bool = True):
        """Сохраняет файл и запускает DASH обработку"""

        # Базовая обработка
        super().save(name, content, save)

        field: DASHVideoField = self.field
        inst = self.instance

        if not getattr(field, "dash_on_save", True):
            return

        # Отложенная обработка если нет PK
        if getattr(inst, "pk", None) is None:
            setattr(inst, f"__dash_pending__{field.attname}", True)
            return

        field._trigger_dash(inst)


class DASHVideoField(VideoField):
    """
    Поле для автоматического создания DASH (Dynamic Adaptive Streaming) видео.

    DASH - современный стандарт адаптивного стриминга, альтернатива HLS.
    Лучше поддерживается современными браузерами и CDN.

    Создает:
    - Несколько представлений разного качества
    - MPD манифест с описанием всех качеств
    - M4S сегменты для каждого качества
    - Более точная адаптация к сетевым условиям

    Пример использования:
        video = DASHVideoField(
            upload_to="videos/",
            dash_manifest_field="dash_manifest",  # поле для manifest.mpd
            ladder=[
                {"height": 480, "v_bitrate": 1200, "a_bitrate": 96},
                {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
                {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
            ],
            segment_duration=4,  # DASH обычно использует более короткие сегменты
        )
        dash_manifest = models.CharField(max_length=500, null=True, blank=True)
    """

    attr_class = DASHVideoFieldFile

    def __init__(
        self,
        *args,
        dash_manifest_field: str | None = None,
        dash_base_subdir: str | None = None,
        ladder: list[dict] | None = None,
        segment_duration: int | None = None,
        dash_on_save: bool = True,
        **kwargs: Any,
    ):

        super().__init__(*args, **kwargs)

        self.dash_manifest_field = dash_manifest_field
        self.dash_base_subdir = dash_base_subdir or defaults.DASH_SUBDIR
        self.ladder = ladder or defaults.DEFAULT_LADDER.copy()
        self.segment_duration = segment_duration or defaults.DASH_SEGMENT_DURATION
        self.dash_on_save = dash_on_save

    def contribute_to_class(self, cls, name, **kwargs):
        """Интеграция в модель с post_save обработчиком"""

        super().contribute_to_class(cls, name, **kwargs)
        self.attname = name

        from django.db.models.signals import post_save

        def _dash_post_save_handler(sender, instance, created, **kw):
            pending_attr = f"__dash_pending__{name}"

            if getattr(instance, pending_attr, False):
                setattr(instance, pending_attr, False)
                try:
                    self._trigger_dash(instance)
                except Exception as e:
                    logger.error(f"DASH processing failed in post_save: {e}")

        post_save.connect(_dash_post_save_handler, sender=cls, weak=False)

    def _trigger_dash(self, instance):
        """Запускает DASH транскодинг"""

        try:
            from .tasks import build_dash_for_field, build_dash_for_field_sync

            if hasattr(build_dash_for_field, "delay"):
                logger.info(
                    f"Starting DASH transcoding (async) for {instance._meta.label}:{instance.pk}"
                )
                task = build_dash_for_field.delay(instance._meta.label, instance.pk, self.attname)

                if hasattr(instance, "dash_task_id"):
                    setattr(instance, "dash_task_id", task.id)
            else:
                logger.info(
                    f"Starting DASH transcoding (sync) for {instance._meta.label}:{instance.pk}"
                )
                build_dash_for_field_sync(instance._meta.label, instance.pk, self.attname)

        except ImportError:
            from .tasks import build_dash_for_field_sync

            build_dash_for_field_sync(instance._meta.label, instance.pk, self.attname)

    def deconstruct(self):
        """Декомпозиция для migrations"""
        name, path, args, kwargs = super().deconstruct()

        if self.dash_manifest_field is not None:
            kwargs["dash_manifest_field"] = self.dash_manifest_field
        if self.dash_base_subdir != defaults.DASH_SUBDIR:
            kwargs["dash_base_subdir"] = self.dash_base_subdir
        if self.ladder != defaults.DEFAULT_LADDER:
            kwargs["ladder"] = self.ladder
        if self.segment_duration != defaults.DASH_SEGMENT_DURATION:
            kwargs["segment_duration"] = self.segment_duration
        if not self.dash_on_save:
            kwargs["dash_on_save"] = self.dash_on_save

        return name, path, args, kwargs


# ==============================================================================
# ADAPTIVE VIDEO FIELD - HLS + DASH COMBO
# ==============================================================================


class AdaptiveVideoFieldFile(VideoFieldFile):
    """FieldFile для комбинированного HLS+DASH поля"""

    def master_url(self) -> Optional[str]:
        """URL HLS master плейлиста"""
        field: AdaptiveVideoField = self.field
        inst = self.instance

        playlist_field = getattr(field, "hls_playlist_field", None)
        if playlist_field:
            playlist_name = getattr(inst, playlist_field, None)
            if playlist_name:
                try:
                    return self.storage.url(playlist_name)
                except Exception as e:
                    logger.warning(f"Could not get HLS URL: {e}")
        return None

    def dash_url(self) -> Optional[str]:
        """URL DASH манифеста"""
        field: AdaptiveVideoField = self.field
        inst = self.instance

        manifest_field = getattr(field, "dash_manifest_field", None)
        if manifest_field:
            manifest_name = getattr(inst, manifest_field, None)
            if manifest_name:
                try:
                    return self.storage.url(manifest_name)
                except Exception as e:
                    logger.warning(f"Could not get DASH URL: {e}")
        return None

    def save(self, name: str, content: File, save: bool = True):
        """Сохраняет файл и запускает комбинированную обработку"""

        # Базовая обработка
        super().save(name, content, save)

        field: AdaptiveVideoField = self.field
        inst = self.instance

        if not getattr(field, "adaptive_on_save", True):
            return

        # Отложенная обработка
        if getattr(inst, "pk", None) is None:
            setattr(inst, f"__adaptive_pending__{field.attname}", True)
            return

        field._trigger_adaptive(inst)


class AdaptiveVideoField(VideoField):
    """
    Универсальное поле для создания HLS + DASH одновременно.

    Создает оба формата из одного исходного файла для максимальной совместимости:
    - HLS для Safari и iOS устройств
    - DASH для современных браузеров и Android

    Удобно для проектов где нужна поддержка всех устройств без компромиссов.

    Пример использования:
        video = AdaptiveVideoField(
            upload_to="videos/",
            hls_playlist_field="hls_master",      # поле для master.m3u8
            dash_manifest_field="dash_manifest",  # поле для manifest.mpd
            ladder=[
                {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
                {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
                {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
            ]
        )
        hls_master = models.CharField(max_length=500, null=True, blank=True)
        dash_manifest = models.CharField(max_length=500, null=True, blank=True)
    """

    attr_class = AdaptiveVideoFieldFile

    def __init__(
        self,
        *args,
        hls_playlist_field: str | None = None,
        dash_manifest_field: str | None = None,
        adaptive_base_subdir: str | None = None,
        ladder: list[dict] | None = None,
        segment_duration: int | None = None,
        adaptive_on_save: bool = True,
        **kwargs: Any,
    ):

        super().__init__(*args, **kwargs)

        self.hls_playlist_field = hls_playlist_field
        self.dash_manifest_field = dash_manifest_field
        self.adaptive_base_subdir = adaptive_base_subdir or defaults.ADAPTIVE_SUBDIR
        self.ladder = ladder or defaults.DEFAULT_LADDER.copy()
        self.segment_duration = segment_duration or defaults.SEGMENT_DURATION
        self.adaptive_on_save = adaptive_on_save

    def contribute_to_class(self, cls, name, **kwargs):
        """Интеграция в модель"""

        super().contribute_to_class(cls, name, **kwargs)
        self.attname = name

        from django.db.models.signals import post_save

        def _adaptive_post_save_handler(sender, instance, created, **kw):
            pending_attr = f"__adaptive_pending__{name}"

            if getattr(instance, pending_attr, False):
                setattr(instance, pending_attr, False)
                try:
                    self._trigger_adaptive(instance)
                except Exception as e:
                    logger.error(f"Adaptive processing failed in post_save: {e}")

        post_save.connect(_adaptive_post_save_handler, sender=cls, weak=False)

    def _trigger_adaptive(self, instance):
        """Запускает комбинированный HLS+DASH транскодинг"""

        try:
            from .tasks import build_adaptive_for_field, build_adaptive_for_field_sync

            if hasattr(build_adaptive_for_field, "delay"):
                logger.info(
                    f"Starting adaptive transcoding (async) for {instance._meta.label}:{instance.pk}"
                )
                task = build_adaptive_for_field.delay(
                    instance._meta.label, instance.pk, self.attname
                )

                if hasattr(instance, "adaptive_task_id"):
                    setattr(instance, "adaptive_task_id", task.id)
            else:
                logger.info(
                    f"Starting adaptive transcoding (sync) for {instance._meta.label}:{instance.pk}"
                )
                build_adaptive_for_field_sync(instance._meta.label, instance.pk, self.attname)

        except ImportError:
            from .tasks import build_adaptive_for_field_sync

            build_adaptive_for_field_sync(instance._meta.label, instance.pk, self.attname)

    def deconstruct(self):
        """Декомпозиция для migrations"""
        name, path, args, kwargs = super().deconstruct()

        if self.hls_playlist_field is not None:
            kwargs["hls_playlist_field"] = self.hls_playlist_field
        if self.dash_manifest_field is not None:
            kwargs["dash_manifest_field"] = self.dash_manifest_field
        if self.adaptive_base_subdir != defaults.ADAPTIVE_SUBDIR:
            kwargs["adaptive_base_subdir"] = self.adaptive_base_subdir
        if self.ladder != defaults.DEFAULT_LADDER:
            kwargs["ladder"] = self.ladder
        if self.segment_duration != defaults.SEGMENT_DURATION:
            kwargs["segment_duration"] = self.segment_duration
        if not self.adaptive_on_save:
            kwargs["adaptive_on_save"] = self.adaptive_on_save

        return name, path, args, kwargs


# ==============================================================================
# УТИЛИТЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================


def validate_ladder(ladder: list[dict]) -> bool:
    """
    Валидирует лестницу качеств видео.

    Args:
        ladder: Список словарей с параметрами качества

    Returns:
        bool: True если лестница валидна

    Raises:
        ValueError: При некорректных параметрах
    """

    if not ladder or not isinstance(ladder, list):
        raise ValueError("Ladder must be a non-empty list")

    for i, rung in enumerate(ladder):
        if not isinstance(rung, dict):
            raise ValueError(f"Ladder rung {i} must be a dictionary")

        # Проверяем обязательные поля
        required_fields = ["height", "v_bitrate", "a_bitrate"]
        for field in required_fields:
            if field not in rung:
                raise ValueError(f"Ladder rung {i} missing required field: {field}")

            try:
                value = int(rung[field])
                if value < 0:
                    raise ValueError(f"Ladder rung {i} field {field} cannot be negative: {value}")
            except (ValueError, TypeError):
                raise ValueError(f"Ladder rung {i} field {field} must be a positive integer")

        # Проверяем разумные пределы
        height = int(rung["height"])
        v_bitrate = int(rung["v_bitrate"])
        a_bitrate = int(rung["a_bitrate"])

        if not (144 <= height <= 8192):
            raise ValueError(f"Height {height} out of range (144-8192)")

        if not (100 <= v_bitrate <= 100000):  # 100kbps - 100Mbps
            raise ValueError(f"Video bitrate {v_bitrate} out of range (100-100000)")

        if not (0 <= a_bitrate <= 512):  # 0-512kbps
            raise ValueError(f"Audio bitrate {a_bitrate} out of range (0-512)")

    return True


def get_optimal_ladder_for_resolution(source_width: int, source_height: int) -> list[dict]:
    """
    Генерирует оптимальную лестницу качеств на основе разрешения источника.

    Args:
        source_width: Ширина исходного видео
        source_height: Высота исходного видео

    Returns:
        list[dict]: Оптимизированная лестница качеств
    """

    # Базовые качества
    base_ladder = [
        {"height": 240, "v_bitrate": 300, "a_bitrate": 64},
        {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
        {"height": 480, "v_bitrate": 1200, "a_bitrate": 96},
        {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
        {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
        {"height": 1440, "v_bitrate": 8000, "a_bitrate": 192},
        {"height": 2160, "v_bitrate": 15000, "a_bitrate": 256},  # 4K
    ]

    # Фильтруем качества которые не превышают источник
    filtered_ladder = []

    for rung in base_ladder:
        if rung["height"] <= source_height * 1.1:  # +10% запас
            filtered_ladder.append(rung.copy())
        else:
            break

    # Если исходное видео очень маленькое - добавляем хотя бы одно качество
    if not filtered_ladder:
        min_rung = min(base_ladder, key=lambda x: x["height"])
        filtered_ladder.append(min_rung)

    # Добавляем исходное разрешение как максимальное качество
    if filtered_ladder[-1]["height"] < source_height:
        # Оцениваем битрейт для исходного разрешения
        pixels_ratio = (source_width * source_height) / (1920 * 1080)  # относительно 1080p
        estimated_bitrate = int(4500 * pixels_ratio)  # базируясь на 1080p = 4500kbps
        estimated_bitrate = max(500, min(estimated_bitrate, 50000))  # 500kbps - 50Mbps

        filtered_ladder.append(
            {
                "height": source_height,
                "v_bitrate": estimated_bitrate,
                "a_bitrate": 160 if source_height >= 720 else 128,
            }
        )

    return filtered_ladder


# ==============================================================================
# ЭКСПОРТ КЛАССОВ
# ==============================================================================

__all__ = [
    "VideoField",
    "VideoFieldFile",
    "HLSVideoField",
    "HLSVideoFieldFile",
    "DASHVideoField",
    "DASHVideoFieldFile",
    "AdaptiveVideoField",
    "AdaptiveVideoFieldFile",
    "validate_ladder",
    "get_optimal_ladder_for_resolution",
]
