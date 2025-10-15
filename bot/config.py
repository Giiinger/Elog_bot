import os
import base64
import logging
from dotenv import load_dotenv
from openai import AzureOpenAI

# .env file load
load_dotenv()

# environmental variables
AZURE_API_KEY = os.getenv("AZURE_API_KEY")
AZURE_API_ENDPOINT = os.getenv("AZURE_API_ENDPOINT")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com") 
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))      


# security-related envs
MASTER_KEY_B64 = os.getenv("MASTER_KEY")
SECRET_LINK_KEY_B64 = os.getenv("SECRET_LINK_KEY")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")
MAX_DOWNLOADS = int(os.getenv("MAX_DOWNLOADS", "1"))
DELETE_AFTER_DOWNLOAD = os.getenv("DELETE_AFTER_DOWNLOAD", "true").lower() == "true"
OTP_ATTEMPT_LIMIT = int(os.getenv("OTP_ATTEMPT_LIMIT", "5"))
SESSION_TTL_SEC = int(os.getenv("SESSION_TTL_SEC", "86400"))

# sanity check (warning for missing required envs)
for key in ["AZURE_API_KEY","AZURE_API_ENDPOINT","AZURE_DEPLOYMENT_NAME",
            "TELEGRAM_BOT_TOKEN","SMTP_EMAIL","SMTP_PASSWORD",
            "MASTER_KEY","SECRET_LINK_KEY"]:
    if not os.getenv(key):
        logging.warning(f"[WARN] Missing env: {key}")

# In a production environment, you must set actual keys.
if not MASTER_KEY_B64 or not SECRET_LINK_KEY_B64:
    logging.error("[CRITICAL] MASTER_KEY and SECRET_LINK_KEY must be set in your environment!")


MASTER_KEY = base64.b64decode(MASTER_KEY_B64) if MASTER_KEY_B64 else b"\x00"*32
SECRET_LINK_KEY = base64.b64decode(SECRET_LINK_KEY_B64) if SECRET_LINK_KEY_B64 else b"\x00"*32

# Azure OpenAI client setup
client = AzureOpenAI(
    api_key=AZURE_API_KEY,
    api_version="2024-02-01", #Changed to a valid API version (example)
    azure_endpoint=AZURE_API_ENDPOINT
)
deployment = AZURE_DEPLOYMENT_NAME


# data dir

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(PROJECT_ROOT, "user_data")
os.makedirs(DATA_DIR, exist_ok=True)

