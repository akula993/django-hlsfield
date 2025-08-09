# django-hlsfield (черновик)

**Цель**: Сделать два поля для Django:

* `VideoField` — хранит оригинал, автоматически извлекает метаданные (длительность/размер кадра), делает превью-кадр.
* `HLSVideoField(VideoField)` — наследуется от `VideoField` и **автоматизирует** генерацию HLS (варианты качества,
  master.m3u8), чтобы фронтенд мог выбирать качество без дублирования полноразмерных файлов.

Особенности:

* ffmpeg/ffprobe через `subprocess`.
* Генерация превью-кадра (jpg/png) на указанной секунде.
* Хранение метаданных в полях модели (`DurationField`, `width`, `height`) + путь к `master.m3u8`.
* Построено под асинхронную обработку через Celery (тяжёлая перекодировка уходит в задачу). Есть синхронный «fallback»
  на случай отсутствия Celery.
* Работа с любым `Storage` (в т.ч. S3): все вычисления в temp-директории, потом — заливка артефактов в хранилище.

> **Требования**: установленный `ffmpeg`/`ffprobe` в PATH или указать пути в Django settings.

---

## Структура пакета

```
apps/
  hlsfield/
    __init__.py
    fields.py          # VideoField, HLSVideoField
    utils.py           # ffprobe/ffmpeg helpers, temp utils
    widgets.py         # Превью в админке
    tasks.py           # Celery задача: генерация HLS
    players/
      hls_player.html  # Пример шаблона с hls.js
```

---

## settings.py (пример)

```python
# Пути к бинарям (опционально)
HLSFIELD_FFPROBE = r"ffprobe"  # или полный путь
HLSFIELD_FFMPEG = r"ffmpeg"  # или полный путь

# Лестница качеств по умолчанию (h x video_bitrate_kbps)
HLSFIELD_DEFAULT_LADDER = [
    {"height": 240, "v_bitrate": 300, "a_bitrate": 64},
    {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
    {"height": 480, "v_bitrate": 1200, "a_bitrate": 96},
    {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
    {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
]

# HLS сегментация
HLSFIELD_SEGMENT_DURATION = 6  # секунд
```

---

## utils.py

```python
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings

FFPROBE = getattr(settings, "HLSFIELD_FFPROBE", "ffprobe")
FFMPEG = getattr(settings, "HLSFIELD_FFMPEG", "ffmpeg")


@contextmanager
def tempdir(prefix: str = "hlsfield_"):
    d = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT: {cp.stdout}\nSTDERR: {cp.stderr}")
    return cp


def ffprobe_streams(input_path: str | os.PathLike) -> dict:
    cmd = [
        FFPROBE, "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(input_path),
    ]
    cp = run(cmd)
    return json.loads(cp.stdout)


def pick_video_audio_streams(info: dict):
    v = a = None
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and v is None:
            v = s
        if s.get("codec_type") == "audio" and a is None:
            a = s
    return v, a


def extract_preview(input_path: Path, out_image: Path, at_sec: float = 3.0):
    cmd = [
        FFMPEG, "-y",
        "-ss", str(at_sec),
        "-i", str(input_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(out_image),
    ]
    run(cmd)


def transcode_hls_variants(
    input_path: Path,
    out_dir: Path,
    ladder: list[dict],
    segment_duration: int = 6,
):
    out_dir.mkdir(parents=True, exist_ok=True)
    variant_infos = []
    for rung in ladder:
        h = int(rung["height"])  # e.g. 720
        vkbps = int(rung["v_bitrate"])  # e.g. 2500
        akbps = int(rung["a_bitrate"])  # e.g. 128
        var_dir = out_dir / f"v{h}"
        var_dir.mkdir(exist_ok=True)
        playlist = var_dir / "index.m3u8"
        cmd = [
            FFMPEG, "-y",
            "-i", str(input_path),
            "-vf", f"scale=w=-2:h={h}:force_original_aspect_ratio=decrease",
            "-c:v", "h264", "-profile:v", "main", "-preset", "veryfast",
            "-b:v", f"{vkbps}k", "-maxrate", f"{int(vkbps * 1.07)}k", "-bufsize", f"{vkbps * 2}k",
            "-c:a", "aac", "-b:a", f"{akbps}k",
            "-f", "hls",
            "-hls_time", str(segment_duration),
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", str(var_dir / "seg_%04d.ts"),
            str(playlist),
        ]
        run(cmd)
        # Примерная ширина (для мастера): читаем первую сегментную плейлист/ffprobe — упростим: ширина ≈ 16:9
        variant_infos.append({
            "height": h,
            "bandwidth": (vkbps + akbps) * 1000,
            "playlist": playlist.name,  # относительный путь внутри var_dir
            "dir": var_dir.name,
            "resolution": f"{int(h * 16 / 9)}x{h}",
        })

    # Пишем master.m3u8
    master = out_dir / "master.m3u8"
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for vi in sorted(variant_infos, key=lambda x: x["height"]):
        lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH={vi['bandwidth']},RESOLUTION={vi['resolution']}")
        lines.append(f"{vi['dir']}/{vi['playlist']}")
    master.write_text("\n".join(lines), encoding="utf-8")
    return master


def save_tree_to_storage(local_root: Path, storage, base_path: str) -> list[str]:
    """Заливает все файлы/папки из temp на Storage.
    Возвращает список относительных путей, сохраненных в сторадже.
    """
    saved_paths: list[str] = []
    for root, _dirs, files in os.walk(local_root):
        for fname in files:
            abs_path = Path(root) / fname
            rel = str(abs_path.relative_to(local_root)).replace("\\", "/")
            key = f"{base_path.rstrip('/')}/{rel}"
            with abs_path.open("rb") as fh:
                storage.save(key, fh)
            saved_paths.append(key)
    return saved_paths


def pull_to_local(storage, name: str, dst_dir: Path) -> Path:
    """Скачать файл из Storage в temp.
    Если storage.path доступен — используем прямой путь.
    """
    try:
        p = Path(storage.path(name))
        if p.exists():
            return p
    except Exception:
        pass

    dst = dst_dir / Path(name).name
    with storage.open(name, "rb") as src, dst.open("wb") as out:
        shutil.copyfileobj(src, out)
    return dst
```

---

## fields.py

```python
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any

from django.core.files.base import File
from django.core.files.storage import Storage
from django.db import models
from django.utils import timezone
from django.conf import settings

from . import utils


class VideoFieldFile(models.fields.files.FieldFile):
    """Расширение FieldFile: после сохранения извлекает метаданные и превью.

    Работает только если поле настроено соответствующими *_field аргументами.
    """

    def _get_sidecar_storage_key(self, suffix: str) -> str:
        base, _ext = os.path.splitext(self.name)
        return f"{base}{suffix}"

    def save(self, name: str, content: File, save: bool = True):
        super().save(name, content, save)
        field: VideoField = self.field  # type: ignore
        inst = self.instance
        # Ничего не делаем, если отключено
        if not getattr(field, "process_on_save", True):
            return

        # В temp — ffprobe + превью
        with utils.tempdir() as td:
            local_path = utils.pull_to_local(self.storage, self.name, td)
            info = utils.ffprobe_streams(local_path)
            v, _a = utils.pick_video_audio_streams(info)
            if field.duration_field and (fmt := info.get("format")):
                dur = fmt.get("duration")
                try:
                    seconds = float(dur)
                    setattr(inst, field.duration_field, dt.timedelta(seconds=seconds))
                except Exception:
                    pass
            if v is not None:
                if field.width_field:
                    setattr(inst, field.width_field, int(v.get("width") or 0))
                if field.height_field:
                    setattr(inst, field.height_field, int(v.get("height") or 0))

            # превью-кадр
            if field.preview_field:
                preview_name = self._get_sidecar_storage_key("_preview.jpg")
                preview_rel = Path(preview_name).name
                preview_tmp = Path(td) / preview_rel
                try:
                    utils.extract_preview(local_path, preview_tmp, at_sec=field.preview_at)
                    with preview_tmp.open("rb") as fh:
                        self.storage.save(preview_name, fh)
                    setattr(inst, field.preview_field, preview_name)
                except Exception:
                    # мягкая ошибка — не роняем сохранение
                    pass

            # Отметим время обработки, если поле задано
            if hasattr(inst, "video_processed_at"):
                setattr(inst, "video_processed_at", timezone.now())

            # Синхронно не сохраняем модель здесь — пусть вызывающий код сам решит.


class VideoField(models.FileField):
    attr_class = VideoFieldFile

    def __init__(
        self,
        *args,
        duration_field: str | None = None,
        width_field: str | None = None,
        height_field: str | None = None,
        preview_field: str | None = None,
        preview_at: float = 3.0,
        process_on_save: bool = True,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.duration_field = duration_field
        self.width_field = width_field
        self.height_field = height_field
        self.preview_field = preview_field
        self.preview_at = preview_at
        self.process_on_save = process_on_save


class HLSVideoFieldFile(VideoFieldFile):
    def save(self, name: str, content: File, save: bool = True):
        super().save(name, content, save)
        field: HLSVideoField = self.field  # type: ignore
        inst = self.instance
        if not getattr(field, "hls_on_save", True):
            return

        # Пробуем отправить Celery-задачу
        try:
            from .tasks import build_hls_for_field
            build_hls_for_field.delay(inst._meta.label, inst.pk, field.attname)
        except Exception:
            # Фоллбэк — синхронно (может занять время)
            from .tasks import build_hls_for_field_sync
            build_hls_for_field_sync(inst._meta.label, inst.pk, field.attname)


class HLSVideoField(VideoField):
    attr_class = HLSVideoFieldFile

    def __init__(
        self,
        *args,
        hls_playlist_field: str | None = None,
        hls_base_subdir: str = "hls",  # подкаталог рядом с оригиналом
        ladder: list[dict] | None = None,
        segment_duration: int | None = None,
        hls_on_save: bool = True,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.hls_playlist_field = hls_playlist_field
        self.hls_base_subdir = hls_base_subdir
        self.ladder = ladder or getattr(settings, "HLSFIELD_DEFAULT_LADDER", [])
        self.segment_duration = segment_duration or getattr(settings, "HLSFIELD_SEGMENT_DURATION", 6)
        self.hls_on_save = hls_on_save
```

---

## tasks.py (Celery)

```python
from __future__ import annotations

import importlib
import os
from pathlib import Path

from celery import shared_task

from django.apps import apps
from django.db import transaction

from . import utils


def _resolve_field(instance, field_name: str):
    field = instance._meta.get_field(field_name)
    file = getattr(instance, field_name)
    storage = file.storage
    name = file.name
    return field, file, storage, name


def _hls_out_base(name: str, subdir: str) -> str:
    base, _ext = os.path.splitext(name)
    return f"{base}/{subdir}/"  # каталог для HLS-артефактов в Storage


@shared_task
def build_hls_for_field(model_label: str, pk: int | str, field_name: str):
    build_hls_for_field_sync(model_label, pk, field_name)


def build_hls_for_field_sync(model_label: str, pk: int | str, field_name: str):
    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)

    # Выгружаем оригинал в temp, строим HLS в temp/ и заливаем в Storage
    with utils.tempdir() as td:
        local_input = utils.pull_to_local(storage, name, td)
        local_hls_root = Path(td) / "hls_out"
        local_hls_root.mkdir(parents=True, exist_ok=True)
        master = utils.transcode_hls_variants(
            input_path=local_input,
            out_dir=local_hls_root,
            ladder=getattr(field, "ladder"),
            segment_duration=getattr(field, "segment_duration"),
        )
        base_key = _hls_out_base(name, getattr(field, "hls_base_subdir"))
        saved = utils.save_tree_to_storage(local_hls_root, storage, base_key)
        # Ищем путь к master
        master_key = base_key + master.name

    # Сохраняем путь к master.m3u8 в указанный CharField/TextField
    playlist_field = getattr(field, "hls_playlist_field", None)
    if playlist_field:
        setattr(instance, playlist_field, master_key)

    # Обновляем «время обработки», если есть
    if hasattr(instance, "hls_built_at"):
        from django.utils import timezone
        instance.hls_built_at = timezone.now()

    # Пишем в БД
    with transaction.atomic():
        instance.save(update_fields=[
            playlist_field
        ] if playlist_field else None)
```

---

## widgets.py (для админки)

```python
from django.forms.widgets import ClearableFileInput
from django.utils.safestring import mark_safe


class AdminVideoWidget(ClearableFileInput):
    template_name = ""

    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        if value and hasattr(value, "url"):
            html += mark_safe(
                f'<div style="margin-top:8px">\n'
                f'  <video src="{value.url}" controls preload="metadata" style="max-width: 480px; width:100%"></video>\n'
                f'</div>'
            )
        return html
```

---

## players/hls\_player.html (пример фронтенда с выбором качества)

```html
{% load static %}
<div id="video-wrap" style="max-width: 960px">
    <video id="video" controls playsinline style="width: 100%;"></video>
    <div style="margin:8px 0">
        <label>Качество:</label>
        <select id="quality"></select>
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<script>
    (function () {
        const src = "{{ hls_url }}"; // путь к master.m3u8 из БД
        const video = document.getElementById('video');
        const sel = document.getElementById('quality');
        if (Hls.isSupported()) {
            const hls = new Hls();
            hls.loadSource(src);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, function () {
                // Заполним список уровней
                sel.innerHTML = '';
                const auto = document.createElement('option');
                auto.value = '-1';
                auto.text = 'Auto';
                sel.appendChild(auto);
                hls.levels.forEach((lvl, i) => {
                    const o = document.createElement('option');
                    o.value = i;
                    o.text = (lvl.height || '?') + 'p';
                    sel.appendChild(o);
                });
                sel.addEventListener('change', () => {
                    hls.currentLevel = parseInt(sel.value, 10);
                });
            });
        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
            // Safari
            video.src = src;
        } else {
            document.getElementById('video-wrap').innerHTML = '<p>Ваш браузер не поддерживает HLS.</p>';
        }
    })();
</script>
```

---

## Пример модели и админки

```python
# models.py
from django.db import models
from apps.hlsfield.fields import HLSVideoField


class Lecture(models.Model):
    title = models.CharField(max_length=255)

    # сайдкары (куда Video/HLSField будет писать метаданные и превью)
    duration = models.DurationField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    preview = models.ImageField(upload_to="video_previews/", null=True, blank=True)

    # HLS master (путь в storage)
    hls_master = models.CharField(max_length=500, null=True, blank=True)

    # основное поле видео (оригинал)
    video = HLSVideoField(
        upload_to="videos/",
        duration_field="duration",
        width_field="width",
        height_field="height",
        preview_field="preview",
        hls_playlist_field="hls_master",
        # ladder / segment_duration можно переопределить тут
    )

    video_processed_at = models.DateTimeField(null=True, blank=True)
    hls_built_at = models.DateTimeField(null=True, blank=True)

    def hls_url(self):
        # У вас может быть S3 и т.п. — используйте storage.url
        # Здесь для простоты предполагаем default storage with .url
        from django.core.files.storage import default_storage
        if self.hls_master:
            try:
                return default_storage.url(self.hls_master)
            except Exception:
                return None
        return None
```

```python
# admin.py
from django.contrib import admin
from .models import Lecture
from apps.hlsfield.widgets import AdminVideoWidget
from django import forms


class LectureAdminForm(forms.ModelForm):
    class Meta:
        model = Lecture
        fields = "__all__"
        widgets = {
            "video": AdminVideoWidget,
        }


@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    form = LectureAdminForm
    list_display = ("id", "title", "duration", "hls_built_at")
```

---

## Пример шаблона просмотра

```django
{# templates/lecture_detail.html #}
{% extends "base.html" %}
{% block content %}
  <h1>{{ object.title }}</h1>
  {% if object.hls_url %}
    {% include "apps/hlsfield/players/hls_player.html" with hls_url=object.hls_url %}
  {% else %}
    <p>Видео ещё обрабатывается…</p>
  {% endif %}
{% endblock %}
```

---

## Заметки по продакшену

* **Кодеки**: для совместимости используем H.264/AAC. Если нужен HEVC/AV1 — добавьте флаги в
  `utils.transcode_hls_variants`.
* **S3/MinIO**: будет работать «из коробки», так как все артефакты сохраняются через `storage.save()`.
* **Без дублирования**: оригинал хранится один; фронтенд воспроизводит HLS, набор «кусков» на разных битрейтах — это не
  «полные копии», а сегменты для адаптивного стриминга.
* **Транскодирование в фоне**: используйте Celery + отдельный воркер. В админке/вью можно показать статус
  `hls_built_at`.
* **Очистка**: по сигналу `post_delete` модели удаляйте оригинал и директорию HLS-артефактов (реализуйте при
  необходимости).
* **Безопасность**: для приватного доступа отдавайте HLS через подписанные URL (S3, Nginx/X-Accel, CloudFront).

---

## TODO / Идеи

* Валидация MIME через `python-magic`.
* Генерация WebVTT-сабов для предпросмотра (sprite) и таймкодов.
* Генерация DASH (mpd) параллельно HLS.
* Пул воркеров ffmpeg, лимиты CPU/GPU.

````
# settings.py
HLSFIELD_DEFAULT_UPLOAD_TO = "hlsfield.upload_to.video_upload_to"
HLSFIELD_SIDECAR_LAYOUT = "nested"  # по умолчанию и так nested в моём примере



---

## Быстрый старт: Model + Admin + Views + URLs + Templates

Ниже — минимальный набор кода, чтобы **сразу загрузить видео** и посмотреть HLS в браузере без плясок с бубном.

> Предполагаем, что пакет `django-hlsfield` уже установлен, а в системе есть `ffmpeg/ffprobe` в PATH.

### 0) settings.py
```python
INSTALLED_APPS = [
    # ...
    "django.contrib.staticfiles",
    "hlsfield",   # наше приложение-пакет
    "video",      # ваше app с моделью Lecture
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# (опционально) указать явные пути к бинарям
HLSFIELD_FFPROBE = "ffprobe"
HLSFIELD_FFMPEG  = "ffmpeg"
````

### 1) models.py

```python
from django.db import models
from hlsfield.fields import HLSVideoField


class Lecture(models.Model):
    title = models.CharField(max_length=255)
    video = HLSVideoField(upload_to="videos/", hls_playlist_field="hls_master")
    hls_master = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return self.title
```

### 2) admin.py

```python
from django.contrib import admin
from .models import Lecture


@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    list_display = ("id", "title")
```

> Можно красиво врезать плеер и в админке, если захотите, через `hlsfield.widgets.AdminVideoWidget`.

### 3) views.py (в app `video`)

```python
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView
from django import forms
from .models import Lecture


class LectureForm(forms.ModelForm):
    class Meta:
        model = Lecture
        fields = ["title", "video"]


class LectureCreateView(CreateView):
    model = Lecture
    form_class = LectureForm
    template_name = "video/upload.html"

    def get_success_url(self):
        return reverse("video:detail", args=[self.object.pk])


class LectureDetailView(DetailView):
    model = Lecture
    template_name = "video/detail.html"


class LectureListView(ListView):
    model = Lecture
    template_name = "video/list.html"
    paginate_by = 20
```

### 4) urls.py (в app `video`)

```python
from django.urls import path
from .views import LectureCreateView, LectureDetailView, LectureListView

app_name = "video"

urlpatterns = [
    path("upload/", LectureCreateView.as_view(), name="upload"),
    path("<int:pk>/", LectureDetailView.as_view(), name="detail"),
    path("", LectureListView.as_view(), name="list"),
]
```

### 5) Корневой urls.py (проекта)

```python
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("video.urls", namespace="video")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### 6) Шаблоны

Создайте папки:

```
video/templates/video/
```

**`video/templates/video/base.html`** (примитивный каркас)

```html
<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>{% block title %}Видео{% endblock %}</title>
    <style>body {
        font-family: system-ui, sans-serif;
        margin: 2rem auto;
        max-width: 960px
    }</style>
</head>
<body>
<nav><a href="{% url 'video:list' %}">Список</a> · <a href="{% url 'video:upload' %}">Загрузить</a></nav>
<hr/>
{% block content %}{% endblock %}
</body>
</html>
```

**`video/templates/video/upload.html`**

```html
{% extends "video/base.html" %}
{% block title %}Загрузка{% endblock %}
{% block content %}
<h1>Загрузить видео</h1>
<form method="post" enctype="multipart/form-data">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Сохранить</button>
</form>
<p>Совет: для проверки возьми небольшой файл (5–20 МБ), иначе без Celery запрос будет дольше.</p>
{% endblock %}
```

**`video/templates/video/detail.html`**

```html
{% extends "video/base.html" %}
{% block title %}{{ object.title }}{% endblock %}
{% block content %}
<h1>{{ object.title }}</h1>
{% if object.video.master_url %}
{% include "hlsfield/players/hls_player.html" with hls_url=object.video.master_url %}
{% else %}
<p>Видео ещё обрабатывается… Обновите страницу через минуту.</p>
{% endif %}
{% endblock %}
```

**`video/templates/video/list.html`**

```html
{% extends "video/base.html" %}
{% block title %}Список{% endblock %}
{% block content %}
<h1>Лекции</h1>
<ul>
    {% for obj in object_list %}
    <li><a href="{% url 'video:detail' obj.pk %}">{{ obj.title }}</a></li>
    {% empty %}
    <li>Пока пусто. <a href="{% url 'video:upload' %}">Загрузите первое видео</a>.</li>
    {% endfor %}
</ul>
{% endblock %}
```

### 7) Миграции и запуск

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser  # по желанию
python manage.py runserver
```

Затем открой:

* загрузка: `http://127.0.0.1:8000/upload/`
* список: `http://127.0.0.1:8000/`

> **Как это работает:** при сохранении `Lecture` поле `HLSVideoField` создаёт превью и метаданные; HLS-генерация
> запускается после `post_save` (когда объект уже имеет `pk`). Если Celery не установлен — выполняется синхронно, но уже *
*после** того, как объект записан в БД.
