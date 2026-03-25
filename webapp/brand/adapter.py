from allauth.account.adapter import DefaultAccountAdapter


class BrandAccountAdapter(DefaultAccountAdapter):
    def get_signup_redirect_url(self, request):
        return '/brand/onboarding/'
