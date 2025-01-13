from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='users-home'),
    path('register/', views.RegisterView.as_view(), name='users-register'),
    path('profile/', views.profile, name='users-profile'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('alight-chatbot/', views.alight_chatbot, name='alight_chatbot'),
    path('document-management/', views.document_management, name='document_management'),
    path('document-management/upload/', views.upload_document, name='upload_document'),
    path('document-management/delete/<int:doc_id>/', views.delete_document, name='delete_document'),    path('document-management/download/<int:doc_id>/', views.download_document, name='download_document'),
    path('document-management/preview/<int:doc_id>/', views.preview_document, name='preview_document'),
    path('document-chat/', views.document_chat, name='document_chat'),   
    path('api/document-list/', views.document_list, name='document_list'),
    path('logout/', views.custom_logout, name='logout'),
    path('logout-page/', views.logout_page, name='logout_page'),
    path('api/chat/initialize/', views.initialize_chat, name='initialize_chat'),
    path('api/chat/response/', views.chat_response, name='chat_response'),
    path('', views.home, name='home'),
    
]