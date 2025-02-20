import os
import json
import imaplib
import email
import time
from dotenv import load_dotenv
import requests
from email.header import decode_header

# Load konfigurasi dari .env
load_dotenv()

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
IMAP_SERVER = os.getenv("IMAP_SERVER")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Load ALLOWED_SENDERS dari .env (dengan format JSON string)
try:
    ALLOWED_SENDERS = json.loads(os.getenv("ALLOWED_SENDERS", "[]"))
    if not isinstance(ALLOWED_SENDERS, list):
        raise ValueError("ALLOWED_SENDERS harus berupa array di .env!")
except json.JSONDecodeError:
    print("⚠️ ERROR: Format ALLOWED_SENDERS salah! Harus JSON array.")
    exit(1)

print(f"✅ Allowed Senders: {ALLOWED_SENDERS}")

# Variabel tracking untuk delay looping
no_email_count = 0   # Hitungan cek tanpa email yang sesuai
interval = 60        # Interval awal: 1 menit

def decode_mime(encoded_str):
    try:
        decoded_parts = decode_header(encoded_str)
        return ''.join(
            part.decode(charset or "utf-8", errors="ignore") if isinstance(part, bytes) else part
            for part, charset in decoded_parts
        ).strip()
    except Exception:
        return encoded_str

def get_email_body(msg):
    """Mengambil isi email dengan prioritas text/plain, fallback ke text/html."""
    body = None
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disp = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disp:
                body = part.get_payload(decode=True).decode(errors="ignore").strip()
                break
            elif content_type == "text/html" and body is None:
                body = part.get_payload(decode=True).decode(errors="ignore").strip()
    else:
        body = msg.get_payload(decode=True).decode(errors="ignore").strip()
    return body or "(Tidak ada isi email)"

def check_email():
    global no_email_count, interval
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select("inbox")

        allowed_email_ids = []
        # Cari email UNSEEN untuk setiap allowed sender
        for allowed in ALLOWED_SENDERS:
            result, data = mail.search(None, f'(UNSEEN FROM "{allowed}")')
            if result == "OK":
                ids = data[0].split()
                allowed_email_ids.extend(ids)
            else:
                print(f"⚠️ ERROR: Gagal mencari email dari {allowed}: {result}")

        # Hilangkan duplikasi
        allowed_email_ids = list(set(allowed_email_ids))

        if not allowed_email_ids:
            no_email_count += 1
            print(f"🔍 Tidak ada email baru dari allowed senders. (Cek ke-{no_email_count})")
            if no_email_count >= 5:
                interval = 900  # 15 menit
                print("⏳ Tidak ada email selama 5x cek, mengubah interval ke 15 menit.")
        else:
            no_email_count = 0
            interval = 60  # Reset interval ke 1 menit jika ada email
            for num in allowed_email_ids:
                result, msg_data = mail.fetch(num, "(RFC822)")
                if result != "OK":
                    print(f"⚠️ ERROR: Gagal mengambil email ID {num}")
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                sender = decode_mime(msg["From"])
                subject = decode_mime(msg["Subject"])
                body = get_email_body(msg)

                print(f"""
📩 Email Baru!
📧 Dari: {sender}
📌 Subject: {subject}
✉️ Pesan: {body[:200]}...
""")
                # Payload yang dikirim menggunakan key "body"
                payload = {
                    "sender": sender,
                    "subject": subject,
                    "body": body
                }
                response = requests.post(WEBHOOK_URL, json=payload)
                print(f"📩 Email dari {sender} diteruskan ke WA! Status: {response.status_code}")

        mail.logout()
    except Exception as e:
        print(f"⚠️ ERROR: {e}")

while True:
    print("\n🔍 Memeriksa email...")
    check_email()
    print(f"⏳ Menunggu {interval // 60} menit sebelum cek ulang...\n")
    time.sleep(interval)
