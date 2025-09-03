import pytest
from django.test import TestCase
from hlsfield import VideoField, HLSVideoField


class TestBasicImports(TestCase):
    def test_imports(self):
        """Тест базового импорта"""
        assert VideoField is not None
        assert HLSVideoField is not None

    def test_version(self):
        """Тест версии"""
        import hlsfield
        assert hasattr(hlsfield, '__version__')
