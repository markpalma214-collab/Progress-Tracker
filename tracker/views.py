from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from . import services
from django.db import IntegrityError

from .forms import ProfileForm, RewardForm, TaskForm, UsernameForm
from .models import Reward, Task

User = get_user_model()

TASK_FILTERS = {
    "all": {},
    "pending": {"started_at__isnull": True},
    "running": {"started_at__isnull": False, "completed_at__isnull": True},
    "done": {"is_completed": True},
}


def _paginate(request, queryset, per_page=20):
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


def _user_tasks(user):
    return Task.objects.filter(user=user)


def _running_task(user):
    return _user_tasks(user).filter(started_at__isnull=False, completed_at__isnull=True).first()


# --- dashboard & task pages --------------------------------------------------
@login_required
def dashboard(request):
    now = timezone.now()
    tasks = _user_tasks(request.user)
    services.finalize_expired(tasks, now)

    active = _running_task(request.user)
    pending = list(tasks.filter(started_at__isnull=True).prefetch_related("rewards"))
    recent = list(tasks.filter(is_completed=True).order_by("-completed_at").prefetch_related("rewards")[:8])

    break_task = None
    if active is None and recent and recent[0].in_break(now):
        break_task = recent[0]

    return render(
        request,
        "tracker/dashboard.html",
        {
            "active": active,
            "pending": pending,
            "recent": recent,
            "break_task": break_task,
            "break_end_ms": int(break_task.break_ends_at.timestamp() * 1000) if break_task else 0,
            "now_ms": int(now.timestamp() * 1000),
            "stats": services.dashboard_stats(request.user, now),
            "latest_rewards": Reward.objects.filter(task__user=request.user).select_related("task")[:4],
            "presence": services.presence_counts(now),
        },
    )


@login_required
def task_list(request):
    services.finalize_expired(_user_tasks(request.user))
    current = request.GET.get("status", "all")
    if current not in TASK_FILTERS:
        current = "all"
    tasks = _user_tasks(request.user).filter(**TASK_FILTERS[current]).prefetch_related("rewards")
    return render(
        request,
        "tracker/task_list.html",
        {
            "page_obj": _paginate(request, tasks, 24),
            "current": current,
            "filters": TASK_FILTERS.keys(),
            "active": _running_task(request.user),
            "counts": services.dashboard_stats(request.user),
        },
    )


@login_required
def task_create(request):
    form = TaskForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.user = request.user  # never taken from the form
        task.save()
        messages.success(request, f"Task '{task.title}' created. Press START when you're ready.")
        return redirect("dashboard")
    return render(request, "tracker/task_form.html", {"form": form})


@login_required
def task_detail(request, pk):
    services.finalize_expired(_user_tasks(request.user))
    task = get_object_or_404(Task.objects.prefetch_related("rewards"), pk=pk, user=request.user)
    return render(
        request,
        "tracker/task_detail.html",
        {"task": task, "active": _running_task(request.user)},
    )


# --- timer endpoints (POST only, owner only) ---------------------------------
def _wants_json(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


@login_required
@require_POST
def task_start(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)  # 404 for other users' tasks
    try:
        services.start_task(task)
        messages.success(request, f"Timer started: {task.title}.")
    except services.TimerError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard")


@login_required
@require_POST
def task_stop(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    try:
        task = services.stop_task(task)
    except services.TimerError as exc:
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": str(exc)}, status=409)
        messages.error(request, str(exc))
        return redirect("dashboard")
    if _wants_json(request):
        return JsonResponse({"ok": True, "status": task.status, "studied_seconds": task.studied_seconds})
    messages.success(request, f"Timer stopped. {task.studied_seconds // 60} min recorded.")
    return redirect("dashboard")


@login_required
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    if task.is_running:
        messages.error(request, "Stop the timer before deleting this task.")
        return redirect("task_detail", pk=task.pk)
    task.delete()
    messages.success(request, "Task deleted.")
    return redirect("task_list")


# --- history, subjects, rankings ---------------------------------------------
@login_required
def history(request):
    services.finalize_expired(_user_tasks(request.user))
    period = request.GET.get("period", "today")
    if period not in services.PERIOD_LABELS:
        period = "today"
    sessions = services.completed_in_period(_user_tasks(request.user), period)
    return render(
        request,
        "tracker/history.html",
        {
            "period": period,
            "periods": services.PERIOD_LABELS,
            "totals": services.study_totals(sessions),
            "page_obj": _paginate(request, sessions.order_by("-completed_at").prefetch_related("rewards")),
        },
    )


@login_required
def subjects(request):
    services.finalize_expired(_user_tasks(request.user))
    key = request.GET.get("range", "7d")
    if key not in services.SUBJECT_RANGE_LABELS:
        key = "7d"
    rows = services.subject_breakdown(request.user, key)
    top = rows[0]["seconds"] if rows else 0
    for row in rows:
        row["percent"] = row["seconds"] / top * 100 if top else 0  # bar width
    return render(
        request,
        "tracker/subjects.html",
        {"current": key, "ranges": services.SUBJECT_RANGE_LABELS, "rows": rows},
    )


@login_required
def rankings(request, period):
    if period not in services.PERIOD_LABELS:
        raise Http404("Unknown ranking period")
    services.finalize_expired()  # close any timers that ran out while nobody was looking
    return render(
        request,
        "tracker/rankings.html",
        {"period": period, "periods": services.PERIOD_LABELS, "rows": services.leaderboard(period)},
    )


@login_required
def user_progress(request, username):
    person = get_object_or_404(User, username=username, is_active=True)
    services.finalize_expired(_user_tasks(person))
    is_owner = person == request.user
    tasks = _user_tasks(person)
    recent = tasks.filter(is_completed=True).order_by("-completed_at")[:10]
    return render(
        request,
        "tracker/user_progress.html",
        {
            "person": person,
            "is_owner": is_owner,
            "active": _running_task(person),
            "stats": services.dashboard_stats(person),
            "recent": recent,
        },
    )


# --- rewards & profile -------------------------------------------------------
@login_required
def rewards(request):
    form = RewardForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Reward added.")
        return redirect("rewards")
    items = Reward.objects.filter(task__user=request.user).select_related("task")
    return render(request, "tracker/rewards.html", {"form": form, "items": items})


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("profile")
    return render(
        request, "tracker/profile.html", {"form": form, "stats": services.dashboard_stats(request.user)}
    )


# --- live features ---------------------------------------------------------------
def _json_login_required(view):
    """Like @login_required, but answers 401 JSON instead of redirecting (for fetch())."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "login required"}, status=401)
        return view(request, *args, **kwargs)

    return wrapper


@login_required
def live(request):
    return render(request, "tracker/live.html", {"presence": services.presence_counts()})


@never_cache
@_json_login_required
@require_POST
def presence_ping(request):
    """Heartbeat: the middleware has already refreshed last_seen; reply with the counts."""
    return JsonResponse(services.presence_counts())


@never_cache
@_json_login_required
@require_GET
def live_data(request):
    now = timezone.now()
    sessions = services.running_sessions(request.user, now)
    for session in sessions:
        session["url"] = reverse("user_progress", args=[session["username"]])
    return JsonResponse(
        {"now": int(now.timestamp() * 1000), "sessions": sessions, **services.presence_counts(now, finalize=False)}
    )


@login_required
@require_POST
def username_set(request):
    """Save the username chosen in the pop-up (only allowed while one is still needed)."""
    ajax = _wants_json(request)
    if not request.needs_username:
        if ajax:
            return JsonResponse({"ok": False, "errors": {"username": ["Your username is already set."]}}, status=403)
        messages.info(request, "Your username is already set.")
        return redirect("dashboard")

    form = UsernameForm(request.POST, user=request.user)
    if form.is_valid():
        try:
            services.set_username(request.user, form.cleaned_data["username"], request.session)
        except IntegrityError:  # someone took it a moment ago
            form.add_error("username", "That username is already taken.")
        else:
            if ajax:
                return JsonResponse({"ok": True})
            messages.success(request, f"Welcome, {request.user.username}!")
            return redirect("dashboard")

    errors = {field: [str(error) for error in errs] for field, errs in form.errors.items()}
    if ajax:
        return JsonResponse({"ok": False, "errors": errors}, status=400)
    for error in errors.get("username", []):
        messages.error(request, error)
    return redirect("dashboard")
