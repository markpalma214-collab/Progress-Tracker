"""Business logic: timer operations, rewards, statistics and rankings.

Views stay thin and call into this module. Everything here treats the
database timestamps as the single source of truth.
"""
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Avg, Case, CharField, Count, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Presence, Profile, Reward, Task

User = get_user_model()


class TimerError(Exception):
    """A timer action that isn't allowed (message is safe to show to the user)."""


# --- periods -----------------------------------------------------------------
PERIOD_LABELS = {
    "today": "Today",
    "week": "This week",
    "month": "This month",
    "year": "This year",
    "all": "All time",
}
SUBJECT_RANGE_LABELS = {
    "today": "Today",
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    "365d": "Last year",
    "all": "All time",
}
_ROLLING_DAYS = {"7d": 7, "30d": 30, "365d": 365}


def period_bounds(period, now=None):
    """Return ``(start, end)`` aware datetimes (end exclusive) or ``(None, None)`` for 'all'.

    Day boundaries are computed in the *current Django timezone*, so "today"
    means today's date where the user is, not in UTC. Weeks start on Monday.
    """
    if period == "all":
        return None, None
    now = timezone.localtime(now or timezone.now())
    today = now.date()

    def midnight(day):
        return timezone.make_aware(datetime.combine(day, time.min), now.tzinfo)

    if period == "today":
        start_day = today
    elif period == "week":
        start_day = today - timedelta(days=today.weekday())
    elif period == "month":
        start_day = today.replace(day=1)
    elif period == "year":
        start_day = today.replace(month=1, day=1)
    elif period in _ROLLING_DAYS:
        start_day = today - timedelta(days=_ROLLING_DAYS[period] - 1)
    else:
        raise ValueError(f"Unknown period: {period}")
    return midnight(start_day), midnight(today + timedelta(days=1))


def completed_in_period(queryset, period, now=None):
    """Completed sessions whose end time falls inside the period."""
    queryset = queryset.filter(is_completed=True)
    start, end = period_bounds(period, now)
    if start is not None:
        queryset = queryset.filter(completed_at__gte=start, completed_at__lt=end)
    return queryset


# --- timer -------------------------------------------------------------------
def finalize_expired(queryset=None, now=None):
    """Close sessions whose planned time has passed (e.g. the browser was closed).

    The recorded end is capped at the planned end, so leaving a tab open can
    never inflate study time.
    """
    now = now or timezone.now()
    tasks = Task.objects.all() if queryset is None else queryset
    for task in tasks.filter(started_at__isnull=False, completed_at__isnull=True):
        if now >= task.planned_end:
            try:
                stop_task(task, now)
            except TimerError:
                pass  # closed by a concurrent request


def start_task(task, now=None):
    now = now or timezone.now()
    finalize_expired(Task.objects.filter(user=task.user), now)
    try:
        with transaction.atomic():
            task = Task.objects.select_for_update().get(pk=task.pk, user=task.user)
            if task.started_at is not None:
                raise TimerError("This task has already been started.")
            if Task.objects.filter(
                user=task.user, started_at__isnull=False, completed_at__isnull=True
            ).exists():
                raise TimerError(
                    "You already have a running timer. Stop it before starting another task."
                )
            task.started_at = now
            task.save(update_fields=["started_at"])
    except IntegrityError:  # lost a race against the one-running-task constraint
        raise TimerError("You already have a running timer.") from None
    return task


def stop_task(task, now=None):
    """Stop a running task and record the measured study time."""
    now = now or timezone.now()
    with transaction.atomic():
        task = Task.objects.select_for_update().get(pk=task.pk)
        if not task.is_running:
            raise TimerError("This task is not running.")
        end = max(task.started_at, min(now, task.planned_end))
        task.completed_at = end
        task.studied_seconds = int((end - task.started_at).total_seconds())
        task.is_completed = True
        task.save(update_fields=["completed_at", "studied_seconds", "is_completed"])
        award_rewards(task)
    return task


# --- rewards -------------------------------------------------------------------
def award_rewards(task):
    """Give automatic badges for a finished session (idempotent)."""
    earned = []
    if task.studied_seconds >= task.duration_seconds:
        earned.append("Session complete")
        if task.duration >= 60:
            earned.append("Deep work")
    first = not Task.objects.filter(user=task.user, is_completed=True).exclude(pk=task.pk).exists()
    if first:
        earned.append("First session")
    for name in earned:
        Reward.objects.get_or_create(task=task, reward=name)


# --- statistics ------------------------------------------------------------------
def _seconds(filter_q=None):
    return Coalesce(Sum("studied_seconds", filter=filter_q), Value(0))


def dashboard_stats(user, now=None):
    """All dashboard numbers in ONE aggregate query."""
    start, end = period_bounds("today", now)
    done = Q(is_completed=True)
    counts = Task.objects.filter(user=user).aggregate(
        total=Count("pk"),
        completed=Count("pk", filter=done),
        active=Count("pk", filter=Q(started_at__isnull=False, completed_at__isnull=True)),
        study_seconds=_seconds(done),
        today_seconds=_seconds(done & Q(completed_at__gte=start, completed_at__lt=end)),
    )
    counts["remaining"] = counts["total"] - counts["completed"] - counts["active"]
    return counts


def study_totals(queryset):
    """Total seconds, session count and average length for a completed-task queryset."""
    return queryset.aggregate(
        seconds=_seconds(),
        sessions=Count("pk"),
        average=Coalesce(Avg("studied_seconds"), Value(0.0)),
    )


def leaderboard(period, now=None, limit=50):
    """Users ranked by recorded study seconds in the period (ties share a rank)."""
    counted = Q(tasks__is_completed=True)
    start, end = period_bounds(period, now)
    if start is not None:
        counted &= Q(tasks__completed_at__gte=start, tasks__completed_at__lt=end)
    users = (
        User.objects.filter(is_active=True)
        .exclude(profile__needs_username=True)  # nobody appears under a placeholder name
        .annotate(
            total_seconds=Sum("tasks__studied_seconds", filter=counted),
            completed_count=Count("tasks", filter=counted),
        )
        .filter(total_seconds__gt=0)
        .order_by("-total_seconds", "username")[:limit]
    )
    rows, rank, previous = [], 0, None
    for position, user in enumerate(users, start=1):
        if user.total_seconds != previous:
            rank, previous = position, user.total_seconds
        rows.append(
            {"rank": rank, "user": user, "seconds": user.total_seconds, "tasks": user.completed_count}
        )
    return rows


def subject_breakdown(user, range_key, now=None):
    """Study time grouped by category (or by title when no category is set)."""
    label = Case(
        When(category="", then=F("title")),
        default=F("category"),
        output_field=CharField(),
    )
    return list(
        completed_in_period(Task.objects.filter(user=user), range_key, now)
        .annotate(label=label)
        .values("label")
        .annotate(seconds=Sum("studied_seconds"), sessions=Count("pk"), average=Avg("studied_seconds"))
        .order_by("-seconds", "label")
    )


# --- presence ("who is online") ------------------------------------------------
ACTIVE_WINDOW = timedelta(minutes=2)  # seen within this long ago = online
PRESENCE_UPDATE_SECONDS = 45  # write to the database at most this often per user
PRESENCE_SESSION_KEY = "presence_updated_at"


def touch_presence(user, session, now=None):
    """Record that ``user`` is active. Returns True when the database was written.

    The time of the last write is kept in the user's session (which Django has
    already loaded), so most requests cost no extra query.
    """
    now = now or timezone.now()
    last_write = session.get(PRESENCE_SESSION_KEY)
    if last_write is not None and now.timestamp() - last_write < PRESENCE_UPDATE_SECONDS:
        return False
    if not Presence.objects.filter(user=user).update(last_seen=now):
        try:
            with transaction.atomic():
                Presence.objects.create(user=user, last_seen=now)
        except IntegrityError:  # another request created the row first
            Presence.objects.filter(user=user).update(last_seen=now)
    session[PRESENCE_SESSION_KEY] = now.timestamp()
    return True


def presence_counts(now=None, finalize=True):
    """``{"online": users seen recently, "studying": running timers}``."""
    now = now or timezone.now()
    if finalize:
        finalize_expired(now=now)  # so finished timers don't count as "studying"
    return {
        "online": Presence.objects.filter(
            last_seen__gte=now - ACTIVE_WINDOW, user__is_active=True
        ).count(),
        "studying": Task.objects.filter(started_at__isnull=False, completed_at__isnull=True).count(),
    }


def running_sessions(viewer, now=None, limit=100):
    """Everyone's running timers, oldest first. Private titles are hidden from others."""
    now = now or timezone.now()
    finalize_expired(now=now)
    tasks = (
        Task.objects.filter(started_at__isnull=False, completed_at__isnull=True)
        .select_related("user")
        .order_by("started_at")[:limit]
    )
    return [
        {
            "username": task.user.username,
            "title": task.title if (task.is_public or task.user_id == viewer.pk) else "Private session",
            "started": task.started_ms,
            "duration": task.duration_seconds,
            "is_me": task.user_id == viewer.pk,
        }
        for task in tasks
    ]


# --- choosing a username after OAuth signup --------------------------------------
USERNAME_OK_KEY = "username_ok"


def needs_username(user, session):
    """True while the user still has to pick a username.

    Once the answer is "no" it is remembered in the session, so normal users
    cost one query per login instead of one per request.
    """
    if session.get(USERNAME_OK_KEY):
        return False
    needs = Profile.objects.filter(user=user, needs_username=True).exists()
    if not needs:
        session[USERNAME_OK_KEY] = True
    return needs


def set_username(user, username, session):
    with transaction.atomic():
        user.username = username
        user.save(update_fields=["username"])
        Profile.objects.filter(user=user).update(needs_username=False)
    session[USERNAME_OK_KEY] = True
