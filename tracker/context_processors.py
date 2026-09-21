from .forms import UsernameForm


def username_setup(request):
    """Adds the pop-up's form to every template while a username is still needed."""
    if getattr(request, "needs_username", False):
        return {"needs_username": True, "username_form": UsernameForm(user=request.user)}
    return {"needs_username": False}
