from django.db import models
from hlsfield import VideoField, HLSVideoField, DASHVideoField, AdaptiveVideoField


class SimpleVideo(models.Model):
    """Простая модель с базовым VideoField"""
    title = models.CharField(max_length=200, verbose_name="Название")
    video = VideoField(
        upload_to='simple_videos/',
        verbose_name="Видеофайл",
        duration_field='duration',
        width_field='width',
        height_field='height',
        preview_field='preview'
    )
    duration = models.DurationField(null=True, blank=True, verbose_name="Длительность")
    width = models.IntegerField(null=True, blank=True, verbose_name="Ширина")
    height = models.IntegerField(null=True, blank=True, verbose_name="Высота")
    preview = models.ImageField(null=True, blank=True, verbose_name="Превью")

    class Meta:
        verbose_name = "Простое видео"
        verbose_name_plural = "Простые видео"

    def __str__(self):
        return self.title


class HLSVideo(models.Model):
    """Модель с HLSVideoField"""
    title = models.CharField(max_length=200, verbose_name="Название")
    video = HLSVideoField(
        upload_to='hls_videos/',
        verbose_name="HLS видео",
        hls_playlist_field='hls_master'
    )
    hls_master = models.CharField(max_length=500, null=True, blank=True, verbose_name="HLS плейлист")

    class Meta:
        verbose_name = "HLS видео"
        verbose_name_plural = "HLS видео"

    def __str__(self):
        return self.title


class DASHVideo(models.Model):
    """Модель с DASHVideoField"""
    title = models.CharField(max_length=200, verbose_name="Название")
    video = DASHVideoField(
        upload_to='dash_videos/',
        verbose_name="DASH видео",
        dash_manifest_field='dash_manifest'
    )
    dash_manifest = models.CharField(max_length=500, null=True, blank=True, verbose_name="DASH манифест")

    class Meta:
        verbose_name = "DASH видео"
        verbose_name_plural = "DASH видео"

    def __str__(self):
        return self.title


class AdaptiveVideo(models.Model):
    """Модель с AdaptiveVideoField"""
    title = models.CharField(max_length=200, verbose_name="Название")
    video = AdaptiveVideoField(
        upload_to='adaptive_videos/',
        verbose_name="Адаптивное видео",
        hls_playlist_field='hls_master',
        dash_manifest_field='dash_manifest'
    )
    hls_master = models.CharField(max_length=500, null=True, blank=True, verbose_name="HLS плейлист")
    dash_manifest = models.CharField(max_length=500, null=True, blank=True, verbose_name="DASH манифест")

    class Meta:
        verbose_name = "Адаптивное видео"
        verbose_name_plural = "Адаптивные видео"

    def __str__(self):
        return self.title
