import os
import json
import tempfile
import shutil
import logging
from typing import Dict, Any

# Local module imports
from config import DATA_DIR
from security_utils import _encrypt_for_storage, _decrypt_from_storage, compute_chain_hash, _ensure_session_key


def load_user_log(user_id):
    path = os.path.join(DATA_DIR, f"{user_id}.json") 
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_user_log(user_id, log):
    os.umask(0o077)
    path = os.path.join(DATA_DIR, f"{user_id}.json") 
    tmp_fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR)
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    shutil.move(tmp_path, path)


def append_message(user_id: int, role: str, content_plain: str, timestamp: str):
    """
    Purpose: Appends a single message to the log after redaction, encryption, and including a hash chain.

    Parameters:
        user_id (int), role (str), content_plain (str), timestamp (str)

    Returns:
        None (file is updated).
    """
    enc = _encrypt_for_storage(user_id, content_plain)
    log = load_user_log(user_id)
    
    # Changed to use .get() for compatibility with older log formats
    prev_hash = log[-1].get("chain_hash", "") if log else ""
    
    chain_hash = compute_chain_hash(prev_hash, timestamp, role, content_plain)
    log.append({
        "role": role,
        "content_enc": enc,
        "timestamp": timestamp,
        "chain_hash": chain_hash,
        "pii_tags": []
    })
    save_user_log(user_id, log)


def load_recent_plain(user_id: int, n: int = 3):
    log = load_user_log(user_id)[-n:]
    msgs = []
    for e in log:
        try:
            pt = _decrypt_from_storage(user_id, e["content_enc"])
        except Exception:
            logging.error(f"FINAL DECRYPTION FAILED for user {user_id}: {e}")
            pt = "(Decryption of past messages is not possible due to security policy)"
        msgs.append({"role": e["role"], "content": pt, "timestamp": e["timestamp"]})
    return msgs

def save_counselor_email(user_id: int, email: str):
    """Saves the counselor's email for a specific user."""
    config_path = os.path.join(DATA_DIR, f"{user_id}_config.json")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError:
                pass  # If file is empty or corrupted, start with a new config
    config["counselor_email"] = email
    os.umask(0o077)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def load_counselor_email(user_id: int): 
    """Loads the counselor's email for a specific user."""
    config_path = os.path.join(DATA_DIR, f"{user_id}_config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
                return config.get("counselor_email")
            except json.JSONDecodeError:
                return None # Return None if file is invalid
    return None
