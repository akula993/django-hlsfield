from __future__ import annotations

import datetime as dt
import json
import os
from importlib import import_module
from pathlib import Path
from typing import Any, Optional

from django.core.files.base import File
from django.db import models
from django.utils import timezone

from . import defaults, utils

META_SUFFIX = "_meta.json"
PREVIEW_SUFFIX = "_preview.jpg"


class VideoFieldFile(models.fields.files.FieldFile):
    def _base_key(self) -> str:
        base, _ext = os.path.splitext(self.name);
        return base

    def _sidecar_dir_key(self) -> str:
        # videos/foo -> videos/foo  (используем для nested)
        return self._base_key()

    def _meta_key(self) -> str:
        field: VideoField = self.field  # type: ignore
        if field.sidecar_layout == "nested":
            return f"{self._sidecar_dir_key()}/{field.meta_filename}"
        return f"{self._base_key()}{META_SUFFIX}"

    def _preview_key(self) -> str:
        field: VideoField = self.field  # type: ignore
        if field.sidecar_layout == "nested":
            return f"{self._sidecar_dir_key()}/{field.preview_filename}"
        return f"{self._base_key()}{PREVIEW_SUFFIX}"

    def metadata(self) -> dict:
        field: VideoField = self.field  # type: ignore
        inst = self.instance
        have_model_fields = any([field.duration_field, field.width_field, field.height_field, field.preview_field])
        if have_model_fields:
            out = {}
            if field.duration_field:
                dur = getattr(inst, field.duration_field, None)
                if isinstance(dur, dt.timedelta):
                    out["duration_seconds"] = int(dur.total_seconds())
            if field.width_field:  out["width"] = getattr(inst, field.width_field, None)
            if field.height_field: out["height"] = getattr(inst, field.height_field, None)
            if field.preview_field: out["preview_name"] = getattr(inst, field.preview_field, None)
            return out
        try:
            with self.storage.open(self._meta_key(), "r") as fh:
                return json.loads(fh.read())
        except Exception:
            return {}

    def preview_url(self) -> Optional[str]:
        field: VideoField = self.field  # type: ignore
        inst = self.instance
        if field.preview_field:
            name = getattr(inst, field.preview_field, None)
            if name:
                try:
                    return self.storage.url(name)
                except Exception:
                    return None
        try:
            if self.storage.exists(self._preview_key()):
                return self.storage.url(self._preview_key())
        except Exception:
            pass
        return None

    def master_url(self) -> Optional[str]:
        field: VideoField = self.field  # type: ignore
        inst = self.instance
        playlist_field = getattr(field, "hls_playlist_field", None)
        if playlist_field:
            name = getattr(inst, playlist_field, None)
            if name:
                try:
                    return self.storage.url(name)
                except Exception:
                    return None
        return None

    def save(self, name: str, content: File, save: bool = True):
        super().save(name, content, save)
        field: VideoField = self.field  # type: ignore
        inst = self.instance
        if not getattr(field, "process_on_save", True):
            return
        with utils.tempdir() as td:
            local_path = utils.pull_to_local(self.storage, self.name, td)
            info = utils.ffprobe_streams(local_path)
            v, _a = utils.pick_video_audio_streams(info)
            meta = {}
            if (fmt := info.get("format")):
                dur = fmt.get("duration")
                try:
                    meta["duration_seconds"] = int(float(dur))
                except Exception:
                    pass
            if v is not None:
                try:
                    meta["width"] = int(v.get("width") or 0)
                    meta["height"] = int(v.get("height") or 0)
                except Exception:
                    pass
            if field.duration_field and "duration_seconds" in meta:
                setattr(inst, field.duration_field, dt.timedelta(seconds=meta["duration_seconds"]))
            if field.width_field and "width" in meta:
                setattr(inst, field.width_field, meta["width"])
            if field.height_field and "height" in meta:
                setattr(inst, field.height_field, meta["height"])

            # превью
            preview_tmp = Path(td) / "preview.jpg"
            try:
                utils.extract_preview(local_path, preview_tmp, at_sec=field.preview_at)
                with preview_tmp.open("rb") as fh:
                    self.storage.save(self._preview_key(), fh)
                meta["preview_name"] = self._preview_key()
                if field.preview_field:
                    setattr(inst, field.preview_field, self._preview_key())
            except Exception:
                pass

            # JSON sidecar, если явные поля модели не используются
            if not any([field.duration_field, field.width_field, field.height_field, field.preview_field]):
                try:
                    payload = json.dumps(meta, ensure_ascii=False)
                    from io import StringIO
                    self.storage.save(self._meta_key(), StringIO(payload))
                except Exception:
                    pass

            if hasattr(inst, "video_processed_at"):
                setattr(inst, "video_processed_at", timezone.now())


class VideoField(models.FileField):
    attr_class = VideoFieldFile

    def __init__(self, *args,
                 duration_field: str | None = None,
                 width_field: str | None = None,
                 height_field: str | None = None,
                 preview_field: str | None = None,
                 preview_at: float = 3.0,
                 process_on_save: bool = True,
                 sidecar_layout: str | None = None,  # "flat" | "nested"
                 preview_filename: str | None = None,  # used if nested
                 meta_filename: str | None = None,  # used if nested
                 use_default_upload_to: bool | None = None,
                 **kwargs: Any,
                 ):

        # ---- Авто-логика upload_to ----
        explicit_upload_to = kwargs.get("upload_to", None)
        has_explicit = bool(explicit_upload_to)  # callable/str → True; None/""/False → False

        # Если поле уже получило явный upload_to – уважим его и не трогаем
        if not has_explicit:
            # Решаем, включать ли дефолт
            use_flag = defaults.USE_DEFAULT_UPLOAD_TO if use_default_upload_to is None else bool(use_default_upload_to)
            if use_flag:
                # 1) пробуем dotted-path из настроек
                fn = None
                if getattr(defaults, "DEFAULT_UPLOAD_TO_PATH", None):
                    try:
                        mod_path, func_name = defaults.DEFAULT_UPLOAD_TO_PATH.rsplit(".", 1)
                        fn = getattr(import_module(mod_path), func_name)
                    except Exception:
                        fn = None
                # 2) если нет – пакетный фоллбэк
                kwargs["upload_to"] = fn or defaults.default_upload_to
            # else: оставляем как есть (пусть Django кладёт по умолчанию)
        # ---- конец авто-логики ----

        super().__init__(*args, **kwargs)
        self.duration_field = duration_field
        self.width_field = width_field
        self.height_field = height_field
        self.preview_field = preview_field
        self.preview_at = preview_at
        self.process_on_save = process_on_save
        # дефолты nested/имён
        self.sidecar_layout  = sidecar_layout  or defaults.SIDECAR_LAYOUT
        self.preview_filename = preview_filename or defaults.PREVIEW_FILENAME
        self.meta_filename    = meta_filename    or defaults.META_FILENAME


class HLSVideoFieldFile(VideoFieldFile):
    def save(self, name: str, content: File, save: bool = True):
        super().save(name, content, save)
        field: HLSVideoField = self.field  # type: ignore
        inst = self.instance
        if not getattr(field, "hls_on_save", True):
            return
        # если pk ещё нет — отложим до post_save
        if getattr(inst, "pk", None) is None:
            setattr(inst, f"__hls_pending__{field.attname}", True)
            return
        field._trigger_hls(inst)


class HLSVideoField(VideoField):
    attr_class = HLSVideoFieldFile

    def __init__(self, *args,
                 hls_playlist_field: str | None = None,
                 hls_base_subdir: str | None = None,
                 ladder: list[dict] | None = None,
                 segment_duration: int | None = None,
                 hls_on_save: bool = True,
                 **kwargs: Any,
                 ):
        super().__init__(*args, **kwargs)
        self.hls_playlist_field = hls_playlist_field
        self.hls_base_subdir = hls_base_subdir or defaults.HLS_SUBDIR
        self.ladder = ladder or defaults.DEFAULT_LADDER
        self.segment_duration = segment_duration or defaults.SEGMENT_DURATION
        self.hls_on_save = hls_on_save

    def contribute_to_class(self, cls, name, **kwargs):
        super().contribute_to_class(cls, name, **kwargs)
        self.attname = name
        from django.db.models.signals import post_save
        def _handler(sender, instance, created, **kw):
            if getattr(instance, f"__hls_pending__{name}", False):
                setattr(instance, f"__hls_pending__{name}", False)
                try:
                    self._trigger_hls(instance)
                except Exception:
                    # не роняем админку
                    pass

        post_save.connect(_handler, sender=cls, weak=False)

    def _trigger_hls(self, instance):
        try:
            from .tasks import build_hls_for_field, build_hls_for_field_sync
            if hasattr(build_hls_for_field, "delay"):
                build_hls_for_field.delay(instance._meta.label, instance.pk, self.attname)
            else:
                build_hls_for_field_sync(instance._meta.label, instance.pk, self.attname)
        except Exception:
            from .tasks import build_hls_for_field_sync
            build_hls_for_field_sync(instance._meta.label, instance.pk, self.attname)
