"""
ARCreations Remote License, Kill-Switch & Update Manager
Connects to a remote GitHub Gist / Raw JSON to verify client access,
handle remote kill switches, and notify of software updates.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path

APP_VERSION = "1.0.0"
if getattr(sys, 'frozen', False):
    CURRENT_DIR = Path(sys.executable).parent.resolve()
else:
    CURRENT_DIR = Path(__file__).parent.resolve()
KEY_FILE = CURRENT_DIR / "license.key"
CACHE_FILE = CURRENT_DIR / ".license_cache"

# Developer's Remote GitHub JSON URL (Gist raw URL - always pointing to the latest version):
DEFAULT_REMOTE_CONFIG_URL = "https://gist.githubusercontent.com/Aliairdrops/7564e61bf75b3baef6706f7db9a52c56/raw/license.json"


class LicenseCheckResult:
    def __init__(self, allowed=True, message="", update_available=False, latest_version="", update_url="", client_name=""):
        self.allowed = allowed
        self.message = message
        self.update_available = update_available
        self.latest_version = latest_version
        self.update_url = update_url
        self.client_name = client_name


def get_client_license_key() -> str:
    """Reads local license key if present, otherwise returns 'DEFAULT'."""
    if KEY_FILE.exists():
        try:
            with open(KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if key:
                    return key
        except Exception:
            pass
    return "DEFAULT"


def fetch_remote_config(url: str, timeout: int = 5) -> dict:
    """Fetches JSON configuration from remote GitHub URL."""
    headers = {
        "User-Agent": "ARCreations-FlowPrompter-Auth/1.0",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content = response.read().decode("utf-8")
        return json.loads(content)


def check_license(remote_url: str = None) -> LicenseCheckResult:
    """
    Validates application license against remote GitHub configuration.
    Returns LicenseCheckResult.
    """
    url = remote_url or DEFAULT_REMOTE_CONFIG_URL
    client_key = get_client_license_key()

    remote_data = None
    try:
        remote_data = fetch_remote_config(url, timeout=5)
        # Cache successful response
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "data": remote_data
                }, f)
        except Exception:
            pass
    except Exception:
        # Fallback to local cache if internet is temporarily offline
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                    remote_data = cache.get("data")
            except Exception:
                pass
        
        if not remote_data:
            # If no remote access and no cache, allow startup with notice
            return LicenseCheckResult(
                allowed=True,
                message="Offline mode: Server unreachable. Running local instance.",
                client_name="Local User"
            )

    # 1. Check Master Kill Switch
    app_status = remote_data.get("app_status", "ACTIVE").upper()
    if app_status == "BLOCKED":
        msg = remote_data.get("status_message", "Application access has been suspended by ARCreations.")
        return LicenseCheckResult(
            allowed=False,
            message=f"🚫 ACCESS REVOKED\n\n{msg}\n\nContact @arcreations008 on Instagram."
        )
    
    if app_status == "MAINTENANCE":
        msg = remote_data.get("status_message", "Application is undergoing scheduled maintenance.")
        return LicenseCheckResult(
            allowed=False,
            message=f"🛠️ MAINTENANCE MODE\n\n{msg}\n\nPlease try again later."
        )

    # 2. Check Client License Key
    licenses = remote_data.get("licenses", {})
    client_info = licenses.get(client_key) or licenses.get("DEFAULT")

    if not client_info:
        return LicenseCheckResult(
            allowed=False,
            message=f"🚫 INVALID LICENSE\n\nKey '{client_key}' is not authorized.\n\nContact @arcreations008 on Instagram."
        )

    client_status = client_info.get("status", "ACTIVE").upper()
    if client_status != "ACTIVE":
        return LicenseCheckResult(
            allowed=False,
            message=f"🚫 LICENSE SUSPENDED\n\nLicense for '{client_key}' has been deactivated.\n\nContact @arcreations008 on Instagram."
        )

    # Expiry Check
    expiry_str = client_info.get("expiry")
    if expiry_str:
        try:
            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            if date.today() > expiry_date:
                return LicenseCheckResult(
                    allowed=False,
                    message=f"⚠️ LICENSE EXPIRED\n\nYour license expired on {expiry_str}.\n\nRenew by contacting @arcreations008 on Instagram."
                )
        except Exception:
            pass

    # 3. Check for Updates
    latest_version = remote_data.get("latest_version", APP_VERSION)
    update_url = remote_data.get("update_url", "")
    update_available = False
    
    try:
        def parse_v(v):
            return [int(x) for x in v.split(".") if x.isdigit()]
        if parse_v(latest_version) > parse_v(APP_VERSION):
            update_available = True
    except Exception:
        pass

    return LicenseCheckResult(
        allowed=True,
        message=f"Licensed to {client_info.get('client_name', client_key)}",
        update_available=update_available,
        latest_version=latest_version,
        update_url=update_url,
        client_name=client_info.get('client_name', client_key)
    )
