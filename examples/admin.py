from django.contrib import admin
from .models import SimpleVideo, HLSVideo, DASHVideo, AdaptiveVideo


@admin.register(SimpleVideo)
class SimpleVideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'duration', 'width', 'height']
    readonly_fields = ['duration', 'width', 'height', 'preview']


@admin.register(HLSVideo)
class HLSVideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'hls_master']
    readonly_fields = ['hls_master']


@admin.register(DASHVideo)
class DASHVideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'dash_manifest']
    readonly_fields = ['dash_manifest']


@admin.register(AdaptiveVideo)
class AdaptiveVideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'hls_master', 'dash_manifest']
    readonly_fields = ['hls_master', 'dash_manifest']
