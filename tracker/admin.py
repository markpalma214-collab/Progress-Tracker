from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count, Sum

from .models import Presence, Profile, Reward, Task

User = get_user_model()


class RewardInline(admin.TabularInline):
    model = Reward
    extra = 0


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "category", "duration", "status", "studied_minutes", "created_at", "is_public")
    list_filter = ("is_completed", "is_public", "created_at", "category")
    search_fields = ("title", "description", "category", "user__username")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_select_related = ("user",)
    readonly_fields = ("created_at",)
    inlines = [RewardInline]

    @admin.display(description="Studied (min)")
    def studied_minutes(self, obj):
        return round(obj.studied_seconds / 60, 1)


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    list_display = ("reward", "task", "created_at")
    list_filter = ("created_at",)
    search_fields = ("reward", "task__title", "task__user__username")
    ordering = ("-created_at",)
    list_select_related = ("task", "task__user")


admin.site.unregister(User)


@admin.register(User)
class TrackerUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ("task_count", "study_hours")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _tasks=Count("tasks", distinct=True), _seconds=Sum("tasks__studied_seconds")
        )

    @admin.display(description="Tasks", ordering="_tasks")
    def task_count(self, obj):
        return obj._tasks

    @admin.display(description="Study hours", ordering="_seconds")
    def study_hours(self, obj):
        return round((obj._seconds or 0) / 3600, 1)


@admin.register(Presence)
class PresenceAdmin(admin.ModelAdmin):
    list_display = ("user", "last_seen")
    search_fields = ("user__username",)
    ordering = ("-last_seen",)
    list_select_related = ("user",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """Tick "needs username" to make someone choose a new username at next login."""

    list_display = ("user", "needs_username")
    list_filter = ("needs_username",)
    search_fields = ("user__username",)
    list_select_related = ("user",)
