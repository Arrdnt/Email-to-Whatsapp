# Email Notifier to WhatsApp (via Webhook)
📌 Deskripsi

Script ini berfungsi untuk memeriksa email masuk secara real-time dan meneruskan email dari pengirim yang diizinkan (allowed senders) ke WhatsApp melalui Webhook. Sistem ini menggunakan IMAP untuk membaca email dan memiliki mekanisme delay adaptif agar tetap responsif tanpa membebani server email.

🛠 Fitur

✅ Real-time email monitoring (Email dari allowed senders langsung diteruskan).✅ Delay adaptif (1 menit jika ada email, 15 menit jika tidak ada email selama 5x berturut-turut).✅ Parsing email body (Menghindari encoding aneh seperti ?utf-8?B?).✅ Mengirim pesan ke WhatsApp melalui webhook.✅ Aman dari rate limit karena tidak melakukan polling berlebihan.

🔄 Alur Kerja

Script terhubung ke IMAP server dan login menggunakan kredensial email.

Script mencari email baru dari daftar allowed senders.

Jika ada email baru:

Mengambil pengirim, subjek, dan isi pesan.

Mengirimkan data ke Webhook WhatsApp.

Reset delay ke 1 menit.

Jika tidak ada email baru selama 5x berturut-turut:

Meningkatkan delay ke 15 menit untuk menghemat resource.

Jika saat delay 15 menit ada email masuk:

Email langsung dikirim ke WhatsApp.

Delay di-reset kembali ke 1 menit.

Proses berulang secara terus-menerus.

🛠 Instalasi dan Konfigurasi

1️⃣ Clone Repository

git clone https://github.com/username/email-notifier.git
cd email-notifier

2️⃣ Buat Virtual Environment (Opsional, tapi disarankan)

python -m venv venv
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows

3️⃣ Install Dependensi

pip install -r requirements.txt

4️⃣ Konfigurasi .env

Buat file .env di direktori utama proyek dan isi dengan informasi berikut:

EMAIL="youremail@gmail.com"
PASSWORD="yourpassword"
IMAP_SERVER="imap.gmail.com"
WEBHOOK_URL="https://your-webhook-url"
ALLOWED_SENDERS="[\"example1@gmail.com\", \"example2@yahoo.com\"]"

💡 Catatan: Jika menggunakan Gmail, aktifkan IMAP di pengaturan email dan buat App Password jika autentikasi dua faktor aktif.

5️⃣ Jalankan Script

python main.py

📌 Dependensi yang Digunakan

Paket

Deskripsi

imaplib

Library bawaan Python untuk membaca email via IMAP.

email

Library bawaan Python untuk parsing email.

requests

Untuk mengirimkan email ke Webhook WhatsApp.

python-dotenv

Untuk membaca konfigurasi dari file .env.

time

Library bawaan Python untuk delay adaptif.

📝 Penutup

Script ini dirancang untuk real-time, efisien, dan tidak membebani server email. 🚀 Jika ada saran atau pertanyaan, jangan ragu untuk membuka Issue atau Pull Request di repo ini. 😊 Happy coding! 🎉
