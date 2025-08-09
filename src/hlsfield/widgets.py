from django.forms.widgets import ClearableFileInput
from django.utils.safestring import mark_safe

class AdminVideoWidget(ClearableFileInput):
    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        if value and hasattr(value, "url"):
            html += mark_safe(
                '<div style="margin-top:8px">'
                f'<video src="{value.url}" controls preload="metadata" style="max-width: 480px; width:100%"></video>'
                '</div>'
            )
        return html
