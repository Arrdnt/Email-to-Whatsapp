import os
import json
import imaplib
import email
import time
from dotenv import load_dotenv
import requests

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

# Variabel tracking
no_email_count = 0  # Jumlah pengecekan tanpa email
interval = 60  # Interval awal (1 menit)

def check_email():
    global no_email_count, interval
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
            no_email_count += 1
            print(f"🔍 Tidak ada email baru dari allowed senders. (Cek ke-{no_email_count})")

            # Jika sudah 5 kali berturut-turut tidak ada email, naikkan delay jadi 15 menit
            if no_email_count >= 5:
                interval = 900  # 15 menit
                print("⏳ Tidak ada email selama 5x cek, mengubah interval ke 15 menit.")
        else:
            no_email_count = 0  # Reset hitungan
            interval = 60  # Kembalikan interval ke 1 menit

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
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode(errors="ignore")
                            break
                else:
                    body = msg.get_payload(decode=True).decode(errors="ignore")

                # Kirim ke webhook untuk diteruskan ke WhatsApp
                payload = {
                    "sender": sender,
                    "subject": subject,
                    "body": body
                }
                response = requests.post(WEBHOOK_URL, json=payload)
                print(f"📩 Email dari {sender} diteruskan ke WA! Status: {response.status_code}")

                # 🚀 Jika email baru masuk selama delay 15 menit, reset interval ke 1 menit
                if interval == 900:
                    interval = 60
                    print("🚀 Email ditemukan! Mengubah interval kembali ke 1 menit.")

        mail.logout()
    except Exception as e:
        print(f"⚠️ ERROR: {e}")

# Loop utama
while True:
    print("\n🔍 Memeriksa email...")
    check_email()
    print(f"⏳ Menunggu {interval // 60} menit sebelum cek ulang...\n")
    time.sleep(interval)
