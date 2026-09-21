from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def clock(seconds):
    """Seconds -> 'mm:ss' or 'h:mm:ss'."""
    seconds = max(0, int(seconds or 0))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


@register.filter
def hm(seconds):
    """Seconds -> '2h 15m' (or '45m', '30s')."""
    seconds = int(seconds or 0)
    if seconds < 60:
        return f"{seconds}s"
    hours, minutes = divmod(seconds // 60, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


@register.filter
def hours(seconds):
    """Seconds -> hours with one decimal (e.g. 1.5)."""
    return f"{(seconds or 0) / 3600:.1f}"


@register.inclusion_tag("tracker/_progress.html")
def progress_bar(task, controls=False, large=False):
    """Render a task's progress bar.

    ``controls=True`` lets the timer script call the stop endpoint when the
    bar reaches 100% (only pass it for the task's owner).
    """
    now = timezone.now()
    return {
        "task": task,
        "controls": controls,
        "large": large,
        "now_ms": int(now.timestamp() * 1000),
        "elapsed": task.elapsed_seconds(now),
        "remaining": task.remaining_seconds(now),
        "percent": task.progress_percent(now),
        "percent_int": int(task.progress_percent(now)),  # floor: never shows 100% early
    }
