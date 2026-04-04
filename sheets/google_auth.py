from google_auth_oauthlib.flow import Flow
from django.conf import settings

def get_google_oauth_flow():
    redirect_uri = getattr(settings, "GOOGLE_REDIRECT_URI", "http://localhost:8000/google/callback/")
    
    if getattr(settings, "GOOGLE_CLIENT_ID", None) and getattr(settings, "GOOGLE_CLIENT_SECRET", None):
        client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "project_id": "linksheet",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": settings.GOOGLE_CLIENT_SECRET
            }
        }
        return Flow.from_client_config(
            client_config,
            scopes=settings.GOOGLE_SCOPES,
            redirect_uri=redirect_uri,
        )
    else:
        return Flow.from_client_secrets_file(
            settings.GOOGLE_CLIENT_SECRET_FILE,
            scopes=settings.GOOGLE_SCOPES,
            redirect_uri=redirect_uri,
        )
