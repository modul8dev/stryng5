from django import forms

from media_library.models import ImageGroup

from .models import Brand

class BrandForm(forms.ModelForm):
    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project is not None:
            self.fields['logo'].queryset = ImageGroup.objects.filter(project=project)
        else:
            self.fields['logo'].queryset = ImageGroup.objects.none()
        self.fields['logo'].required = False
        self.fields['logo'].empty_label = '— None —'
        self.fields['logo'].widget.attrs.update({'class': 'select select-bordered w-full'})

    class Meta:
        model = Brand
        fields = ['name', 'website_url', 'summary', 'style_guide', 'tone_of_voice', 'target_audience', 'fonts', 'primary_color', 'secondary_color', 'logo']
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
            'style_guide': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'placeholder': 'Tone of voice, visual style, messaging principles…',
                'rows': 5,
            }),
            'tone_of_voice': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'placeholder': 'Describe how your brand communicates…',
                'rows': 3,
            }),
            'target_audience': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'placeholder': 'Who is your ideal customer?',
                'rows': 3,
            }),
            'fonts': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'e.g. Inter (headings), Lora (body)',
            }),
            'primary_color': forms.TextInput(attrs={
                'class': 'input input-bordered w-full font-mono',
                'placeholder': '#3B82F6',
                'maxlength': '7',
            }),
            'secondary_color': forms.TextInput(attrs={
                'class': 'input input-bordered w-full font-mono',
                'placeholder': '#6366F1',
                'maxlength': '7',
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
