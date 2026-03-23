from django import forms
from django.forms import inlineformset_factory

from .models import ImageGroup, Image


class ImageGroupForm(forms.ModelForm):
    class Meta:
        model = ImageGroup
        fields = ['title', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Group title',
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'placeholder': 'Description (optional)',
                'rows': 3,
            }),
        }


ImageFormSet = inlineformset_factory(
    ImageGroup,
    Image,
    fields=['image'],
    extra=0,
    can_delete=True,
    widgets={
        'image': forms.FileInput(attrs={
            'class': 'file-input file-input-ghost w-full',
            'accept': 'image/*',
        }),
    },
)
