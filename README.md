
---

```markdown
# 📦 Email → WhatsApp Forwarder + Reminder Bot  

Bot ini menghubungkan **email (IMAP)** dengan **WhatsApp**.  
Fitur utama:  
- 🔄 Forward email berdasarkan mapping `sender → target WhatsApp` via `config.json`.  
- ⏰ Reminder langsung dari WhatsApp, dengan notifikasi sebelum deadline.  
- ⚙️ Admin commands langsung dari WhatsApp (.help, .addgroup, .addsender, dst).  
- 📡 Webhook (Python → Node.js) untuk komunikasi antar modul.  
- 🔒 Konfigurasi sensitif di `.env`.  

---

## 📂 Struktur Project
```

project-root/
│── wa-bot.js         # Bot WhatsApp (Node.js)
│── email-listener.py # Listener IMAP email (Python)
│── config.json       # Mapping sender → target
│── reminders.db      # SQLite untuk reminder
│── .env              # Variabel sensitif (jangan commit!)
│── README.md         # Dokumentasi

````

---

## ⚙️ Instalasi

### 1. Clone project
```bash
git clone <repo-url>
cd <project-folder>
````

### 2. Install dependencies Node.js

```bash
npm install whatsapp-web.js qrcode-terminal express dotenv sqlite3 figlet chalk
```

### 3. Install dependencies Python

```bash
pip install requests python-dotenv
```

### 4. Buat file `.env`

Isi contoh:

```env
# Email IMAP
IMAP_HOST=imap.example.com
IMAP_USER=your_email@example.com
IMAP_PASS=your_password

# Webhook (Python → Node.js)
WEBHOOK_URL=http://localhost:3000/send-email

# Interval cek email (detik)
POLL_INTERVAL=60
```

---

## 🗂️ Konfigurasi `config.json`

Mapping sender ke target WhatsApp disimpan di file ini.

Contoh:

```json
{
  "admins": ["6281234567890@c.us"],
  "groups": {
    "akademik": {
      "senders": [
        "notifikasi@example.com",
        "akademik@example.com"
      ],
      "target": "6281234567890@c.us"
    },
    "umum": {
      "senders": [
        "humas@example.com",
        "info@example.com"
      ],
      "target": "6289876543210@c.us"
    }
  },
  "default_target": "6281234567890@c.us"
}
```

* `admins` → hanya nomor ini yang bisa pakai command admin.
* `groups` → kumpulan email sender + target WA masing-masing.
* `default_target` → fallback jika sender tidak ada di group manapun.

---

## 🚀 Menjalankan Bot

### 1. Jalankan WhatsApp bot

```bash
node wa-bot.js
```

* Scan QR Code pertama kali.
* Reminder otomatis load dari `reminders.db`.

### 2. Jalankan Email Listener

```bash
python email-listener.py
```

* Akan cek email tiap `POLL_INTERVAL` detik.
* Kalau ada email baru dari sender yang match → kirim ke webhook (WhatsApp bot).

---

## ⌨️ Command WhatsApp

### User Commands

```
.remind <pesan> <dd-mm-yyyy> jam <hh:mm>  → Tambah reminder
.listremind                              → Lihat semua reminder aktif
.delremind <id>                          → Hapus reminder
```

### Admin Commands

```
.ping
.help
.listgroups
.listsenders <group>
.addgroup <groupName> <targetId>
.delgroup <groupName>
.addsender <groupName> <email>
.delsender <groupName> <email>
.settarget <groupName> <targetId>
.setdefault <targetId>
.listconfig
```

---

## 🛡️ Catatan

* Jangan commit `.env` dan `reminders.db`.
* Kalau pakai penyedia email dengan 2FA → gunakan app password khusus IMAP.
* `targetId` untuk WhatsApp:

  * Nomor pribadi → `628xxxxxx@c.us`
  * Grup → `1203630xxxx@g.us`

---

## Thankyou 😥
