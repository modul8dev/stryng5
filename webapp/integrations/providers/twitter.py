import requests as http_requests
from datetime import timedelta

from django.utils import timezone

from ..models import IntegrationConnection
from ..oauth import oauth
from .base import BaseProvider

TWITTER_API_BASE = 'https://api.twitter.com/2'


class TwitterProvider(BaseProvider):
    """
    Twitter / X — OAuth 2.0 with PKCE (Twitter API v2).
    Single user account per auth, no selection step needed.
    """

    key = 'twitter'
    display_name = 'X (Twitter)'
    category = 'social_media'

    icon_svg = (
        '<svg class="size-6" viewBox="0 0 24 24" fill="currentColor">'
        '<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17'
        'l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08'
        'l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>'
    )

    has_account_selection = False

    def handle_callback(self, request):
        token = oauth.twitter.authorize_access_token(request)
        return token

    def list_accounts(self, token_data):
        """Fetch the authenticated Twitter user's profile."""
        resp = http_requests.get(
            f'{TWITTER_API_BASE}/users/me',
            headers={'Authorization': f"Bearer {token_data.get('access_token', '')}"},
            params={'user.fields': 'id,name,username,profile_image_url'},
            timeout=15,
        )
        resp.raise_for_status()
        user = resp.json().get('data', {})
        return [{
            'id': user['id'],
            'name': f"@{user.get('username', user['id'])}",
            'username': user.get('username', ''),
            'display_name': user.get('name', ''),
            'picture_url': user.get('profile_image_url', '').replace('_normal', ''),
        }]

    def save_connection(self, user, selected_account, token_data, project=None):
        expires_in = token_data.get('expires_in')
        expires_at = timezone.now() + timedelta(seconds=expires_in) if expires_in else None

        conn, _created = IntegrationConnection.objects.update_or_create(
            project=project,
            provider=self.key,
            external_account_id=selected_account['id'],
            defaults={
                'user': user,
                'provider_category': self.category,
                'external_account_name': selected_account['name'],
                'access_token': token_data.get('access_token', ''),
                'refresh_token': token_data.get('refresh_token', ''),
                'token_expires_at': expires_at,
                'scopes': token_data.get('scope', ''),
                'status': IntegrationConnection.ConnectionStatus.ACTIVE,
                'metadata': {
                    'username': selected_account.get('username', ''),
                    'display_name': selected_account.get('display_name', ''),
                    'picture_url': selected_account.get('picture_url', ''),
                },
            },
        )
        return conn
