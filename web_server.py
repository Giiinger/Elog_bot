import os
import logging
import threading
from flask import Flask, request, Response, send_file

# Local module imports
from config import DELETE_AFTER_DOWNLOAD, OTP_ATTEMPT_LIMIT
from export_handler import _verify_token, _load_registry, _save_registry, hash_otp, revoke_secure_link

web_app = Flask(__name__)


@web_app.route('/')
def home():
    return "I'm alive!"

def _render_otp_form(signed, error=None):
    msg = f"<p style='color:red'>{error}</p>" if error else ""
    return f"""
    <html><body>
      <h3>Secure Download</h3>
      <p>Please enter the OTP provided by the client.</p>
      {msg}
      <form method="POST" action="/secure-download">
        <input type="hidden" name="token" value="{signed}">
        <label>OTP: <input type="password" name="otp" /></label>
        <button type="submit">Download</button>
      </form>
      <p style="font-size:12px;color:#666">This link does not expire, but the number of downloads is limited.</p>
    </body></html>
    """

@web_app.route("/secure-download", methods=["GET", "POST"])
def secure_download():
    signed = request.args.get("token") if request.method == "GET" else request.form.get("token")
    if not signed:
        return "Token is required.", 400
    token = _verify_token(signed)
    if not token:
        return "Invalid or tampered token.", 403

    reg = _load_registry()
    meta = reg.get(token)
    if not meta:
        return Response("Invalid or revoked link.", status=410)
    if meta.get("locked"):
        return Response("This link is locked due to too many invalid attempts.", status=423)

    if request.method == "GET":
        return _render_otp_form(signed)

    otp_input = request.form.get("otp","")
    if not otp_input:
        return _render_otp_form(signed, error="OTP is required.")

    if hash_otp(otp_input) != meta.get("otp_hash"):
        meta["otp_attempts"] = meta.get("otp_attempts", 0) + 1
        if meta["otp_attempts"] >= OTP_ATTEMPT_LIMIT:
            meta["locked"] = True
        _save_registry({**reg, token: meta})
        left = max(0, OTP_ATTEMPT_LIMIT - meta["otp_attempts"])
        return _render_otp_form(signed, error=f"Invalid OTP. Attempts left: {left}")

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if meta.get("ip_lock") is None:
        meta["ip_lock"] = client_ip
    elif meta["ip_lock"] != client_ip:
        logging.warning(f"IP mismatch for token {token[:8]}... Expected {meta['ip_lock']}, got {client_ip}")
        return Response("IP not allowed for this link.", status=403)

    if meta["downloads"] >= meta.get("max_downloads", 1):
        return Response("Download limit reached.", status=410)

    fpath = meta["file_path"]
    if not os.path.exists(fpath):
        revoke_secure_link(token)
        return Response("File not found (possibly removed).", status=410)

    meta["downloads"] += 1
    _save_registry({**reg, token: meta})

    resp = send_file(fpath, as_attachment=True, download_name=os.path.basename(fpath))

    if meta["downloads"] >= meta.get("max_downloads", 1):
        if DELETE_AFTER_DOWNLOAD:
            revoke_secure_link(token)
        else: # If not deleting the file after download, only remove from the registry
            reg = _load_registry()
            if token in reg:
                del reg[token]
                _save_registry(reg)

    return resp

def run_flask():
    web_app.run(host='0.0.0.0', port=8080)

def start_keep_alive():
    thread = threading.Thread(target=run_flask)
    thread.daemon = True # Terminate along with the main thread
    thread.start()
