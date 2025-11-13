from django.conf import settings
from django.urls import path, re_path

from . import views
from .views import (
    PictureDeleteView,
)

app_name = 'noteshrinker'
urlpatterns = [
    path('shrink', views.shrink, name='shrink'),
    path('download_pdf', views.download_pdf, name='download_pdf'),
    path('download_zip', views.download_zip, name='download_zip'),
    re_path(r'^delete/(?P<pk>\d+)$', PictureDeleteView.as_view(), name='upload-delete'),
    # path('view/', PictureListView.as_view(), name='upload-view'),

    # Book PDF optimization endpoints
    path('books/', views.book_list, name='book_list'),
    path('books/upload/', views.book_upload, name='book_upload'),
    path('books/<int:book_id>/preview/', views.book_preview, name='book_preview'),
    path('books/<int:book_id>/generate-preview/', views.generate_preview, name='generate_preview'),
    path('books/<int:book_id>/process/', views.book_process, name='book_process'),
    path('books/<int:book_id>/status/', views.book_status, name='book_status'),
    path('books/<int:book_id>/status/json/', views.book_status_json, name='book_status_json'),
    path('books/<int:book_id>/download/', views.book_download, name='book_download'),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
