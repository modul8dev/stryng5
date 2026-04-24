import types
from collections import Counter
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from projects.models import Project

from .models import ImageGroup
from .views import (
    _import_domain_with_crawl,
    _normalize_image_identity,
    _select_distinct_product_image_urls,
)


class MediaLibraryImportTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='media@example.com',
            password='password123',
        )
        self.project = Project.objects.create(owner=self.user, name='Test Project')

    def test_select_distinct_product_image_urls_filters_junk_and_keeps_best_variants(self):
        page_url = 'https://www.example.com/products/blue-mug-12oz'
        page_title = 'Blue Mug 12 oz | Example'
        page_description = 'Buy our blue mug in a 12 oz size.'
        image_urls = [
            'https://totebot.ai/apple-icon.png',
            'https://www.example.com/Documents/front_item_icon/a.svg?t=1',
            'https://www.example.com/image_style/product_list_item/Documents/Products/113357/030425_1.jpg.webp?t=1',
            'https://www.example.com/image_style/product_140/Documents/Products/113357/030425_1.jpg.webp?t=2',
            'https://www.example.com/image_style/product_image/Documents/Products/113357/030425_1.jpg.webp?t=3',
            'https://www.example.com/image_style/product_image/Documents/Products/113357/030425_2.jpg.webp?t=4',
        ]
        asset_page_counts = Counter({
            _normalize_image_identity(image_urls[0]): 20,
            _normalize_image_identity(image_urls[1]): 20,
            _normalize_image_identity(image_urls[2]): 1,
            _normalize_image_identity(image_urls[3]): 1,
            _normalize_image_identity(image_urls[4]): 1,
            _normalize_image_identity(image_urls[5]): 1,
        })

        selected = _select_distinct_product_image_urls(
            image_urls,
            page_url=page_url,
            page_title=page_title,
            page_description=page_description,
            asset_page_counts=asset_page_counts,
            total_pages=40,
        )

        self.assertEqual(selected, [
            'https://www.example.com/image_style/product_image/Documents/Products/113357/030425_1.jpg.webp?t=3',
            'https://www.example.com/image_style/product_image/Documents/Products/113357/030425_2.jpg.webp?t=4',
        ])

    def test_select_distinct_product_image_urls_keeps_multiple_unknown_images_on_product_like_page(self):
        page_url = 'https://shop.example.com/p/blue-mug-12oz'
        page_title = 'Blue Mug 12 oz'
        page_description = 'Ceramic mug, 12 oz.'
        image_urls = [
            'https://cdn.example.com/media/blue-mug-front.jpg',
            'https://cdn.example.com/media/blue-mug-side.jpg',
            'https://cdn.example.com/media/site-logo.png',
        ]
        asset_page_counts = Counter({
            _normalize_image_identity(image_urls[0]): 1,
            _normalize_image_identity(image_urls[1]): 1,
            _normalize_image_identity(image_urls[2]): 15,
        })

        selected = _select_distinct_product_image_urls(
            image_urls,
            page_url=page_url,
            page_title=page_title,
            page_description=page_description,
            asset_page_counts=asset_page_counts,
            total_pages=20,
        )

        self.assertEqual(selected, image_urls[:2])

    @patch.dict('os.environ', {'FIRECRAWL_API_KEY': 'test-key'})
    def test_import_domain_with_crawl_filters_icons_and_keeps_distinct_product_images(self):
        product_page = types.SimpleNamespace(
            images=[
                'https://totebot.ai/apple-icon.png',
                'https://www.example.com/Documents/front_item_icon/a.svg?t=1',
                'https://www.example.com/image_style/product_list_item/Documents/Products/113357/030425_1.jpg.webp?t=1',
                'https://www.example.com/image_style/product_image/Documents/Products/113357/030425_1.jpg.webp?t=2',
                'https://www.example.com/image_style/product_image/Documents/Products/113357/030425_2.jpg.webp?t=3',
            ],
            metadata={
                'title': 'Blue Mug 12 oz | Example',
                'description': 'Buy our blue mug in a 12 oz size.',
                'source_url': 'https://www.example.com/products/blue-mug-12oz',
            },
        )
        about_page = types.SimpleNamespace(
            images=[
                'https://totebot.ai/apple-icon.png',
                'https://www.example.com/Documents/front_item_icon/a.svg?t=1',
                'https://www.example.com/image_style/brand/Documents/brand_image/story.jpg.webp?t=1',
            ],
            metadata={
                'title': 'About Example',
                'description': 'Learn more about our company.',
                'source_url': 'https://www.example.com/about',
            },
        )

        class FakeFirecrawl:
            def __init__(self, api_key):
                self.api_key = api_key

            def crawl(self, *_args, **_kwargs):
                return types.SimpleNamespace(data=[product_page, about_page])

        fake_module = types.SimpleNamespace(Firecrawl=FakeFirecrawl)

        with patch.dict('sys.modules', {'firecrawl': fake_module}):
            success, error = _import_domain_with_crawl(
                self.user,
                'https://www.example.com',
                project=self.project,
            )

        self.assertTrue(success)
        self.assertIsNone(error)

        groups = list(ImageGroup.objects.filter(project=self.project).prefetch_related('images'))
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].title, 'Blue Mug 12 oz | Example')
        self.assertEqual(
            [image.external_url for image in groups[0].images.order_by('id')],
            [
                'https://www.example.com/image_style/product_image/Documents/Products/113357/030425_1.jpg.webp?t=2',
                'https://www.example.com/image_style/product_image/Documents/Products/113357/030425_2.jpg.webp?t=3',
            ],
        )
