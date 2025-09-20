// wahan.js (FULL-FEATURED)
// Dependencies: whatsapp-web.js, qrcode-terminal, express, dotenv, sqlite3, figlet, chalk, fs-extra
// npm i whatsapp-web.js qrcode-terminal express dotenv sqlite3 figlet chalk fs-extra

const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const express = require("express");
const dotenv = require("dotenv");
const sqlite3 = require("sqlite3").verbose();
const figlet = require("figlet");
const chalk = require("chalk");
const fs = require("fs");
const fse = require("fs-extra");
const path = require("path");

dotenv.config();

// ---------------------------
// Config paths & defaults
// ---------------------------
const ROOT = __dirname;
const CONFIG_FILE = path.join(ROOT, "config.json");
const AUDIT_FILE = path.join(ROOT, "audit.log");
const DB_FILE = path.join(ROOT, "reminders.db");
const PORT = process.env.PORT ? parseInt(process.env.PORT) : 3000;

let config = loadConfig(); // initial load

// ---------------------------
// Utility: load & save config (safe)
// ---------------------------
function loadConfig() {
    try {
        if (!fs.existsSync(CONFIG_FILE)) {
            // create template default
            const template = {
                admins: [(process.env.PHONE_NUMBER ? process.env.PHONE_NUMBER + "@c.us" : "")].filter(Boolean),
                groups: {},
                default_target: ""
            };
            fse.writeJsonSync(CONFIG_FILE, template, { spaces: 2 });
            logAudit("CONFIG", "Created default config.json");
            return template;
        }
        const raw = fs.readFileSync(CONFIG_FILE, "utf8");
        const parsed = JSON.parse(raw);
        parsed.groups = parsed.groups || {};
        parsed.admins = parsed.admins || [];
        return parsed;
    } catch (e) {
        console.error(chalk.red("⚠️ Failed load config.json"), e);
        return { admins: [], groups: {}, default_target: "" };
    }
}

function saveConfig() {
    try {
        fse.writeJsonSync(CONFIG_FILE, config, { spaces: 2 });
        logAudit("CONFIG", "Saved config.json");
        // reload to normalize
        config = loadConfig();
    } catch (e) {
        console.error(chalk.red("⚠️ Failed save config.json"), e);
    }
}

function logAudit(tag, message) {
    const line = `${new Date().toISOString()} [${tag}] ${message}\n`;
    try {
        fs.appendFileSync(AUDIT_FILE, line);
    } catch (e) {
        console.error("Failed write audit:", e);
    }
}

// watch config.json changes (manual edits)
try {
    fs.watch(CONFIG_FILE, { persistent: true }, (ev, filename) => {
        if (filename && (ev === "change" || ev === "rename")) {
            try {
                config = loadConfig();
                console.log(chalk.yellow("🔄 config.json reloaded due to file change"));
            } catch (e) { /* ignore */ }
        }
    });
} catch (e) {
    console.warn("fs.watch not available:", e.message || e);
}

// ---------------------------
// Boot UI
// ---------------------------
console.log(chalk.green(figlet.textSync("WA BOT", { horizontalLayout: "default" })));
console.log(chalk.gray(`Config: ${CONFIG_FILE}`));
console.log(chalk.gray(`Audit log: ${AUDIT_FILE}`));

// ---------------------------
// WhatsApp client setup
// ---------------------------
const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        headless: true,
        args: ["--no-sandbox", "--disable-setuid-sandbox"]
    }
});

client.on("qr", (qr) => {
    console.log(chalk.yellow("📲 Scan QR untuk login WhatsApp:"));
    qrcode.generate(qr, { small: true });
});

client.on("ready", () => {
    console.log(chalk.green("✅ WhatsApp bot siap!"));
    // load reminders after ready
    loadReminders();
});

client.on("auth_failure", (msg) => {
    console.log(chalk.red("❌ Auth gagal, coba ulang login..."), msg);
});

client.on("disconnected", (reason) => {
    console.log(chalk.red(`⚠️ Terputus: ${reason}. Attempting reconnect...`));
    // attempt reconnect by re-initialize (local-auth persists)
    setTimeout(() => {
        try {
            client.initialize();
        } catch (e) {
            console.error("Reconnect attempt failed:", e);
        }
    }, 3000);
});

// Keep alive presence + uptime
const startTime = Date.now();
function keepAlive() {
    const min = 15 * 60 * 1000;
    const max = 20 * 60 * 1000;
    const randomInterval = Math.floor(Math.random() * (max - min + 1)) + min;

    const uptime = Math.floor((Date.now() - startTime) / 1000);
    const mins = Math.floor(uptime / 60);
    const secs = uptime % 60;

    console.log(chalk.cyanBright(`💡 Bot hidup | Uptime: ${mins}m ${secs}s | ${new Date().toLocaleTimeString()}`));
    client.sendPresenceAvailable().catch(() => {});

    setTimeout(keepAlive, randomInterval);
}
keepAlive();

// ---------------------------
// DB: reminders (sqlite)
// ---------------------------
const db = new sqlite3.Database(DB_FILE);
db.serialize(() => {
    db.run(`CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chatId TEXT,
        message TEXT,
        deadline INTEGER
    )`);
});

// ---------------------------
// Helpers: reminders
// ---------------------------
function scheduleReminder(chatId, message, deadline, id, isNew = true) {
    const now = Date.now();
    const msUntil = deadline - now;
    if (msUntil <= 0) {
        console.log("⚠️ Deadline sudah lewat, skip");
        deleteReminder(id);
        return;
    }
    if (isNew) {
        client.sendMessage(chatId, `✅ Reminder diset untuk "${message}" pada ${new Date(deadline).toLocaleString("id-ID", { timeZone: "Asia/Jakarta" })}`);
    }

    // at-deadline notification
    setTimeout(() => {
        client.sendMessage(chatId, `🚨 "${message}" TELAH MEMASUKI DEADLINE sekarang!`);
        deleteReminder(id);
    }, msUntil);

    // 45 & 30 min notifications if applicable
    const notify = (minsBefore, text) => {
        const t = msUntil - minsBefore * 60 * 1000;
        if (t > 0) {
            setTimeout(() => {
                client.sendMessage(chatId, `${text}\n📌 ${message}`);
            }, t);
        }
    };
    notify(45, "⏰ Reminder 45 menit sebelum deadline!");
    notify(30, "⏰ Reminder 30 menit sebelum deadline!");
}

function saveReminderDB(chatId, message, deadline) {
    return new Promise((resolve, reject) => {
        db.run(`INSERT INTO reminders (chatId, message, deadline) VALUES (?, ?, ?)`,
            [chatId, message, deadline],
            function (err) {
                if (err) return reject(err);
                resolve(this.lastID);
            });
    });
}

function loadReminders() {
    db.all(`SELECT * FROM reminders`, [], (err, rows) => {
        if (err) return console.error("⚠️ Gagal load reminder:", err);
        rows.forEach(r => {
            scheduleReminder(r.chatId, r.message, r.deadline, r.id, false);
        });
    });
}

function deleteReminder(id) {
    db.run(`DELETE FROM reminders WHERE id = ?`, [id]);
}

// ---------------------------
// Utils: parse .remind command
// ---------------------------
function parseDateTime(text) {
    // .remind pesan dd-mm-yyyy jam hh:mm
    const regex = /^\.remind\s+(.+)\s+(\d{2}-\d{2}-\d{4})\s+jam\s+(\d{2}:\d{2})$/i;
    const match = text.match(regex);
    if (!match) return null;
    const message = match[1];
    const [day, month, year] = match[2].split("-").map(Number);
    const [hour, minute] = match[3].split(":").map(Number);
    // convert to Date object in Asia/Jakarta (WIB = UTC+7)
    const deadline = new Date(Date.UTC(year, month - 1, day, hour - 7, minute, 0)); // as previously used
    return { message, deadline };
}

// ---------------------------
// Routing: find targets by sender
// ---------------------------
function getTargetsForSender(senderEmail) {
    // reload config for safety
    config = loadConfig();
    const s = (senderEmail || "").toLowerCase().trim();
    const targets = new Set();

    if (config.groups && typeof config.groups === "object") {
        for (const [groupName, groupData] of Object.entries(config.groups)) {
            const senders = (groupData.senders || []).map(x => x.toLowerCase());
            // match either exact email or contains domain fragment
            for (const allowed of senders) {
                if (!allowed) continue;
                if (s.includes(allowed) || allowed === s) {
                    const t = groupData.target;
                    if (t) targets.add(normalizeTarget(t));
                }
            }
        }
    }

    // fallback
    if (targets.size === 0 && config.default_target) {
        targets.add(normalizeTarget(config.default_target));
    }

    return Array.from(targets);
}

// normalize target into a valid chat id for whatsapp-web.js
function normalizeTarget(t) {
    if (!t) return null;
    t = String(t).trim();
    // if format already "@c.us" or "@g.us" keep
    if (t.endsWith("@c.us") || t.endsWith("@g.us")) return t;
    // if group id form like "1203630..." assume group -> g.us
    if (/^120[0-9]+$/.test(t)) return `${t}@g.us`;
    // otherwise treat as phone number
    const digits = t.replace(/\D/g, "");
    return `${digits}@c.us`;
}

// safe text escaping
function safeText(msg) {
    if (!msg) return "";
    return String(msg);
}

// ---------------------------
// Command handler
// ---------------------------
client.on("message", async (msg) => {
    try {
        const chatId = msg.from;
        const body = (msg.body || "").trim();
        const lower = body.toLowerCase();

        // basic commands
        if (lower === ".ping") return client.sendMessage(chatId, "Active ✅");

        if (lower === ".help") {
            const help = [
                "📖 *WA Bot Help*",
                "User commands:",
                ".remind <pesan> <dd-mm-yyyy> jam <hh:mm>",
                ".listremind",
                ".delremind <id>",
                "",
                "Admin commands:",
                ".listgroups",
                ".listsenders <group>",
                ".addgroup <group> <targetId>",
                ".delgroup <group>",
                ".addsender <group> <email>",
                ".delsender <group> <email>",
                ".settarget <group> <targetId>",
                ".setdefault <targetId>",
                ".listconfig",
                ".help"
            ].join("\n");
            return client.sendMessage(chatId, help);
        }

        // REMINDER commands (available to any user)
        if (lower.startsWith(".remind")) {
            const parsed = parseDateTime(body);
            if (!parsed) return client.sendMessage(chatId, "❌ Format salah!\nContoh: .remind Quiz 18-09-2025 jam 19:09");
            const { message, deadline } = parsed;
            try {
                const id = await saveReminderDB(chatId, message, deadline.getTime());
                scheduleReminder(chatId, message, deadline.getTime(), id, true);
                return client.sendMessage(chatId, `✅ Reminder disimpan (ID: ${id})`);
            } catch (e) {
                console.error("Save reminder error:", e);
                return client.sendMessage(chatId, "⚠️ Gagal menyimpan reminder.");
            }
        }

        if (lower === ".listremind") {
            db.all(`SELECT * FROM reminders WHERE chatId = ?`, [chatId], (err, rows) => {
                if (err) return client.sendMessage(chatId, "⚠️ Gagal ambil data reminder.");
                if (!rows || rows.length === 0) return client.sendMessage(chatId, "📭 Tidak ada reminder aktif.");
                let reply = "📋 Reminder aktif:\n";
                rows.forEach(r => {
                    const deadline = new Date(r.deadline);
                    reply += `\n🆔 ${r.id} | ${r.message} | ${deadline.toLocaleString("id-ID", { timeZone: "Asia/Jakarta" })}`;
                });
                return client.sendMessage(chatId, reply);
            });
            return;
        }

        if (lower.startsWith(".delremind")) {
            const parts = body.split(" ");
            if (parts.length < 2) return client.sendMessage(chatId, "❌ Format salah!\nContoh: .delremind 1");
            const id = parseInt(parts[1]);
            if (isNaN(id)) return client.sendMessage(chatId, "❌ ID harus angka.");
            deleteReminder(id);
            return client.sendMessage(chatId, `🗑️ Reminder dengan ID ${id} berhasil dihapus.`);
        }

        // Admin-only commands
        const isAdmin = config.admins && config.admins.includes(chatId);
        if (!isAdmin) return; // stop here for non-admins for admin commands

        // .listgroups
        if (lower === ".listgroups") {
            const lines = [];
            for (const [g, d] of Object.entries(config.groups || {})) {
                lines.push(`${g} -> ${d.target || "(no target)"} (${(d.senders||[]).length} senders)`);
            }
            const reply = lines.length ? `📂 Groups:\n${lines.join("\n")}` : "📭 Tidak ada groups terdaftar.";
            return client.sendMessage(chatId, reply);
        }

        // .listsenders <group>
        if (lower.startsWith(".listsenders")) {
            const parts = body.split(" ");
            if (parts.length < 2) return client.sendMessage(chatId, "❌ Format: .listsenders <group>");
            const group = parts[1];
            const g = config.groups[group];
            if (!g) return client.sendMessage(chatId, "❌ Group tidak ditemukan.");
            const list = (g.senders || []).join("\n") || "(tidak ada sender)";
            return client.sendMessage(chatId, `📜 Senders for ${group}:\n${list}`);
        }

        // .addgroup <group> <target>
        if (lower.startsWith(".addgroup")) {
            const parts = body.split(" ");
            if (parts.length < 3) return client.sendMessage(chatId, "❌ Format: .addgroup <group> <targetId>");
            const group = parts[1];
            const target = parts[2];
            if (!config.groups) config.groups = {};
            if (config.groups[group]) return client.sendMessage(chatId, "❌ Group sudah ada.");
            config.groups[group] = { senders: [], target };
            saveConfig();
            logAudit("ADMIN", `${chatId} added group ${group} -> ${target}`);
            return client.sendMessage(chatId, `✅ Group ${group} dibuat, target = ${target}`);
        }

        // .delgroup <group>
        if (lower.startsWith(".delgroup")) {
            const parts = body.split(" ");
            if (parts.length < 2) return client.sendMessage(chatId, "❌ Format: .delgroup <groupName>");
            const group = parts[1];
            if (!config.groups || !config.groups[group]) return client.sendMessage(chatId, "❌ Group tidak ditemukan.");
            delete config.groups[group];
            saveConfig();
            logAudit("ADMIN", `${chatId} deleted group ${group}`);
            return client.sendMessage(chatId, `🗑️ Group ${group} dihapus.`);
        }

        // .addsender <group> <email>
        if (lower.startsWith(".addsender")) {
            const parts = body.split(" ");
            if (parts.length < 3) return client.sendMessage(chatId, "❌ Format: .addsender <group> <email>");
            const group = parts[1];
            const emailAddr = parts[2].toLowerCase();
            if (!config.groups || !config.groups[group]) return client.sendMessage(chatId, "❌ Group tidak ditemukan.");
            config.groups[group].senders = config.groups[group].senders || [];
            if (!config.groups[group].senders.includes(emailAddr)) config.groups[group].senders.push(emailAddr);
            saveConfig();
            logAudit("ADMIN", `${chatId} added sender ${emailAddr} -> ${group}`);
            return client.sendMessage(chatId, `✅ Sender ${emailAddr} ditambahkan ke ${group}`);
        }

        // .delsender <group> <email>
        if (lower.startsWith(".delsender")) {
            const parts = body.split(" ");
            if (parts.length < 3) return client.sendMessage(chatId, "❌ Format: .delsender <group> <email>");
            const group = parts[1];
            const emailAddr = parts[2].toLowerCase();
            if (!config.groups || !config.groups[group]) return client.sendMessage(chatId, "❌ Group tidak ditemukan.");
            config.groups[group].senders = (config.groups[group].senders || []).filter(s => s !== emailAddr);
            saveConfig();
            logAudit("ADMIN", `${chatId} removed sender ${emailAddr} from ${group}`);
            return client.sendMessage(chatId, `🗑️ Sender ${emailAddr} dihapus dari ${group}`);
        }

        // .settarget <group> <target>
        if (lower.startsWith(".settarget")) {
            const parts = body.split(" ");
            if (parts.length < 3) return client.sendMessage(chatId, "❌ Format: .settarget <group> <targetId>");
            const group = parts[1];
            const target = parts[2];
            if (!config.groups || !config.groups[group]) return client.sendMessage(chatId, "❌ Group tidak ditemukan.");
            config.groups[group].target = target;
            saveConfig();
            logAudit("ADMIN", `${chatId} set target ${group} -> ${target}`);
            return client.sendMessage(chatId, `✅ Target untuk ${group} diset ke ${target}`);
        }

        // .setdefault <target>
        if (lower.startsWith(".setdefault")) {
            const parts = body.split(" ");
            if (parts.length < 2) return client.sendMessage(chatId, "❌ Format: .setdefault <targetId>");
            const target = parts[1];
            config.default_target = target;
            saveConfig();
            logAudit("ADMIN", `${chatId} set default_target -> ${target}`);
            return client.sendMessage(chatId, `✅ Default fallback target diset ke ${target}`);
        }

        // .listconfig
        if (lower === ".listconfig") {
            return client.sendMessage(chatId, `📂 Config:\n${JSON.stringify(config, null, 2)}`);
        }

    } catch (e) {
        console.error("Command handler error:", e);
    }
});

// ---------------------------
// Express webhook (/send-email)
// ---------------------------
const app = express();
app.use(express.json({ limit: "1mb" }));

app.post("/send-email", async (req, res) => {
    try {
        const { sender, subject, body } = req.body;
        if (!sender) return res.status(400).json({ error: "missing sender" });

        // Find unique targets (dedupe)
        const targets = getTargetsForSender(sender);
        if (!targets || targets.length === 0) {
            console.warn(`⚠️ No target matched for sender ${sender}`);
            return res.status(200).json({ ok: true, note: "no target matched" });
        }

        const message = `📩 Email Baru!\n📧 Dari: ${sender}\n📌 Subject: ${subject || "(no subject)"}\n\n${body || ""}`;

        // send sequentially (could be parallel but sequential is safer to avoid rate issues)
        const results = [];
        for (const t of targets) {
            try {
                await client.sendMessage(t, message);
                console.log(`✅ Forwarded from ${sender} -> ${t}`);
                results.push({ target: t, ok: true });
            } catch (err) {
                console.error(`⚠️ Failed send to ${t}:`, err && err.message ? err.message : err);
                results.push({ target: t, ok: false, error: err.message || String(err) });
            }
        }

        return res.status(200).json({ ok: true, results });
    } catch (err) {
        console.error("⚠️ Error /send-email:", err);
        return res.status(500).json({ error: "internal error" });
    }
});

// root health
app.get("/", (req, res) => {
    res.send({ ok: true, uptime: Math.floor((Date.now() - startTime)/1000) });
});

// start server
app.listen(PORT, () => {
    console.log(chalk.green(`🚀 Webhook berjalan di port ${PORT}`));
});

// initialize client
client.initialize();
