from django import forms
from django.forms import inlineformset_factory

from .models import (
    SocialMediaPost,
    SocialMediaPostPlatform,
    SocialMediaPostMedia,
)
class SocialMediaPostForm(forms.ModelForm):
    class Meta:
        model = SocialMediaPost
        fields = ['title', 'shared_text', 'topic', 'post_type', 'ai_instruction']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Post title…',
            }),
            'shared_text': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 5,
                'placeholder': 'Write your post content…',
                'id': 'id_shared_text',
                'x-model': 'sharedText',
            }),
            'topic': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Post topic…',
            }),
            'post_type': forms.Select(attrs={
                'class': 'select select-bordered w-full',
            }),
            'ai_instruction': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 2,
                'placeholder': 'Additional instructions for AI…',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].required = False


class SocialMediaPostPlatformForm(forms.ModelForm):
    class Meta:
        model = SocialMediaPostPlatform
        fields = ['platform', 'use_shared_text', 'override_text', 'use_shared_media']
        widgets = {
            'platform': forms.HiddenInput(),
            'use_shared_text': forms.CheckboxInput(attrs={'class': 'checkbox checkbox-primary use-shared-text-toggle'}),
            'override_text': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full override-text-field',
                'rows': 5,
                'placeholder': 'Override text for this platform…',
            }),
            'use_shared_media': forms.CheckboxInput(attrs={'class': 'checkbox checkbox-primary use-shared-media-toggle'}),
        }


PlatformFormSet = inlineformset_factory(
    SocialMediaPost,
    SocialMediaPostPlatform,
    form=SocialMediaPostPlatformForm,
    extra=0,
    can_delete=False,
)


class SharedMediaForm(forms.ModelForm):
    class Meta:
        model = SocialMediaPostMedia
        fields = ['image', 'sort_order']
        widgets = {
            'image': forms.Select(attrs={'class': 'select select-bordered w-full'}),
            'sort_order': forms.HiddenInput(),
        }


SharedMediaFormSet = inlineformset_factory(
    SocialMediaPost,
    SocialMediaPostMedia,
    form=SharedMediaForm,
    extra=0,
    can_delete=True,
)
