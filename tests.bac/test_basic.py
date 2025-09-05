import pytest
from django.test import TestCase

from hlsfield import VideoField, HLSVideoField


@pytest.mark.django_db
class TestBasicImports(TestCase):
    def test_imports(self):
        """Тест базового импорта"""
        from hlsfield import VideoField, HLSVideoField
        assert VideoField is not None
        assert HLSVideoField is not None

    def test_version(self):
        """Тест версии"""
        import hlsfield
        assert hasattr(hlsfield, '__version__')

@pytest.mark.django_db
class TestVideoFieldBasics(TestCase):
    def test_field_creation(self):
        from hlsfield import VideoField
        field = VideoField(upload_to="videos/")
        assert field is not None
