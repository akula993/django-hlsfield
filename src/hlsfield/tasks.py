"""
🎬 Celery задачи для django-hlsfield

Этот модуль содержит все Celery задачи для асинхронной обработки видео:
- HLS/DASH транскодинг
- Прогрессивная обработка
- Оптимизация и аналитика
- Batch операции

Автор: akula993
Лицензия: MIT
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Any

from django.apps import apps
from django.core.cache import cache
from django.db import transaction, models
from django.utils import timezone

from . import utils, defaults
from .exceptions import TranscodingError, StorageError

try:
    from celery import shared_task, group, chain
    from celery.exceptions import Retry

    CELERY_AVAILABLE = True
except ImportError:
    # Заглушки для работы без Celery
    def shared_task(*args, **kwargs):
        def decorator(func):
            func.delay = lambda *args, **kwargs: func(*args, **kwargs)
            return func

        return decorator

    CELERY_AVAILABLE = False

logger = logging.getLogger(__name__)


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================


def _resolve_field(instance, field_name: str):
    """Получает информацию о поле и связанных объектах"""
    field = instance._meta.get_field(field_name)
    file = getattr(instance, field_name)
    storage = file.storage
    name = file.name
    return field, file, storage, name


def _get_base_key(name: str, subdir: str) -> str:
    """Генерирует базовый ключ для выходных файлов"""
    base, _ext = os.path.splitext(name)
    result = f"{base}/{subdir}/"
    
    # Add debugging to track path generation
    logger.debug(f"Generated base_key: '{result}' from name='{name}', subdir='{subdir}'")
    return result


def _update_instance_status(instance, status: str, **extra_fields):
    """Безопасно обновляет статус обработки"""
    try:
        update_fields = []

        # Статус обработки
        if hasattr(instance, "processing_status"):
            setattr(instance, "processing_status", status)
            update_fields.append("processing_status")

        # Дополнительные поля
        for field_name, value in extra_fields.items():
            if hasattr(instance, field_name):
                setattr(instance, field_name, value)
                update_fields.append(field_name)

        if update_fields:
            with transaction.atomic():
                instance.save(update_fields=update_fields)

    except Exception as e:
        logger.warning(f"Could not update instance status: {e}")


def _handle_task_error(instance, error: Exception, task_name: str):
    """Обрабатывает ошибки задач"""
    error_msg = f"{task_name} failed: {str(error)[:100]}"
    logger.error(f"Task {task_name} failed for {instance}: {error}")

    _update_instance_status(instance, f"error_{task_name}", error_message=error_msg)

    # Отправляем уведомление если настроено
    try:
        from django.core.mail import mail_admins

        mail_admins(
            f"Video processing error: {task_name}",
            f"Error processing {instance}: {error}",
            fail_silently=True,
        )
    except:
        pass


# ==============================================================================
# ОСНОВНЫЕ ЗАДАЧИ ТРАНСКОДИНГА
# ==============================================================================


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def build_hls_for_field(self, model_label: str, pk: int | str, field_name: str):
    """Асинхронная задача создания HLS стрима"""
    try:
        return build_hls_for_field_sync(model_label, pk, field_name)
    except Exception as exc:
        logger.error(f"HLS task failed (attempt {self.request.retries + 1}): {exc}")

        # Retry на временные ошибки
        if self.request.retries < self.max_retries:
            if isinstance(exc, (StorageError, TranscodingError)):
                raise self.retry(countdown=60 * (self.request.retries + 1))

        # Финальная ошибка
        Model = apps.get_model(model_label)
        instance = Model.objects.get(pk=pk)
        _handle_task_error(instance, exc, "HLS")
        raise


def build_hls_for_field_sync(model_label: str, pk: int | str, field_name: str):
    """Синхронная версия создания HLS"""
    logger.info(f"Starting HLS transcoding for {model_label}:{pk}.{field_name}")

    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)

    _update_instance_status(instance, "transcoding_hls")

    start_time = time.time()

    try:
        with utils.tempdir(prefix=f"hls_{pk}_") as td:
            # Загружаем исходник локально
            logger.debug("Pulling video to local storage...")
            local_input = utils.pull_to_local(storage, name, td)

            # Создаем HLS структуру
            local_hls_root = td / "hls_out"
            local_hls_root.mkdir(parents=True, exist_ok=True)

            # Получаем параметры обработки
            ladder = getattr(field, "ladder", defaults.DEFAULT_LADDER)
            segment_duration = getattr(field, "segment_duration", defaults.SEGMENT_DURATION)

            logger.info(f"Transcoding {len(ladder)} HLS variants, {segment_duration}s segments")

            # Выполняем транскодинг
            master = utils.transcode_hls_variants(
                input_path=local_input,
                out_dir=local_hls_root,
                ladder=ladder,
                segment_duration=segment_duration,
            )

            # Загружаем результат в storage
            base_key = _get_base_key(name, getattr(field, "hls_base_subdir", defaults.HLS_SUBDIR))
            utils.save_tree_to_storage(local_hls_root, storage, base_key)

            master_key = base_key + master.name

        # Обновляем модель
        playlist_field = getattr(field, "hls_playlist_field", None)
        update_fields = {}

        if playlist_field:
            setattr(instance, playlist_field, master_key)
            update_fields[playlist_field] = master_key

        if hasattr(instance, "hls_built_at"):
            built_at = timezone.now()
            setattr(instance, "hls_built_at", built_at)
            update_fields["hls_built_at"] = built_at

        elapsed = time.time() - start_time
        logger.info(f"HLS transcoding completed in {elapsed:.1f}s")

        _update_instance_status(
            instance, "hls_ready", transcoding_time=int(elapsed), **update_fields
        )

        return {
            "status": "success",
            "master_playlist": master_key,
            "transcoding_time": elapsed,
            "variants": len(ladder),
        }

    except Exception as e:
        _handle_task_error(instance, e, "HLS")
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def build_dash_for_field(self, model_label: str, pk: int | str, field_name: str):
    """Асинхронная задача создания DASH стрима"""
    try:
        return build_dash_for_field_sync(model_label, pk, field_name)
    except Exception as exc:
        logger.error(f"DASH task failed (attempt {self.request.retries + 1}): {exc}")

        if self.request.retries < self.max_retries:
            if isinstance(exc, (StorageError, TranscodingError)):
                raise self.retry(countdown=60 * (self.request.retries + 1))

        Model = apps.get_model(model_label)
        instance = Model.objects.get(pk=pk)
        _handle_task_error(instance, exc, "DASH")
        raise


def build_dash_for_field_sync(model_label: str, pk: int | str, field_name: str):
    """Синхронная версия создания DASH"""
    logger.info(f"Starting DASH transcoding for {model_label}:{pk}.{field_name}")

    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)

    _update_instance_status(instance, "transcoding_dash")

    start_time = time.time()

    try:
        with utils.tempdir(prefix=f"dash_{pk}_") as td:
            local_input = utils.pull_to_local(storage, name, td)
            local_dash_root = td / "dash_out"
            local_dash_root.mkdir(parents=True, exist_ok=True)

            ladder = getattr(field, "ladder", defaults.DEFAULT_LADDER)
            segment_duration = getattr(field, "segment_duration", defaults.DASH_SEGMENT_DURATION)

            logger.info(f"Transcoding {len(ladder)} DASH representations")

            manifest = utils.transcode_dash_variants(
                input_path=local_input,
                out_dir=local_dash_root,
                ladder=ladder,
                segment_duration=segment_duration,
            )

            base_key = _get_base_key(name, getattr(field, "dash_base_subdir", defaults.DASH_SUBDIR))
            utils.save_tree_to_storage(local_dash_root, storage, base_key)

            manifest_key = base_key + manifest.name

        # Обновляем модель
        manifest_field = getattr(field, "dash_manifest_field", None)
        update_fields = {}

        if manifest_field:
            setattr(instance, manifest_field, manifest_key)
            update_fields[manifest_field] = manifest_key

        if hasattr(instance, "dash_built_at"):
            built_at = timezone.now()
            setattr(instance, "dash_built_at", built_at)
            update_fields["dash_built_at"] = built_at

        elapsed = time.time() - start_time
        logger.info(f"DASH transcoding completed in {elapsed:.1f}s")

        _update_instance_status(
            instance, "dash_ready", transcoding_time=int(elapsed), **update_fields
        )

        return {
            "status": "success",
            "manifest": manifest_key,
            "transcoding_time": elapsed,
            "representations": len(ladder),
        }

    except Exception as e:
        _handle_task_error(instance, e, "DASH")
        raise


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def build_adaptive_for_field(self, model_label: str, pk: int | str, field_name: str):
    """Асинхронная задача создания HLS + DASH"""
    try:
        return build_adaptive_for_field_sync(model_label, pk, field_name)
    except Exception as exc:
        logger.error(f"Adaptive task failed (attempt {self.request.retries + 1}): {exc}")

        if self.request.retries < self.max_retries:
            if isinstance(exc, (StorageError, TranscodingError)):
                raise self.retry(countdown=120 * (self.request.retries + 1))

        Model = apps.get_model(model_label)
        instance = Model.objects.get(pk=pk)
        _handle_task_error(instance, exc, "Adaptive")
        raise


def build_adaptive_for_field_sync(model_label: str, pk: int | str, field_name: str):
    """Синхронная версия создания HLS + DASH"""
    logger.info(f"Starting adaptive transcoding for {model_label}:{pk}.{field_name}")

    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)

    _update_instance_status(instance, "transcoding_adaptive")

    start_time = time.time()

    try:
        with utils.tempdir(prefix=f"adaptive_{pk}_") as td:
            local_input = utils.pull_to_local(storage, name, td)
            local_adaptive_root = td / "adaptive_out"
            local_adaptive_root.mkdir(parents=True, exist_ok=True)

            ladder = getattr(field, "ladder", defaults.DEFAULT_LADDER)
            segment_duration = getattr(field, "segment_duration", defaults.SEGMENT_DURATION)

            logger.info(f"Creating HLS + DASH with {len(ladder)} qualities")

            results = utils.transcode_adaptive_variants(
                input_path=local_input,
                out_dir=local_adaptive_root,
                ladder=ladder,
                segment_duration=segment_duration,
            )

            base_key = _get_base_key(name, getattr(field, "adaptive_base_subdir", defaults.ADAPTIVE_SUBDIR))
            utils.save_tree_to_storage(local_adaptive_root, storage, base_key)

            hls_master_key = base_key + f"hls/{results['hls_master'].name}"
            dash_manifest_key = base_key + f"dash/{results['dash_manifest'].name}"

        # Обновляем модель
        hls_field = getattr(field, "hls_playlist_field", None)
        dash_field = getattr(field, "dash_manifest_field", None)
        update_fields = {}

        if hls_field:
            setattr(instance, hls_field, hls_master_key)
            update_fields[hls_field] = hls_master_key

        if dash_field:
            setattr(instance, dash_field, dash_manifest_key)
            update_fields[dash_field] = dash_manifest_key

        if hasattr(instance, "adaptive_built_at"):
            built_at = timezone.now()
            setattr(instance, "adaptive_built_at", built_at)
            update_fields["adaptive_built_at"] = built_at

        elapsed = time.time() - start_time
        logger.info(f"Adaptive transcoding completed in {elapsed:.1f}s")

        _update_instance_status(
            instance, "adaptive_ready", transcoding_time=int(elapsed), **update_fields
        )

        return {
            "status": "success",
            "hls_master": hls_master_key,
            "dash_manifest": dash_manifest_key,
            "transcoding_time": elapsed,
            "variants": len(ladder),
        }

    except Exception as e:
        _handle_task_error(instance, e, "Adaptive")
        raise


# ==============================================================================
# ПРОГРЕССИВНЫЕ ЗАДАЧИ
# ==============================================================================


@shared_task
def build_progressive_for_field(
    model_label: str, pk: int | str, field_name: str, options: Dict[str, Any]
):
    """Прогрессивное создание адаптивного видео"""
    return build_progressive_for_field_sync(model_label, pk, field_name, options)


def build_progressive_for_field_sync(
    model_label: str, pk: int | str, field_name: str, options: Dict[str, Any]
):
    """Синхронная версия прогрессивной обработки"""
    logger.info(f"Starting progressive transcoding for {model_label}:{pk}")

    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)

    preview_first = options.get("preview_first", True)
    progressive_delay = options.get("progressive_delay", 60)
    priority_heights = options.get("priority_heights", [360, 720])

    ladder = getattr(field, "ladder", defaults.DEFAULT_LADDER)

    # Сортируем лестницу: приоритетные сначала
    priority_ladder = [r for r in ladder if r["height"] in priority_heights]
    regular_ladder = [r for r in ladder if r["height"] not in priority_heights]

    ordered_ladder = sorted(priority_ladder, key=lambda x: x["height"]) + sorted(
        regular_ladder, key=lambda x: x["height"]
    )

    try:
        with utils.tempdir(prefix=f"progressive_{pk}_") as td:
            local_input = utils.pull_to_local(storage, name, td)

            if preview_first and ordered_ladder:
                # Создаем превью качество
                preview_quality = ordered_ladder[0]
                logger.info(f"Creating preview quality: {preview_quality['height']}p")

                _build_single_quality(
                    local_input, storage, name, [preview_quality], field, instance, is_preview=True
                )

                remaining_ladder = ordered_ladder[1:]
            else:
                remaining_ladder = ordered_ladder

            # Создаем остальные качества с задержками
            for i, quality in enumerate(remaining_ladder):
                if i > 0 and progressive_delay > 0:
                    logger.info(f"Waiting {progressive_delay}s before next quality...")
                    time.sleep(progressive_delay)

                current_ladder = ordered_ladder[
                    : len(ordered_ladder) - len(remaining_ladder) + i + 1
                ]
                logger.info(f"Adding quality: {quality['height']}p ({len(current_ladder)} total)")

                _build_single_quality(
                    local_input, storage, name, current_ladder, field, instance, is_preview=False
                )

        logger.info("Progressive transcoding completed")
        return {"status": "success", "total_qualities": len(ordered_ladder)}

    except Exception as e:
        _handle_task_error(instance, e, "Progressive")
        raise


def _build_single_quality(
    local_input: Path,
    storage,
    name: str,
    current_ladder: List[Dict],
    field,
    instance,
    is_preview: bool = False,
):
    """Создает текущую лестницу качеств и обновляет манифесты"""

    with utils.tempdir(prefix=f"quality_{len(current_ladder)}_") as td:
        adaptive_root = td / "adaptive_out"
        adaptive_root.mkdir(parents=True, exist_ok=True)

        segment_duration = getattr(field, "segment_duration", defaults.SEGMENT_DURATION)

        results = utils.transcode_adaptive_variants(
            input_path=local_input,
            out_dir=adaptive_root,
            ladder=current_ladder,
            segment_duration=segment_duration,
        )

        # Загружаем в storage
        base_key = _get_base_key(name, getattr(field, "adaptive_base_subdir", defaults.ADAPTIVE_SUBDIR))
        utils.save_tree_to_storage(adaptive_root, storage, base_key)

        hls_master_key = base_key + f"hls/{results['hls_master'].name}"
        dash_manifest_key = base_key + f"dash/{results['dash_manifest'].name}"

        # Обновляем модель
        hls_field = getattr(field, "hls_playlist_field", None)
        dash_field = getattr(field, "dash_manifest_field", None)
        update_fields = {}

        if hls_field:
            setattr(instance, hls_field, hls_master_key)
            update_fields[hls_field] = hls_master_key

        if dash_field:
            setattr(instance, dash_field, dash_manifest_key)
            update_fields[dash_field] = dash_manifest_key

        # Статус
        if is_preview:
            status = "preview_ready"
        else:
            status = f"ready_{len(current_ladder)}_qualities"

        _update_instance_status(
            instance, status, qualities_ready=len(current_ladder), **update_fields
        )


# ==============================================================================
# BATCH ОПЕРАЦИИ
# ==============================================================================


@shared_task
def batch_optimize_videos(
    model_label: str, pks: List[int], field_name: str, target_qualities: int = 3
):
    """Массовая оптимизация видео"""
    logger.info(f"Starting batch optimization for {len(pks)} videos")

    results = []
    Model = apps.get_model(model_label)

    for pk in pks:
        try:
            instance = Model.objects.get(pk=pk)

            # Запускаем оптимизацию
            result = optimize_existing_video.delay(model_label, pk, field_name, target_qualities)

            results.append({"pk": pk, "status": "queued", "task_id": result.id})

        except Exception as e:
            logger.error(f"Failed to queue optimization for {pk}: {e}")
            results.append({"pk": pk, "status": "error", "message": str(e)})

    return {
        "total_processed": len(pks),
        "successful": len([r for r in results if r["status"] == "queued"]),
        "failed": len([r for r in results if r["status"] == "error"]),
        "results": results,
    }


@shared_task
def optimize_existing_video(
    model_label: str,
    pk: int | str,
    field_name: str,
    target_qualities: int = 5,
    max_file_size_mb: int = None,
):
    """Оптимизирует существующее видео"""
    logger.info(f"Optimizing video {model_label}:{pk}")

    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)

    try:
        with utils.tempdir(prefix=f"optimize_{pk}_") as td:
            local_input = utils.pull_to_local(storage, name, td)

            # Анализируем исходное видео
            analysis = utils.analyze_video_complexity(local_input)

            # Генерируем оптимальную лестницу
            from .fields import get_optimal_ladder_for_resolution

            info = utils.ffprobe_streams(local_input)
            video_stream, _ = utils.pick_video_audio_streams(info)

            if video_stream:
                width = int(video_stream.get("width", 1920))
                height = int(video_stream.get("height", 1080))
                new_ladder = get_optimal_ladder_for_resolution(width, height)

                # Ограничиваем количество качеств
                if len(new_ladder) > target_qualities:
                    step = len(new_ladder) // target_qualities
                    new_ladder = new_ladder[::step][:target_qualities]

                # Корректируем под ограничения размера
                if max_file_size_mb:
                    new_ladder = _adjust_ladder_for_size_limit(
                        new_ladder, analysis, max_file_size_mb
                    )

                # Создаем новые варианты
                _build_single_quality(local_input, storage, name, new_ladder, field, instance)

                logger.info(f"Video optimized with {len(new_ladder)} qualities")
                return {
                    "status": "success",
                    "optimized_qualities": len(new_ladder),
                    "estimated_size_reduction": "N/A",
                }

    except Exception as e:
        _handle_task_error(instance, e, "Optimization")
        raise


def _adjust_ladder_for_size_limit(
    ladder: List[Dict], analysis: Dict, max_size_mb: int
) -> List[Dict]:
    """Корректирует битрейты под ограничение размера"""
    duration = analysis.get("duration", 0)
    if duration <= 0:
        return ladder

    # Рассчитываем текущий размер
    total_size = 0
    for quality in ladder:
        total_bitrate = (quality["v_bitrate"] + quality["a_bitrate"]) * 1000
        size_mb = (total_bitrate * duration) / (8 * 1024 * 1024)
        total_size += size_mb

    if total_size <= max_size_mb:
        return ladder

    # Пропорционально уменьшаем битрейты
    reduction_factor = max_size_mb / total_size

    adjusted_ladder = []
    for quality in ladder:
        adjusted = quality.copy()
        adjusted["v_bitrate"] = max(200, int(quality["v_bitrate"] * reduction_factor))
        adjusted["a_bitrate"] = max(64, int(quality["a_bitrate"] * reduction_factor))
        adjusted_ladder.append(adjusted)

    return adjusted_ladder


@shared_task
def health_check_videos(model_label: str, field_name: str):
    """Проверяет целостность видео файлов"""
    logger.info(f"Running health check for {model_label}.{field_name}")

    Model = apps.get_model(model_label)
    issues = []
    checked_count = 0

    for instance in Model.objects.all():
        checked_count += 1
        field, file, storage, name = _resolve_field(instance, field_name)

        issue = {"pk": instance.pk, "problems": []}

        # Проверяем основной файл
        try:
            if not storage.exists(name):
                issue["problems"].append("Original file missing")
        except Exception as e:
            issue["problems"].append(f"Cannot check original file: {e}")

        # Проверяем манифесты
        hls_field = getattr(field, "hls_playlist_field", None)
        if hls_field:
            hls_path = getattr(instance, hls_field, None)
            if hls_path:
                try:
                    if not storage.exists(hls_path):
                        issue["problems"].append("HLS manifest missing")
                except Exception as e:
                    issue["problems"].append(f"Cannot check HLS manifest: {e}")

        dash_field = getattr(field, "dash_manifest_field", None)
        if dash_field:
            dash_path = getattr(instance, dash_field, None)
            if dash_path:
                try:
                    if not storage.exists(dash_path):
                        issue["problems"].append("DASH manifest missing")
                except Exception as e:
                    issue["problems"].append(f"Cannot check DASH manifest: {e}")

        if issue["problems"]:
            issues.append(issue)

    logger.info(f"Health check completed: {len(issues)} issues found")

    return {
        "total_checked": checked_count,
        "issues_found": len(issues),
        "issues": issues,
        "healthy_videos": checked_count - len(issues),
    }


# ==============================================================================
# УТИЛИТЫ И МОНИТОРИНГ
# ==============================================================================


@shared_task
def cleanup_old_temp_files():
    """Очищает старые временные файлы"""
    import glob
    import time

    temp_patterns = [
        "/tmp/hlsfield_*",
        "/tmp/hls_*",
        "/tmp/dash_*",
        "/tmp/adaptive_*",
    ]

    cleaned = 0
    errors = 0
    cutoff_time = time.time() - 86400  # 24 часа

    for pattern in temp_patterns:
        try:
            for path in glob.glob(pattern):
                path_obj = Path(path)
                if path_obj.stat().st_mtime < cutoff_time:
                    if path_obj.is_dir():
                        import shutil

                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        path_obj.unlink(missing_ok=True)
                    cleaned += 1
        except Exception as e:
            logger.warning(f"Error cleaning temp files {pattern}: {e}")
            errors += 1

    logger.info(f"Cleaned {cleaned} old temp files, {errors} errors")
    return {"cleaned": cleaned, "errors": errors}


@shared_task
def generate_video_analytics_report(days: int = 7):
    """Генерирует отчет аналитики видео"""
    from django.utils import timezone
    from datetime import timedelta

    try:
        from .views import VideoEvent

        start_date = timezone.now() - timedelta(days=days)
        events = VideoEvent.objects.filter(timestamp__gte=start_date)

        report = {
            "period": f"Last {days} days",
            "total_events": events.count(),
            "unique_videos": events.values("video_id").distinct().count(),
            "unique_sessions": events.values("session_id").distinct().count(),
            "play_events": events.filter(event_type="play").count(),
            "completion_events": events.filter(event_type="ended").count(),
            "error_events": events.filter(event_type="error").count(),
            "buffer_events": events.filter(event_type="buffer_start").count(),
        }

        # Топ видео по просмотрам
        top_videos = (
            events.filter(event_type="play")
            .values("video_id")
            .annotate(views=models.Count("id"))
            .order_by("-views")[:10]
        )
        report["top_videos"] = list(top_videos)

        # Распределение по качеству
        quality_dist = (
            events.exclude(quality__isnull=True)
            .values("quality")
            .annotate(count=models.Count("id"))
            .order_by("-count")
        )
        report["quality_distribution"] = list(quality_dist)

        # Сохраняем в кеш
        cache.set(f"video_analytics_report_{days}d", report, 3600)  # 1 час

        logger.info(f"Generated analytics report for {days} days")
        return report

    except Exception as e:
        logger.error(f"Failed to generate analytics report: {e}")
        return {"error": str(e)}


@shared_task
def monitor_transcoding_performance():
    """Мониторинг производительности транскодинга"""

    # Получаем статистику из кеша или базы
    stats = {
        "average_hls_time": 0,
        "average_dash_time": 0,
        "success_rate": 0,
        "failed_tasks_24h": 0,
        "queue_length": 0,
    }

    try:
        # Анализируем последние задачи
        if CELERY_AVAILABLE:
            from celery import current_app

            inspect = current_app.control.inspect()

            # Длина очереди
            active_tasks = inspect.active()
            if active_tasks:
                total_active = sum(len(tasks) for tasks in active_tasks.values())
                stats["queue_length"] = total_active

        # Статистика ошибок из логов или базы
        # Здесь можно добавить анализ логов или специальной таблицы

        cache.set("transcoding_performance_stats", stats, 300)  # 5 минут
        return stats

    except Exception as e:
        logger.error(f"Performance monitoring failed: {e}")
        return {"error": str(e)}


# ==============================================================================
# ЗАДАЧИ ОБСЛУЖИВАНИЯ
# ==============================================================================


@shared_task
def regenerate_missing_previews(model_label: str, field_name: str):
    """Восстанавливает отсутствующие превью"""
    logger.info(f"Regenerating missing previews for {model_label}.{field_name}")

    Model = apps.get_model(model_label)
    regenerated = 0
    errors = 0

    for instance in Model.objects.all():
        try:
            field, file, storage, name = _resolve_field(instance, field_name)

            # Проверяем есть ли превью
            has_preview = False

            # Проверяем поле модели
            preview_field = getattr(field, "preview_field", None)
            if preview_field:
                preview_path = getattr(instance, preview_field, None)
                if preview_path and storage.exists(preview_path):
                    has_preview = True

            # Проверяем sidecar файл
            if not has_preview:
                try:
                    preview_url = file.preview_url()
                    if preview_url:
                        has_preview = True
                except:
                    pass

            if not has_preview:
                # Создаем превью
                with utils.tempdir(prefix=f"preview_{instance.pk}_") as td:
                    local_input = utils.pull_to_local(storage, name, td)
                    preview_tmp = td / "preview.jpg"

                    utils.extract_preview(
                        local_input, preview_tmp, at_sec=getattr(field, "preview_at", 3.0)
                    )

                    if preview_tmp.exists():
                        # Сохраняем превью
                        if field.sidecar_layout == "nested":
                            preview_key = f"{file._base_key()}/{field.preview_filename}"
                        else:
                            preview_key = f"{file._base_key()}_preview.jpg"

                        with preview_tmp.open("rb") as fh:
                            saved_path = storage.save(preview_key, fh)

                        # Обновляем модель
                        if preview_field:
                            setattr(instance, preview_field, saved_path)
                            instance.save(update_fields=[preview_field])

                        regenerated += 1
                        logger.info(f"Regenerated preview for {instance.pk}")

        except Exception as e:
            logger.error(f"Failed to regenerate preview for {instance.pk}: {e}")
            errors += 1

    return {"regenerated": regenerated, "errors": errors, "total_processed": regenerated + errors}


@shared_task
def update_video_statistics():
    """Обновляет статистику видео"""

    try:
        from django.db.models import Count, Avg, Sum
        from .views import VideoEvent

        # Группируем статистику по видео
        video_stats = VideoEvent.objects.values("video_id").annotate(
            total_views=Count("id", filter=models.Q(event_type="play")),
            unique_viewers=Count("session_id", distinct=True),
            avg_watch_time=Avg("current_time", filter=models.Q(event_type__in=["ended", "pause"])),
            completion_rate=Count("id", filter=models.Q(event_type="ended"))
            * 100.0
            / Count("id", filter=models.Q(event_type="play")),
        )

        updated = 0

        for stat in video_stats:
            video_id = stat["video_id"]

            # Сохраняем в кеш для быстрого доступа
            cache_key = f"video_stats_{video_id}"
            cache.set(
                cache_key,
                {
                    "total_views": stat["total_views"] or 0,
                    "unique_viewers": stat["unique_viewers"] or 0,
                    "avg_watch_time": stat["avg_watch_time"] or 0,
                    "completion_rate": stat["completion_rate"] or 0,
                },
                3600,
            )  # 1 час

            updated += 1

        logger.info(f"Updated statistics for {updated} videos")
        return {"updated": updated}

    except Exception as e:
        logger.error(f"Failed to update video statistics: {e}")
        return {"error": str(e)}


# ==============================================================================
# ЗАДАЧИ МИГРАЦИИ И ОБСЛУЖИВАНИЯ
# ==============================================================================


@shared_task
def migrate_old_video_format(model_label: str, field_name: str):
    """Мигрирует видео из старого формата в новый"""
    logger.info(f"Starting video format migration for {model_label}.{field_name}")

    Model = apps.get_model(model_label)
    migrated = 0
    errors = 0

    # Находим видео которые нужно мигрировать
    instances = Model.objects.filter(
        # Условие что есть исходное видео но нет HLS/DASH
        **{f"{field_name}__isnull": False}
    )

    hls_field_name = None
    dash_field_name = None

    # Определяем поля для HLS/DASH
    field = instances.first()._meta.get_field(field_name) if instances.exists() else None
    if field:
        hls_field_name = getattr(field, "hls_playlist_field", None)
        dash_field_name = getattr(field, "dash_manifest_field", None)

    if hls_field_name:
        instances = instances.filter(**{f"{hls_field_name}__isnull": True})

    logger.info(f"Found {instances.count()} videos to migrate")

    for instance in instances:
        try:
            # Запускаем транскодинг для миграции
            if hasattr(field, "dash_manifest_field") and hasattr(field, "hls_playlist_field"):
                # Адаптивное поле
                build_adaptive_for_field.delay(model_label, instance.pk, field_name)
            elif hls_field_name:
                # HLS поле
                build_hls_for_field.delay(model_label, instance.pk, field_name)
            elif dash_field_name:
                # DASH поле
                build_dash_for_field.delay(model_label, instance.pk, field_name)

            migrated += 1

        except Exception as e:
            logger.error(f"Failed to queue migration for {instance.pk}: {e}")
            errors += 1

    return {"queued_for_migration": migrated, "errors": errors, "total_found": migrated + errors}


@shared_task
def validate_video_integrity(model_label: str, field_name: str, repair: bool = False):
    """Валидирует целостность видео файлов и при необходимости восстанавливает"""
    logger.info(f"Validating video integrity for {model_label}.{field_name}, repair={repair}")

    Model = apps.get_model(model_label)
    results = {
        "checked": 0,
        "valid": 0,
        "corrupted": 0,
        "missing": 0,
        "repaired": 0,
        "repair_failed": 0,
    }

    for instance in Model.objects.all():
        results["checked"] += 1

        try:
            field, file, storage, name = _resolve_field(instance, field_name)

            # Проверяем существование
            if not storage.exists(name):
                results["missing"] += 1
                logger.warning(f"Missing video file for {instance.pk}: {name}")
                continue

            # Валидируем через ffprobe
            with utils.tempdir(prefix=f"validate_{instance.pk}_") as td:
                try:
                    local_file = utils.pull_to_local(storage, name, td)
                    validation = utils.validate_video_file(local_file)

                    if validation["valid"]:
                        results["valid"] += 1
                    else:
                        results["corrupted"] += 1
                        logger.warning(f"Corrupted video {instance.pk}: {validation['issues']}")

                        if repair:
                            # Пытаемся восстановить через повторный транскодинг
                            try:
                                _update_instance_status(instance, "repairing")

                                # Определяем тип поля и запускаем соответствующую задачу
                                if hasattr(field, "adaptive_base_subdir"):
                                    build_adaptive_for_field.delay(
                                        model_label, instance.pk, field_name
                                    )
                                elif hasattr(field, "hls_playlist_field"):
                                    build_hls_for_field.delay(model_label, instance.pk, field_name)
                                elif hasattr(field, "dash_manifest_field"):
                                    build_dash_for_field.delay(model_label, instance.pk, field_name)

                                results["repaired"] += 1
                                logger.info(f"Queued repair for {instance.pk}")

                            except Exception as repair_error:
                                results["repair_failed"] += 1
                                logger.error(
                                    f"Failed to queue repair for {instance.pk}: {repair_error}"
                                )

                except Exception as validation_error:
                    logger.error(f"Validation failed for {instance.pk}: {validation_error}")
                    results["corrupted"] += 1

        except Exception as e:
            logger.error(f"Error processing {instance.pk}: {e}")
            continue

    logger.info(f"Integrity check completed: {results}")
    return results


# ==============================================================================
# ЗАДАЧА ОЧИСТКИ И ОПТИМИЗАЦИИ
# ==============================================================================


@shared_task
def cleanup_orphaned_files(model_label: str, field_name: str, dry_run: bool = True):
    """Очищает файлы-сироты (без соответствующих записей в БД)"""
    logger.info(f"Cleaning orphaned files for {model_label}.{field_name}, dry_run={dry_run}")

    Model = apps.get_model(model_label)

    # Получаем все пути файлов из БД
    db_paths = set()

    for instance in Model.objects.all():
        try:
            field, file, storage, name = _resolve_field(instance, field_name)

            if name:
                db_paths.add(name)

                # Добавляем связанные файлы
                hls_field = getattr(field, "hls_playlist_field", None)
                if hls_field:
                    hls_path = getattr(instance, hls_field, None)
                    if hls_path:
                        db_paths.add(hls_path)

                dash_field = getattr(field, "dash_manifest_field", None)
                if dash_field:
                    dash_path = getattr(instance, dash_field, None)
                    if dash_path:
                        db_paths.add(dash_path)

                # Добавляем превью
                preview_field = getattr(field, "preview_field", None)
                if preview_field:
                    preview_path = getattr(instance, preview_field, None)
                    if preview_path:
                        db_paths.add(preview_path)

        except Exception as e:
            logger.warning(f"Error processing {instance.pk}: {e}")
            continue

    # Здесь нужна логика сканирования storage и поиска сирот
    # Это зависит от конкретного storage backend

    orphaned_files = []  # Заглушка

    if not dry_run:
        deleted = 0
        for file_path in orphaned_files:
            try:
                # storage.delete(file_path)  # Раскомментировать для реального удаления
                deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")

        logger.info(f"Deleted {deleted} orphaned files")
        return {"deleted": deleted, "found": len(orphaned_files)}
    else:
        logger.info(f"Found {len(orphaned_files)} orphaned files (dry run)")
        return {"found": len(orphaned_files), "files": orphaned_files[:50]}  # Первые 50


# ==============================================================================
# ПЕРИОДИЧЕСКИЕ ЗАДАЧИ (для Celery Beat)
# ==============================================================================

# В settings.py добавить:
# CELERY_BEAT_SCHEDULE = {
#     'cleanup-temp-files': {
#         'task': 'hlsfield.tasks.cleanup_old_temp_files',
#         'schedule': crontab(hour=2, minute=0),  # Каждый день в 2:00
#     },
#     'update-video-stats': {
#         'task': 'hlsfield.tasks.update_video_statistics',
#         'schedule': crontab(minute='*/30'),  # Каждые 30 минут
#     },
#     'monitor-performance': {
#         'task': 'hlsfield.tasks.monitor_transcoding_performance',
#         'schedule': crontab(minute='*/10'),  # Каждые 10 минут
#     },
# }


# ==============================================================================
# ЭКСПОРТ
# ==============================================================================

__all__ = [
    # Основные задачи
    "build_hls_for_field",
    "build_hls_for_field_sync",
    "build_dash_for_field",
    "build_dash_for_field_sync",
    "build_adaptive_for_field",
    "build_adaptive_for_field_sync",
    # Прогрессивные задачи
    "build_progressive_for_field",
    "build_progressive_for_field_sync",
    # Batch операции
    "batch_optimize_videos",
    "optimize_existing_video",
    "health_check_videos",
    # Обслуживание
    "cleanup_old_temp_files",
    "regenerate_missing_previews",
    "update_video_statistics",
    "migrate_old_video_format",
    "validate_video_integrity",
    "cleanup_orphaned_files",
    # Аналитика
    "generate_video_analytics_report",
    "monitor_transcoding_performance",
]
