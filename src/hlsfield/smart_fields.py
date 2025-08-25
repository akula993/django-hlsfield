# src/hlsfield/smart_fields.py

import os
import math
from typing import List, Dict, Any
from pathlib import Path

from django.core.files.base import File
from .fields import AdaptiveVideoField
from . import utils, defaults


class SmartAdaptiveVideoField(AdaptiveVideoField):
    """
    Интеллектуальное поле, которое автоматически подбирает оптимальную
    лестницу качеств на основе характеристик исходного видео.
    """

    def __init__(self, *args,
                 max_qualities: int = 5,
                 min_bitrate_ratio: float = 0.3,  # мин битрейт = 30% от оригинала
                 max_bitrate_ratio: float = 1.2,  # макс битрейт = 120% от оригинала
                 target_segments: int = 100,  # целевое кол-во сегментов
                 quality_algorithm: str = "smart",  # "smart" | "fixed" | "source_based"
                 **kwargs):

        # Не передаваем ladder в родительский класс - создадим динамически
        if 'ladder' in kwargs:
            del kwargs['ladder']

        super().__init__(*args, ladder=[], **kwargs)
        self.max_qualities = max_qualities
        self.min_bitrate_ratio = min_bitrate_ratio
        self.max_bitrate_ratio = max_bitrate_ratio
        self.target_segments = target_segments
        self.quality_algorithm = quality_algorithm

    def _analyze_source_video(self, file_path: Path) -> Dict[str, Any]:
        """Анализирует исходное видео и возвращает его характеристики"""
        info = utils.ffprobe_streams(file_path)
        v_stream, a_stream = utils.pick_video_audio_streams(info)

        analysis = {
            'width': 0,
            'height': 0,
            'duration': 0,
            'bitrate': 0,
            'fps': 30,
            'has_audio': a_stream is not None,
            'codec': 'unknown'
        }

        if v_stream:
            analysis.update({
                'width': int(v_stream.get('width', 0)),
                'height': int(v_stream.get('height', 0)),
                'fps': self._parse_fps(v_stream.get('r_frame_rate', '30/1')),
                'codec': v_stream.get('codec_name', 'unknown')
            })

        if format_info := info.get('format'):
            try:
                analysis['duration'] = float(format_info.get('duration', 0))
                analysis['bitrate'] = int(format_info.get('bit_rate', 0))
            except (ValueError, TypeError):
                pass

        return analysis

    def _parse_fps(self, fps_str: str) -> float:
        """Парсит FPS из формата '30000/1001' в число"""
        try:
            if '/' in fps_str:
                num, den = map(int, fps_str.split('/'))
                return num / den
            return float(fps_str)
        except (ValueError, ZeroDivisionError):
            return 30.0

    def _generate_smart_ladder(self, analysis: Dict[str, Any]) -> List[Dict]:
        """Генерирует умную лестницу качеств на основе анализа"""
        source_height = analysis['height']
        source_width = analysis['width']
        source_bitrate = analysis['bitrate']
        duration = analysis['duration']

        # Определяем базовые разрешения в зависимости от источника
        if source_height <= 480:
            base_heights = [240, 360, source_height]
        elif source_height <= 720:
            base_heights = [240, 360, 480, source_height]
        elif source_height <= 1080:
            base_heights = [360, 480, 720, source_height]
        elif source_height <= 1440:
            base_heights = [480, 720, 1080, source_height]
        else:  # 4K+
            base_heights = [720, 1080, 1440, source_height]

        # Ограничиваем количество качеств
        if len(base_heights) > self.max_qualities:
            # Оставляем равномерно распределенные + всегда включаем исходное
            step = len(base_heights) // (self.max_qualities - 1)
            base_heights = base_heights[::step] + [source_height]
            base_heights = sorted(list(set(base_heights)))[:self.max_qualities]

        ladder = []

        for height in base_heights:
            # Рассчитываем пропорциональную ширину
            width = int((height * source_width) / source_height)
            width = (width // 2) * 2  # Четная ширина для кодека

            # Рассчитываем битрейт на основе разрешения и характеристик источника
            pixels_ratio = (width * height) / (source_width * source_height)

            if source_bitrate > 0:
                # На основе битрейта источника
                base_video_bitrate = source_bitrate * 0.85  # 85% битрейта на видео
                target_bitrate = int(base_video_bitrate * pixels_ratio)
            else:
                # Эвристические формулы для разных разрешений
                target_bitrate = self._estimate_bitrate_for_resolution(height)

            # Ограничиваем битрейт заданными пропорциями
            if source_bitrate > 0:
                min_bitrate = int(source_bitrate * self.min_bitrate_ratio)
                max_bitrate = int(source_bitrate * self.max_bitrate_ratio)
                target_bitrate = max(min_bitrate, min(target_bitrate, max_bitrate))

            # Аудио битрейт в зависимости от качества видео
            if height <= 360:
                audio_bitrate = 64
            elif height <= 720:
                audio_bitrate = 96
            elif height <= 1080:
                audio_bitrate = 128
            else:
                audio_bitrate = 160

            if not analysis['has_audio']:
                audio_bitrate = 0

            ladder.append({
                'height': height,
                'width': width,
                'v_bitrate': target_bitrate // 1000,  # в Kbps
                'a_bitrate': audio_bitrate,
                'pixels': width * height,
                'estimated_size_mb': self._estimate_file_size(
                    target_bitrate + audio_bitrate * 1000, duration
                )
            })

        # Сортируем по разрешению
        return sorted(ladder, key=lambda x: x['height'])

    def _estimate_bitrate_for_resolution(self, height: int) -> int:
        """Эвристическая оценка битрейта для разрешения (в bps)"""
        bitrate_map = {
            240: 400_000,
            360: 800_000,
            480: 1_200_000,
            720: 2_500_000,
            1080: 4_500_000,
            1440: 8_000_000,
            2160: 15_000_000  # 4K
        }

        # Находим ближайшее разрешение или интерполируем
        heights = sorted(bitrate_map.keys())

        if height <= heights[0]:
            return bitrate_map[heights[0]]
        if height >= heights[-1]:
            return bitrate_map[heights[-1]]

        # Линейная интерполяция
        for i in range(len(heights) - 1):
            if heights[i] <= height <= heights[i + 1]:
                ratio = (height - heights[i]) / (heights[i + 1] - heights[i])
                return int(bitrate_map[heights[i]] +
                           ratio * (bitrate_map[heights[i + 1]] - bitrate_map[heights[i]]))

        return bitrate_map[720]  # fallback

    def _estimate_file_size(self, bitrate_bps: int, duration_sec: float) -> float:
        """Оценка размера файла в МБ"""
        if duration_sec <= 0:
            return 0
        return (bitrate_bps * duration_sec) / (8 * 1024 * 1024)

    def _optimize_segment_duration(self, analysis: Dict[str, Any]) -> int:
        """Оптимизирует длину сегментов на основе характеристик видео"""
        duration = analysis['duration']

        if duration <= 0:
            return self.segment_duration or defaults.SEGMENT_DURATION

        # Стремимся к target_segments сегментам
        optimal_duration = duration / self.target_segments

        # Ограничиваем разумными пределами
        optimal_duration = max(2, min(optimal_duration, 10))

        # Округляем до четного числа
        return int(optimal_duration // 2) * 2

    class SmartVideoFieldFile(AdaptiveVideoField.attr_class):
        def save(self, name: str, content: File, save: bool = True):
            # Сохраняем файл сначала через родительский VideoField
            from .fields import VideoField
            VideoField.attr_class.save(self, name, content, save)

            field: SmartAdaptiveVideoField = self.field
            inst = self.instance

            if not getattr(field, "adaptive_on_save", True):
                return

            if getattr(inst, "pk", None) is None:
                setattr(inst, f"__smart_adaptive_pending__{field.attname}", True)
                return

            # Анализируем видео и создаем умную лестницу
            with utils.tempdir() as td:
                local_path = utils.pull_to_local(self.storage, self.name, td)
                analysis = field._analyze_source_video(local_path)

                # Генерируем оптимальную лестницу
                smart_ladder = field._generate_smart_ladder(analysis)
                optimal_segment_duration = field._optimize_segment_duration(analysis)

                # Сохраняем анализ в модель если есть соответствующие поля
                if hasattr(inst, 'video_analysis'):
                    import json
                    setattr(inst, 'video_analysis', json.dumps(analysis))

                # Обновляем параметры поля для этого конкретного случая
                field.ladder = smart_ladder
                field.segment_duration = optimal_segment_duration

            field._trigger_adaptive(inst)

    attr_class = SmartVideoFieldFile

    def contribute_to_class(self, cls, name, **kwargs):
        super().contribute_to_class(cls, name, **kwargs)

        # Дополнительный обработчик для smart pending
        from django.db.models.signals import post_save
        def _smart_handler(sender, instance, created, **kw):
            if getattr(instance, f"__smart_adaptive_pending__{name}", False):
                setattr(instance, f"__smart_adaptive_pending__{name}", False)
                try:
                    # Повторно анализируем и запускаем обработку
                    field_file = getattr(instance, name)
                    field_file.save(field_file.name, field_file.file, save=False)
                except Exception:
                    pass

        post_save.connect(_smart_handler, sender=cls, weak=False)


class ProgressiveVideoField(SmartAdaptiveVideoField):
    """
    Поле для прогрессивной загрузки - сначала создает быстрое превью,
    затем постепенно добавляет качества по возрастанию
    """

    def __init__(self, *args,
                 preview_first: bool = True,  # создать сначала превью-качество
                 progressive_delay: int = 60,  # задержка между качествами (сек)
                 priority_heights: List[int] = None,  # приоритетные разрешения
                 **kwargs):

        super().__init__(*args, **kwargs)
        self.preview_first = preview_first
        self.progressive_delay = progressive_delay
        self.priority_heights = priority_heights or [360, 720]

    def _trigger_adaptive(self, instance):
        """Запускает прогрессивную обработку вместо обычной"""
        try:
            from .tasks import build_progressive_for_field, build_progressive_for_field_sync

            task_kwargs = {
                'preview_first': self.preview_first,
                'progressive_delay': self.progressive_delay,
                'priority_heights': self.priority_heights
            }

            if hasattr(build_progressive_for_field, "delay"):
                build_progressive_for_field.delay(
                    instance._meta.label, instance.pk, self.attname, task_kwargs
                )
            else:
                build_progressive_for_field_sync(
                    instance._meta.label, instance.pk, self.attname, task_kwargs
                )
        except Exception:
            from .tasks import build_progressive_for_field_sync
            build_progressive_for_field_sync(
                instance._meta.label, instance.pk, self.attname, {}
            )
