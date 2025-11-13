from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.upload, name='upload'),
    path('parser/', views.parser, name='parser'), 
    path('generate/', views.generate, name='generate'), 
]
