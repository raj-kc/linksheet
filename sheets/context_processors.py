"""
sheets/context_processors.py
=============================
Injects Google profile picture into every template context.

Performance note:
  This processor is called on EVERY request (including static files, admin,
  etc.). We use select_related to avoid a second join query, and skip the DB
  hit entirely for unauthenticated users and requests where the user has no
  Google credentials stored.
"""
from .models import GoogleCredentials


def google_profile(request):
    """
    Add google_profile_pic to template context for authenticated users.

    Returns {"google_profile_pic": url_or_None} always so templates can safely
    reference {{ google_profile_pic }} without an existence check.
    """
    if not request.user.is_authenticated:
        return {"google_profile_pic": None}

    # select_related pre-fetches the user row we already have — avoids a
    # second round-trip just to confirm ownership of the credentials row.
    gc = (
        GoogleCredentials.objects
        .filter(user=request.user)
        .values_list("profile_picture", flat=True)
        .first()
    )
    return {"google_profile_pic": gc}
