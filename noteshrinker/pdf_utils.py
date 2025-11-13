"""
PDF Book Processing Utilities

This module handles PDF book optimization including:
- Extracting pages from PDF
- Converting PDF pages to images
- Optimizing images
- Reassembling into compressed PDF
"""

import logging
import os
from pathlib import Path
from typing import List, Tuple, Optional
from io import BytesIO

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pdf2image import convert_from_path
from django.core.files.base import ContentFile

from .noteshrink_module import AttrDict, notescan_main

logger = logging.getLogger(__name__)


def get_pdf_info(pdf_path: Path) -> dict:
    """Extract metadata from PDF file.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Dictionary with page_count and size_mb
    """
    try:
        reader = PdfReader(pdf_path)
        page_count = len(reader.pages)
        size_mb = pdf_path.stat().st_size / (1024 * 1024)

        return {
            'page_count': page_count,
            'size_mb': round(size_mb, 2)
        }
    except Exception as e:
        logger.error(f"Error reading PDF info: {e}")
        raise


def extract_pdf_page_as_image(pdf_path: Path, page_number: int, dpi: int = 150) -> Image.Image:
    """Extract a specific page from PDF as PIL Image.

    Args:
        pdf_path: Path to PDF file
        page_number: Page number (1-indexed)
        dpi: DPI for conversion (default 150)

    Returns:
        PIL Image object
    """
    try:
        images = convert_from_path(
            pdf_path,
            dpi=dpi,
            first_page=page_number,
            last_page=page_number
        )
        return images[0]
    except Exception as e:
        logger.error(f"Error extracting page {page_number}: {e}")
        raise


def pdf_to_images(pdf_path: Path, output_dir: Path, dpi: int = 150) -> List[Path]:
    """Convert all PDF pages to images.

    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save images
        dpi: DPI for conversion

    Returns:
        List of paths to generated images
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Converting PDF to images at {dpi} DPI...")
        images = convert_from_path(pdf_path, dpi=dpi)

        image_paths = []
        for i, image in enumerate(images, 1):
            image_path = output_dir / f"page_{i:04d}.png"
            image.save(image_path, 'PNG')
            image_paths.append(image_path)
            logger.debug(f"Saved page {i} to {image_path}")

        logger.info(f"Converted {len(images)} pages to images")
        return image_paths

    except Exception as e:
        logger.error(f"Error converting PDF to images: {e}")
        raise


def optimize_images(image_paths: List[Path], settings: dict, output_dir: Path) -> List[Path]:
    """Optimize images using noteshrink algorithm.

    Args:
        image_paths: List of image paths to optimize
        settings: Optimization settings dictionary
        output_dir: Directory for optimized images

    Returns:
        List of paths to optimized images
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        # Convert paths to strings for noteshrink
        filenames = [str(p) for p in image_paths]

        # Prepare options for noteshrink
        options = {
            "basename": "optimized",
            "filenames": filenames,
            "global_palette": settings.get('global_palette', True),
            "num_colors": settings.get('num_colors', 8),
            "pdf_cmd": None,  # We don't want PDF output here
            "pdfname": None,
            "postprocess_cmd": None,
            "postprocess_ext": '_post.png',
            "quiet": False,
            "sample_fraction": settings.get('sample_fraction', 0.05),
            "sat_threshold": settings.get('sat_threshold', 0.20),
            "saturate": True,
            "sort_numerically": True,
            "value_threshold": settings.get('value_threshold', 0.25),
            "white_bg": settings.get('white_bg', True),
            "picture_folder": str(output_dir)
        }

        logger.info(f"Optimizing {len(filenames)} images with settings: {settings}")
        optimized_files, _ = notescan_main(AttrDict(options))

        # Convert to Path objects
        optimized_paths = [Path(output_dir) / f for f in optimized_files]
        logger.info(f"Optimized {len(optimized_paths)} images")

        return optimized_paths

    except Exception as e:
        logger.error(f"Error optimizing images: {e}")
        raise


def images_to_pdf(image_paths: List[Path], output_pdf_path: Path) -> Path:
    """Convert images to a single PDF file.

    Args:
        image_paths: List of image paths
        output_pdf_path: Output PDF path

    Returns:
        Path to created PDF
    """
    try:
        if not image_paths:
            raise ValueError("No images provided")

        logger.info(f"Creating PDF from {len(image_paths)} images...")

        # Open first image to get dimensions
        first_image = Image.open(image_paths[0])
        if first_image.mode != 'RGB':
            first_image = first_image.convert('RGB')

        # Create list of all images
        image_list = []
        for img_path in image_paths[1:]:
            img = Image.open(img_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            image_list.append(img)

        # Save as PDF
        output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        first_image.save(
            output_pdf_path,
            'PDF',
            save_all=True,
            append_images=image_list,
            resolution=100.0
        )

        logger.info(f"Created PDF: {output_pdf_path}")
        return output_pdf_path

    except Exception as e:
        logger.error(f"Error creating PDF: {e}")
        raise


def merge_pdfs(cover_pdf_path: Optional[Path], main_pdf_path: Path, output_path: Path) -> Path:
    """Merge cover and main PDF files.

    Args:
        cover_pdf_path: Optional cover PDF path
        main_pdf_path: Main PDF path
        output_path: Output merged PDF path

    Returns:
        Path to merged PDF
    """
    try:
        writer = PdfWriter()

        # Add cover pages if provided
        if cover_pdf_path and cover_pdf_path.exists():
            logger.info(f"Adding cover from {cover_pdf_path}")
            cover_reader = PdfReader(cover_pdf_path)
            for page in cover_reader.pages:
                writer.add_page(page)

        # Add main content
        logger.info(f"Adding main content from {main_pdf_path}")
        main_reader = PdfReader(main_pdf_path)
        for page in main_reader.pages:
            writer.add_page(page)

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as output_file:
            writer.write(output_file)

        logger.info(f"Merged PDF created: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Error merging PDFs: {e}")
        raise


def process_book(book_instance, settings: dict) -> Path:
    """Complete book processing workflow.

    Args:
        book_instance: Book model instance
        settings: Processing settings

    Returns:
        Path to optimized PDF
    """
    from django.conf import settings as django_settings

    try:
        # Create temporary working directory
        work_dir = Path(django_settings.MEDIA_ROOT) / 'books' / 'temp' / str(book_instance.id)
        work_dir.mkdir(parents=True, exist_ok=True)

        main_pdf_path = Path(book_instance.main_pdf.path)
        cover_pdf_path = Path(book_instance.cover_pdf.path) if book_instance.cover_pdf else None

        # Step 1: Convert main PDF to images
        logger.info("Step 1: Converting PDF pages to images...")
        images_dir = work_dir / 'images'
        image_paths = pdf_to_images(main_pdf_path, images_dir, dpi=settings.get('dpi', 150))

        # Step 2: Optimize images
        logger.info("Step 2: Optimizing images...")
        optimized_dir = work_dir / 'optimized'
        optimized_paths = optimize_images(image_paths, settings, optimized_dir)

        # Step 3: Convert optimized images to PDF
        logger.info("Step 3: Creating optimized PDF...")
        main_optimized_pdf = work_dir / 'main_optimized.pdf'
        images_to_pdf(optimized_paths, main_optimized_pdf)

        # Step 4: Merge with cover if provided
        final_pdf = work_dir / 'final_optimized.pdf'
        if cover_pdf_path:
            logger.info("Step 4: Merging with cover...")
            merge_pdfs(cover_pdf_path, main_optimized_pdf, final_pdf)
        else:
            logger.info("Step 4: No cover, using main PDF...")
            final_pdf = main_optimized_pdf

        logger.info(f"Book processing complete: {final_pdf}")
        return final_pdf

    except Exception as e:
        logger.error(f"Error processing book: {e}")
        raise
