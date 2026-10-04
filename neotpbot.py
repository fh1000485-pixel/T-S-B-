	#!/usr/bin/env python3
"""
Firebase SMS Dashboard Bot — FINAL

Multi-Firebase (40)

Force Join + Captcha Verification

Referral System (1 refer = 3 hours)

Channel leave → referrer access revoke

Admin unlimited access

SMS monitor auto-stop on access revoke

SMS monitor idle timeout (10 min no button tap)

Admin Gift Access (single user / all users)
"""


import os
import re
import json
import time
import asyncio
import logging
import gc
import random
from html import escape as html_escape
from collections import Counter
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Set

import aiohttp
from telegram import (
Bot,
Update,
InlineKeyboardButton,
InlineKeyboardMarkup,
)
from telegram.ext import (
Application,
CommandHandler,
CallbackQueryHandler,
MessageHandler,
filters,
ContextTypes,
)

============================================================

CONFIG

============================================================

BOT_TOKEN = "8713575379:AAEpigb0b1Ks-rS0788kYPCZQ3SnZ08bn64 "
ADMIN_IDS = [7122430770]

logging.basicConfig(
level=logging.INFO,
format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("FirebaseSMSBot")

============================================================

CONSTANTS

============================================================

FB_REQUEST_TIMEOUT = 10
FB_RETRY_MAX = 1
FB_RETRY_BACKOFF = 1.2
FB_CLIENTS_MAX_BYTES = 50 * 1024 * 1024
FB_MESSAGES_LIMIT = 5
MAX_FIREBASES = 40
CLEANUP_INTERVAL = 60
SMS_MONITOR_INTERVAL = 1
SMS_MONITOR_DURATION = 300
SMS_MONITOR_IDLE_TIMEOUT = 600
ADMIN_PANEL_EDIT_INTERVAL = 5
WELCOME_IMAGE_URL = "https://i.ibb.co/CK3s8vzR/Gemini-Generated-Image-en17gcen17gcen17.png"

Referral

REFERRAL_HOURS = 3
REFERRAL_SECONDS = REFERRAL_HOURS * 3600

Gift

GIFT_ACCESS_MAX_HOURS = 24 * 365

Files

FORCE_JOIN_FILE = os.getenv("FORCE_JOIN_FILE", "force_join_channels.json")
USER_IDS_FILE = os.getenv("USER_IDS_FILE", "bot_users.json")
MAINTENANCE_FILE = os.getenv("MAINTENANCE_FILE", "maintenance_mode.json")
GLOBAL_FB_FILE = os.getenv("GLOBAL_FB_FILE", "global_firebases.json")
GLOBAL_DEVICE_CACHE_FILE = os.getenv(
"GLOBAL_DEVICE_CACHE_FILE", "global_devices_cache.json"
)
CAPTCHA_STATE_FILE = os.getenv("CAPTCHA_STATE_FILE", "captcha_state.json")
REFERRAL_DB_FILE = os.getenv("REFERRAL_DB_FILE", "referrals.json")

ACCESS_CHECK_INTERVAL = 30
ADMIN_DEVICE_REFRESH_INTERVAL = 180

DEFAULT_CHANNELS = [
{"id": "@tgotpbot_18", "label": "otp_180", "url": "https://t.me/tgotpbot_18"},
{"id": "@otp_180", "label": "@otp_180", "url": "https://t.me/otp_180"},
]

============================================================

FILE HELPERS

============================================================

def _parse_channel_items(raw: str):
channels = []
for item in raw.split(","):
item = item.strip()
if not item:
continue
parts = [part.strip() for part in item.split("|", 2)]
identifier = parts[0]
label = parts[1] if len(parts) > 1 and parts[1] else identifier
join_url = (
parts[2]
if len(parts) > 2 and parts[2]
else (
f"https://t.me/{identifier.lstrip('@')}"
if identifier.startswith("@")
else ""
)
)
channels.append({"id": identifier, "label": label, "url": join_url})
return channels

def _load_required_channels():
try:
with open(FORCE_JOIN_FILE, "r", encoding="utf-8") as fh:
saved = json.load(fh)
if isinstance(saved, list):
return [
item
for item in saved
if isinstance(item, dict) and item.get("id")
]
except (FileNotFoundError, json.JSONDecodeError, OSError):
pass
return list(DEFAULT_CHANNELS)

def _save_required_channels():
try:
with open(FORCE_JOIN_FILE, "w", encoding="utf-8") as fh:
json.dump(REQUIRED_CHANNELS, fh, ensure_ascii=False, indent=2)
except OSError as exc:
logger.warning("could not save force-join channels: %s", exc)

def _load_user_ids():
try:
with open(USER_IDS_FILE, "r", encoding="utf-8") as fh:
values = json.load(fh)
return {int(value) for value in values}
except (
FileNotFoundError,
json.JSONDecodeError,
OSError,
TypeError,
ValueError,
):
return set()

def _save_user_ids():
try:
with open(USER_IDS_FILE, "w", encoding="utf-8") as fh:
json.dump(sorted(known_users), fh)
except OSError as exc:
logger.warning("could not save user ids: %s", exc)

def _load_maintenance_mode() -> bool:
try:
with open(MAINTENANCE_FILE, "r", encoding="utf-8") as fh:
saved = json.load(fh)
return (
bool(saved.get("enabled", False))
if isinstance(saved, dict)
else bool(saved)
)
except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
return False

def _save_maintenance_mode():
try:
with open(MAINTENANCE_FILE, "w", encoding="utf-8") as fh:
json.dump({"enabled": maintenance_mode}, fh)
except OSError as exc:
logger.warning("could not save maintenance mode: %s", exc)

def _load_captcha_enabled() -> bool:
try:
with open(CAPTCHA_STATE_FILE, "r", encoding="utf-8") as fh:
saved = json.load(fh)
return (
bool(saved.get("enabled", True))
if isinstance(saved, dict)
else True
)
except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
return True

def _save_captcha_enabled():
try:
with open(CAPTCHA_STATE_FILE, "w", encoding="utf-8") as fh:
json.dump({"enabled": captcha_enabled}, fh)
except OSError as exc:
logger.warning("could not save captcha state: %s", exc)

def _load_global_firebases():
try:
with open(GLOBAL_FB_FILE, "r", encoding="utf-8") as fh:
saved = json.load(fh)
if not isinstance(saved, list):
return []

out = []  

    for i, item in enumerate(saved):  
        if isinstance(item, dict) and item.get("url"):  
            u = str(item["url"]).strip().rstrip("/")  

            while u.endswith(".json"):  
                u = u[:-5].rstrip("/")  

            if (  
                "firebaseio.com" in u  
                or "firebasedatabase.app" in u  
            ):  
                tag = str(item.get("tag") or f"FB{i + 1}")  
                out.append((u, tag))  

    return out  

except Exception:  
    return []

def _save_global_firebases():
try:
payload = [
{"url": url, "tag": tag}
for url, tag in global_fb_list
]

with open(GLOBAL_FB_FILE, "w", encoding="utf-8") as fh:  
        json.dump(  
            payload,  
            fh,  
            ensure_ascii=False,  
            indent=2,  
        )  

except OSError as exc:  
    logger.warning(  
        "could not save global firebases: %s",  
        exc,  
    )

def _retag_global_firebases():
global global_fb_list

global_fb_list = [  
    (url, f"FB{i + 1}")  
    for i, (url, _) in enumerate(global_fb_list)  
]

============================================================

GLOBAL STATE

============================================================

REQUIRED_CHANNELS = _load_required_channels()
maintenance_mode = _load_maintenance_mode()
captcha_enabled = _load_captcha_enabled()
global_fb_list = _load_global_firebases()

_last_refresh_time: float = time.monotonic()

known_users = _load_user_ids()

user_access_state: Dict[int, bool] = {}
verified_access_users: Set[int] = set()

---- Referral DB ----

_referral_lock = asyncio.Lock()

def _load_referral_db() -> Dict[str, dict]:
try:
with open(REFERRAL_DB_FILE, "r", encoding="utf-8") as fh:
data = json.load(fh)

if isinstance(data, dict):  
        return data  

except (  
    FileNotFoundError,  
    json.JSONDecodeError,  
    OSError,  
    TypeError,  
):  
    pass  

return {}

def _save_referral_db():
try:
with open(REFERRAL_DB_FILE, "w", encoding="utf-8") as fh:
json.dump(
REFERRAL_DB,
fh,
ensure_ascii=False,
indent=2,
)

except OSError as exc:  
    logger.warning(  
        "could not save referral db: %s",  
        exc,  
    )

REFERRAL_DB: Dict[str, dict] = _load_referral_db()

_PHONE_PATTERNS = [
re.compile(r"\b(?:+91|91|0)?([6-9]\d{9})\b"),
re.compile(
r"\b(?:phone|mobile|number)[\s:]*([6-9]\d{9})\b",
re.IGNORECASE,
),
re.compile(r"^0-9[^0-9]"),
re.compile(r"(+91[-\s]?[6-9][0-9]{9})"),
re.compile(r"(?:\b91)([6-9][0-9]{9})\b"),
re.compile(
r"(?:^|\s|:)([6-9][0-9]{9})(?:\s|$|.)"
),
]

============================================================

REFERRAL HELPERS

============================================================

def _ensure_user_record(user_id: int) -> dict:
uid = str(user_id)

if uid not in REFERRAL_DB:  
    REFERRAL_DB[uid] = {  
        "access_expires_at": 0.0,  
        "referrals": [],  
        "referred_by": None,  
        "referral_count": 0,  
        "expired_notified": False,  
        "cooldown_until": 0.0,  
        "captcha_verified": False,  
    }  

else:  
    rec = REFERRAL_DB[uid]  

    rec.setdefault("access_expires_at", 0.0)  
    rec.setdefault("referrals", [])  
    rec.setdefault("referred_by", None)  
    rec.setdefault(  
        "referral_count",  
        len(rec.get("referrals", [])),  
    )  
    rec.setdefault("expired_notified", False)  
    rec.setdefault("cooldown_until", 0.0)  
    rec.setdefault("captcha_verified", False)  

return REFERRAL_DB[uid]

def get_remaining_seconds(user_id: int) -> float:
if user_id in ADMIN_IDS:
return float("inf")

rec = _ensure_user_record(user_id)  

return max(  
    0.0,  
    rec.get("access_expires_at", 0.0) - time.time(),  
)

def has_access(user_id: int) -> bool:
if user_id in ADMIN_IDS:
return True

return get_remaining_seconds(user_id) > 0

def format_remaining_time(user_id: int) -> str:
if user_id in ADMIN_IDS:
return "Unlimited ♾️"

remaining = get_remaining_seconds(user_id)  

if remaining <= 0:  
    return "Expired"  

total_minutes = int(remaining // 60)  

hours = total_minutes // 60  
minutes = total_minutes % 60  

if hours > 0 and minutes > 0:  
    return f"{hours}h {minutes}m"  

elif hours > 0:  
    return f"{hours}h"  

return f"{minutes}m"

def grant_access(user_id: int, seconds: int):
rec = _ensure_user_record(user_id)

now = time.time()  
current = rec.get("access_expires_at", 0.0)  

if current < now:  
    rec["access_expires_at"] = now + seconds  
else:  
    rec["access_expires_at"] = current + seconds  

rec["expired_notified"] = False  

_save_referral_db()

def revoke_access(user_id: int):
rec = _ensure_user_record(user_id)

rec["access_expires_at"] = 0.0  
rec["expired_notified"] = False  

_save_referral_db()

async def process_referral(
referrer_id: int,
referred_id: int,
) -> dict:

async with _referral_lock:  

    if referrer_id == referred_id:  
        return {  
            "success": False,  
            "reason": "self_referral",  
        }  

    if referrer_id in ADMIN_IDS:  
        return {  
            "success": False,  
            "reason": "admin_referrer",  
        }  

    if str(referrer_id) not in REFERRAL_DB:  
        return {  
            "success": False,  
            "reason": "invalid_referrer",  
        }  

    ref_rec = _ensure_user_record(referrer_id)  
    new_rec = _ensure_user_record(referred_id)  

    if new_rec.get("referred_by") is not None:  
        return {  
            "success": False,  
            "reason": "already_referred",  
        }  

    if referred_id in ref_rec.get("referrals", []):  
        return {  
            "success": False,  
            "reason": "duplicate",  
        }  

    now = time.time()  

    current_expiry = ref_rec.get(  
        "access_expires_at",  
        0.0,  
    )  

    if current_expiry < now:  
        ref_rec["access_expires_at"] = (  
            now + REFERRAL_SECONDS  
        )  
    else:  
        ref_rec["access_expires_at"] = (  
            current_expiry + REFERRAL_SECONDS  
        )  

    ref_rec["expired_notified"] = False  

    ref_rec.setdefault(  
        "referrals",  
        []  
    ).append(referred_id)  

    ref_rec["referral_count"] = len(  
        ref_rec["referrals"]  
    )  

    new_rec["referred_by"] = referrer_id  

    _save_referral_db()  

    return {  
        "success": True,  
        "reason": "ok",  
        "referrer_remaining": format_remaining_time(  
            referrer_id  
        ),  
    }

async def check_referred_user_left(
referred_id: int,
):
"""When a referred user leaves channel, revoke referrer's access too."""

try:  
    uid = str(referred_id)  

    if uid not in REFERRAL_DB:  
        return None  

    rec = REFERRAL_DB[uid]  

    referrer_id = rec.get("referred_by")  

    if not referrer_id:  
        return None  

    referrer_uid = str(referrer_id)  

    if referrer_uid not in REFERRAL_DB:  
        return None  

    ref_rec = REFERRAL_DB[referrer_uid]  

    if referred_id not in ref_rec.get(  
        "referrals",  
        [],  
    ):  
        return None  

    ref_rec["referrals"] = [  
        r  
        for r in ref_rec.get(  
            "referrals",  
            [],  
        )  
        if r != referred_id  
    ]  

    ref_rec["referral_count"] = len(  
        ref_rec["referrals"]  
    )  

    revoke_access(referrer_id)  

    rec["referred_by"] = None  

    _save_referral_db()  

    logger.info(  
        "[REFERRAL] User %s left channel → referrer %s access revoked",  
        referred_id,  
        referrer_id,  
    )  

    return referrer_id  

except Exception as exc:  
    logger.error(  
        "[REFERRAL] check_referred_user_left error: %s",  
        exc,  
    )  
    return None

============================================================

FIREBASE HELPERS

============================================================

def normalize_fb_url(url: str) -> Optional[str]:
try:
if not url or not isinstance(url, str):
return None

u = url.strip()  

    if not u.startswith("http"):  
        return None  

    if (  
        "firebaseio.com" not in u  
        and "firebasedatabase.app" not in u  
    ):  
        return None  

    u = u.rstrip("/")  

    while u.endswith(".json"):  
        u = u[:-5].rstrip("/")  

    return u  

except Exception:  
    return None

def _load_global_device_cache():
try:
with open(
GLOBAL_DEVICE_CACHE_FILE,
"r",
encoding="utf-8",
) as fh:
saved = json.load(fh)

if (  
        not isinstance(saved, dict)  
        or not isinstance(  
            saved.get("devices"),  
            dict,  
        )  
    ):  
        return {  
            "devices": {},  
            "online_count": 0,  
            "offline_count": 0,  
            "per_fb": {},  
            "updated_at": "",  
        }  

    if "per_fb" not in saved:  
        saved["per_fb"] = {}  

    return saved  

except (  
    FileNotFoundError,  
    json.JSONDecodeError,  
    OSError,  
    TypeError,  
):  
    return {  
        "devices": {},  
        "online_count": 0,  
        "offline_count": 0,  
        "per_fb": {},  
        "updated_at": "",  
    }

def _save_global_device_cache(cache):
try:
tmp = f"{GLOBAL_DEVICE_CACHE_FILE}.tmp"

with open(  
        tmp,  
        "w",  
        encoding="utf-8",  
    ) as fh:  
        json.dump(  
            cache,  
            fh,  
            ensure_ascii=False,  
        )  

    os.replace(  
        tmp,  
        GLOBAL_DEVICE_CACHE_FILE,  
    )  

except OSError as exc:  
    logger.warning(  
        "could not save device cache: %s",  
        exc,  
    )

global_device_cache = _load_global_device_cache()

def fb_host_short(url: str) -> str:
try:
s = (
url.replace("https://", "")
.replace("http://", "")
)

s = (  
        s.replace(".firebaseio.com", "")  
        .replace(".firebasedatabase.app", "")  
    )  

    return s.split(".")[0][:30]  

except Exception:  
    return url[:30]

def build_fb_endpoint(
base_url: str,
path: str = "",
query: str = "",
) -> str:

base = base_url.rstrip("/")  

p = (path or "").strip("/")  
q = (query or "").strip().lstrip("?")  

url = (  
    f"{base}/{p}/.json"  
    if p  
    else f"{base}/.json"  
)  

if q:  
    url += f"?{q}"  

return url

async def fb_get_json(
session,
url,
*,
timeout=FB_REQUEST_TIMEOUT,
max_bytes=FB_CLIENTS_MAX_BYTES,
retries=FB_RETRY_MAX,
):

last_err = ""  

for attempt in range(retries + 1):  

    try:  
        async with session.get(  
            url,  
            timeout=aiohttp.ClientTimeout(  
                total=timeout  
            ),  
        ) as resp:  

            status = resp.status  

            if status == 413:  
                return (  
                    None,  
                    "TOO_LARGE",  
                    "HTTP 413",  
                )  

            cl = resp.headers.get(  
                "Content-Length"  
            )  

            if (  
                cl  
                and cl.isdigit()  
                and int(cl) > max_bytes  
            ):  
                return (  
                    None,  
                    "TOO_LARGE",  
                    f"CL {cl}",  
                )  

            body = b""  

            async for chunk in resp.content.iter_chunked(  
                8192  
            ):  
                body += chunk  

                if len(body) > max_bytes:  
                    return (  
                        None,  
                        "TOO_LARGE",  
                        "too big",  
                    )  

            text = body.decode(  
                "utf-8",  
                errors="ignore",  
            ).strip()  

            if status in (401, 403):  
                return (  
                    None,  
                    "ACCESS_DENIED",  
                    f"HTTP {status}",  
                )  

            if status == 404:  
                return (  
                    None,  
                    "NOT_FOUND",  
                    "HTTP 404",  
                )  

            if status in (408, 504):  

                last_err = (  
                    f"HTTP {status}"  
                )  

                if attempt < retries:  
                    await asyncio.sleep(  
                        FB_RETRY_BACKOFF  
                        ** attempt  
                    )  
                    continue  

                return (  
                    None,  
                    "TIMEOUT",  
                    last_err,  
                )  

            if status == 429 or 500 <= status < 600:  

                last_err = (  
                    f"HTTP {status}"  
                )  

                if attempt < retries:  
                    await asyncio.sleep(  
                        FB_RETRY_BACKOFF  
                        ** attempt  
                    )  
                    continue  

                return (  
                    None,  
                    "HTTP_ERROR",  
                    last_err,  
                )  

            if status >= 400:  
                return (  
                    None,  
                    "HTTP_ERROR",  
                    f"HTTP {status}",  
                )  

            if (  
                not text  
                or text == "null"  
            ):  
                return (  
                    None,  
                    "EMPTY_DATA",  
                    "null/empty",  
                )  

            try:  
                data = json.loads(text)  

            except json.JSONDecodeError:  
                return (  
                    None,  
                    "INVALID_JSON",  
                    "json decode",  
                )  

            if data is None:  
                return (  
                    None,  
                    "EMPTY_DATA",  
                    "null",  
                )  

            return (  
                data,  
                "SUCCESS",  
                "",  
            )  

    except asyncio.TimeoutError:  

        last_err = "timeout"  

        if attempt < retries:  
            await asyncio.sleep(  
                FB_RETRY_BACKOFF  
                ** attempt  
            )  
            continue  

        return (  
            None,  
            "TIMEOUT",  
            last_err,  
        )  

    except aiohttp.ClientError as 