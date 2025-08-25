"""
Дополнительные продвинутые возможности для django-hlsfield v2.0
"""

import asyncio
import aiohttp
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import numpy as np
from sklearn.linear_model import LinearRegression
import cv2
import torch
from pathlib import Path
import redis
import json
import hashlib
from django.core.cache import cache
from django.db import models
from django.utils import timezone
from datetime import timedelta


# ==============================================================================
# 1. MACHINE LEARNING для предсказания качества
# ==============================================================================

class MLQualityPredictor:
    """
    Использует машинное обучение для предсказания оптимального качества видео
    на основе исторических данных пользователя и сети.
    """

    def __init__(self):
        self.model = LinearRegression()
        self.is_trained = False
        self.feature_names = [
            'bandwidth', 'latency', 'packet_loss', 'time_of_day',
            'day_of_week', 'device_type', 'previous_quality',
            'buffer_health', 'segment_download_time'
        ]

    def train(self, historical_data: List[Dict]):
        """Обучает модель на исторических данных"""
        if len(historical_data) < 100:
            return  # Недостаточно данных

        # Подготовка данных
        X = []
        y = []

        for record in historical_data:
            features = self.extract_features(record)
            X.append(features)
            y.append(record['optimal_quality'])

        X = np.array(X)
        y = np.array(y)

        # Обучение
        self.model.fit(X, y)
        self.is_trained = True

        # Сохраняем модель
        self.save_model()

    def predict(self, current_metrics: Dict) -> int:
        """Предсказывает оптимальное качество"""
        if not self.is_trained:
            return self.fallback_prediction(current_metrics)

        features = self.extract_features(current_metrics)
        features = np.array(features).reshape(1, -1)

        prediction = self.model.predict(features)[0]
        return max(0, int(round(prediction)))

    def extract_features(self, metrics: Dict) -> List[float]:
        """Извлекает признаки из метрик"""
        from datetime import datetime

        now = datetime.now()

        return [
            metrics.get('bandwidth', 0),
            metrics.get('latency', 0),
            metrics.get('packet_loss', 0),
            now.hour,  # время суток
            now.weekday(),  # день недели
            self.encode_device_type(metrics.get('device_type', 'unknown')),
            metrics.get('previous_quality', 0),
            metrics.get('buffer_health', 0),
            metrics.get('segment_download_time', 0)
        ]

    def encode_device_type(self, device_type: str) -> float:
        """Кодирует тип устройства в число"""
        device_map = {
            'mobile': 0,
            'tablet': 1,
            'desktop': 2,
            'smart_tv': 3,
            'unknown': -1
        }
        return device_map.get(device_type, -1)

    def fallback_prediction(self, metrics: Dict) -> int:
        """Простое правило-based предсказание когда ML не доступно"""
        bandwidth = metrics.get('bandwidth', 0)

        if bandwidth < 1:
            return 0  # 360p
        elif bandwidth < 2.5:
            return 1  # 480p
        elif bandwidth < 5:
            return 2  # 720p
        else:
            return 3  # 1080p

    def save_model(self):
        """Сохраняет обученную модель"""
        import pickle
        cache.set('ml_quality_model', pickle.dumps(self.model), 86400)

    def load_model(self):
        """Загружает сохраненную модель"""
        import pickle
        model_data = cache.get('ml_quality_model')
        if model_data:
            self.model = pickle.loads(model_data)
            self.is_trained = True


# ==============================================================================
# 2. P2P CDN для экономии трафика
# ==============================================================================

class P2PVideoDistribution:
    """
    Peer-to-peer распределение видео сегментов между пользователями
    для снижения нагрузки на сервер.
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.peer_ttl = 300  # 5 минут

    async def register_peer(self, peer_id: str, video_id: str, segments: List[int]):
        """Регистрирует пира с его доступными сегментами"""
        key = f"p2p:video:{video_id}:peers"
        peer_data = {
            'id': peer_id,
            'segments': segments,
            'timestamp': timezone.now().isoformat()
        }

        await self.redis.hset(key, peer_id, json.dumps(peer_data))
        await self.redis.expire(key, self.peer_ttl)

    async def find_peers_with_segment(self, video_id: str, segment_num: int) -> List[str]:
        """Находит пиров у которых есть нужный сегмент"""
        key = f"p2p:video:{video_id}:peers"
        peers = await self.redis.hgetall(key)

        available_peers = []
        for peer_id, data in peers.items():
            peer_data = json.loads(data)
            if segment_num in peer_data['segments']:
                available_peers.append(peer_id.decode())

        return available_peers

    async def get_segment_from_peer(self, peer_id: str, video_id: str, segment_num: int) -> Optional[bytes]:
        """Получает сегмент от другого пира через WebRTC"""
        # Это упрощенный пример - в реальности нужен WebRTC

        # Проверяем доступность пира
        if not await self.is_peer_available(peer_id):
            return None

        # Здесь должна быть реализация WebRTC соединения
        # Для примера возвращаем None
        return None

    async def is_peer_available(self, peer_id: str) -> bool:
        """Проверяет доступность пира"""
        # Пинг через WebSocket или другой механизм
        return False  # Заглушка


# ==============================================================================
# 3. AI-POWERED оптимизация видео
# ==============================================================================

class AIVideoOptimizer:
    """
    Использует AI для интеллектуальной оптимизации видео:
    - Определение оптимального битрейта для каждой сцены
    - Умное кадрирование для мобильных устройств
    - Улучшение качества через super-resolution
    """

    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def analyze_video_complexity(self, video_path: Path) -> Dict[str, Any]:
        """
        Анализирует сложность видео для определения оптимальных настроек кодирования.
        """
        cap = cv2.VideoCapture(str(video_path))

        complexity_scores = []
        motion_scores = []
        scene_changes = []

        prev_frame = None
        frame_num = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Анализ сложности кадра
            complexity = self._calculate_frame_complexity(frame)
            complexity_scores.append(complexity)

            # Детекция движения
            if prev_frame is not None:
                motion = self._calculate_motion(prev_frame, frame)
                motion_scores.append(motion)

                # Детекция смены сцен
                if motion > 0.7:  # Порог для смены сцены
                    scene_changes.append(frame_num)

            prev_frame = frame
            frame_num += 1

            # Анализируем каждый 30й кадр для скорости
            for _ in range(29):
                cap.read()
                frame_num += 1

        cap.release()

        return {
            'avg_complexity': np.mean(complexity_scores),
            'max_complexity': np.max(complexity_scores),
            'avg_motion': np.mean(motion_scores) if motion_scores else 0,
            'scene_changes': scene_changes,
            'recommended_bitrates': self._recommend_bitrates(
                np.mean(complexity_scores),
                np.mean(motion_scores) if motion_scores else 0
            )
        }

    def _calculate_frame_complexity(self, frame: np.ndarray) -> float:
        """Рассчитывает визуальную сложность кадра"""
        # Конвертируем в grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Вычисляем градиенты (edges)
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)

        # Магнитуда градиентов
        magnitude = np.sqrt(sobelx ** 2 + sobely ** 2)

        # Нормализуем сложность от 0 до 1
        complexity = np.mean(magnitude) / 255.0

        return min(1.0, complexity * 2)  # Усиливаем для лучшей дифференциации

    def _calculate_motion(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        """Рассчитывает количество движения между кадрами"""
        # Конвертируем в grayscale
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

        # Вычисляем разницу
        diff = cv2.absdiff(gray1, gray2)

        # Пороговая обработка
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

        # Процент измененных пикселей
        motion = np.sum(thresh > 0) / thresh.size

        return motion

    def _recommend_bitrates(self, complexity: float, motion: float) -> Dict[str, int]:
        """Рекомендует битрейты на основе анализа"""

        # Базовые битрейты для простого статичного видео
        base_bitrates = {
            '360p': 400,
            '480p': 800,
            '720p': 1500,
            '1080p': 3000,
            '1440p': 6000,
            '2160p': 12000
        }

        # Множители на основе сложности и движения
        complexity_multiplier = 1.0 + complexity * 0.5  # до +50%
        motion_multiplier = 1.0 + motion * 0.5  # до +50%

        total_multiplier = complexity_multiplier * motion_multiplier

        recommended = {}
        for quality, bitrate in base_bitrates.items():
            recommended[quality] = int(bitrate * total_multiplier)

        return recommended

    def generate_smart_thumbnails(self, video_path: Path, num_thumbnails: int = 5) -> List[np.ndarray]:
        """
        Генерирует умные превью, выбирая наиболее репрезентативные кадры.
        """
        cap = cv2.VideoCapture(str(video_path))

        # Получаем общее количество кадров
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Анализируем кадры и выбираем лучшие
        candidates = []

        for i in range(0, total_frames, total_frames // (num_thumbnails * 3)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()

            if not ret:
                continue

            # Оцениваем качество кадра
            score = self._score_thumbnail_quality(frame)
            candidates.append((score, frame))

        cap.release()

        # Сортируем по качеству и выбираем лучшие
        candidates.sort(key=lambda x: x[0], reverse=True)
        thumbnails = [frame for _, frame in candidates[:num_thumbnails]]

        return thumbnails

    def _score_thumbnail_quality(self, frame: np.ndarray) -> float:
        """Оценивает качество кадра для использования как превью"""

        # Проверяем резкость (не размытый)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness_score = min(1.0, laplacian_var / 1000)

        # Проверяем контрастность
        contrast_score = gray.std() / 127.5

        # Проверяем наличие лиц (если есть - хороший кадр)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        face_score = 1.0 if len(faces) > 0 else 0.5

        # Комбинированный счет
        total_score = sharpness_score * 0.4 + contrast_score * 0.3 + face_score * 0.3

        return total_score


# ==============================================================================
# 4. Расширенная аналитика и A/B тестирование
# ==============================================================================

class VideoAnalyticsEngine:
    """
    Продвинутая аналитика для видео с A/B тестированием качества.
    """

    def __init__(self):
        self.redis = redis.Redis(decode_responses=True)

    async def track_quality_metrics(self, session_id: str, metrics: Dict):
        """Отслеживает метрики качества для сессии"""

        key = f"analytics:session:{session_id}"

        # Сохраняем метрики
        await self.redis.hset(key, mapping={
            'timestamp': timezone.now().isoformat(),
            'quality': metrics.get('quality'),
            'buffer_ratio': metrics.get('buffer_ratio'),
            'startup_time': metrics.get('startup_time'),
            'rebuffer_count': metrics.get('rebuffer_count'),
            'quality_switches': metrics.get('quality_switches'),
            'average_bitrate': metrics.get('average_bitrate'),
            'qoe_score': self.calculate_qoe_score(metrics)
        })

        # TTL 7 дней
        await self.redis.expire(key, 604800)

    def calculate_qoe_score(self, metrics: Dict) -> float:
        """
        Рассчитывает Quality of Experience (QoE) score.
        """

        # Веса для разных факторов
        weights = {
            'quality': 0.3,
            'buffering': 0.3,
            'stability': 0.2,
            'startup': 0.2
        }

        # Качество видео (нормализованное)
        quality_score = min(1.0, metrics.get('average_bitrate', 0) / 5000)

        # Буферизация (чем меньше, тем лучше)
        buffer_score = max(0, 1.0 - metrics.get('buffer_ratio', 0))

        # Стабильность (меньше переключений качества)
        stability_score = max(0, 1.0 - (metrics.get('quality_switches', 0) / 10))

        # Время старта (чем быстрее, тем лучше)
        startup_score = max(0, 1.0 - (metrics.get('startup_time', 0) / 10))

        qoe = (
            quality_score * weights['quality'] +
            buffer_score * weights['buffering'] +
            stability_score * weights['stability'] +
            startup_score * weights['startup']
        )

        return round(qoe * 100, 2)  # Возвращаем в процентах

    async def run_ab_test(self, test_name: str, variant: str, metrics: Dict):
        """Запускает A/B тест для разных алгоритмов ABR"""

        key = f"abtest:{test_name}:{variant}"

        # Сохраняем результаты теста
        await self.redis.lpush(key, json.dumps({
            'timestamp': timezone.now().isoformat(),
            'qoe_score': self.calculate_qoe_score(metrics),
            'metrics': metrics
        }))

        # Ограничиваем размер списка
        await self.redis.ltrim(key, 0, 9999)

    async def get_ab_test_results(self, test_name: str) -> Dict:
        """Получает результаты A/B теста"""

        variants = ['control', 'experiment']
        results = {}

        for variant in variants:
            key = f"abtest:{test_name}:{variant}"
            data = await self.redis.lrange(key, 0, -1)

            if not data:
                continue

            scores = []
            for item in data:
                item_data = json.loads(item)
                scores.append(item_data['qoe_score'])

            results[variant] = {
                'count': len(scores),
                'avg_qoe': np.mean(scores),
                'std_qoe': np.std(scores),
                'min_qoe': np.min(scores),
                'max_qoe': np.max(scores)
            }

        # Статистическая значимость
        if len(results) == 2:
            from scipy import stats
            control_scores = results['control'].get('scores', [])
            experiment_scores = results['experiment'].get('scores', [])

            if control_scores and experiment_scores:
                t_stat, p_value = stats.ttest_ind(control_scores, experiment_scores)
                results['statistical_significance'] = {
                    't_statistic': t_stat,
                    'p_value': p_value,
                    'significant': p_value < 0.05
                }

        return results


# ==============================================================================
# 5. Django модели для расширенных функций
# ==============================================================================

class VideoQualityProfile(models.Model):
    """Профиль качества для видео с ML-оптимизацией"""

    video = models.ForeignKey('Video', on_delete=models.CASCADE, related_name='quality_profiles')

    # Результаты AI анализа
    complexity_score = models.FloatField(help_text="Визуальная сложность 0-1")
    motion_score = models.FloatField(help_text="Количество движения 0-1")

    # Рекомендованные битрейты
    recommended_bitrates = models.JSONField(default=dict)

    # ML модель для этого видео
    ml_model_data = models.BinaryField(null=True, blank=True)

    # Статистика использования
    total_views = models.IntegerField(default=0)
    avg_qoe_score = models.FloatField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'hlsfield'

    def update_ml_model(self):
        """Обновляет ML модель на основе новых данных"""
        predictor = MLQualityPredictor()

        # Получаем исторические данные
        events = VideoEvent.objects.filter(
            video_id=self.video_id,
            event_type='quality_change'
        ).values('additional_data')

        historical_data = [e['additional_data'] for e in events]

        if len(historical_data) > 100:
            predictor.train(historical_data)

            # Сохраняем модель
            import pickle
            self.ml_model_data = pickle.dumps(predictor.model)
            self.save()


class UserVideoPreference(models.Model):
    """Предпочтения пользователя для видео"""

    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)

    # Предпочтения качества
    preferred_quality = models.CharField(max_length=10, default='auto')
    max_quality = models.CharField(max_length=10, default='1080p')

    # Сетевые предпочтения
    save_data_mode = models.BooleanField(default=False)
    wifi_only_hd = models.BooleanField(default=False)

    # Статистика
    avg_bandwidth = models.FloatField(default=0)
    typical_watch_time = models.DurationField(default=timedelta(0))

    class Meta:
        app_label = 'hlsfield'


# ==============================================================================
# Интеграция всех компонентов
# ==============================================================================

def setup_advanced_features():
    """Настройка всех продвинутых функций"""

    # Инициализация ML предиктора
    ml_predictor = MLQualityPredictor()
    ml_predictor.load_model()

    # Инициализация P2P
    redis_client = redis.Redis()
    p2p_system = P2PVideoDistribution(redis_client)

    # AI оптимизатор
    ai_optimizer = AIVideoOptimizer()

    # Аналитика
    analytics = VideoAnalyticsEngine()

    return {
        'ml_predictor': ml_predictor,
        'p2p_system': p2p_system,
        'ai_optimizer': ai_optimizer,
        'analytics': analytics
    }


# Пример использования
if __name__ == "__main__":
    # Настройка
    components = setup_advanced_features()

    # Анализ видео с AI
    video_path = Path('/path/to/video.mp4')
    analysis = components['ai_optimizer'].analyze_video_complexity(video_path)
    print(f"Video complexity: {analysis['avg_complexity']}")
    print(f"Recommended bitrates: {analysis['recommended_bitrates']}")

    # ML предсказание качества
    current_metrics = {
        'bandwidth': 3.5,
        'latency': 50,
        'buffer_health': 0.8,
        'device_type': 'mobile'
    }

    optimal_quality = components['ml_predictor'].predict(current_metrics)
    print(f"ML predicted optimal quality: {optimal_quality}")
