from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import ImageFormSet, ImageGroupForm
from .models import ImageGroup


def _accept_layer_response():
    """Return a response that tells Unpoly to close the current modal layer."""
    response = HttpResponse(status=204)
    response['X-Up-Accept-Layer'] = 'null'
    return response


def image_group_list(request):
    groups = ImageGroup.objects.prefetch_related('images').all()
    return render(request, 'media_library/image_group_list.html', {'groups': groups})


def image_group_create(request):
    if request.method == 'POST':
        form = ImageGroupForm(request.POST)
        formset = ImageFormSet(request.POST, request.FILES)
        if form.is_valid() and formset.is_valid():
            group = form.save()
            formset.instance = group
            formset.save()
            return _accept_layer_response()
    else:
        form = ImageGroupForm()
        formset = ImageFormSet()
    return render(request, 'media_library/image_group_form.html', {
        'form': form,
        'formset': formset,
        'is_edit': False,
    })


def image_group_edit(request, pk):
    group = get_object_or_404(ImageGroup, pk=pk)
    if request.method == 'POST':
        form = ImageGroupForm(request.POST, instance=group)
        formset = ImageFormSet(request.POST, request.FILES, instance=group)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return _accept_layer_response()
    else:
        form = ImageGroupForm(instance=group)
        formset = ImageFormSet(instance=group)
    return render(request, 'media_library/image_group_form.html', {
        'form': form,
        'formset': formset,
        'group': group,
        'is_edit': True,
    })


@require_POST
def image_group_delete(request, pk):
    group = get_object_or_404(ImageGroup, pk=pk)
    group.delete()
    response = redirect(reverse('media_library:image_group_list'))
    response['X-Up-Events'] = '[{"type":"media_library:changed"}]'
    return response
