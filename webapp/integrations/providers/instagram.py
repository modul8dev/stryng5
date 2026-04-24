import requests as http_requests

from ..models import IntegrationConnection
from ..oauth import oauth
from .base import BaseProvider

IG_GRAPH_BASE = 'https://graph.instagram.com/v22.0'


class InstagramProvider(BaseProvider):
    """
    Instagram API with Instagram Login (Business Login).
    Users authenticate directly with their Instagram account —
    no Facebook Pages dependency.
    """

    key = 'instagram'
    display_name = 'Instagram'
    category = 'social_media'

    icon_svg = (
        '<svg class="size-6" viewBox="0 0 24 24" fill="currentColor">'
        '<path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 '
        '4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 '
        '3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 '
        '4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849'
        '-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644'
        '-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 '
        '4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 '
        '0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 '
        '8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 '
        '2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 '
        '3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059'
        '-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947'
        '-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 '
        '0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324'
        'zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 '
        '100 2.881 1.44 1.44 0 000-2.881z"/></svg>'
    )

    # Direct Instagram login — single account per auth, no selection step needed.
    has_account_selection = False

    def handle_callback(self, request):
        token = oauth.instagram.authorize_access_token(request)
        # Exchange short-lived token for a long-lived one (~60 days)
        long_lived = self._exchange_long_lived_token(token['access_token'])
        token.update(long_lived)
        return token

    def list_accounts(self, token_data):
        """Fetch the authenticated Instagram business account's profile."""
        access_token = token_data.get('access_token', '')
        resp = http_requests.get(
            f'{IG_GRAPH_BASE}/me',
            params={
                'fields': 'id,username,name,profile_picture_url,account_type',
                'access_token': access_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        user = resp.json()
        return [{
            'id': user['id'],
            'name': f"@{user.get('username', user['id'])}",
            'username': user.get('username', ''),
            'picture_url': user.get('profile_picture_url', ''),
            'account_type': user.get('account_type', ''),
        }]

    def save_connection(self, user, selected_account, token_data, project=None):
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
                'token_expires_at': None,
                'scopes': token_data.get('scope', ''),
                'status': IntegrationConnection.ConnectionStatus.ACTIVE,
                'metadata': {
                    'username': selected_account.get('username', ''),
                    'picture_url': selected_account.get('picture_url', ''),
                    'account_type': selected_account.get('account_type', ''),
                },
            },
        )
        return conn

    def _exchange_long_lived_token(self, short_lived_token):
        from django.conf import settings as django_settings

        client_config = django_settings.AUTHLIB_OAUTH_CLIENTS.get('instagram', {})
        # Instagram Business Login uses graph.instagram.com for token exchange
        # with grant_type=ig_exchange_token (not fb_exchange_token)
        resp = http_requests.get(
            'https://graph.instagram.com/access_token',
            params={
                'grant_type': 'ig_exchange_token',
                'client_secret': client_config.get('client_secret', ''),
                'access_token': short_lived_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
