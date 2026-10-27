"""Notification email sender for Qwen3.5-4B RunPod training milestones."""
import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]

def get_email_config():
    env_path = ROOT / ".env"
    vals = dotenv_values(env_path) if env_path.exists() else {}
    sender = vals.get("NOTIFICATION_SENDER") or os.environ.get("NOTIFICATION_SENDER") or "gom532454@gmail.com"
    pw = vals.get("NOTIFICATION_APP_PASSWORD") or os.environ.get("NOTIFICATION_APP_PASSWORD") or ""
    recipient = vals.get("NOTIFICATION_RECIPIENT") or os.environ.get("NOTIFICATION_RECIPIENT") or "gom2553@naver.com"
    return sender, pw.replace(" ", "").strip(), recipient

def send_email(subject: str, body: str, recipient: str = None,
               sender: str = None, app_password: str = None) -> bool:
    cfg_sender, cfg_pw, cfg_rec = get_email_config()
    sender = sender or cfg_sender
    app_password = app_password or cfg_pw
    recipient = recipient or cfg_rec

    if not app_password:
        print("[EMAIL] Error: NOTIFICATION_APP_PASSWORD is not configured.")
        return False

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender, app_password)
        server.send_message(msg)
        server.quit()
        print(f"[EMAIL] Successfully sent email to {recipient}: {subject}")
        return True
    except Exception as e:
        print(f"[EMAIL] Failed to send email: {type(e).__name__} - {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        ok = send_email("[GrowPath] Qwen3.5-4B RunPod 연동 테스트 메일",
                        "안녕하세요!\nRunPod B200 파인튜닝 알림 메일 발송 테스트가 성공했습니다.")
        sys.exit(0 if ok else 1)
