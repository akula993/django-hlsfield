# src/hlsfield/abr.py
"""
Advanced Adaptive Bitrate (ABR) алгоритм для динамического выбора качества
на основе состояния сети, размера буфера и истории воспроизведения.
"""

import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque


@dataclass
class NetworkMetrics:
    """Метрики сети для принятия решений ABR"""
    bandwidth: float  # Mbps
    latency: float  # ms
    packet_loss: float  # percentage
    jitter: float  # ms
    connection_type: str  # 'wifi', '4g', '3g', 'ethernet'


@dataclass
class PlaybackMetrics:
    """Метрики воспроизведения"""
    buffer_level: float  # seconds
    buffer_stalls: int  # количество остановок
    dropped_frames: int
    current_quality: int
    playback_time: float  # seconds
    segment_download_time: float  # последний сегмент


class AdaptiveBitrateController:
    """
    Продвинутый ABR контроллер, который выбирает оптимальное качество
    на основе множества факторов.
    """

    def __init__(self, qualities: List[Dict[str, int]]):
        """
        Args:
            qualities: Список доступных качеств [{height, v_bitrate, a_bitrate}, ...]
        """
        self.qualities = sorted(qualities, key=lambda x: x['v_bitrate'])
        self.history = deque(maxlen=10)  # История последних 10 решений
        self.network_history = deque(maxlen=20)  # История сети

        # Настройки алгоритма
        self.min_buffer_level = 10.0  # минимум секунд в буфере
        self.max_buffer_level = 30.0  # максимум секунд в буфере
        self.panic_buffer_level = 3.0  # критический уровень буфера

        # Веса для разных факторов
        self.weights = {
            'bandwidth': 0.4,
            'buffer': 0.3,
            'history': 0.2,
            'stability': 0.1
        }

        # Статистика для ML
        self.decision_history = []

    def calculate_optimal_quality(
        self,
        network: NetworkMetrics,
        playback: PlaybackMetrics
    ) -> Tuple[int, Dict[str, float]]:
        """
        Рассчитывает оптимальное качество видео.

        Returns:
            (quality_index, confidence_scores)
        """
        scores = {}

        # 1. Оценка пропускной способности
        bandwidth_score = self._calculate_bandwidth_score(network)

        # 2. Оценка состояния буфера
        buffer_score = self._calculate_buffer_score(playback)

        # 3. Оценка стабильности сети
        stability_score = self._calculate_stability_score()

        # 4. Исторический анализ
        history_score = self._calculate_history_score(playback)

        # 5. Комбинированная оценка для каждого качества
        for i, quality in enumerate(self.qualities):
            bitrate = quality['v_bitrate'] + quality['a_bitrate']

            # Можем ли мы поддерживать этот битрейт?
            bandwidth_factor = min(1.0, network.bandwidth * 1000 / bitrate)

            # Учитываем все факторы
            score = (
                bandwidth_factor * self.weights['bandwidth'] +
                buffer_score[i] * self.weights['buffer'] +
                stability_score * self.weights['stability'] +
                history_score[i] * self.weights['history']
            )

            # Штрафы
            if network.packet_loss > 5:
                score *= 0.8  # Штраф за потери пакетов
            if network.latency > 200:
                score *= 0.9  # Штраф за высокую задержку
            if playback.buffer_stalls > 2:
                score *= 0.7  # Штраф за частые остановки

            scores[i] = score

        # Выбираем качество с максимальным счетом
        optimal_quality = max(scores.keys(), key=lambda k: scores[k])

        # Применяем сглаживание для избежания частых переключений
        optimal_quality = self._apply_smoothing(optimal_quality, playback.current_quality)

        # Сохраняем решение
        self._record_decision(optimal_quality, network, playback, scores)

        return optimal_quality, scores

    def _calculate_bandwidth_score(self, network: NetworkMetrics) -> Dict[int, float]:
        """Оценка качеств на основе пропускной способности"""
        scores = {}
        available_bandwidth = network.bandwidth * 1000  # конвертируем в Kbps

        # Используем консервативную оценку (70% от доступной)
        safe_bandwidth = available_bandwidth * 0.7

        for i, quality in enumerate(self.qualities):
            required = quality['v_bitrate'] + quality['a_bitrate']

            if required <= safe_bandwidth:
                # Качество подходит, чем выше - тем лучше
                scores[i] = min(1.0, safe_bandwidth / required)
            else:
                # Качество слишком высокое
                scores[i] = max(0, 1.0 - (required - safe_bandwidth) / required)

        return scores

    def _calculate_buffer_score(self, playback: PlaybackMetrics) -> Dict[int, float]:
        """Оценка качеств на основе состояния буфера"""
        scores = {}
        buffer_health = playback.buffer_level / self.max_buffer_level

        for i, quality in enumerate(self.qualities):
            if playback.buffer_level < self.panic_buffer_level:
                # Критический буфер - только низкие качества
                scores[i] = 1.0 if i == 0 else 0.1
            elif playback.buffer_level < self.min_buffer_level:
                # Низкий буфер - предпочитаем низкие качества
                scores[i] = 1.0 - (i / len(self.qualities))
            else:
                # Нормальный буфер - можем повышать качество
                scores[i] = min(1.0, buffer_health + (i / len(self.qualities)) * 0.3)

        return scores

    def _calculate_stability_score(self) -> float:
        """Оценка стабильности сети на основе истории"""
        if len(self.network_history) < 3:
            return 0.5  # Недостаточно данных

        # Анализируем вариацию пропускной способности
        bandwidths = [m.bandwidth for m in self.network_history]
        avg_bandwidth = sum(bandwidths) / len(bandwidths)
        variance = sum((b - avg_bandwidth) ** 2 for b in bandwidths) / len(bandwidths)

        # Чем меньше вариация, тем стабильнее сеть
        stability = 1.0 / (1.0 + variance)

        return stability

    def _calculate_history_score(self, playback: PlaybackMetrics) -> Dict[int, float]:
        """Оценка на основе истории переключений"""
        scores = {}

        if not self.history:
            # Нет истории - нейтральные оценки
            return {i: 0.5 for i in range(len(self.qualities))}

        # Анализируем успешность предыдущих решений
        recent_qualities = list(self.history)[-5:]
        avg_quality = sum(recent_qualities) / len(recent_qualities)

        for i in range(len(self.qualities)):
            # Предпочитаем качества близкие к среднему успешному
            distance = abs(i - avg_quality)
            scores[i] = 1.0 / (1.0 + distance * 0.3)

        return scores

    def _apply_smoothing(self, target_quality: int, current_quality: int) -> int:
        """Сглаживание переключений для избежания частых изменений"""
        if abs(target_quality - current_quality) <= 1:
            # Небольшое изменение - применяем
            return target_quality
        elif target_quality > current_quality:
            # Повышение качества - делаем постепенно
            return min(current_quality + 2, target_quality)
        else:
            # Понижение качества - можем делать быстрее
            return max(current_quality - 2, target_quality)

    def _record_decision(
        self,
        quality: int,
        network: NetworkMetrics,
        playback: PlaybackMetrics,
        scores: Dict[int, float]
    ):
        """Записывает решение для анализа и обучения"""
        self.history.append(quality)
        self.network_history.append(network)

        # Сохраняем для возможного ML анализа
        self.decision_history.append({
            'timestamp': time.time(),
            'quality': quality,
            'network': network.__dict__,
            'playback': playback.__dict__,
            'scores': scores
        })

    def predict_bandwidth(self) -> float:
        """Предсказывает будущую пропускную способность на основе истории"""
        if len(self.network_history) < 3:
            return 0

        # Простое экспоненциальное сглаживание
        alpha = 0.3
        predicted = self.network_history[0].bandwidth

        for metric in self.network_history:
            predicted = alpha * metric.bandwidth + (1 - alpha) * predicted

        return predicted

    def get_emergency_quality(self) -> int:
        """Возвращает аварийное качество при проблемах"""
        return 0  # Самое низкое качество

    def get_startup_quality(self, network: Optional[NetworkMetrics] = None) -> int:
        """Определяет начальное качество при старте воспроизведения"""
        if not network:
            return 1  # Начинаем со второго снизу

        # Выбираем консервативно на основе сети
        if network.connection_type == 'ethernet' or network.connection_type == 'wifi':
            return min(2, len(self.qualities) - 1)
        elif network.connection_type == '4g':
            return min(1, len(self.qualities) - 1)
        else:
            return 0


class SmartSegmentPrefetcher:
    """
    Интеллектуальная предзагрузка сегментов на основе предсказаний ABR
    """

    def __init__(self, abr_controller: AdaptiveBitrateController):
        self.abr = abr_controller
        self.prefetch_queue = deque(maxlen=5)
        self.cache = {}

    def calculate_prefetch_strategy(
        self,
        current_segment: int,
        current_quality: int,
        network: NetworkMetrics,
        playback: PlaybackMetrics
    ) -> List[Tuple[int, int]]:
        """
        Определяет какие сегменты и в каком качестве предзагружать.

        Returns:
            List of (segment_number, quality_index) to prefetch
        """
        strategy = []

        # Предсказываем пропускную способность
        predicted_bandwidth = self.abr.predict_bandwidth()

        # Определяем вероятные качества для следующих сегментов
        likely_qualities = self._predict_quality_sequence(
            current_quality, predicted_bandwidth
        )

        # Планируем предзагрузку
        for i, quality in enumerate(likely_qualities[:3]):
            segment = current_segment + i + 1
            strategy.append((segment, quality))

            # Если сеть хорошая, загружаем альтернативные качества
            if predicted_bandwidth > 5.0 and i == 0:
                # Загружаем соседние качества для быстрого переключения
                if quality > 0:
                    strategy.append((segment, quality - 1))
                if quality < len(self.abr.qualities) - 1:
                    strategy.append((segment, quality + 1))

        return strategy

    def _predict_quality_sequence(
        self,
        current: int,
        predicted_bandwidth: float
    ) -> List[int]:
        """Предсказывает последовательность качеств"""
        sequence = []

        for _ in range(5):
            # Упрощенная модель предсказания
            if predicted_bandwidth > 5.0:
                target = min(current + 1, len(self.abr.qualities) - 1)
            elif predicted_bandwidth < 2.0:
                target = max(current - 1, 0)
            else:
                target = current

            sequence.append(target)
            current = target

        return sequence


# Интеграция с Django моделью
def enhance_video_field_with_abr(field_class):
    """Декоратор для добавления ABR функциональности к video field"""

    class ABREnhancedField(field_class):
        def __init__(self, *args, **kwargs):
            self.enable_abr = kwargs.pop('enable_abr', True)
            self.abr_algorithm = kwargs.pop('abr_algorithm', 'smart')
            self.prefetch_segments = kwargs.pop('prefetch_segments', 3)
            super().__init__(*args, **kwargs)

            if self.enable_abr:
                self.abr_controller = AdaptiveBitrateController(self.ladder)

        def get_abr_controller(self) -> AdaptiveBitrateController:
            """Возвращает ABR контроллер для этого поля"""
            if not hasattr(self, 'abr_controller'):
                self.abr_controller = AdaptiveBitrateController(self.ladder)
            return self.abr_controller

    return ABREnhancedField


# Пример использования
if __name__ == "__main__":
    # Создаем контроллер с лестницей качеств
    qualities = [
        {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
        {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
        {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
    ]

    abr = AdaptiveBitrateController(qualities)

    # Симулируем метрики
    network = NetworkMetrics(
        bandwidth=3.5,  # 3.5 Mbps
        latency=50,
        packet_loss=0.5,
        jitter=10,
        connection_type='wifi'
    )

    playback = PlaybackMetrics(
        buffer_level=15.0,
        buffer_stalls=0,
        dropped_frames=0,
        current_quality=1,
        playback_time=120.0,
        segment_download_time=2.0
    )

    # Получаем оптимальное качество
    optimal_quality, scores = abr.calculate_optimal_quality(network, playback)
    print(f"Optimal quality: {optimal_quality}")
    print(f"Scores: {scores}")
