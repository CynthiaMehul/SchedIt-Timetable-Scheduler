from django.urls import path
from . import views

app_name = "myapp"

urlpatterns = [
    path("", views.home, name="home"),
    path("instructions/", views.instructions, name="instructions"),  # <-- add this
    path("api/check_session/", views.check_session, name="check_session"),
    path("api/upload_raw/", views.upload_raw_text, name="upload_raw"),
    path("edit/", views.edit_courses, name="edit_courses"),
    path("generate/", views.generate, name="generate"),
    path("timetable/", views.timetable_view, name="timetable"),
]
