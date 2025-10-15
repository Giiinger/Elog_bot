import logging
from datetime import datetime, timezone

# Local module imports
from ..config import client, deployment
from .data_manager import load_recent_plain, append_message
from .security_utils import _ensure_session_key

def load_system_content(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logging.error(f"System prompt file not found: {file_path}")
        return "Failed to load the system prompt."

def get_gpt_response(user_id: int, user_input: str):
    _ensure_session_key(user_id)
    history = load_recent_plain(user_id, 3)
    now = datetime.now(timezone.utc).isoformat()

    history.append({"role": "user", "content": user_input, "timestamp": now})

    system_content = load_system_content("prompt_templates/Response_Guide.txt")
    messages = [{"role": "system", "content": system_content}] + [
        {"role": m["role"], "content": m["content"]} for m in history
    ]

    response = client.chat.completions.create(
        model=deployment,
        messages=messages,
        max_tokens=4096,
        temperature=1.0,
        top_p=1.0
    )
    reply = response.choices[0].message.content

    append_message(user_id, "user", user_input, now)
    append_message(user_id, "assistant", reply, now)
    
    # Removed unnecessary del statement
    return reply

