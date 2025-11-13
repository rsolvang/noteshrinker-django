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


class BookModelTests(TestCase):
    """Test Book model operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def test_book_creation(self):
        """Test creating a Book instance."""
        from .models import Book

        pdf_content = b'%PDF-1.4\nfake pdf content'
        main_pdf = SimpleUploadedFile(
            "test_book.pdf",
            pdf_content,
            content_type="application/pdf"
        )

        book = Book.objects.create(
            title="Test Book",
            original_filename="test_book.pdf",
            main_pdf=main_pdf
        )

        self.assertIsNotNone(book.pk)
        self.assertEqual(book.title, "Test Book")
        self.assertEqual(book.status, 'uploaded')
        self.assertIsNotNone(book.main_pdf)

    def test_book_with_cover(self):
        """Test creating a Book with cover PDF."""
        from .models import Book

        main_pdf = SimpleUploadedFile("main.pdf", b'%PDF-1.4\nmain', content_type="application/pdf")
        cover_pdf = SimpleUploadedFile("cover.pdf", b'%PDF-1.4\ncover', content_type="application/pdf")

        book = Book.objects.create(
            title="Book with Cover",
            original_filename="main.pdf",
            main_pdf=main_pdf,
            cover_pdf=cover_pdf
        )

        self.assertIsNotNone(book.cover_pdf)
        self.assertTrue(book.cover_pdf.name.endswith('.pdf'))

    def test_compression_ratio_property(self):
        """Test compression ratio calculation."""
        from .models import Book

        book = Book.objects.create(
            title="Test",
            original_filename="test.pdf",
            main_pdf=SimpleUploadedFile("test.pdf", b'%PDF-1.4\ntest'),
            original_size_mb=10.0,
            optimized_size_mb=2.0
        )

        self.assertEqual(book.compression_ratio, 80.0)  # 80% reduction

    def test_total_pages_property(self):
        """Test total pages calculation."""
        from .models import Book

        book = Book.objects.create(
            title="Test",
            original_filename="test.pdf",
            main_pdf=SimpleUploadedFile("test.pdf", b'%PDF-1.4\ntest'),
            page_count=100,
            cover_page_count=5
        )

        self.assertEqual(book.total_pages, 105)

    def test_book_status_choices(self):
        """Test that all book status values are valid."""
        from .models import Book

        valid_statuses = ['uploaded', 'preview', 'processing', 'completed', 'failed']

        for status in valid_statuses:
            book = Book.objects.create(
                title=f"Test {status}",
                original_filename="test.pdf",
                main_pdf=SimpleUploadedFile("test.pdf", b'%PDF-1.4\ntest'),
                status=status
            )
            self.assertEqual(book.status, status)


class BookViewTests(TestCase):
    """Test book-related views."""

    def setUp(self):
        """Set up test client."""
        self.client = Client()

    def test_book_upload_get(self):
        """Test that book upload page loads."""
        response = self.client.get(reverse('noteshrinker:book_upload'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/upload.html')

    def test_book_upload_post_valid(self):
        """Test uploading a valid book PDF."""
        from .models import Book

        pdf_content = b'%PDF-1.4\n%fake pdf content for testing'
        main_pdf = SimpleUploadedFile("test.pdf", pdf_content, content_type="application/pdf")

        with patch('noteshrinker.views.pdf_utils.get_pdf_info') as mock_info:
            mock_info.return_value = {'page_count': 10, 'size_mb': 5.0}

            response = self.client.post(reverse('noteshrinker:book_upload'), {
                'title': 'My Test Book',
                'main_pdf': main_pdf
            })

        # Should redirect to preview
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Book.objects.filter(title='My Test Book').exists())

    def test_book_upload_missing_main_pdf(self):
        """Test that upload fails without main PDF."""
        response = self.client.post(reverse('noteshrinker:book_upload'), {
            'title': 'Test'
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'Main PDF is required', response.content)

    def test_book_upload_invalid_file_type(self):
        """Test that non-PDF files are rejected."""
        text_file = SimpleUploadedFile("test.txt", b'not a pdf', content_type="text/plain")

        response = self.client.post(reverse('noteshrinker:book_upload'), {
            'title': 'Test',
            'main_pdf': text_file
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'must be a PDF', response.content)

    def test_book_list_view(self):
        """Test book list view."""
        response = self.client.get(reverse('noteshrinker:book_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/list.html')

    @patch('noteshrinker.views.pdf_utils.get_pdf_info')
    def test_book_preview_view(self, mock_info):
        """Test book preview view."""
        from .models import Book

        # Create a book
        book = Book.objects.create(
            title="Test Book",
            original_filename="test.pdf",
            main_pdf=SimpleUploadedFile("test.pdf", b'%PDF-1.4\ntest'),
            page_count=10,
            status='preview'
        )

        response = self.client.get(reverse('noteshrinker:book_preview', kwargs={'book_id': book.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/preview.html')
        self.assertIn('book', response.context)
        self.assertIn('settings', response.context)

    def test_book_status_view(self):
        """Test book status view."""
        from .models import Book

        book = Book.objects.create(
            title="Processing Book",
            original_filename="test.pdf",
            main_pdf=SimpleUploadedFile("test.pdf", b'%PDF-1.4\ntest'),
            status='processing'
        )

        response = self.client.get(reverse('noteshrinker:book_status', kwargs={'book_id': book.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/status.html')

    def test_book_status_json(self):
        """Test book status JSON endpoint."""
        from .models import Book

        book = Book.objects.create(
            title="Test Book",
            original_filename="test.pdf",
            main_pdf=SimpleUploadedFile("test.pdf", b'%PDF-1.4\ntest'),
            status='completed',
            original_size_mb=10.0,
            optimized_size_mb=2.0,
            page_count=50
        )

        response = self.client.get(reverse('noteshrinker:book_status_json', kwargs={'book_id': book.id}))
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data['status'], 'completed')
        self.assertEqual(data['title'], 'Test Book')
        self.assertEqual(data['compression_ratio'], 80.0)
        self.assertIn('download_url', data)

    def test_book_download_not_completed(self):
        """Test that download fails for non-completed books."""
        from .models import Book

        book = Book.objects.create(
            title="Processing Book",
            original_filename="test.pdf",
            main_pdf=SimpleUploadedFile("test.pdf", b'%PDF-1.4\ntest'),
            status='processing'
        )

        response = self.client.get(reverse('noteshrinker:book_download', kwargs={'book_id': book.id}))
        self.assertEqual(response.status_code, 400)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PDFUtilsTests(TestCase):
    """Test PDF utility functions."""

    def test_get_pdf_info_invalid_pdf(self):
        """Test that get_pdf_info handles invalid PDFs."""
        from .pdf_utils import get_pdf_info

        temp_file = Path(tempfile.mktemp(suffix='.pdf'))
        temp_file.write_bytes(b'not a valid pdf')

        with self.assertRaises(Exception):
            get_pdf_info(temp_file)

        temp_file.unlink()

    @patch('noteshrinker.pdf_utils.convert_from_path')
    def test_pdf_to_images(self, mock_convert):
        """Test PDF to images conversion."""
        from .pdf_utils import pdf_to_images
        from PIL import Image

        # Mock the conversion
        mock_image = MagicMock(spec=Image.Image)
        mock_convert.return_value = [mock_image, mock_image]

        pdf_path = Path(tempfile.mktemp(suffix='.pdf'))
        pdf_path.write_bytes(b'%PDF-1.4\ntest')

        output_dir = Path(tempfile.mkdtemp())

        result = pdf_to_images(pdf_path, output_dir, dpi=150)

        self.assertEqual(len(result), 2)
        mock_convert.assert_called_once()

        # Cleanup
        pdf_path.unlink()

    @patch('noteshrinker.pdf_utils.notescan_main')
    def test_optimize_images(self, mock_notescan):
        """Test image optimization."""
        from .pdf_utils import optimize_images

        # Create mock images
        image_paths = []
        for i in range(2):
            img_path = Path(tempfile.mktemp(suffix='.png'))
            img_path.write_bytes(b'fake image data')
            image_paths.append(img_path)

        output_dir = Path(tempfile.mkdtemp())

        # Mock notescan_main to return optimized file names
        mock_notescan.return_value = (['optimized_page1.png', 'optimized_page2.png'], None)

        # Create the expected output files
        for fname in ['optimized_page1.png', 'optimized_page2.png']:
            (output_dir / fname).write_bytes(b'optimized')

        settings = {
            'num_colors': 8,
            'sample_fraction': 0.05,
            'sat_threshold': 0.20,
            'value_threshold': 0.25,
            'white_bg': True,
            'global_palette': True
        }

        result = optimize_images(image_paths, settings, output_dir)

        self.assertEqual(len(result), 2)
        mock_notescan.assert_called_once()

        # Cleanup
        for path in image_paths:
            path.unlink(missing_ok=True)
