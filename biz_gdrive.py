# =============================================================================
#  biz_gdrive.py — Google Drive Integration for Sarathi-AI CRM
# =============================================================================
#
#  Provides:
#    - OAuth2 flow (authorization URL → callback → token storage)
#    - Upload PDF reports to tenant's Google Drive folder
#    - Create/manage per-tenant CRM folder hierarchy
#    - List & retrieve uploaded files
#
#  Env vars required (in biz.env):
#    GDRIVE_CLIENT_ID      — Google Cloud OAuth2 client ID
#    GDRIVE_CLIENT_SECRET   — Google Cloud OAuth2 client secret
#    GDRIVE_REDIRECT_URI    — Redirect URI (e.g., {SERVER_URL}/api/gdrive/callback)
#
# =============================================================================

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("sarathi.gdrive")

# =============================================================================
#  CONFIG
# =============================================================================

_client_id: str = ""
_client_secret: str = ""
_redirect_uri: str = ""
_token_store: Path = Path("gdrive_tokens")

# Google OAuth2 endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_DRIVE_API = "https://www.googleapis.com/drive/v3"
GOOGLE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
GOOGLE_SHEETS_API = "https://sheets.googleapis.com/v4"

# Scopes needed:
#   drive.file        — write/manage files created by Sarathi (uploaded reports)
#   drive.readonly    — list user's existing Sheets/Excel for bulk import
#   spreadsheets.readonly — read cell data from user's Google Sheets
SCOPES = (
    "https://www.googleapis.com/auth/drive.file "
    "https://www.googleapis.com/auth/drive.readonly "
    "https://www.googleapis.com/auth/spreadsheets.readonly "
    "https://www.googleapis.com/auth/userinfo.email"
)


def init_gdrive():
    """Initialize Google Drive integration from env vars."""
    global _client_id, _client_secret, _redirect_uri
    # Accept either GDRIVE_* or GOOGLE_CLIENT_* (same Google OAuth credentials)
    _client_id = os.getenv("GDRIVE_CLIENT_ID", "").strip() or os.getenv("GOOGLE_CLIENT_ID", "").strip()
    _client_secret = os.getenv("GDRIVE_CLIENT_SECRET", "").strip() or os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    _redirect_uri = os.getenv("GDRIVE_REDIRECT_URI", "").strip() or os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    _token_store.mkdir(exist_ok=True)

    if is_enabled():
        logger.info("✅ Google Drive integration ready")
    else:
        logger.warning("⚠️ Google Drive not configured (GDRIVE_CLIENT_ID missing)")


def is_enabled() -> bool:
    """Check if Google Drive integration is configured."""
    return bool(_client_id and _client_secret)


# =============================================================================
#  OAUTH2 FLOW
# =============================================================================

def get_auth_url(tenant_id: int) -> str:
    """
    Generate OAuth2 authorization URL for a tenant.
    The 'state' param carries the tenant_id for the callback.
    """
    import urllib.parse
    params = {
        "client_id": _client_id,
        "redirect_uri": _redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": str(tenant_id),
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def handle_callback(code: str, tenant_id: int) -> dict:
    """
    Exchange authorization code for tokens and store them.
    Returns: {"success": True, "email": "..."} or {"success": False, "error": "..."}
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code,
                "client_id": _client_id,
                "client_secret": _client_secret,
                "redirect_uri": _redirect_uri,
                "grant_type": "authorization_code",
            })
            if resp.status_code != 200:
                logger.error("Token exchange failed: %s", resp.text)
                return {"success": False, "error": "Token exchange failed"}

            tokens = resp.json()
            tokens["obtained_at"] = int(time.time())

            # Get user email for display
            user_info = await _get_user_info(tokens["access_token"])
            tokens["email"] = user_info.get("email", "")

            # Store tokens for tenant
            _save_tokens(tenant_id, tokens)

            logger.info("Google Drive connected for tenant %d (%s)",
                        tenant_id, tokens["email"])
            return {"success": True, "email": tokens["email"]}

    except Exception as e:
        logger.error("OAuth callback error: %s", e)
        return {"success": False, "error": str(e)}


async def _get_user_info(access_token: str) -> dict:
    """Get Google user info (email) from access token."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            return resp.json() if resp.status_code == 200 else {}
    except Exception:
        return {}


# =============================================================================
#  TOKEN MANAGEMENT
# =============================================================================

def _token_path(tenant_id: int) -> Path:
    return _token_store / f"tenant_{tenant_id}.json"


def _save_tokens(tenant_id: int, tokens: dict):
    _token_path(tenant_id).write_text(json.dumps(tokens, indent=2))


def _load_tokens(tenant_id: int) -> Optional[dict]:
    path = _token_path(tenant_id)
    if path.exists():
        return json.loads(path.read_text())
    return None


def is_connected(tenant_id: int) -> bool:
    """Check if a tenant has connected Google Drive."""
    return _token_path(tenant_id).exists()


def get_connected_email(tenant_id: int) -> str:
    """Get the email of the connected Google account."""
    tokens = _load_tokens(tenant_id)
    return tokens.get("email", "") if tokens else ""


async def _get_valid_token(tenant_id: int) -> Optional[str]:
    """
    Get a valid access token, refreshing if expired.
    Returns None if not connected.
    """
    tokens = _load_tokens(tenant_id)
    if not tokens:
        return None

    # Check if token is expired (tokens typically last 1 hour)
    obtained = tokens.get("obtained_at", 0)
    expires_in = tokens.get("expires_in", 3600)
    if time.time() > obtained + expires_in - 300:  # 5 min buffer
        # Refresh the token
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            logger.warning("No refresh token for tenant %d", tenant_id)
            return None

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(GOOGLE_TOKEN_URL, data={
                    "client_id": _client_id,
                    "client_secret": _client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                })
                if resp.status_code != 200:
                    logger.error("Token refresh failed for tenant %d", tenant_id)
                    return None

                new_tokens = resp.json()
                tokens["access_token"] = new_tokens["access_token"]
                tokens["expires_in"] = new_tokens.get("expires_in", 3600)
                tokens["obtained_at"] = int(time.time())
                _save_tokens(tenant_id, tokens)
        except Exception as e:
            logger.error("Token refresh error: %s", e)
            return None

    return tokens.get("access_token")


async def disconnect(tenant_id: int) -> bool:
    """Disconnect Google Drive for a tenant (revoke + delete tokens)."""
    tokens = _load_tokens(tenant_id)
    if tokens:
        # Try to revoke the token
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": tokens.get("access_token", "")},
                )
        except Exception:
            pass  # Best effort revocation

        _token_path(tenant_id).unlink(missing_ok=True)
        logger.info("Google Drive disconnected for tenant %d", tenant_id)
    return True


# =============================================================================
#  FOLDER MANAGEMENT
# =============================================================================

async def _ensure_crm_folder(tenant_id: int, firm_name: str = "Sarathi-AI CRM") -> Optional[str]:
    """
    Create (or find) the root CRM folder in the tenant's Google Drive.
    Returns folder ID or None.
    """
    token = await _get_valid_token(tenant_id)
    if not token:
        return None

    folder_name = f"{firm_name} — Reports"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient() as client:
            # Search for existing folder
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            resp = await client.get(
                f"{GOOGLE_DRIVE_API}/files",
                headers=headers,
                params={"q": query, "fields": "files(id,name)", "spaces": "drive"},
            )
            if resp.status_code == 200:
                files = resp.json().get("files", [])
                if files:
                    return files[0]["id"]

            # Create new folder
            resp = await client.post(
                f"{GOOGLE_DRIVE_API}/files",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "name": folder_name,
                    "mimeType": "application/vnd.google-apps.folder",
                },
            )
            if resp.status_code == 200:
                folder_id = resp.json()["id"]
                logger.info("Created Drive folder '%s' for tenant %d", folder_name, tenant_id)
                return folder_id
    except Exception as e:
        logger.error("Drive folder error: %s", e)

    return None


# =============================================================================
#  FILE UPLOAD
# =============================================================================

async def upload_report(
    tenant_id: int,
    file_path: str,
    filename: str,
    firm_name: str = "Sarathi-AI CRM",
    mime_type: str = "text/html",
) -> Optional[dict]:
    """
    Upload a report file to the tenant's Google Drive CRM folder.
    Returns: {"id": "...", "name": "...", "webViewLink": "..."} or None.
    """
    token = await _get_valid_token(tenant_id)
    if not token:
        return None

    folder_id = await _ensure_crm_folder(tenant_id, firm_name)
    if not folder_id:
        return None

    headers = {"Authorization": f"Bearer {token}"}

    try:
        file_data = Path(file_path).read_bytes()

        # Multipart upload
        metadata = json.dumps({
            "name": filename,
            "parents": [folder_id],
        })

        async with httpx.AsyncClient() as client:
            # Use resumable upload for simplicity with httpx
            resp = await client.post(
                f"{GOOGLE_UPLOAD_API}/files?uploadType=multipart",
                headers={
                    "Authorization": f"Bearer {token}",
                },
                files={
                    "metadata": ("metadata.json", metadata.encode(), "application/json"),
                    "file": (filename, file_data, mime_type),
                },
                params={"fields": "id,name,webViewLink"},
            )

            if resp.status_code == 200:
                result = resp.json()
                logger.info("Uploaded '%s' to Drive for tenant %d", filename, tenant_id)
                return result
            else:
                logger.error("Drive upload failed (%d): %s", resp.status_code, resp.text[:200])

    except Exception as e:
        logger.error("Drive upload error: %s", e)

    return None


async def upload_calc_report(
    tenant_id: int,
    report_filename: str,
    firm_name: str = "Sarathi-AI CRM",
) -> Optional[dict]:
    """
    Upload a calculator report HTML file from the generated_pdfs directory.
    Convenience wrapper around upload_report().
    """
    report_path = Path("generated_pdfs") / Path(report_filename).name
    if not report_path.exists():
        logger.warning("Report file not found: %s", report_path)
        return None

    return await upload_report(
        tenant_id=tenant_id,
        file_path=str(report_path),
        filename=report_filename,
        firm_name=firm_name,
        mime_type="text/html",
    )


# =============================================================================
#  LIST FILES
# =============================================================================

async def list_reports(tenant_id: int, firm_name: str = "Sarathi-AI CRM", max_results: int = 20) -> list:
    """
    List report files in the tenant's CRM folder.
    Returns list of {"id", "name", "createdTime", "webViewLink"}.
    """
    token = await _get_valid_token(tenant_id)
    if not token:
        return []

    folder_id = await _ensure_crm_folder(tenant_id, firm_name)
    if not folder_id:
        return []

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GOOGLE_DRIVE_API}/files",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "q": f"'{folder_id}' in parents and trashed=false",
                    "fields": "files(id,name,createdTime,webViewLink,size)",
                    "orderBy": "createdTime desc",
                    "pageSize": max_results,
                },
            )
            if resp.status_code == 200:
                return resp.json().get("files", [])
    except Exception as e:
        logger.error("Drive list error: %s", e)

    return []


# =============================================================================
#  GOOGLE SHEETS — LIST / PREVIEW / READ (for bulk lead import)
# =============================================================================

async def list_sheets(tenant_id: int, max_results: int = 50, search: str = "") -> list:
    """
    List Google Sheets in the user's Drive (most recent first).
    Returns: [{"id", "name", "modifiedTime", "owners"}].
    """
    token = await _get_valid_token(tenant_id)
    if not token:
        return []

    # Build query: only spreadsheets, not trashed
    query_parts = ["mimeType='application/vnd.google-apps.spreadsheet'", "trashed=false"]
    if search:
        # Escape single-quotes in search term
        safe = search.replace("'", "\\'")
        query_parts.append(f"name contains '{safe}'")
    query = " and ".join(query_parts)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{GOOGLE_DRIVE_API}/files",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "q": query,
                    "fields": "files(id,name,modifiedTime,owners(displayName,emailAddress))",
                    "orderBy": "modifiedTime desc",
                    "pageSize": max_results,
                },
            )
            if resp.status_code == 200:
                return resp.json().get("files", [])
            logger.warning("list_sheets failed (%d): %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("list_sheets error: %s", e)
    return []


async def get_sheet_metadata(tenant_id: int, sheet_id: str) -> Optional[dict]:
    """
    Get spreadsheet metadata: list of tabs (sheets) inside the file.
    Returns: {"title": "...", "sheets": [{"name": "Sheet1", "rowCount": N, "columnCount": M}]}.
    """
    token = await _get_valid_token(tenant_id)
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{GOOGLE_SHEETS_API}/spreadsheets/{sheet_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"fields": "properties.title,sheets.properties"},
            )
            if resp.status_code == 200:
                data = resp.json()
                tabs = []
                for s in data.get("sheets", []):
                    p = s.get("properties", {})
                    grid = p.get("gridProperties", {})
                    tabs.append({
                        "name": p.get("title", ""),
                        "sheet_id": p.get("sheetId"),
                        "rowCount": grid.get("rowCount", 0),
                        "columnCount": grid.get("columnCount", 0),
                    })
                return {
                    "title": data.get("properties", {}).get("title", ""),
                    "sheets": tabs,
                }
            logger.warning("get_sheet_metadata failed (%d): %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("get_sheet_metadata error: %s", e)
    return None


async def read_sheet_values(tenant_id: int, sheet_id: str, tab_name: str = "",
                            max_rows: int = 1000) -> list:
    """
    Read all values from a sheet tab. Returns list-of-lists (rows of cell strings).
    First row is typically headers. Caps at max_rows for safety.
    If tab_name is empty, reads the first tab.
    """
    token = await _get_valid_token(tenant_id)
    if not token:
        return []

    # Build A1 range — restrict to first 30 columns and max_rows for safety
    if tab_name:
        # Escape quotes & wrap in single quotes if name has special chars
        safe = tab_name.replace("'", "''")
        a1_range = f"'{safe}'!A1:AD{max_rows}"
    else:
        a1_range = f"A1:AD{max_rows}"

    try:
        import urllib.parse
        encoded_range = urllib.parse.quote(a1_range, safe="")
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{GOOGLE_SHEETS_API}/spreadsheets/{sheet_id}/values/{encoded_range}",
                headers={"Authorization": f"Bearer {token}"},
                params={"valueRenderOption": "FORMATTED_VALUE"},
            )
            if resp.status_code == 200:
                return resp.json().get("values", [])
            logger.warning("read_sheet_values failed (%d): %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("read_sheet_values error: %s", e)
    return []


def rows_to_lead_dicts(rows: list) -> list:
    """
    Convert sheet rows (list-of-lists) into lead dicts using first row as headers.
    Header normalization: lowercased, spaces → underscores.
    Returns: list of dicts ready for db.bulk_add_leads().
    """
    if not rows or len(rows) < 2:
        return []

    raw_headers = [str(h or "").strip() for h in rows[0]]
    # Normalize: lowercase + replace spaces/hyphens with underscores
    headers = [h.lower().replace(" ", "_").replace("-", "_") for h in raw_headers]

    # Common header aliases → canonical
    aliases = {
        "full_name": "name", "client_name": "name", "lead_name": "name", "customer_name": "name",
        "mobile": "phone", "mobile_no": "phone", "phone_number": "phone", "contact": "phone",
        "whatsapp_no": "whatsapp", "wa": "whatsapp",
        "email_id": "email", "email_address": "email",
        "date_of_birth": "dob", "birthday": "dob",
        "address": "city", "location": "city",
        "income": "monthly_income", "salary": "monthly_income",
        "remarks": "notes", "comments": "notes", "note": "notes",
        "category": "need_type", "product": "need_type", "interest": "need_type",
    }
    headers = [aliases.get(h, h) for h in headers]

    leads = []
    for row in rows[1:]:
        if not any(str(c).strip() for c in row):
            continue  # skip empty rows
        rec = {}
        for i, h in enumerate(headers):
            if not h:
                continue
            val = row[i] if i < len(row) else ""
            val = str(val).strip() if val is not None else ""
            if val:
                rec[h] = val
        if rec.get("name"):
            leads.append(rec)
    return leads


# =============================================================================
#  TENANT CONNECTION COUNTER (for superadmin status)
# =============================================================================

def count_connected_tenants() -> int:
    """Count how many tenants have an active GDrive token stored."""
    if not _token_store.exists():
        return 0
    return sum(1 for _ in _token_store.glob("tenant_*.json"))
