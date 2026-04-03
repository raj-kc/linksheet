from google_auth_oauthlib.flow import Flow
from django.conf import settings

def get_google_oauth_flow():
    redirect_uri = getattr(settings, "GOOGLE_REDIRECT_URI", "http://localhost:8000/google/callback/")
    return Flow.from_client_secrets_file(
        settings.GOOGLE_CLIENT_SECRET_FILE,
        scopes=settings.GOOGLE_SCOPES,
        redirect_uri=redirect_uri,
    )
