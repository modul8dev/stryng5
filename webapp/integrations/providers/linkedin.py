import requests as http_requests
from datetime import timedelta

from django.utils import timezone

from ..models import IntegrationConnection
from ..oauth import oauth
from .base import BaseProvider

LINKEDIN_API_BASE = 'https://api.linkedin.com'


class LinkedInProvider(BaseProvider):
    """
    LinkedIn — OAuth 2.0 with OpenID Connect.
    Single user account per auth, no selection step needed.
    """

    key = 'linkedin'
    display_name = 'LinkedIn'
    category = 'social_media'

    icon_svg = (
        '<svg class="size-6" viewBox="0 0 24 24" fill="currentColor">'
        '<path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037'
        '-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9'
        'h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 '
        '4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 '
        '01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H'
        '3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729'
        'v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 '
        '24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>'
    )

    has_account_selection = False

    def handle_callback(self, request):
        token = oauth.linkedin.authorize_access_token(request)
        return token

    def list_accounts(self, token_data):
        """Fetch the authenticated LinkedIn member's profile via /v2/me."""
        headers = {'Authorization': f"Bearer {token_data.get('access_token', '')}"}

        profile_resp = http_requests.get(
            f'{LINKEDIN_API_BASE}/v2/me',
            headers=headers,
            params={'projection': '(id,localizedFirstName,localizedLastName,profilePicture(displayImage~digitalmediaAsset:playableStreams))'},
            timeout=15,
        )
        profile_resp.raise_for_status()
        profile = profile_resp.json()

        member_id = profile.get('id', '')
        first = profile.get('localizedFirstName', '')
        last = profile.get('localizedLastName', '')
        name = f'{first} {last}'.strip() or member_id

        # Extract smallest profile picture URL if present
        picture_url = ''
        try:
            elements = profile['profilePicture']['displayImage~']['elements']
            picture_url = elements[0]['identifiers'][0]['identifier']
        except (KeyError, IndexError, TypeError):
            pass

        # Fetch email separately
        email = ''
        try:
            email_resp = http_requests.get(
                f'{LINKEDIN_API_BASE}/v2/emailAddress',
                headers=headers,
                params={'q': 'members', 'projection': '(elements*(handle~))'},
                timeout=15,
            )
            email_resp.raise_for_status()
            email = email_resp.json()['elements'][0]['handle~']['emailAddress']
        except Exception:
            pass

        return [{
            'id': member_id,
            'name': name,
            'picture_url': picture_url,
            'email': email,
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
                    'picture_url': selected_account.get('picture_url', ''),
                    'email': selected_account.get('email', ''),
                },
            },
        )
        return conn
