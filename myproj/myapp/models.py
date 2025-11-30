from django.db import models

class UploadedCourses(models.Model):
    session_key = models.CharField(max_length=100, unique=True)
    courses = models.JSONField()  # Django 3.1+ supports this
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Courses for {self.session_key}"
