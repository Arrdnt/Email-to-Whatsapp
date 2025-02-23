import os
import json
import imaplib
import email
import requests
import threading
from dotenv import load_dotenv

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

REFRESH_INTERVAL = 1200  # 20 menit dalam detik

def process_email(mail, num):
    """Fungsi untuk memproses email dan mengirim ke webhook."""
    try:
        result, msg_data = mail.fetch(num, "(RFC822)")
        if result != "OK":
            print(f"⚠️ ERROR: Gagal mengambil email ID {num}")
            return

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

        # Tandai email sebagai sudah dibaca (opsional)
        mail.store(num, '+FLAGS', '\\Seen')

    except Exception as e:
        print(f"⚠️ ERROR saat memproses email: {e}")

def check_email_idle():
    """Fungsi untuk mendengarkan email baru menggunakan IMAP IDLE dengan refresh berkala."""
    try:
        # Hubungkan ke server IMAP dengan SSL
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select("inbox")

        print("🔍 Menunggu email baru dengan IMAP IDLE...")

        while True:
            # Masuk ke mode IDLE
            mail.send(b'%s IDLE\r\n' % mail._new_tag())
            response = mail.readline().strip()
            if response != b'+ idling':
                print("⚠️ ERROR: Gagal memulai IDLE")
                break

            # Set timer untuk refresh setelah REFRESH_INTERVAL detik
            timer = threading.Timer(REFRESH_INTERVAL, lambda: mail.send(b'DONE\r\n'))
            timer.start()

            # Tunggu notifikasi dari server atau timeout
            while True:
                line = mail.readline().strip()
                if line.startswith(b'*'):
                    # Ada perubahan di mailbox
                    print("📬 Ada perubahan di mailbox!")
                    # Keluar dari mode IDLE
                    mail.send(b'DONE\r\n')
                    break
                elif line == b'':
                    # Koneksi terputus
                    print("⚠️ Koneksi terputus, mencoba reconnect...")
                    break

            # Batalkan timer jika ada perubahan
            timer.cancel()

            # Cek email baru dari pengirim yang diizinkan
            for allowed in ALLOWED_SENDERS:
                result, data = mail.search(None, f'(UNSEEN FROM "{allowed}")')
                if result == "OK":
                    ids = data[0].split()
                    for num in ids:
                        process_email(mail, num)
                else:
                    print(f"⚠️ ERROR: Gagal mencari email dari {allowed}: {result}")

            print("🔍 Kembali ke mode IDLE...")

    except Exception as e:
        print(f"⚠️ ERROR: {e}")
    finally:
        mail.logout()

# Jalankan fungsi
check_email_idle()
