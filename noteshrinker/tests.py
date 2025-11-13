"""
Test suite for noteshrinker application.

Tests cover:
- Security: Path traversal prevention
- Views: PDF/ZIP downloads, image processing
- Models: Picture model operations
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import Picture
from .views import random_string


class SecurityTests(TestCase):
    """Test security features including path traversal prevention."""

    def setUp(self):
        self.client = Client()
        self.temp_dir = tempfile.mkdtemp()

    def test_path_traversal_prevention_pdf(self):
        """Test that path traversal attacks are prevented in PDF download."""
        # Attempt path traversal
        response = self.client.get(reverse('noteshrinker:download_pdf'), {
            'filename': '../../../etc/passwd'
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'Invalid filename', response.content)

    def test_path_traversal_prevention_backslash(self):
        """Test that backslash path traversal is prevented."""
        response = self.client.get(reverse('noteshrinker:download_pdf'), {
            'filename': '..\\..\\windows\\system32'
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'Invalid filename', response.content)

    def test_empty_filename_rejected(self):
        """Test that empty filenames are rejected."""
        response = self.client.get(reverse('noteshrinker:download_pdf'), {
            'filename': ''
        })
        self.assertEqual(response.status_code, 400)

    def test_missing_filename_parameter(self):
        """Test handling of missing filename parameter."""
        response = self.client.get(reverse('noteshrinker:download_pdf'))
        self.assertEqual(response.status_code, 400)


class UtilityFunctionTests(TestCase):
    """Test utility functions."""

    def test_random_string_length(self):
        """Test that random_string generates correct length."""
        for length in [1, 5, 10, 20]:
            result = random_string(length)
            self.assertEqual(len(result), length)

    def test_random_string_characters(self):
        """Test that random_string uses only valid characters."""
        result = random_string(100)
        valid_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        result_chars = set(result)
        self.assertTrue(result_chars.issubset(valid_chars))

    def test_random_string_randomness(self):
        """Test that random_string produces different results."""
        results = [random_string(10) for _ in range(10)]
        # All strings should be unique (very high probability)
        self.assertEqual(len(results), len(set(results)))


class PictureModelTests(TestCase):
    """Test Picture model operations."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_picture_creation(self):
        """Test creating a Picture instance."""
        # Create a test image file
        image_content = b'fake image content'
        image_file = SimpleUploadedFile(
            "test_image.jpg",
            image_content,
            content_type="image/jpeg"
        )

        picture = Picture.objects.create(file=image_file)
        self.assertIsNotNone(picture.pk)
        self.assertTrue(picture.file.name.endswith('.jpg'))

    def test_picture_str_representation(self):
        """Test string representation of Picture."""
        image_file = SimpleUploadedFile(
            "test.jpg",
            b'content',
            content_type="image/jpeg"
        )
        picture = Picture.objects.create(file=image_file)
        # Django may append random string to prevent collisions
        file_str = str(picture.file)
        self.assertTrue(file_str.endswith('.jpg'))
        self.assertIn('test', file_str)


class ViewTests(TestCase):
    """Test view functions."""

    def setUp(self):
        self.client = Client()

    def test_index_view(self):
        """Test that index view renders successfully."""
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'index.html')

    def test_download_pdf_nonexistent_file(self):
        """Test downloading non-existent PDF returns error."""
        response = self.client.get(reverse('noteshrinker:download_pdf'), {
            'filename': 'nonexistent.pdf'
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'File not found', response.content)

    def test_download_zip_no_images(self):
        """Test that ZIP download without images returns error."""
        response = self.client.get(reverse('noteshrinker:download_zip'))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'No images specified', response.content)

    @patch('noteshrinker.views.notescan_main')
    def test_shrink_view_missing_parameters(self, mock_notescan):
        """Test that shrink view validates required parameters."""
        response = self.client.post(reverse('noteshrinker:shrink'), {
            'files[]': ['test.jpg'],
            # Missing required parameters
        })
        self.assertEqual(response.status_code, 400)

    def test_shrink_view_requires_post(self):
        """Test that shrink view only accepts POST."""
        response = self.client.get(reverse('noteshrinker:shrink'))
        self.assertEqual(response.status_code, 405)  # Method not allowed


@override_settings(
    MEDIA_ROOT=tempfile.mkdtemp(),
    PDF_ROOT=Path(tempfile.mkdtemp()),
    PNG_ROOT=Path(tempfile.mkdtemp())
)
class IntegrationTests(TestCase):
    """Integration tests for full workflows."""

    def setUp(self):
        self.client = Client()

        # Ensure directories exist
        settings.PDF_ROOT.mkdir(parents=True, exist_ok=True)
        settings.PNG_ROOT.mkdir(parents=True, exist_ok=True)

    def test_pdf_download_with_valid_file(self):
        """Test downloading a valid PDF file."""
        # Create a test PDF file
        test_pdf = settings.PDF_ROOT / 'test.pdf'
        test_pdf.write_bytes(b'%PDF-1.4 fake pdf content')

        response = self.client.get(reverse('noteshrinker:download_pdf'), {
            'filename': 'test.pdf'
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment', response['Content-Disposition'])

    def test_zip_download_with_valid_images(self):
        """Test creating and downloading ZIP of images."""
        # Create test image files
        test_images = ['img1_page1.png', 'img1_page2.png']
        for img_name in test_images:
            img_path = settings.PNG_ROOT / img_name
            img_path.write_bytes(b'fake image content')

        response = self.client.get(reverse('noteshrinker:download_zip'), {
            'images': test_images
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/x-zip-compressed')
        self.assertIn('attachment', response['Content-Disposition'])


class ConfigurationTests(TestCase):
    """Test configuration and settings."""

    def test_required_settings_exist(self):
        """Test that all required settings are defined."""
        required_settings = [
            'BASE_DIR',
            'SECRET_KEY',
            'DEBUG',
            'ALLOWED_HOSTS',
            'INSTALLED_APPS',
            'MIDDLEWARE',
            'TEMPLATES',
            'DATABASES',
            'MEDIA_ROOT',
            'PDF_ROOT',
            'PNG_ROOT',
            'RANDOM_STRING_LEN',
        ]

        for setting_name in required_settings:
            self.assertTrue(
                hasattr(settings, setting_name),
                f"Setting {setting_name} is not defined"
            )

    def test_security_settings(self):
        """Test that security settings are properly configured."""
        # These should be True in settings
        self.assertTrue(settings.SECURE_BROWSER_XSS_FILTER)
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')

    def test_logging_configuration(self):
        """Test that logging is properly configured."""
        self.assertIn('version', settings.LOGGING)
        self.assertIn('handlers', settings.LOGGING)
        self.assertIn('loggers', settings.LOGGING)
        self.assertIn('noteshrinker', settings.LOGGING['loggers'])
