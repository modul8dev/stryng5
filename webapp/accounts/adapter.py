from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


def _needs_onboarding(user):
    from brand.models import Brand
    from projects.models import Project

    project = Project.objects.filter(owner=user).first()
    if project is None:
        return True
    try:
        brand = Brand.objects.get(project=project)
        return not brand.has_data
    except Brand.DoesNotExist:
        return True

onboarding_url = '/brand/onboarding/'

class AccountAdapter(DefaultAccountAdapter):
    def get_signup_redirect_url(self, request):
        return onboarding_url

    def get_login_redirect_url(self, request):
        if _needs_onboarding(request.user):
            return onboarding_url
        return super().get_login_redirect_url(request)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # This is where allauth hides the redirect for social flows
        if _needs_onboarding(sociallogin.user):
            sociallogin.state['next'] = onboarding_url
