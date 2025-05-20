#updated ada di RDP 
import os
import json
import imaplib
import email
import time
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup  # Library buat parse HTML

# Load konfigurasi dari .env
load_dotenv()

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
IMAP_SERVER = os.getenv("IMAP_SERVER")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Load daftar pengirim yang diizinkan
try:
    ALLOWED_SENDERS = json.loads(os.getenv("ALLOWED_SENDERS", "[]"))
    if not isinstance(ALLOWED_SENDERS, list):
        raise ValueError("ALLOWED_SENDERS harus berupa array di .env!")
except json.JSONDecodeError:
    print("⚠️ ERROR: Format ALLOWED_SENDERS salah! Harus JSON array.")
    exit(1)

print(f"✅ Allowed Senders: {ALLOWED_SENDERS}")

# Interval cek email (3 menit)
interval = 180  # 3 menit dalam detik

def extract_text_from_html(html):
    """Fungsi untuk ekstrak teks biasa dari HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(separator=' ', strip=True)

def check_email():
    try:
        # Hubungkan ke server email
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select("inbox")

        allowed_email_ids = []
        
        # Cari email baru dari pengirim yang diizinkan
        for allowed in ALLOWED_SENDERS:
            result, data = mail.search(None, f'(UNSEEN FROM "{allowed}")')
            if result == "OK":
                ids = data[0].split()
                allowed_email_ids.extend(ids)
            else:
                print(f"⚠️ ERROR: Gagal mencari email dari {allowed}: {result}")

        # Hilangkan duplikasi jika ada
        allowed_email_ids = list(set(allowed_email_ids))

        if not allowed_email_ids:
            print("🔍 Tidak ada email baru dari allowed senders.")
        else:
            for num in allowed_email_ids:
                result, msg_data = mail.fetch(num, "(RFC822)")
                if result != "OK":
                    print(f"⚠️ ERROR: Gagal mengambil email ID {num}")
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                sender = msg["From"]
                subject = msg["Subject"]

                # Ambil isi email
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/plain":
                            body = part.get_payload(decode=True).decode(errors="ignore")
                            break  # Prioritas teks biasa
                        elif content_type == "text/html":
                            html = part.get_payload(decode=True).decode(errors="ignore")
                            body = extract_text_from_html(html)  # Ekstrak teks dari HTML
                            break
                else:
                    content_type = msg.get_content_type()
                    if content_type == "text/plain":
                        body = msg.get_payload(decode=True).decode(errors="ignore")
                    elif content_type == "text/html":
                        html = msg.get_payload(decode=True).decode(errors="ignore")
                        body = extract_text_from_html(html)  # Ekstrak teks dari HTML

                # Kirim ke webhook untuk diteruskan ke WhatsApp
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

# Loop utama
while True:
    print("\n🔍 Memeriksa email...")
    check_email()
    print(f"⏳ Menunggu 3 menit sebelum cek ulang...\n")
    time.sleep(interval)
