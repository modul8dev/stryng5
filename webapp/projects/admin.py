from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import path
from django.utils.html import format_html

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'enable_autopost', 'created_at', 'trigger_autopost_btn')
    list_filter = ('created_at', 'enable_autopost')
    search_fields = ('name', 'owner__email')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:project_id>/trigger-autopost/',
                self.admin_site.admin_view(self.trigger_autopost_view),
                name='projects_trigger_autopost',
            ),
        ]
        return custom_urls + urls

    def trigger_autopost_view(self, request, project_id):
        from django_q.tasks import async_task
        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            self.message_user(request, f'Project {project_id} not found.', level='error')
            return HttpResponseRedirect('../../')
        async_task('social_media.tasks.autopost_project_task', project_id)
        self.message_user(request, f'Autopost task enqueued for "{project.name}".')
        return HttpResponseRedirect('../../')

    @admin.display(description='Trigger Autopost')
    def trigger_autopost_btn(self, obj):
        url = f'{obj.pk}/trigger-autopost/'
        return format_html('<a class="button" href="{}">Run now</a>', url)
