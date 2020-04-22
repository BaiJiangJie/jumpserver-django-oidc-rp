"""
    Project base URL configuration
    ==============================

    For more information on this file, see https://docs.djangoproject.com/en/1.10/topics/http/urls/

"""

from django.conf.urls import include, url
from django.contrib import admin


urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^oidc/', include('jms_oidc_rp.urls')),
]
