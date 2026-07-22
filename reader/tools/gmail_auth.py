"""
Google Gmail API Authentication Module.
Handles OAuth2 credentials loading, token creation/refreshing, and validation.
"""

import ssl
import urllib3
import requests
# Bypass SSL verification to avoid CERTIFICATE_VERIFY_FAILED errors in proxy/corporate environments
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Monkeypatch requests to disable certificate verification globally
original_request = requests.Session.request
def patched_request(self, method, url, *args, **kwargs):
    kwargs['verify'] = False
    return original_request(self, method, url, *args, **kwargs)
requests.Session.request = patched_request

# Monkeypatch httplib2 to disable SSL certificate verification globally
try:
    import httplib2
    original_httplib2_init = httplib2.Http.__init__
    def patched_httplib2_init(self, *args, **kwargs):
        kwargs['disable_ssl_certificate_validation'] = True
        original_httplib2_init(self, *args, **kwargs)
    httplib2.Http.__init__ = patched_httplib2_init
except ImportError:
    pass



from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from config import Config
from tools.utils import setup_logger


logger = setup_logger("gmail_auth")

# SCOPES required to read emails and download attachments
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]


class GmailAuthError(Exception):
    """Exception raised during OAuth/Gmail connection failures."""
    pass


def get_gmail_service() -> Resource:
    """
    Authenticates with Gmail API. Loads token.json or runs the local OAuth flow.
    
    Returns:
        A Google API Discovery client resource for Gmail.
        
    Raises:
        GmailAuthError: If authentication/connection fails, with troubleshooting info.
    """
    creds = None
    
    # 1. Load existing token if it exists
    if Config.TOKEN_PATH.exists():
        logger.debug(f"Loading cached OAuth token from {Config.TOKEN_PATH}")
        try:
            creds = Credentials.from_authorized_user_file(str(Config.TOKEN_PATH), SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load token from {Config.TOKEN_PATH}: {e}. Will re-authenticate.")

    # 2. If credentials not valid or don't exist, handle refresh or authorization
    try:
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired Google API OAuth credentials...")
                try:
                    creds.refresh(Request())
                except Exception as refresh_err:
                    logger.error(f"Failed to refresh credentials: {refresh_err}")
                    creds = None  # Force full flow if refresh fails
            
            if not creds:
                logger.info("Starting new Google API OAuth Flow...")
                if not Config.CREDENTIALS_PATH.exists():
                    raise GmailAuthError(
                        f"Google OAuth client credentials file 'credentials.json' is missing at: {Config.CREDENTIALS_PATH.resolve()}\n"
                        "Troubleshooting:\n"
                        "1. Go to Google Cloud Console (https://console.cloud.google.com/).\n"
                        "2. Enable 'Gmail API' for your project.\n"
                        "3. Set up the OAuth Consent Screen (User Type: External, add your email as a Test User).\n"
                        "4. Go to Credentials -> Create Credentials -> OAuth client ID (Application Type: Desktop app).\n"
                        "5. Download the JSON file, rename it to 'credentials.json', and place it in the 'reader/' directory."
                    )
                
                # Run local server to complete auth
                flow = InstalledAppFlow.from_client_secrets_file(str(Config.CREDENTIALS_PATH), SCOPES)
                creds = flow.run_local_server(port=0)
                
                # Save the credentials for the next run
                with open(Config.TOKEN_PATH, "w") as token_file:
                    token_file.write(creds.to_json())
                    logger.info(f"Saved OAuth token to {Config.TOKEN_PATH}")

        # Build Gmail Service
        service = build("gmail", "v1", credentials=creds)
        logger.info("Successfully connected to Gmail API.")
        return service

    except GmailAuthError:
        # Re-raise custom OAuth credential issues
        raise
    except Exception as e:
        logger.exception("Gmail API connection failed.")
        raise GmailAuthError(
            "An unexpected error occurred during Google OAuth / Gmail client initialization.\n"
            f"Error details: {e}\n"
            "Troubleshooting:\n"
            "1. Verify that your machine has internet access and can reach accounts.google.com.\n"
            "2. If you changed scopes, delete the 'token.json' file and run the application again to re-authenticate."
        ) from e
