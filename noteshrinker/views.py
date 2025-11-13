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
from django.shortcuts import render
from django.views.decorators.http import require_POST, require_GET
from django.views.generic import CreateView, DeleteView, ListView

from .models import Picture
from .noteshrink_module import AttrDict, notescan_main
from .response import JSONResponse, response_mimetype
from .serialize import serialize

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
