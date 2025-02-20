const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const express = require("express");
const dotenv = require("dotenv");

dotenv.config();

const app = express();
app.use(express.json());

const client = new Client({
    authStrategy: new LocalAuth()
});

client.on("qr", (qr) => {
    console.log("Scan QR untuk login WhatsApp:");
    qrcode.generate(qr, { small: true });
});

client.on("ready", () => {
    console.log("✅ WhatsApp bot siap!");
});

// Webhook endpoint: Node.js akan menerima payload dengan keys: sender, subject, body
app.post("/send-email", async (req, res) => {
    const { sender, subject, body } = req.body; // Menggunakan key "body" dari payload
    const chatId = process.env.PHONE_NUMBER + "@c.us";

    if (!chatId) {
        return res.status(400).json({ error: "PHONE_NUMBER belum diset!" });
    }

    try {
        const message = `📩 Email Baru!\n📧 Dari: ${sender}\n📌 Subject: ${subject}\n✉️ Pesan: ${body}`;
        await client.sendMessage(chatId, message);
        console.log(`✅ Pesan dikirim ke WA: ${message}`);
        res.sendStatus(200);
    } catch (error) {
        console.error("⚠️ Gagal mengirim ke WhatsApp:", error);
        res.sendStatus(500);
    }
});

client.initialize();
app.listen(3000, () => console.log("🚀 Webhook berjalan di port 3000"));
