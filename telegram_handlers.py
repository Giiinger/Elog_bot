import logging
import asyncio
import re
from telegram import Update
from telegram.ext import ContextTypes

# Local module imports
from data_manager import save_counselor_email
from export_handler import send_logs_via_secure_link, revoke_secure_link, _verify_token
from llm_handler import get_gpt_response


async def send_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        if len(context.args) != 2:
            await update.message.reply_text("Usage: /send_logs YYYY-MM-DD YYYY-MM-DD")
            return
        
        start_date, end_date = context.args
        # Run blocking function in a separate thread
        otp, result_msg = await asyncio.to_thread(
            send_logs_via_secure_link, user_id, start_date, end_date
        )

        if otp is None:
            await update.message.reply_text(result_msg)
            return
        
        await update.message.reply_text(
            "The record transfer is ready.\n"
            f"Please personally deliver the OTP below to the counselor:\n\n"
            f"OTP: `{otp}`\n\n"
            "The counselor can download the file by opening the link received via email and entering this OTP.",
            parse_mode="Markdown"
        )

    except Exception as e:
        logging.exception(e)
        await update.message.reply_text("An error occurred while sending the logs. Please contact the administrator.")


async def register_email_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registers the counselor's email address."""
    user_id = update.effective_user.id
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /register <counselor_email_address>")
        return

    email = context.args[0]
    # Simple regex for basic email validation
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        await update.message.reply_text("The provided email address seems to be invalid. Please check and try again.")
        return

    try:
        # Run the file I/O in a separate thread to avoid blocking
        await asyncio.to_thread(save_counselor_email, user_id, email)
        await update.message.reply_text(f"Counselor's email has been successfully registered as: {email}")
    except Exception as e:
        logging.error(f"Failed to register email for user {user_id}: {e}")
        await update.message.reply_text("An error occurred while registering the email. Please contact the administrator.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text


    if "send mail" in user_input.lower():
        await update.message.reply_text("To send the conversation history, first make sure you've registered your counselor's email with `/register_email <email>`. Then, use the command:\n`/send_logs YYYY-MM-DD YYYY-MM-DD`")
        parse_mode="Markdown"
        return
    
    # Run blocking function in a separate thread
    reply = await asyncio.to_thread(get_gpt_response, user_id, user_input)
    await update.message.reply_text(reply)

async def revoke_export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /revoke_export <signed_token>")
        return
    signed = context.args[0]
    token = _verify_token(signed)
    if not token:
        await update.message.reply_text("The token is invalid.")
        return
    
    # Run blocking function in a separate thread
    ok = await asyncio.to_thread(revoke_secure_link, token)
    await update.message.reply_text("Revocation complete" if ok else "This link has already been revoked or does not exist.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
Hello! I am a psychological counseling chatbot based on Acceptance and Commitment Therapy (ACT) and CBT(Cognitive Behavioral Therapy).

Security Information:
• Conversations are stored on the disk only as 'ciphertext', and the decryption key is kept only by user ID.
• To send your records to a counselor, First, register your counselor's email with `/register youremail@mail.com`. 
  Then, to send your records, use the `/send_logs` command. The counselor will receive a secure link, and you will provide them with an OTP.


Feel free to start talking. I will walk with you in the way of ACT and CBT when you need it.

""")
