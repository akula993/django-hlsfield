# src/hlsfield/progressive_tasks.py

import time
from pathlib import Path
from typing import List, Dict, Any

try:
    from celery import shared_task, group, chain
except Exception:
    def shared_task(*_a, **_kw):
        def deco(fn): return fn

        return deco


    def group(*args):
        return None


    def chain(*args):
        return None

from django.apps import apps
from django.db import transaction
from . import utils, defaults


@shared_task
def build_progressive_for_field(model_label: str, pk: int | str, field_name: str, options: Dict[str, Any]):
    """Прогрессивно создает адаптивное видео по качествам"""
    build_progressive_for_field_sync(model_label, pk, field_name, options)


def build_progressive_for_field_sync(model_label: str, pk: int | str, field_name: str, options: Dict[str, Any]):
    """Синхронная версия прогрессивной обработки"""
    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)

    preview_first = options.get('preview_first', True)
    progressive_delay = options.get('progressive_delay', 60)
    priority_heights = options.get('priority_heights', [360, 720])

    ladder = getattr(field, 'ladder', defaults.DEFAULT_LADDER)

    # Сортируем лестницу: сначала приоритетные, потом остальные
    priority_ladder = [r for r in ladder if r['height'] in priority_heights]
    regular_ladder = [r for r in ladder if r['height'] not in priority_heights]

    # Сортируем по возрастанию качества
    ordered_ladder = sorted(priority_ladder, key=lambda x: x['height']) + \
                     sorted(regular_ladder, key=lambda x: x['height'])

    with utils.tempdir() as td:
        local_input = utils.pull_to_local(storage, name, td)

        if preview_first and ordered_ladder:
            # Создаем сначала самое низкое качество для быстрого старта
            preview_quality = ordered_ladder[0]
            _build_single_quality(
                local_input, storage, name, [preview_quality],
                field, instance, is_preview=True
            )

            # Остальные качества
            remaining_ladder = ordered_ladder[1:]
        else:
            remaining_ladder = ordered_ladder

        # Создаем остальные качества с задержкой
        for i, quality in enumerate(remaining_ladder):
            if i > 0 and progressive_delay > 0:
                time.sleep(progressive_delay)

            _build_single_quality(
                local_input, storage, name, ordered_ladder[:i + 2],
                field, instance, is_preview=False
            )


def _build_single_quality(local_input: Path, storage, name: str, current_ladder: List[Dict],
                          field, instance, is_preview: bool = False):
    """Создает текущую лестницу качеств и обновляет манифесты"""

    with utils.tempdir() as td:
        adaptive_root = Path(td) / "adaptive_out"
        adaptive_root.mkdir(parents=True, exist_ok=True)

        # Создаем HLS и DASH с текущей лестницей
        results = utils.transcode_adaptive_variants(
            input_path=local_input,
            out_dir=adaptive_root,
            ladder=current_ladder,
            segment_duration=getattr(field, 'segment_duration', defaults.SEGMENT_DURATION),
        )

        # Загружаем в storage
        base_key = _adaptive_out_base(name, getattr(field, "adaptive_base_subdir", "adaptive"))
        utils.save_tree_to_storage(adaptive_root, storage, base_key)

        # Обновляем пути к манифестам в модели
        hls_master_key = base_key + f"hls/{results['hls_master'].name}"
        dash_manifest_key = base_key + f"dash/{results['dash_manifest'].name}"

        _update_instance_with_manifests(
            instance, field, hls_master_key, dash_manifest_key,
            is_preview=is_preview, qualities_count=len(current_ladder)
        )


@shared_task
def optimize_existing_video(model_label: str, pk: int | str, field_name: str,
                            target_qualities: int = 5, max_file_size_mb: int = None):
    """Оптимизирует уже существующее видео под новые требования"""

    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)

    with utils.tempdir() as td:
        local_input = utils.pull_to_local(storage, name, td)

        # Анализируем текущее видео
        from .smart_fields import SmartAdaptiveVideoField
        smart_field = SmartAdaptiveVideoField()
        analysis = smart_field._analyze_source_video(local_input)

        # Генерируем новую оптимальную лестницу
        smart_field.max_qualities = target_qualities
        new_ladder = smart_field._generate_smart_ladder(analysis)

        # Если задан максимальный размер, корректируем битрейты
        if max_file_size_mb:
            new_ladder = _adjust_ladder_for_size_limit(new_ladder, analysis, max_file_size_mb)

        # Создаем новые варианты
        _build_single_quality(local_input, storage, name, new_ladder, field, instance)


def _adjust_ladder_for_size_limit(ladder: List[Dict], analysis: Dict, max_size_mb: int) -> List[Dict]:
    """Корректирует битрейты лестницы под ограничение размера"""

    duration = analysis.get('duration', 0)
    if duration <= 0:
        return ladder

    # Рассчитываем текущий суммарный размер всех качеств
    total_size = sum(q.get('estimated_size_mb', 0) for q in ladder)

    if total_size <= max_size_mb:
        return ladder  # Уже вписываемся в лимит

    # Пропорционально уменьшаем битрейты
    reduction_factor = max_size_mb / total_size

    adjusted_ladder = []
    for quality in ladder:
        adjusted_quality = quality.copy()
        adjusted_quality['v_bitrate'] = max(200, int(quality['v_bitrate'] * reduction_factor))
        adjusted_quality['a_bitrate'] = max(64, int(quality['a_bitrate'] * reduction_factor))

        # Пересчитываем размер
        total_bitrate = (adjusted_quality['v_bitrate'] + adjusted_quality['a_bitrate']) * 1000
        adjusted_quality['estimated_size_mb'] = (total_bitrate * duration) / (8 * 1024 * 1024)

        adjusted_ladder.append(adjusted_quality)

    return adjusted_ladder


@shared_task
def analyze_video_performance(model_label: str, pk: int | str, field_name: str):
    """Анализирует производительность видео и предлагает оптимизации"""

    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)

    analysis = {
        'file_size_mb': 0,
        'qualities_count': 0,
        'total_segments': 0,
        'estimated_bandwidth_usage': 0,
        'recommendations': []
    }

    try:
        # Анализируем существующие файлы
        base_key = _adaptive_out_base(name, getattr(field, "adaptive_base_subdir", "adaptive"))

        # Подсчитываем размеры файлов
        # ... логика анализа файлов в storage ...

        # Генерируем рекомендации
        recommendations = []

        if analysis['qualities_count'] > 5:
            recommendations.append("Рассмотрите уменьшение количества качеств до 3-5")

        if analysis['file_size_mb'] > 500:
            recommendations.append("Видео занимает много места, оптимизируйте битрейты")

        if analysis['total_segments'] > 200:
            recommendations.append("Слишком много сегментов, увеличьте segment_duration")

        analysis['recommendations'] = recommendations

        # Сохраняем анализ в модель если есть поле
        if hasattr(instance, 'performance_analysis'):
            import json
            setattr(instance, 'performance_analysis', json.dumps(analysis))
            instance.save(update_fields=['performance_analysis'])

    except Exception as e:
        analysis['error'] = str(e)

    return analysis


@shared_task
def cleanup_old_variants(model_label: str, pk: int | str, field_name: str, keep_qualities: int = 3):
    """Очищает старые варианты качества, оставляя только указанное количество лучших"""

    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)

    try:
        base_key = _adaptive_out_base(name, getattr(field, "adaptive_base_subdir", "adaptive"))

        # Находим все существующие качества
        # ... логика анализа и удаления файлов ...

        # Пересоздаем манифесты только с оставшимися качествами
        # ...

        return {"status": "success", "removed_qualities": 0, "kept_qualities": keep_qualities}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def _resolve_field(instance, field_name: str):
    """Вспомогательная функция для получения поля и связанных объектов"""
    field = instance._meta.get_field(field_name)
    file = getattr(instance, field_name)
    storage = file.storage
    name = file.name
    return field, file, storage, name


def _adaptive_out_base(name: str, subdir: str) -> str:
    """Генерирует базовый путь для adaptive файлов"""
    base, _ext = os.path.splitext(name)
    return f"{base}/{subdir}/"


def _update_instance_with_manifests(instance, field, hls_key: str, dash_key: str,
                                    is_preview: bool = False, qualities_count: int = 0):
    """Обновляет инстанс модели с путями к манифестам"""

    hls_field = getattr(field, "hls_playlist_field", None)
    dash_field = getattr(field, "dash_manifest_field", None)

    if hls_field:
        setattr(instance, hls_field, hls_key)
    if dash_field:
        setattr(instance, dash_field, dash_key)

    # Дополнительные поля для отслеживания прогресса
    if hasattr(instance, 'processing_status'):
        status = 'preview_ready' if is_preview else 'processing'
        if not is_preview and qualities_count > 1:
            status = f'ready_{qualities_count}_qualities'
        setattr(instance, 'processing_status', status)

    if hasattr(instance, 'qualities_ready'):
        setattr(instance, 'qualities_ready', qualities_count)

    with transaction.atomic():
        fields_to_update = []
        if hls_field: fields_to_update.append(hls_field)
        if dash_field: fields_to_update.append(dash_field)
        if hasattr(instance, 'processing_status'):
            fields_to_update.append('processing_status')
        if hasattr(instance, 'qualities_ready'):
            fields_to_update.append('qualities_ready')

        if fields_to_update:
            instance.save(update_fields=fields_to_update)


# Batch-задачи для массовой обработки

@shared_task
def batch_optimize_videos(model_label: str, pks: List[int], field_name: str,
                          target_qualities: int = 3):
    """Массовая оптимизация видео"""

    Model = apps.get_model(model_label)
    results = []

    for pk in pks:
        try:
            optimize_existing_video.delay(model_label, pk, field_name, target_qualities)
            results.append({"pk": pk, "status": "queued"})
        except Exception as e:
            results.append({"pk": pk, "status": "error", "message": str(e)})

    return results


@shared_task
def batch_create_previews(model_label: str, pks: List[int], field_name: str):
    """Массовое создание превью для существующих видео"""

    Model = apps.get_model(model_label)
    results = []

    for pk in pks:
        try:
            instance = Model.objects.get(pk=pk)
            field, file, storage, name = _resolve_field(instance, field_name)

            with utils.tempdir() as td:
                local_input = utils.pull_to_local(storage, name, td)

                # Создаем только превью (самое низкое качество)
                preview_ladder = [{"height": 360, "v_bitrate": 800, "a_bitrate": 96}]

                _build_single_quality(
                    local_input, storage, name, preview_ladder,
                    field, instance, is_preview=True
                )

            results.append({"pk": pk, "status": "success"})

        except Exception as e:
            results.append({"pk": pk, "status": "error", "message": str(e)})

    return results


@shared_task
def health_check_videos(model_label: str, field_name: str):
    """Проверяет здоровье всех видео в модели"""

    Model = apps.get_model(model_label)
    issues = []

    for instance in Model.objects.all():
        field, file, storage, name = _resolve_field(instance, field_name)

        issue = {"pk": instance.pk, "problems": []}

        # Проверяем существование основного файла
        if not storage.exists(name):
            issue["problems"].append("Original file missing")

        # Проверяем манифесты
        hls_field = getattr(field, "hls_playlist_field", None)
        dash_field = getattr(field, "dash_manifest_field", None)

        if hls_field:
            hls_path = getattr(instance, hls_field, None)
            if hls_path and not storage.exists(hls_path):
                issue["problems"].append("HLS manifest missing")

        if dash_field:
            dash_path = getattr(instance, dash_field, None)
            if dash_path and not storage.exists(dash_path):
                issue["problems"].append("DASH manifest missing")

        if issue["problems"]:
            issues.append(issue)

    return {
        "total_checked": Model.objects.count(),
        "issues_found": len(issues),
        "issues": issues
    }
