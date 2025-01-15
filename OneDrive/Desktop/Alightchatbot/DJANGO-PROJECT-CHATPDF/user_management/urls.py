from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from users.views import CustomLoginView
from users.forms import LoginForm

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('users.urls')),
    path('login/', CustomLoginView.as_view(redirect_authenticated_user=True, template_name='users/login.html',
         authentication_form=LoginForm), name='login'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)