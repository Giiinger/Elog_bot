import os
import json
import base64
import secrets
import time
import hashlib
import hmac
import logging
import smtplib
from email.message import EmailMessage
from datetime import datetime
from zipfile import ZipFile, ZIP_DEFLATED
import threading

# Local module imports
from ..config import (
    DATA_DIR, SECRET_LINK_KEY, BASE_URL, MAX_DOWNLOADS, 
    SMTP_EMAIL, SMTP_PASSWORD, SMTP_HOST, SMTP_PORT, client, deployment
)
from .data_manager import load_user_log, load_counselor_email
from .security_utils import _decrypt_from_storage, _ensure_session_key
from .llm_handler import load_system_content

REGISTRY_LOCK = threading.Lock()
EXPORT_REGISTRY = os.path.join(DATA_DIR, "exports_registry.json")

def _load_registry():
    with REGISTRY_LOCK: # Protect file access with a Lock
        if os.path.exists(EXPORT_REGISTRY):
            with open(EXPORT_REGISTRY, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

def _save_registry(reg):
    with REGISTRY_LOCK: # Protect file access with a Lock
        tmp_path = EXPORT_REGISTRY + f".tmp.{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, EXPORT_REGISTRY)

def _sign_token(token: str) -> str:
    mac = hmac.new(SECRET_LINK_KEY, token.encode(), hashlib.sha256).hexdigest()
    return f"{token}.{mac}"

def _verify_token(signed: str):
    try:
        token, mac = signed.split(".", 1)
        expect = hmac.new(SECRET_LINK_KEY, token.encode(), hashlib.sha256).hexdigest()
        return token if hmac.compare_digest(mac, expect) else None
    except Exception:
        return None

def gen_otp(length=10) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

def create_secure_link_with_otp(user_id: int, file_path: str, note: str = "") -> tuple[str, str]:
    token = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    signed = _sign_token(token)
    otp_plain = gen_otp(10)
    otp_hash = hash_otp(otp_plain)
    revoke_id = f"ACT-{datetime.now().strftime('%y%m%d')}-{secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}"


    reg = _load_registry()
    reg[token] = {
        "user_id": user_id,
        "file_path": file_path,
        "created_at": time.time(),
        "downloads": 0,
        "max_downloads": MAX_DOWNLOADS,
        "ip_lock": None,
        "note": note,
        "otp_hash": otp_hash,
        "otp_attempts": 0,
        "locked": False,
        "revoke_id": revoke_id
    }
    _save_registry(reg)
    return f"{BASE_URL}/secure-download?token={signed}", otp_plain, revoke_id

def revoke_secure_link(token: str) -> bool:
    reg = _load_registry()
    if token in reg:
        try:
            if os.path.exists(reg[token]["file_path"]):
                os.remove(reg[token]["file_path"])
        except Exception as e:
            logging.error(f"Failed to remove file on revoke: {e}")
        del reg[token]
        _save_registry(reg)
        return True
    return False

def find_and_revoke_by_id(user_id: int, revoke_id: str) -> tuple[bool, str]:
    """Finds and revokes a link using a user-facing ID."""
    reg = _load_registry()
    token_to_revoke = None
    note = ""
    
    for token, meta in reg.items():
        if int(meta.get("user_id")) == user_id and str(meta.get("revoke_id")) == revoke_id:
            token_to_revoke = token
            note = meta.get("note", "")
            break
    
    if token_to_revoke:
        was_revoked = revoke_secure_link(token_to_revoke)
        return was_revoked, note
    
    return False, ""


def make_plain_zip(files, zip_path):
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for p in files:
            if os.path.exists(p):
                zf.write(p, arcname=os.path.basename(p))
    return zip_path


def send_logs_via_secure_link(user_id, start_date, end_date):

    _ensure_session_key(user_id)

    log_path = os.path.join(DATA_DIR, f"{user_id}.json")
    if not os.path.exists(log_path):
        return None, "Conversation history does not exist."

    full = load_user_log(user_id)
    
    # Compare dates accurately with datetime objects instead of string comparison
    try:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        filtered = [
            e for e in full 
            if 'timestamp' in e and start_date_obj <= datetime.fromisoformat(e["timestamp"]).date() <= end_date_obj
        ]
    except (ValueError, KeyError):
        return None, "The date format is incorrect or the log file is corrupted."

    if not filtered:
        return None, f"No conversation history found for the period {start_date} ~ {end_date}."

    pairs = []
    for e in filtered[:30]:
        role = "User" if e["role"] == "user" else "Chatbot"
        try:
            content = _decrypt_from_storage(user_id, e["content_enc"])
        except Exception:
            content = "(Decryption of past messages not possible due to security policy)"
        pairs.append(f"{role}: {content}")
    dialogue_text = "\n".join(pairs)

    summary_prompt = load_system_content("prompt_templates/summary.txt")
    messages = [{"role": "system", "content": summary_prompt},
                {"role": "user", "content": "summarize the chat dialogue following system prompt if chathistory is not English you can summarize by the langaue in chat history.\n" + dialogue_text}]
    summary_response = client.chat.completions.create(
        model=deployment, messages=messages, max_tokens=4096, temperature=1.0, top_p=1.0
    )
    summary = summary_response.choices[0].message.content

    base_filename = f"{user_id}_{start_date}_to_{end_date}"
    filtered_path = os.path.join(DATA_DIR, f"{base_filename}.json")
    with open(filtered_path, "w", encoding="utf-8") as f:
        json.dump(pairs, f, ensure_ascii=False, indent=2)

    summary_path = os.path.join(DATA_DIR, f"{base_filename}_summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)

    zip_path = os.path.join(DATA_DIR, f"{base_filename}.zip")
    make_plain_zip([filtered_path, summary_path], zip_path)
    
    # Clean up temporary files
    os.remove(filtered_path)
    os.remove(summary_path)

    link, otp_plain, revoke_id = create_secure_link_with_otp(user_id, zip_path, note=f"{start_date}~{end_date}")

    counselor_email = load_counselor_email(user_id)
    if not counselor_email:
        token = link.split("=")[-1]
        revoke_secure_link(token)
        return None, "Counselor's email is not registered. Please register it first using:\n`/register_email your_counselor@example.com`"

    msg = EmailMessage()
    msg["Subject"] = f"Link to conversation log for {user_id} ({start_date} ~ {end_date})"
    msg["From"] = SMTP_EMAIL
    msg["To"] = counselor_email
    msg.set_content(
        "You can download the file from the following link.\n"
        f"{link}\n\n"
        "The password will be sent to the Client.\n"
        "The link does not expire, but the number of downloads is limited."
    )
    # Please match the environment variable names to the ones you are actually using (e.g., SMTP_HOST, SMTP_PORT)
    with smtplib.SMTP_SSL(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", 465))) as smtp:
        smtp.login(SMTP_EMAIL, SMTP_PASSWORD)
        smtp.send_message(msg)

    return otp_plain, "Download Link has been sent to your counselor", revoke_id