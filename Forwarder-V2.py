#!/usr/bin/env python3
"""
email_forwarder_full.py
Robust IMAP -> webhook forwarder that:
- Uses strict IMAP search (UNSEEN FROM "<sender>") per configured senders
- Reads dynamic routing from config.json (groups -> senders -> target)
- Uses .env for IMAP creds and webhook URL
- Retries HTTP posts with exponential backoff
- Marks messages as SEEN only after successful forward
- Logs to both stdout and file
"""

import os
import sys
import time
import json
import logging
import imaplib
import email
import requests
from email.header import decode_header
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, List, Dict

# -------------------------
# Load environment
# -------------------------
load_dotenv()

IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:3000/send-email")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))  # seconds
MAX_BODY_LENGTH = int(os.getenv("MAX_BODY_LENGTH", "2000"))
CONFIG_FILE = os.getenv("CONFIG_FILE", "config.json")
LOG_FILE = os.getenv("LOG_FILE", "email_forwarder_full.log")
USER_AGENT = os.getenv("USER_AGENT", "email-forwarder/1.0")

if not EMAIL or not PASSWORD or not WEBHOOK_URL:
    print("ERROR: EMAIL, PASSWORD, and WEBHOOK_URL must be set in .env")
    sys.exit(1)

# -------------------------
# Logging setup
# -------------------------
logger = logging.getLogger("email_forwarder")
logger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# stdout handler
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(fmt)
logger.addHandler(sh)

# file handler
fh = logging.FileHandler(LOG_FILE)
fh.setFormatter(fmt)
logger.addHandler(fh)

logger.info("Starting email forwarder (strict IMAP mode)")
logger.info(f"IMAP: {IMAP_SERVER}:{IMAP_PORT} | Poll interval: {POLL_INTERVAL}s | Webhook: {WEBHOOK_URL}")

# -------------------------
# Helpers: config.json
# -------------------------
def load_config() -> dict:
    """Load routing config.json, return dict with groups"""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # normalize shape
            if "groups" not in cfg:
                cfg["groups"] = {}
            return cfg
    except FileNotFoundError:
        logger.warning(f"Config file {CONFIG_FILE} not found. Using empty groups.")
        return {"groups": {}}
    except Exception as e:
        logger.exception(f"Failed to load config.json: {e}")
        return {"groups": {}}

# small cache file timestamp to avoid reloading too often
_config_mtime = None
_config_cache = None
def reload_config_if_needed() -> dict:
    global _config_mtime, _config_cache
    try:
        mtime = os.path.getmtime(CONFIG_FILE)
    except Exception:
        # config not present or unreadable
        if _config_cache is None:
            _config_cache = {"groups": {}}
        return _config_cache

    if _config_cache is None or _config_mtime != mtime:
        logger.info("Loading config.json")
        _config_cache = load_config()
        _config_mtime = mtime
    return _config_cache

def find_target_for_sender(sender_email: str) -> Optional[str]:
    """Return target ID (string) for a sender, or None if no match.
    Matching: case-insensitive substring match of allowed senders entries.
    """
    config = reload_config_if_needed()
    s = (sender_email or "").lower()
    for group_name, group_data in config.get("groups", {}).items():
        for allowed in group_data.get("senders", []):
            if not allowed:
                continue
            if allowed.lower() in s or s in allowed.lower():
                # group target may be either 'target' or 'targets' array; support both
                t = group_data.get("target")
                if t:
                    return str(t)
                ts = group_data.get("targets")
                if ts and isinstance(ts, list) and len(ts) > 0:
                    return str(ts[0])
    # fallback to default_target if present
    cfg = reload_config_if_needed()
    default_t = cfg.get("default_target")
    if default_t:
        return str(default_t)
    return None

# -------------------------
# Helpers: parse email fields
# -------------------------
def decode_mime_words(s: Optional[str]) -> str:
    if not s:
        return ""
    try:
        parts = decode_header(s)
        out = []
        for part, enc in parts:
            if isinstance(part, bytes):
                out.append(part.decode(enc or "utf-8", errors="ignore"))
            else:
                out.append(str(part))
        return "".join(out)
    except Exception:
        return s

def extract_text_from_html(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n", strip=True)
    except Exception:
        return html

def get_first_text_block(msg: email.message.Message) -> (str, bool):
    """
    Return (body_text, has_attachment)
    - prefer text/plain
    - fallback to text/html (converted)
    - detect attachments via Content-Disposition or part filename
    """
    body = ""
    has_attachment = False

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            fname = part.get_filename()
            # detect attachment
            if fname or "attachment" in disp.lower():
                has_attachment = True
                continue
            if ctype == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                        return (body, has_attachment)
                except Exception:
                    continue
        # fallback to html
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/html" and "attachment" not in disp.lower():
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        html = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                        body = extract_text_from_html(html)
                        return (body, has_attachment)
                except Exception:
                    continue
    else:
        ctype = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            try:
                text = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
            except Exception:
                text = payload.decode(errors="ignore") if isinstance(payload, bytes) else str(payload)
            if ctype == "text/plain":
                return (text, False)
            elif ctype == "text/html":
                return (extract_text_from_html(text), False)

    return (body, has_attachment)

def safe_truncate(text: str, limit: int = MAX_BODY_LENGTH) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n...[truncated]"

# -------------------------
# HTTP post with retry
# -------------------------
def post_with_retry(url: str, payload: dict, max_retries: int = 4, timeout: int = 10) -> requests.Response:
    backoff = 1
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=timeout, headers=headers)
            if 200 <= r.status_code < 300:
                return r
            else:
                logger.warning(f"Webhook returned status {r.status_code}: {r.text}")
                raise Exception(f"Webhook status {r.status_code}")
        except Exception as e:
            logger.warning(f"Attempt {attempt} failed posting webhook: {e}")
            if attempt == max_retries:
                raise
            time.sleep(backoff)
            backoff *= 2
    raise Exception("Unreachable post_with_retry exit")

# -------------------------
# IMAP connection helper
# -------------------------
def connect_imap():
    try:
        imap = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        imap.login(EMAIL, PASSWORD)
        imap.select("INBOX")
        return imap
    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP login failure: {e}")
        raise
    except Exception as e:
        logger.exception("IMAP connection error")
        raise

# -------------------------
# Core: strict search per configured sender
# -------------------------
def check_email_once():
    cfg = reload_config_if_needed()
    groups = cfg.get("groups", {})
    if not groups:
        logger.info("No groups configured in config.json → skipping this cycle")
        return

    try:
        imap = connect_imap()
    except Exception as e:
        logger.error("Skipping check due to IMAP error")
        return

    try:
        # build list of unique senders to check
        senders_to_check = []
        for grp_name, grp in groups.items():
            for s in grp.get("senders", []) or []:
                s_trim = s.strip()
                if s_trim and s_trim not in senders_to_check:
                    senders_to_check.append(s_trim)

        if not senders_to_check:
            logger.info("No senders configured to check")
            imap.logout()
            return

        logger.info(f"Checking {len(senders_to_check)} configured senders (strict IMAP search)")

        for sender in senders_to_check:
            # IMAP search for unseen from this sender
            try:
                # Use quotes to ensure IMAP treats sender as phrase
                typ, data = imap.search(None, f'(UNSEEN FROM "{sender}")')
            except Exception as e:
                logger.warning(f"IMAP search failed for {sender}: {e}")
                continue

            if typ != "OK":
                logger.warning(f"IMAP search returned {typ} for sender {sender}")
                continue

            ids = data[0].split()
            if not ids:
                continue

            logger.info(f"Found {len(ids)} unseen messages from {sender}")

            for num in ids:
                try:
                    typ, msgdata = imap.fetch(num, "(RFC822)")
                    if typ != "OK":
                        logger.warning(f"Failed fetch id {num} for {sender}: {typ}")
                        continue
                    raw = msgdata[0][1]
                    msg = email.message_from_bytes(raw)

                    # decode from & subject
                    raw_from = decode_mime_words(msg.get("From", ""))
                    subject = decode_mime_words(msg.get("Subject", "(No Subject)"))

                    # parse body & attachments
                    body_text, has_attachment = get_first_text_block(msg)
                    body_text = safe_truncate(body_text, MAX_BODY_LENGTH)
                    if has_attachment and not body_text:
                        body_text = "[Attachment included — not downloaded]"

                    # determine target(s) by config.json mapping (same logic as Node)
                    target = find_target_for_sender(raw_from)
                    if not target:
                        logger.info(f"No target defined for sender {raw_from}, skipping message id {num}")
                        # do not mark seen; maybe config will change later
                        continue

                    payload = {
                        "sender": raw_from,
                        "subject": subject,
                        "body": body_text
                    }

                    # POST with retry; if success -> mark seen
                    try:
                        r = post_with_retry(WEBHOOK_URL, payload, max_retries=3, timeout=10)
                        logger.info(f"Forwarded message from {raw_from} to webhook (status {r.status_code}). Marking as SEEN.")
                        # mark SEEN
                        try:
                            imap.store(num, '+FLAGS', '\\Seen')
                        except Exception as e:
                            logger.warning(f"Failed to mark message {num} as seen: {e}")
                    except Exception as e:
                        logger.error(f"Failed to forward message from {raw_from}: {e}")
                        # do not mark seen -> will retry next poll

                except Exception as e:
                    logger.exception(f"Error processing message id {num} from {sender}: {e}")

        try:
            imap.logout()
        except Exception:
            pass

    except Exception as e:
        logger.exception("Unexpected error during check_email_once")
        try:
            imap.logout()
        except Exception:
            pass

# -------------------------
# Main loop
# -------------------------
def main_loop():
    logger.info("Email forwarder loop started.")
    try:
        while True:
            start = time.time()
            try:
                check_email_once()
            except Exception as e:
                logger.exception("check_email_once crashed")
            elapsed = time.time() - start
            sleep_for = max(0, POLL_INTERVAL - elapsed)
            logger.debug(f"Sleeping {sleep_for:.1f}s until next poll")
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        logger.info("Interrupted by user, exiting.")
    except Exception as e:
        logger.exception("Fatal error in main loop")

if __name__ == "__main__":
    main_loop()
