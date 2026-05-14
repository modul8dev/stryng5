from django import forms

from .models import (
    SocialMediaPost,
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
