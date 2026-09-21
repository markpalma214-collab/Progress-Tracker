from django.shortcuts import redirect

from . import services


class PresenceMiddleware:
    """Marks logged-in users as "seen just now" on each request (throttled)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            services.touch_presence(user, request.session)
        return self.get_response(request)


class UsernameSetupMiddleware:
    """Until an OAuth signup has chosen a username, only the dashboard (which shows
    the pop-up), the save endpoint, the heartbeat and login/logout pages work.
    Everything else redirects to the dashboard, so the step can't be skipped."""

    EXEMPT_URL_NAMES = {"dashboard", "username_set", "presence_ping"}
    EXEMPT_PREFIXES = ("account_", "socialaccount_", "google_")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        request.needs_username = bool(
            user is not None and user.is_authenticated and services.needs_username(user, request.session)
        )
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.needs_username:
            return None
        match = request.resolver_match
        name = match.url_name or ""
        if match.namespace == "admin" or name in self.EXEMPT_URL_NAMES or name.startswith(self.EXEMPT_PREFIXES):
            return None
        return redirect("dashboard")
