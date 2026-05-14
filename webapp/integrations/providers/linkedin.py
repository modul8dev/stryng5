import requests as http_requests
from datetime import timedelta

from django.utils import timezone

from ..models import IntegrationConnection
from ..oauth import oauth
from .base import BaseProvider

LINKEDIN_API_BASE = 'https://api.linkedin.com'
LINKEDIN_REST_BASE = 'https://api.linkedin.com/rest'
LINKEDIN_API_VERSION = '202604'


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

    has_account_selection = True

    def handle_callback(self, request):
        token = oauth.linkedin.authorize_access_token(request)
        return token

    def list_accounts(self, token_data):
        """Fetch LinkedIn organizations the authenticated member administers."""
        access_token = token_data.get('access_token', '')
        headers = {
            'Authorization': f'Bearer {access_token}',
            'LinkedIn-Version': LINKEDIN_API_VERSION,
            'X-Restli-Protocol-Version': '2.0.0',
        }

        # Fetch member profile
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
        member_name = f'{first} {last}'.strip() or member_id

        # Extract profile picture URL if present
        member_picture = ''
        try:
            elements = profile['profilePicture']['displayImage~']['elements']
            member_picture = elements[0]['identifiers'][0]['identifier']
        except (KeyError, IndexError, TypeError):
            pass

        # Start with the personal account
        accounts = [{
            'id': member_id,
            'name': member_name,
            'picture_url': member_picture,
            'category': 'Personal Account',
            'member_id': member_id,
        }]

        # Fetch organizations where the member is an administrator (REST API)
        acl_resp = http_requests.get(
            f'{LINKEDIN_REST_BASE}/organizationAcls',
            headers=headers,
            params={'q': 'roleAssignee', 'role': 'ADMINISTRATOR', 'state': 'APPROVED'},
            timeout=15,
        )
        acl_resp.raise_for_status()
        acl_elements = acl_resp.json().get('elements', [])

        for entry in acl_elements:
            org_urn = entry.get('organization', '')
            # Extract numeric ID from URN like "urn:li:organization:12345"
            org_id = org_urn.split(':')[-1] if org_urn else ''
            if not org_id:
                continue

            # Fetch organization details via v2 API with logo projection expansion
            try:
                org_resp = http_requests.get(
                    f'{LINKEDIN_API_BASE}/v2/organizations/{org_id}',
                    headers=headers,
                    params={'projection': '(id,localizedName,logoV2(original~:playableStreams))'},
                    timeout=15,
                )
                org_resp.raise_for_status()
                org = org_resp.json()
            except Exception:
                continue

            # Extract logo URL if present
            picture_url = ''
            try:
                elements = org['logoV2']['original~']['elements']
                picture_url = elements[0]['identifiers'][0]['identifier']
            except (KeyError, IndexError, TypeError):
                pass

            accounts.append({
                'id': org_id,
                'name': org.get('localizedName', org_id),
                'picture_url': picture_url,
                'category': 'Organization',
                'member_id': member_id,
            })

        return accounts

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
                    'member_id': selected_account.get('member_id', ''),
                },
            },
        )
        return conn
