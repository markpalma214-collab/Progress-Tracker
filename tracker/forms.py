import re

from django import forms
from django.contrib.auth import get_user_model

from .models import MAX_BREAK_MINUTES, MAX_DURATION_MINUTES, Reward, Task


class TaskForm(forms.ModelForm):
    """Note: no started_at/completed_at here - the server owns all timestamps."""

    class Meta:
        model = Task
        fields = ["title", "description", "category", "duration", "break_duration", "is_public"]
        labels = {
            "duration": "Duration (minutes)",
            "break_duration": "Break after (minutes)",
            "is_public": "Show this task's title on my public progress page",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "duration": forms.NumberInput(attrs={"min": 1, "max": MAX_DURATION_MINUTES}),
            "break_duration": forms.NumberInput(attrs={"min": 0, "max": MAX_BREAK_MINUTES}),
        }

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Give the task a title.")
        return title

    def clean_duration(self):
        duration = self.cleaned_data["duration"]
        if duration is None or duration < 1:
            raise forms.ValidationError("Duration must be at least 1 minute.")
        return duration


class RewardForm(forms.ModelForm):
    """Attach your own reward (e.g. 'Bubble tea') to one of YOUR tasks."""

    class Meta:
        model = Reward
        fields = ["task", "reward"]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["task"].queryset = Task.objects.filter(user=user)  # ownership check
        self.fields["reward"].label = "Reward"


class ProfileForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name"]


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
RESERVED_USERNAMES = {
    "admin", "administrator", "root", "system", "staff", "moderator", "support",
    "null", "none", "anonymous", "everyone", "me", "you",
}


class UsernameForm(forms.Form):
    """The username shown on rankings and the live room."""

    username = forms.CharField(
        min_length=3,
        max_length=20,
        label="Username",
        help_text="3-20 characters: letters, numbers, _ . -",
        widget=forms.TextInput(
            attrs={"autocomplete": "off", "autocapitalize": "none", "spellcheck": "false", "placeholder": "e.g. focus_fox"}
        ),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if not USERNAME_PATTERN.match(username):
            raise forms.ValidationError("Use only letters, numbers, underscores, dots and hyphens.")
        if username.lower() in RESERVED_USERNAMES:
            raise forms.ValidationError("That name is reserved. Pick another.")
        taken = get_user_model().objects.filter(username__iexact=username).exclude(pk=self.user.pk)
        if taken.exists():
            raise forms.ValidationError("That username is already taken.")
        return username
