from django import forms
from django.forms import inlineformset_factory

from .models import (
    SocialMediaSettings,
    SocialMediaPost,
    SocialMediaPostPlatform,
    SocialMediaPostMedia,
)


class SocialMediaSettingsForm(forms.ModelForm):
    class Meta:
        model = SocialMediaSettings
        fields = ['enable_linkedin', 'enable_x', 'enable_facebook', 'enable_instagram']
        widgets = {
            'enable_linkedin': forms.CheckboxInput(attrs={'class': 'checkbox checkbox-primary'}),
            'enable_x': forms.CheckboxInput(attrs={'class': 'checkbox checkbox-primary'}),
            'enable_facebook': forms.CheckboxInput(attrs={'class': 'checkbox checkbox-primary'}),
            'enable_instagram': forms.CheckboxInput(attrs={'class': 'checkbox checkbox-primary'}),
        }


class SocialMediaPostForm(forms.ModelForm):
    class Meta:
        model = SocialMediaPost
        fields = ['title', 'shared_text', 'scheduled_at', 'topic', 'post_type', 'ai_instruction']
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
            'scheduled_at': forms.DateTimeInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'datetime-local',
            }, format='%Y-%m-%dT%H:%M'),
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
        self.fields['scheduled_at'].required = False
        if self.instance and self.instance.scheduled_at:
            self.initial['scheduled_at'] = self.instance.scheduled_at.strftime('%Y-%m-%dT%H:%M')


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
