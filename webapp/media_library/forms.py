from django import forms
from django.forms import inlineformset_factory

from .models import MediaGroup, Media

# Max video size: 512 MB (Twitter's limit, the most permissive we allow)
MAX_VIDEO_SIZE_MB = 512
MAX_VIDEO_SIZE_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024


class MediaGroupForm(forms.ModelForm):
    class Meta:
        model = MediaGroup
        fields = ['title', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Group title',
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'placeholder': 'Description (optional)',
                'style': 'field-sizing: content; max-height: calc(10lh + 1rem); overflow-y: auto;',
            }),
        }


class MediaFileInput(forms.ClearableFileInput):
    """File input that accepts media and videos, with client-side size validation."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('attrs', {}).update({
            'class': 'file-input file-input-ghost w-full',
            'accept': 'image/*,video/*',
            'data-max-video-bytes': str(MAX_VIDEO_SIZE_BYTES),
        })
        super().__init__(*args, **kwargs)


def validate_media_file_size(file):
    """Server-side validation: reject video files over MAX_VIDEO_SIZE_BYTES."""
    if file and hasattr(file, 'size'):
        from pathlib import PurePosixPath
        from .models import VIDEO_EXTENSIONS
        ext = PurePosixPath(file.name).suffix.lower()
        if ext in VIDEO_EXTENSIONS and file.size > MAX_VIDEO_SIZE_BYTES:
            raise forms.ValidationError(
                f'Video file size must not exceed {MAX_VIDEO_SIZE_MB} MB '
                f'(uploaded: {file.size // (1024 * 1024)} MB).'
            )


class MediaForm(forms.ModelForm):
    class Meta:
        model = Media
        fields = ['file', 'external_url']
        widgets = {
            'file': MediaFileInput(),
            'external_url': forms.HiddenInput(),
        }

    def clean_file(self):
        f = self.cleaned_data.get('file')
        from django.core.files.uploadedfile import UploadedFile
        if isinstance(f, UploadedFile):
            validate_media_file_size(f)
        return f


MediaFormSet = inlineformset_factory(
    MediaGroup,
    Media,
    form=MediaForm,
    extra=0,
    can_delete=True,
)


