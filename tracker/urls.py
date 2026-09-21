from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/create/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/<int:pk>/start/", views.task_start, name="task_start"),
    path("tasks/<int:pk>/stop/", views.task_stop, name="task_stop"),
    path("tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),
    path("history/", views.history, name="history"),
    path("subjects/", views.subjects, name="subjects"),
    path("rankings/", views.rankings, {"period": "all"}, name="rankings"),
    # rankings/today/, rankings/week/, rankings/month/, rankings/year/
    path("rankings/<str:period>/", views.rankings, name="rankings_period"),
    path("users/<str:username>/progress/", views.user_progress, name="user_progress"),
    path("rewards/", views.rewards, name="rewards"),
    path("profile/", views.profile, name="profile"),
    path("profile/username/", views.username_set, name="username_set"),
    path("live/", views.live, name="live"),
    path("live/data/", views.live_data, name="live_data"),
    path("presence/ping/", views.presence_ping, name="presence_ping"),
]
