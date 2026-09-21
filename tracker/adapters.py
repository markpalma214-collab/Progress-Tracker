import secrets

from allauth.account.utils import user_username
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

from .models import Profile


def placeholder_username():
    """A throw-away name like ``player_3fa9c1d2`` (never derived from the Google account)."""
    User = get_user_model()
    while True:
        name = f"player_{secrets.token_hex(4)}"
        if not User.objects.filter(username__iexact=name).exists():
            return name


class TrackerSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Hooks into django-allauth's social signup.

    * ``populate_user``: allauth would build a username from the person's name
      or Gmail address. We replace it with a placeholder.
    * ``save_user``: mark the new user as needing to choose a real username.
    """

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user_username(user, placeholder_username())
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        Profile.objects.update_or_create(user=user, defaults={"needs_username": True})
        return user
