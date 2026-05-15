from .models import Project


class ProjectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            project = None

            # Query parameter takes priority — allows per-tab/deep-link switching
            param_project_id = request.GET.get('project_id')
            if param_project_id:
                project = Project.objects.filter(
                    pk=param_project_id, owner=request.user
                ).first()
                if project:
                    request.session['active_project_id'] = project.pk

            # Fall back to session
            if project is None:
                project_id = request.session.get('active_project_id')
                if project_id:
                    project = Project.objects.filter(
                        pk=project_id, owner=request.user
                    ).first()

            # Fall back to first project or create one
            if project is None:
                project = Project.objects.filter(owner=request.user).first()
                if project is None:
                    project = Project.objects.create(
                        owner=request.user,
                        name=request.user.company_name or 'My Project',
                    )
                request.session['active_project_id'] = project.pk

            request.project = project
        else:
            request.project = None

        return self.get_response(request)
