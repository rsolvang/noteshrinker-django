from django.db import models
from django.utils import timezone


class Picture(models.Model):
    """This is a small demo using just two fields. The slug field is really not
    necessary, but makes the code simpler. ImageField depends on PIL or
    pillow (where Pillow is easily installable in a virtualenv. If you have
    problems installing pillow, use a more generic FileField instead.

    """
    file = models.ImageField(upload_to="pictures")
    slug = models.SlugField(max_length=50, blank=True)

    def __str__(self):
        return self.file.name

    # @models.permalink
    # def get_absolute_url(self):
    #     return ('index', )

    def save(self, *args, **kwargs):
        self.slug = self.file.name
        super(Picture, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """delete -- Remove to leave file."""
        self.file.delete(False)
        super(Picture, self).delete(*args, **kwargs)


class Book(models.Model):
    """Model for PDF book uploads with optional cover."""

    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('preview', 'Preview Ready'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    # File uploads
    main_pdf = models.FileField(upload_to='books/main/', help_text='Main book PDF')
    cover_pdf = models.FileField(upload_to='books/covers/', blank=True, null=True,
                                  help_text='Optional cover PDF')

    # Output
    optimized_pdf = models.FileField(upload_to='books/optimized/', blank=True, null=True)

    # Metadata
    title = models.CharField(max_length=255, blank=True)
    original_filename = models.CharField(max_length=255)
    upload_date = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')

    # Stats
    original_size_mb = models.FloatField(null=True, blank=True)
    optimized_size_mb = models.FloatField(null=True, blank=True)
    page_count = models.IntegerField(null=True, blank=True)
    cover_page_count = models.IntegerField(null=True, blank=True)

    # Processing settings (stored as JSON)
    processing_settings = models.JSONField(default=dict, blank=True)

    # Session tracking
    session_key = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ['-upload_date']

    def __str__(self):
        return f"{self.title or self.original_filename} ({self.status})"

    def delete(self, *args, **kwargs):
        """Delete associated files when deleting the model."""
        if self.main_pdf:
            self.main_pdf.delete(False)
        if self.cover_pdf:
            self.cover_pdf.delete(False)
        if self.optimized_pdf:
            self.optimized_pdf.delete(False)
        super(Book, self).delete(*args, **kwargs)

    @property
    def compression_ratio(self):
        """Calculate compression ratio percentage."""
        if self.original_size_mb and self.optimized_size_mb:
            ratio = (1 - self.optimized_size_mb / self.original_size_mb) * 100
            return round(ratio, 1)
        return None

    @property
    def total_pages(self):
        """Total pages including cover."""
        cover = self.cover_page_count or 0
        main = self.page_count or 0
        return cover + main

