import os
import base64
import hashlib
import secrets
import requests

from urllib.parse import urlencode
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is missing.")

if not SUPABASE_ANON_KEY:
    raise RuntimeError("SUPABASE_ANON_KEY is missing.")

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_ANON_KEY
)

# =========================================================
# PKCE STORAGE
# =========================================================

_pending_pkce = {}


# =========================================================
# GENERATE PKCE
# =========================================================

def generate_pkce():

    code_verifier = (
        base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        )
        .decode("utf-8")
        .rstrip("=")
    )

    code_challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(
                code_verifier.encode("utf-8")
            ).digest()
        )
        .decode("utf-8")
        .rstrip("=")
    )

    return code_verifier, code_challenge


# =========================================================
# GOOGLE LOGIN URL
# =========================================================

def get_google_login_url():
    code_verifier, code_challenge = generate_pkce()

    _pending_pkce["active"] = code_verifier

    redirect_to = os.getenv(
        "APP_URL",
        "http://localhost:8501"
    )

    params = {
        "provider": "google",
        "redirect_to": redirect_to,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256"
    }

    login_url = (
        f"{SUPABASE_URL}/auth/v1/authorize?"
        f"{urlencode(params)}"
    )

    return str(login_url)
# =========================================================
# EXCHANGE AUTHORIZATION CODE
# =========================================================

def exchange_code(code):

    if not code:

        raise RuntimeError(
            "OAuth authorization code is missing."
        )

    code_verifier = _pending_pkce.pop(
        "active",
        None
    )

    if not code_verifier:

        raise RuntimeError(
            "PKCE verifier is missing or expired. "
            "Please start Google login again."
        )

    url = (
        f"{SUPABASE_URL}"
        f"/auth/v1/token"
        f"?grant_type=pkce"
    )

    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": (
            f"Bearer {SUPABASE_ANON_KEY}"
        )
    }

    payload = {
        "auth_code": code,
        "code_verifier": code_verifier
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=30
    )

    if not response.ok:

        raise RuntimeError(
            "Supabase authentication failed: "
            + response.text
        )

    return response.json()


# =========================================================
# GET CURRENT USER
# =========================================================

def get_current_user(access_token):

    if not access_token:
        return None

    response = requests.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": (
                f"Bearer {access_token}"
            )
        },
        timeout=30
    )

    if not response.ok:
        return None

    return response.json()


# =========================================================
# LOGOUT
# =========================================================

def logout():

    try:
        supabase.auth.sign_out()
    except Exception:
        pass