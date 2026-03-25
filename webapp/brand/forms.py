from django import forms

from media_library.models import ImageGroup

from .models import Brand


class BrandForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['logo'].queryset = ImageGroup.objects.filter(user=user)
        else:
            self.fields['logo'].queryset = ImageGroup.objects.none()
        self.fields['logo'].required = False
        self.fields['logo'].empty_label = '— None —'
        self.fields['logo'].widget.attrs.update({'class': 'select select-bordered w-full'})

    class Meta:
        model = Brand
        fields = ['name', 'website_url', 'summary', 'language', 'style_guide', 'logo']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Your brand name',
            }),
            'website_url': forms.URLInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'https://yourbrand.com',
            }),
            'summary': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'placeholder': 'A short description of your brand…',
                'rows': 3,
            }),
            'language': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'e.g. English, French…',
            }),
            'style_guide': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'placeholder': 'Tone of voice, visual style, messaging principles…',
                'rows': 5,
            }),
        }


class ScrapeURLForm(forms.Form):
    url = forms.URLField(
        widget=forms.URLInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'https://yourbrand.com',
        }),
        label='Brand Website URL',
    )
