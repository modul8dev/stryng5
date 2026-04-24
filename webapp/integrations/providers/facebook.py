import requests as http_requests

from ..models import IntegrationConnection
from ..oauth import oauth
from .base import BaseProvider

GRAPH_API_BASE = 'https://graph.facebook.com/v22.0'


class FacebookProvider(BaseProvider):
    key = 'facebook'
    display_name = 'Facebook'
    category = 'social_media'

    icon_svg = (
        '<svg class="size-6" viewBox="0 0 24 24" fill="currentColor">'
        '<path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12'
        'c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047'
        'V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 '
        '2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25'
        'h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 '
        '12.073z"/></svg>'
    )

    has_account_selection = True

    def handle_callback(self, request):
        token = oauth.facebook.authorize_access_token(request)
        # Exchange for a long-lived user token
        long_lived = self._exchange_long_lived_token(token['access_token'])
        token.update(long_lived)
        return token

    def list_accounts(self, token_data):
        access_token = token_data.get('access_token', '')
        resp = http_requests.get(
            f'{GRAPH_API_BASE}/me/accounts',
            params={
                'access_token': access_token,
                'fields': 'id,name,access_token,category,picture{url}',
            },
            timeout=15,
        )
        resp.raise_for_status()
        pages = resp.json().get('data', [])
        return [
            {
                'id': p['id'],
                'name': p['name'],
                'access_token': p['access_token'],
                'category': p.get('category', ''),
                'picture_url': p.get('picture', {}).get('data', {}).get('url', ''),
            }
            for p in pages
        ]

    def save_connection(self, user, selected_account, token_data, project=None):
        conn, _created = IntegrationConnection.objects.update_or_create(
            project=project,
            provider=self.key,
            external_account_id=selected_account['id'],
            defaults={
                'user': user,
                'provider_category': self.category,
                'external_account_name': selected_account['name'],
                'access_token': selected_account.get('access_token', token_data.get('access_token', '')),
                'refresh_token': token_data.get('refresh_token', ''),
                'token_expires_at': None,
                'scopes': token_data.get('scope', ''),
                'status': IntegrationConnection.ConnectionStatus.ACTIVE,
                'metadata': {
                    'category': selected_account.get('category', ''),
                    'picture_url': selected_account.get('picture_url', ''),
                    'user_access_token': token_data.get('access_token', ''),
                },
            },
        )
        return conn

    def _exchange_long_lived_token(self, short_lived_token):
        """Exchange a short-lived user token for a long-lived one (~60 days)."""
        from django.conf import settings as django_settings

        client_config = django_settings.AUTHLIB_OAUTH_CLIENTS.get('facebook', {})
        resp = http_requests.get(
            f'{GRAPH_API_BASE}/oauth/access_token',
            params={
                'grant_type': 'fb_exchange_token',
                'client_id': client_config.get('client_id', ''),
                'client_secret': client_config.get('client_secret', ''),
                'fb_exchange_token': short_lived_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
