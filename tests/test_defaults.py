import os
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import override_settings

from hlsfield import defaults


class TestDefaults:
    """Тесты для модуля defaults.py"""

    def test_get_setting_with_default(self):
        """Тест получения настроек с значениями по умолчанию"""
        result = defaults._get_setting('NON_EXISTENT_SETTING', 'default_value')
        assert result == 'default_value'

    @override_settings(HLSFIELD_FFMPEG='/custom/ffmpeg')
    def test_get_setting_with_custom(self):
        """Тест получения кастомных настроек"""
        result = defaults._get_setting('HLSFIELD_FFMPEG', 'ffmpeg')
        assert result == '/custom/ffmpeg'

    def test_default_ladder(self):
        """Тест дефолтной лестницы качеств"""
        ladder = defaults.DEFAULT_LADDER
        assert isinstance(ladder, list)
        assert len(ladder) > 0
        assert all('height' in rung for rung in ladder)
        assert all('v_bitrate' in rung for rung in ladder)
        assert all('a_bitrate' in rung for rung in ladder)

    def test_validate_ladder_function(self):
        """Тест валидации лестницы"""
        from hlsfield.fields import validate_ladder

        # Валидная лестница
        valid_ladder = [
            {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
            {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
        ]
        assert validate_ladder(valid_ladder) is True

        # Невалидная лестница
        invalid_ladder = [{"height": 360}]  # Не хватает полей
        with pytest.raises(ValueError):
            validate_ladder(invalid_ladder)

    def test_get_runtime_info(self):
        """Тест получения runtime информации"""
        info = defaults.get_runtime_info()

        assert 'ffmpeg' in info
        assert 'processing' in info
        assert 'system' in info
        assert 'django' in info
        assert 'features' in info

        # Проверяем структуру
        assert 'ffmpeg_path' in info['ffmpeg']
        assert 'ffmpeg_available' in info['ffmpeg']

    def test_validate_settings(self):
        """Тест валидации настроек"""
        issues = defaults.validate_settings()
        # Должен вернуть список (может быть пустым если все ок)
        assert isinstance(issues, list)
