from django.contrib import admin

from .models import ClassSchedule, Course, Enrollment


admin.site.register(Course)
admin.site.register(ClassSchedule)
admin.site.register(Enrollment)
