from collections import Counter
from urllib.parse import urljoin

from django.core.management.base import BaseCommand, CommandError

from brand.models import Brand
from media_library.image_heuristics import _normalize_image_identity, _select_distinct_product_image_urls
from media_library.models import ImageGroup
from projects.models import Project


class Command(BaseCommand):
    help = 'Prune noisy imported product images using the same heuristics as the domain crawler.'

    def add_arguments(self, parser):
        parser.add_argument('--project-id', type=int, help='Project ID to inspect.')
        parser.add_argument('--project-name', help='Exact project name to inspect.')
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Delete the images that the heuristic rejects. Defaults to dry-run.',
        )

    def handle(self, *args, **options):
        project = self._get_project(options)

        try:
            brand = Brand.objects.get(project=project)
            page_url = brand.website_url or ''
        except Brand.DoesNotExist:
            page_url = ''

        groups = list(
            ImageGroup.objects.filter(project=project, type=ImageGroup.GroupType.PRODUCT)
            .prefetch_related('images')
        )
        if not groups:
            self.stdout.write(self.style.WARNING('No product groups found for that project.'))
            return

        asset_page_counts = Counter()
        for group in groups:
            identities = {
                _normalize_image_identity(urljoin(page_url, image.external_url or image.url))
                for image in group.images.all()
                if image.external_url or image.url
            }
            asset_page_counts.update(identity for identity in identities if identity)

        removed = 0
        skipped_groups = 0
        affected_groups = 0

        for group in groups:
            images = list(group.images.all())
            image_urls = [image.external_url or image.url for image in images if image.external_url or image.url]
            keep_urls = set(
                _select_distinct_product_image_urls(
                    image_urls,
                    page_url=page_url,
                    page_title=group.title,
                    page_description=group.description,
                    asset_page_counts=asset_page_counts,
                    total_pages=len(groups),
                )
            )

            if not keep_urls:
                skipped_groups += 1
                continue

            to_remove = [image for image in images if (image.external_url or image.url) not in keep_urls]
            if not to_remove:
                continue

            affected_groups += 1
            removed += len(to_remove)
            self.stdout.write(
                f'Group {group.id} "{group.title}": keep {len(keep_urls)}, remove {len(to_remove)}'
            )

            if options['apply']:
                for image in to_remove:
                    image.delete()

        mode = 'Applied' if options['apply'] else 'Dry run'
        self.stdout.write(
            self.style.SUCCESS(
                f'{mode} complete for project {project.id} "{project.name}". '
                f'Affected groups: {affected_groups}. '
                f'Images removed: {removed}. '
                f'Groups skipped with no confident keepers: {skipped_groups}.'
            )
        )

    def _get_project(self, options):
        project_id = options.get('project_id')
        project_name = options.get('project_name')

        if project_id is None and not project_name:
            raise CommandError('Provide either --project-id or --project-name.')

        if project_id is not None:
            try:
                return Project.objects.get(pk=project_id)
            except Project.DoesNotExist as exc:
                raise CommandError(f'Project {project_id} does not exist.') from exc

        try:
            return Project.objects.get(name=project_name)
        except Project.DoesNotExist as exc:
            raise CommandError(f'Project "{project_name}" does not exist.') from exc
