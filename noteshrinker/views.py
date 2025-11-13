import json
import logging
import os
import random
import string
import zipfile
from pathlib import Path
from typing import List, Dict, Any

from django.conf import settings
from django.http import Http404, JsonResponse, HttpResponseBadRequest, HttpRequest
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.views.generic import CreateView, DeleteView, ListView
from django.core.files.base import ContentFile
from django.urls import reverse
import threading
from io import BytesIO

from .models import Picture, Book
from .noteshrink_module import AttrDict, notescan_main
from .response import JSONResponse, response_mimetype
from .serialize import serialize
from . import pdf_utils

logger = logging.getLogger(__name__)


def random_string(N: int) -> str:
    """Generate a random string of uppercase letters and digits.

    Args:
        N: Length of the random string to generate

    Returns:
        Random string of specified length
    """
    return ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(N))


@require_GET
def download_pdf(request: HttpRequest) -> HttpResponse:
    """Download a PDF file with security validation.

    Args:
        request: HTTP request containing 'filename' parameter

    Returns:
        HttpResponse with PDF file or error message
    """
    filename = request.GET.get('filename', '')

    # Security: Prevent path traversal attacks
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        logger.warning(f"Invalid filename attempted: {filename}")
        return HttpResponseBadRequest("Invalid filename")

    file_path = Path(settings.PDF_ROOT) / filename

    # Security: Ensure the resolved path is still within PDF_ROOT
    try:
        file_path = file_path.resolve()
        pdf_root = Path(settings.PDF_ROOT).resolve()
        if not str(file_path).startswith(str(pdf_root)):
            logger.warning(f"Path traversal attempt: {filename}")
            return HttpResponseBadRequest("Invalid file path")
    except (ValueError, OSError) as e:
        logger.error(f"Error resolving path for {filename}: {e}")
        return HttpResponseBadRequest("Invalid file path")

    if file_path.exists():
        logger.info(f"Serving PDF: {filename}")
        with open(file_path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type="application/pdf")
            response['Content-Disposition'] = f'attachment; filename="{file_path.name}.pdf"'
            return response
    else:
        logger.warning(f"PDF not found: {filename}")
        return HttpResponseBadRequest("File not found")


def download_zip(request: HttpRequest) -> HttpResponse:
    """Create and download a ZIP archive of processed images.

    Args:
        request: HTTP request containing 'images' list parameter

    Returns:
        HttpResponse with ZIP file or error message
    """
    images = request.GET.getlist('images')

    if not images:
        logger.warning("No images specified for ZIP download")
        return HttpResponseBadRequest("No images specified")

    compression = zipfile.ZIP_DEFLATED
    image_prefix = images[0][:images[0].find('_')] if '_' in images[0] else 'noteshrinker'
    zipfile_name = Path(settings.PNG_ROOT) / f'noteshrinker_{image_prefix}_{len(images)}.zip'

    try:
        with zipfile.ZipFile(zipfile_name, mode='w', compression=compression) as zf:
            for filename in images:
                # Security: Validate filename
                if '..' in filename or '/' in filename or '\\' in filename:
                    logger.warning(f"Invalid image filename: {filename}")
                    continue

                file_path = Path(settings.PNG_ROOT) / filename
                if file_path.exists():
                    zf.write(file_path, arcname=filename)
                else:
                    logger.warning(f"Image not found: {filename}")

        logger.info(f"Created ZIP with {len(images)} images: {zipfile_name.name}")
        with open(zipfile_name, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type="application/x-zip-compressed")
            response['Content-Disposition'] = f'attachment; filename="{zipfile_name.name}"'
            return response
    except Exception as e:
        logger.error(f"Error creating ZIP: {e}")
        return HttpResponseBadRequest("Error creating ZIP file")


def index(request: HttpRequest) -> HttpResponse:
    """Render the main index page.

    Args:
        request: HTTP request

    Returns:
        Rendered index template
    """
    return render(request, 'index.html')


# TODO: 1. Сделать чтобы сохранялись загруженные файлы по сессии - Make uploaded files save between session using session key
# DONE: 2. Удалять сразу не разрешенные файлы - не загружаются - Don't upload from file extensions
# TODO: 3. Проверять отсутсвующие параметры в shrink - Check for missing params in shrink
# DONE: 4. Проверять, существуют ли папки PNG_ROOT и PDF_ROOT - создавать если нет - Check for PNG_ROOT and PDF_ROOT
# TODO: 5. Проверять максимальную длину названий файлов - Check for maximum filename length
# DONE: 6. Сделать кнопку для резета - Make a reset button
# DONE: 7. Сделать view для загрузки ZIP-архива картинок - Make a zip-archive download view
# DONE: 8. Кнопка очистить очищает список загруженных файлов в window, деактивирует кнопку скачать - Clear button must clear window._uploadedFiles, deactivates download button
@require_POST
def shrink(request: HttpRequest) -> JsonResponse:
    """Process and shrink uploaded images, creating PDF and PNG outputs.

    Args:
        request: HTTP POST request with image processing parameters

    Returns:
        JsonResponse with list of generated PNGs and PDF filename
    """
    files = request.POST.getlist('files[]')
    existing_files: List[str] = []

    for filename in files:
        path = Path(settings.MEDIA_ROOT) / 'pictures' / filename
        if path.exists():
            existing_files.append(str(path))
        else:
            logger.warning(f"File not found: {filename}")

    if not existing_files:
        logger.error("No valid files found for processing")
        raise Http404("No valid files found")

    on_off = lambda x: True if x == 'on' else False

    try:
        num_colors = int(request.POST['num_colors'])
        sample_fraction = float(request.POST['sample_fraction']) * 0.01
        sat_threshold = float(request.POST['sat_threshold'])
        value_threshold = float(request.POST['value_threshold'])
    except (ValueError, KeyError) as e:
        logger.error(f"Invalid parameter: {e}")
        return HttpResponseBadRequest(f"Invalid parameter: {str(e)}")

    # Generate PDF filename
    requested_name = request.POST.get('pdfname', 'output')
    if not requested_name.endswith('.pdf'):
        pdfname = f"{random_string(settings.RANDOM_STRING_LEN)}_{requested_name}.pdf"
    else:
        pdfname = f"{random_string(settings.RANDOM_STRING_LEN)}_{requested_name}"

    basename = f"{random_string(settings.RANDOM_STRING_LEN)}_{request.POST.get('basename', 'page')}"

    options: Dict[str, Any] = {
        "basename": basename,
        "filenames": existing_files,
        "global_palette": on_off(request.POST.get('global_palette', 'off')),
        "num_colors": num_colors,
        "pdf_cmd": 'convert %i %o',
        "pdfname": str(Path(settings.PDF_ROOT) / pdfname),
        "postprocess_cmd": None,
        "postprocess_ext": '_post.png',
        "quiet": False,
        "sample_fraction": sample_fraction,
        "sat_threshold": sat_threshold,
        "saturate": True,
        "sort_numerically": on_off(request.POST.get('sort_numerically', 'off')),
        "value_threshold": value_threshold,
        "white_bg": on_off(request.POST.get('white_bg', 'off')),
        "picture_folder": str(settings.PNG_ROOT)
    }

    logger.info(f"Processing {len(existing_files)} files with {num_colors} colors")

    try:
        pngs, pdf = notescan_main(AttrDict(options))
        logger.info(f"Successfully processed images: {len(pngs)} PNGs, PDF: {pdfname}")
        return JsonResponse({"pngs": pngs, "pdf": pdfname})
    except Exception as e:
        logger.error(f"Error processing images: {e}")
        return HttpResponseBadRequest(f"Error processing images: {str(e)}")


class PictureCreateView(CreateView):
    model = Picture
    fields = "__all__"
    template_name = 'index.html'

    def form_valid(self, form):
        self.object = form.save()
        files = [serialize(self.object)]
        data = {'files': files}
        response = JSONResponse(data, mimetype=response_mimetype(self.request))
        response['Content-Disposition'] = 'inline; filename=files.json'
        return response

    def form_invalid(self, form):
        data = json.dumps(form.errors)
        return HttpResponse(content=data, status=400, content_type='application/json')


class PictureDeleteView(DeleteView):
    model = Picture

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        response = JSONResponse(True, mimetype=response_mimetype(request))
        response['Content-Disposition'] = 'inline; filename=files.json'
        return response


class PictureListView(ListView):
    model = Picture

    def render_to_response(self, context, **response_kwargs):
        files = [serialize(p) for p in self.get_queryset()]
        data = {'files': files}
        response = JSONResponse(data, mimetype=response_mimetype(self.request))
        response['Content-Disposition'] = 'inline; filename=files.json'
        return response


# ===== Book PDF Optimization Views =====


def book_upload(request: HttpRequest) -> HttpResponse:
    """Handle book PDF upload with optional cover.

    GET: Display upload form
    POST: Process uploaded files and redirect to preview
    """
    if request.method == 'POST':
        try:
            # Get uploaded files
            main_pdf = request.FILES.get('main_pdf')
            cover_pdf = request.FILES.get('cover_pdf')
            title = request.POST.get('title', '')

            if not main_pdf:
                return HttpResponseBadRequest("Main PDF is required")

            # Validate file type
            if not main_pdf.name.endswith('.pdf'):
                return HttpResponseBadRequest("Main file must be a PDF")

            if cover_pdf and not cover_pdf.name.endswith('.pdf'):
                return HttpResponseBadRequest("Cover file must be a PDF")

            # Create Book instance
            book = Book(
                title=title or main_pdf.name,
                original_filename=main_pdf.name,
                session_key=request.session.session_key or ''
            )

            # Save files
            book.main_pdf.save(main_pdf.name, main_pdf, save=False)
            if cover_pdf:
                book.cover_pdf.save(cover_pdf.name, cover_pdf, save=False)

            book.save()

            # Extract PDF info
            try:
                main_info = pdf_utils.get_pdf_info(Path(book.main_pdf.path))
                book.page_count = main_info['page_count']
                book.original_size_mb = main_info['size_mb']

                if cover_pdf:
                    cover_info = pdf_utils.get_pdf_info(Path(book.cover_pdf.path))
                    book.cover_page_count = cover_info['page_count']
                    book.original_size_mb += cover_info['size_mb']

                book.status = 'preview'
                book.save()

                logger.info(f"Book uploaded: {book.id} - {book.title}")
                return redirect('noteshrinker:book_preview', book_id=book.id)

            except Exception as e:
                logger.error(f"Error processing uploaded PDF: {e}")
                book.delete()
                return HttpResponseBadRequest(f"Error processing PDF: {str(e)}")

        except Exception as e:
            logger.error(f"Error uploading book: {e}")
            return HttpResponseBadRequest(f"Upload error: {str(e)}")

    # GET: Display upload form
    return render(request, 'books/upload.html')


def book_preview(request: HttpRequest, book_id: int) -> HttpResponse:
    """Display preview page with settings adjustment.

    Shows preview of a selected page with current settings.
    User can adjust settings and see real-time preview updates.
    """
    book = get_object_or_404(Book, id=book_id)

    # Default settings
    default_settings = {
        'dpi': 150,
        'num_colors': 8,
        'sample_fraction': 5,  # Percentage (5%)
        'sat_threshold': 20,    # Percentage (0.20)
        'value_threshold': 25,  # Percentage (0.25)
        'white_bg': True,
        'global_palette': True,
        'preview_page': 1
    }

    # Merge with stored settings
    settings_dict = {**default_settings, **book.processing_settings}

    context = {
        'book': book,
        'settings': settings_dict,
        'max_page': book.page_count or 1
    }

    return render(request, 'books/preview.html', context)


@require_POST
def generate_preview(request: HttpRequest, book_id: int) -> JsonResponse:
    """AJAX endpoint to generate preview with current settings.

    Extracts specified page, optimizes it with settings, returns base64 image.
    """
    book = get_object_or_404(Book, id=book_id)

    try:
        # Get settings from request
        page_number = int(request.POST.get('preview_page', 1))
        dpi = int(request.POST.get('dpi', 150))
        num_colors = int(request.POST.get('num_colors', 8))
        sample_fraction = float(request.POST.get('sample_fraction', 5)) * 0.01
        sat_threshold = float(request.POST.get('sat_threshold', 20)) * 0.01
        value_threshold = float(request.POST.get('value_threshold', 25)) * 0.01
        white_bg = request.POST.get('white_bg', 'true').lower() == 'true'
        global_palette = request.POST.get('global_palette', 'true').lower() == 'true'

        # Validate page number
        max_page = book.page_count or 1
        if page_number < 1 or page_number > max_page:
            return JsonResponse({'error': f'Page number must be between 1 and {max_page}'}, status=400)

        # Extract page as image
        logger.info(f"Generating preview for book {book_id}, page {page_number}")
        pdf_path = Path(book.main_pdf.path)
        original_image = pdf_utils.extract_pdf_page_as_image(pdf_path, page_number, dpi)

        # Save original to temp location
        temp_dir = Path(settings.MEDIA_ROOT) / 'books' / 'temp' / str(book.id) / 'preview'
        temp_dir.mkdir(parents=True, exist_ok=True)
        original_path = temp_dir / 'original.png'
        original_image.save(original_path, 'PNG')

        # Optimize image
        optimize_settings = {
            'num_colors': num_colors,
            'sample_fraction': sample_fraction,
            'sat_threshold': sat_threshold,
            'value_threshold': value_threshold,
            'white_bg': white_bg,
            'global_palette': global_palette
        }

        optimized_paths = pdf_utils.optimize_images([original_path], optimize_settings, temp_dir)

        if not optimized_paths:
            return JsonResponse({'error': 'Failed to optimize image'}, status=500)

        # Convert to base64 for transmission
        from PIL import Image
        import base64

        optimized_image = Image.open(optimized_paths[0])
        buffer = BytesIO()
        optimized_image.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()

        # Calculate size comparison
        original_size = original_path.stat().st_size
        optimized_size = optimized_paths[0].stat().st_size
        compression_ratio = round((1 - optimized_size / original_size) * 100, 1)

        logger.info(f"Preview generated: {compression_ratio}% compression")

        return JsonResponse({
            'success': True,
            'image': f'data:image/png;base64,{img_str}',
            'original_size_kb': round(original_size / 1024, 1),
            'optimized_size_kb': round(optimized_size / 1024, 1),
            'compression_ratio': compression_ratio
        })

    except ValueError as e:
        logger.error(f"Invalid parameter in preview generation: {e}")
        return JsonResponse({'error': f'Invalid parameter: {str(e)}'}, status=400)
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        return JsonResponse({'error': f'Preview error: {str(e)}'}, status=500)


@require_POST
def book_process(request: HttpRequest, book_id: int) -> HttpResponse:
    """Start book processing with confirmed settings.

    Saves settings and starts background processing.
    """
    book = get_object_or_404(Book, id=book_id)

    if book.status == 'processing':
        return HttpResponseBadRequest("Book is already being processed")

    try:
        # Save processing settings
        settings_dict = {
            'dpi': int(request.POST.get('dpi', 150)),
            'num_colors': int(request.POST.get('num_colors', 8)),
            'sample_fraction': float(request.POST.get('sample_fraction', 5)) * 0.01,
            'sat_threshold': float(request.POST.get('sat_threshold', 20)) * 0.01,
            'value_threshold': float(request.POST.get('value_threshold', 25)) * 0.01,
            'white_bg': request.POST.get('white_bg', 'true').lower() == 'true',
            'global_palette': request.POST.get('global_palette', 'true').lower() == 'true'
        }

        book.processing_settings = settings_dict
        book.status = 'processing'
        book.save()

        logger.info(f"Starting processing for book {book_id}")

        # Start processing in background thread
        thread = threading.Thread(target=_process_book_background, args=(book.id, settings_dict))
        thread.daemon = True
        thread.start()

        return redirect('noteshrinker:book_status', book_id=book.id)

    except Exception as e:
        logger.error(f"Error starting book processing: {e}")
        return HttpResponseBadRequest(f"Processing error: {str(e)}")


def _process_book_background(book_id: int, settings_dict: dict):
    """Background worker to process book.

    This runs in a separate thread to avoid blocking the request.
    """
    try:
        book = Book.objects.get(id=book_id)
        logger.info(f"Background processing started for book {book_id}")

        # Process the book
        output_pdf = pdf_utils.process_book(book, settings_dict)

        # Save optimized PDF to model
        with open(output_pdf, 'rb') as f:
            book.optimized_pdf.save(
                f'optimized_{book.original_filename}',
                ContentFile(f.read()),
                save=False
            )

        # Update stats
        book.optimized_size_mb = output_pdf.stat().st_size / (1024 * 1024)
        book.status = 'completed'
        book.save()

        logger.info(f"Book {book_id} processing completed successfully")

    except Exception as e:
        logger.error(f"Error in background processing for book {book_id}: {e}")
        try:
            book = Book.objects.get(id=book_id)
            book.status = 'failed'
            book.save()
        except Exception:
            pass


def book_status(request: HttpRequest, book_id: int) -> HttpResponse:
    """Display processing status page.

    Shows progress and allows AJAX polling for status updates.
    """
    book = get_object_or_404(Book, id=book_id)

    context = {
        'book': book
    }

    return render(request, 'books/status.html', context)


@require_GET
def book_status_json(request: HttpRequest, book_id: int) -> JsonResponse:
    """AJAX endpoint for status polling.

    Returns current book status and statistics.
    """
    book = get_object_or_404(Book, id=book_id)

    data = {
        'status': book.status,
        'title': book.title,
        'original_size_mb': book.original_size_mb,
        'optimized_size_mb': book.optimized_size_mb,
        'compression_ratio': book.compression_ratio,
        'page_count': book.page_count,
        'total_pages': book.total_pages
    }

    if book.status == 'completed':
        data['download_url'] = reverse('noteshrinker:book_download', kwargs={'book_id': book.id})

    return JsonResponse(data)


@require_GET
def book_download(request: HttpRequest, book_id: int) -> HttpResponse:
    """Download optimized PDF.

    Returns the compressed PDF file.
    """
    book = get_object_or_404(Book, id=book_id)

    if book.status != 'completed' or not book.optimized_pdf:
        return HttpResponseBadRequest("Book processing not completed")

    try:
        logger.info(f"Serving optimized book {book_id}: {book.title}")
        with open(book.optimized_pdf.path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type="application/pdf")
            filename = f"optimized_{book.original_filename}"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
    except Exception as e:
        logger.error(f"Error downloading book {book_id}: {e}")
        return HttpResponseBadRequest("Error downloading file")


def book_list(request: HttpRequest) -> HttpResponse:
    """Display list of all books for current session.

    Shows upload history with status and compression stats.
    """
    session_key = request.session.session_key or ''
    books = Book.objects.filter(session_key=session_key).order_by('-upload_date')

    context = {
        'books': books
    }

    return render(request, 'books/list.html', context)
