from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

MAX_DURATION_MINUTES = 600
MAX_BREAK_MINUTES = 120


class Task(models.Model):
    """A study task and its single timed session.

    Lifecycle (all state is derived from the timestamps, so it can't drift):

        pending   started_at is NULL
        running   started_at set, completed_at NULL
        completed completed_at set and the full duration was studied
        stopped   completed_at set but the user stopped early

    All durations are stored in MINUTES, except ``studied_seconds`` which is the
    server-measured result of the session (seconds, so short sessions still count).

    Break: ``break_duration`` is the break (minutes) planned after the session.
    The break window is derived: completed_at -> completed_at + break_duration.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks"
    )
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=60,
        blank=True,
        help_text="Optional subject (e.g. Python). Used to group study time.",
    )
    duration = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_DURATION_MINUTES)],
        help_text="Planned study time in minutes.",
    )
    break_duration = models.PositiveIntegerField(
        default=5,
        validators=[MaxValueValidator(MAX_BREAK_MINUTES)],
        help_text="Break after the session, in minutes.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    studied_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Seconds actually studied, measured by the server when the session ends.",
    )
    is_completed = models.BooleanField(default=False)
    is_public = models.BooleanField(
        default=True,
        help_text="Public tasks show their title on your progress page. Private ones appear as 'Private session'.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "completed_at"]),
            models.Index(fields=["completed_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration__gt=0), name="task_duration_positive"
            ),
            # The database itself guarantees one running timer per user.
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(started_at__isnull=False, completed_at__isnull=True),
                name="one_running_task_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.duration} min)"

    # --- state -------------------------------------------------------------
    @property
    def is_pending(self):
        return self.started_at is None

    @property
    def is_running(self):
        return self.started_at is not None and self.completed_at is None

    @property
    def status(self):
        if self.is_pending:
            return "pending"
        if self.is_running:
            return "running"
        return "completed" if self.studied_seconds >= self.duration_seconds else "stopped"

    @property
    def status_label(self):
        return {
            "pending": "Ready",
            "running": "Running",
            "completed": "Completed",
            "stopped": "Stopped early",
        }[self.status]

    # --- time maths (server-side, authoritative) -----------------------------
    @property
    def duration_seconds(self):
        return self.duration * 60

    @property
    def planned_end(self):
        return self.started_at + timedelta(minutes=self.duration)

    @property
    def started_ms(self):
        return int(self.started_at.timestamp() * 1000) if self.started_at else 0

    def elapsed_seconds(self, now=None):
        if self.started_at is None:
            return 0
        if self.completed_at is not None:
            return min(self.studied_seconds, self.duration_seconds)
        now = now or timezone.now()
        elapsed = int((now - self.started_at).total_seconds())
        return max(0, min(elapsed, self.duration_seconds))

    def remaining_seconds(self, now=None):
        return self.duration_seconds - self.elapsed_seconds(now)

    def progress_percent(self, now=None):
        """0-100, never above 100."""
        return min(100.0, self.elapsed_seconds(now) / self.duration_seconds * 100)

    # --- break -------------------------------------------------------------
    @property
    def break_ends_at(self):
        if self.completed_at is None:
            return None
        return self.completed_at + timedelta(minutes=self.break_duration)

    def break_seconds_left(self, now=None):
        if self.break_ends_at is None:
            return 0
        now = now or timezone.now()
        return max(0, int((self.break_ends_at - now).total_seconds()))

    def in_break(self, now=None):
        return self.break_seconds_left(now) > 0


class Reward(models.Model):
    """A reward attached to a task (auto-awarded badge or a treat you set yourself)."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="rewards")
    reward = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["task", "reward"], name="unique_reward_per_task"),
        ]

    def __str__(self):
        return f"{self.reward} - {self.task.title}"


class Presence(models.Model):
    """When a user was last seen using the site.

    Updated (throttled) by ``PresenceMiddleware``. "Online" means ``last_seen``
    is within ``services.ACTIVE_WINDOW``.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="presence"
    )
    last_seen = models.DateTimeField(db_index=True)

    def __str__(self):
        return f"{self.user} last seen {self.last_seen:%Y-%m-%d %H:%M}"


class Profile(models.Model):
    """Extra per-user state. Only created for people who signed up through OAuth.

    ``needs_username`` is True until they pick their own username in the
    required pop-up (their Google-derived name is never used).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    needs_username = models.BooleanField(default=False)

    def __str__(self):
        return f"Profile of {self.user}"
