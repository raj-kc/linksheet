"""
sheets/google_sheets.py
========================
Authoritative Google Sheets service factory.

This is the SINGLE source of truth for building an authenticated Sheets v4
service client. sheets/services/google.py imports from here — do not define
get_sheets_service() anywhere else.

Token auto-refresh:
  Google access tokens expire after ~1 hour. This function proactively
  refreshes the token before building the service so the first API call
  never fails with a 401. The refreshed credentials are saved back to the DB.
"""
import logging

from googleapiclient.discovery import build

from sheets.models import GoogleCredentials

logger = logging.getLogger(__name__)


def get_sheets_service(user):
    """
    Return an authenticated Google Sheets v4 service client using the SHEET
    OWNER's credentials (not the requesting user's). The sheet lives on the
    owner's Google Drive, so the owner's credentials are always required for
    API operations.

    Automatically refreshes expired access tokens and persists the new token.
    """
    gc = GoogleCredentials.objects.get(user=user)
    creds = gc.get_credentials()

    # Proactively refresh expired tokens so the first API call never gets a 401.
    if creds.expired and creds.refresh_token:
        try:
            import google.auth.transport.requests
            creds.refresh(google.auth.transport.requests.Request())
            gc.save_credentials(creds)
            logger.debug("Refreshed Google token for user %s", user.username)
        except Exception as exc:
            # Log but don't swallow — the API call will fail with a meaningful error.
            logger.warning("Token refresh failed for user %s: %s", user.username, exc)

    return build(
        "sheets",
        "v4",
        credentials=creds,
        cache_discovery=False,  # avoids stale discovery doc issues
    )
