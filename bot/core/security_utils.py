import os
import base64
import secrets
import hashlib
import hmac
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

# Local module imports
from ..config import MASTER_KEY, DATA_DIR


def _ensure_session_key(user_id: int) -> bytes:
    """
    Obtains/generates a persistent session key for each user from a file.
    - The key is saved to disk, so the same key is used even after a server restart.
    """
    KEY_STORAGE_DIR = os.path.join(DATA_DIR, "user_keys")
    os.makedirs(KEY_STORAGE_DIR, exist_ok=True)
    user_key_path = os.path.join(KEY_STORAGE_DIR, f"{user_id}.key")

    # 1. Check if the user's persistent key file exists
    if os.path.exists(user_key_path):
        # 2. If it exists, read the saved key and return it
        with open(user_key_path, "rb") as f:
            key = f.read()
    else:
        # 3. If not, generate a new key and save it to a file
        seed = secrets.token_bytes(32)
        
        # Pass all required arguments to HKDF correctly
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32, # <- The missing argument that caused the error
            salt=hashlib.sha256(f"{user_id}".encode()).digest(),
            info=b"act-bot-session-persistent-v1" # Changed info as it's a persistent storage method
        )
        key = hkdf.derive(MASTER_KEY + seed)
        
        # Save the generated key to disk as a file (only once)
        os.umask(0o077) # Set file permissions
        with open(user_key_path, "wb") as f:
            f.write(key)

    return key



def _encrypt_for_storage(user_id: int, plaintext: str) -> dict:
    key = _ensure_session_key(user_id)
    aes = AESGCM(key)
    iv = secrets.token_bytes(12)
    ct = aes.encrypt(iv, plaintext.encode("utf-8"), None)
    return {"alg":"AES-GCM","iv":base64.b64encode(iv).decode(),
            "ct":base64.b64encode(ct).decode()}

def _decrypt_from_storage(user_id: int, enc: dict) -> str:
    
    key = _ensure_session_key(user_id)
    aes = AESGCM(key)
    iv = base64.b64decode(enc["iv"])
    ct = base64.b64decode(enc["ct"])
    pt = aes.decrypt(iv, ct, None)
    return pt.decode("utf-8")

def _chain_key():
    return hashlib.sha256(MASTER_KEY + b":chain").digest()

def compute_chain_hash(prev_hash_hex: str, timestamp: str, role: str, content_plain: str) -> str:
    data = (prev_hash_hex or "").encode() + timestamp.encode() + role.encode() + hashlib.sha256(content_plain.encode()).digest()
    mac = hmac.new(_chain_key(), data, hashlib.sha256).hexdigest()
    return mac
