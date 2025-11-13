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
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
