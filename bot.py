#!/usr/bin/env python3
"""
do_bot_final_fixed.py
Perbaikan:
- Tambah jeda & error handling agar sticker + banner selalu tampil.
- Struktur /start lebih stabil dan asinkron.
"""

import os, time, random, json, logging, datetime, asyncio, requests
from typing import Dict, Optional, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ========== CONFIG ==========
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN") or "8281254978:AAFaO5jwLAvuFKr3bf87op-BfdB6PTAlk7k"
DO_TOKEN = os.getenv("DO_TOKEN") or "dop_v1_7d249428d9377e7bcac60a7bf0f25bbe9b23641cbb92bf44dd2af4c5425ce4f1"
API_URL = "https://api.digitalocean.com/v2"
HEADERS = {"Authorization": f"Bearer {DO_TOKEN}", "Content-Type": "application/json"}
REGION = "sgp1"
IMAGE = "ubuntu-22-04-x64"
DEFAULT_PASS = "@@Farzgege1a"
RDP_PORT = 3389

ADMIN_ID = 7790846931
ADMIN_FILE = "admin_id.txt"
ACCESS_FILE = "access.json"
CREATED_LOG = "created.json"

# ✅ Sticker & Banner file_id kamu
STICKER_FILE_ID = "AAMCAgADGQEAAT0meWkDLJ6MfCGXdlITcTXIF45FdLa-AAIFAQACVp29Crfk_bYORV93AQAHbQADNgQ"
BANNER_FILE_ID  = "AgACAgUAAxkBAAE9Jn1pAyz6hNWr8mAjQouauyOk5Ia8pAACXQ1rG86OGFQqe0TzNzAMgwEAAwIAA3MAAzYE"

CLOUD_INIT_TEMPLATE = """#cloud-config
chpasswd:
  list: |
    root:{password}
  expire: False
ssh_pwauth: True
package_update: true
packages:
  - xfce4
  - xfce4-goodies
  - xrdp
runcmd:
  - systemctl enable xrdp
  - ufw allow {rdp_port}/tcp
  - sed -i 's/allowed_users=console/allowed_users=anybody/' /etc/X11/Xwrapper.config || true
  - systemctl restart xrdp
"""

# Intel + AMD Plans
SIZES = {
    "intel_1g_1c": {"slug": "s-1vcpu-1gb", "desc": "Intel • 1 GB / 1 CPU / 35 GB NVMe / 1 TB"},
    "intel_2g_1c": {"slug": "s-1vcpu-2gb", "desc": "Intel • 2 GB / 1 CPU / 70 GB NVMe / 2 TB"},
    "intel_2g_2c": {"slug": "s-2vcpu-2gb", "desc": "Intel • 2 GB / 2 CPUs / 90 GB NVMe / 3 TB"},
    "intel_4g_2c": {"slug": "s-2vcpu-4gb", "desc": "Intel • 4 GB / 2 CPUs / 120 GB NVMe / 4 TB"},
    "intel_8g_2c": {"slug": "s-2vcpu-8gb", "desc": "Intel • 8 GB / 2 CPUs / 160 GB NVMe / 5 TB"},
    "intel_8g_4c": {"slug": "s-4vcpu-8gb", "desc": "Intel • 8 GB / 4 CPUs / 240 GB NVMe / 6 TB"},
    "amd_1g_1c": {"slug": "s-1vcpu-1gb-amd", "desc": "AMD • 1 GB / 1 CPU / 25 GB NVMe / 1 TB"},
    "amd_2g_1c": {"slug": "s-1vcpu-2gb-amd", "desc": "AMD • 2 GB / 1 CPU / 50 GB NVMe / 2 TB"},
    "amd_2g_2c": {"slug": "s-2vcpu-2gb-amd", "desc": "AMD • 2 GB / 2 CPUs / 60 GB NVMe / 3 TB"},
    "amd_4g_2c": {"slug": "s-2vcpu-4gb-amd", "desc": "AMD • 4 GB / 2 CPUs / 80 GB NVMe / 4 TB"},
    "amd_8g_2c": {"slug": "s-2vcpu-8gb-amd", "desc": "AMD • 8 GB / 2 CPUs / 100 GB NVMe / 5 TB"},
    "amd_8g_4c": {"slug": "s-4vcpu-8gb-amd", "desc": "AMD • 8 GB / 4 CPUs / 160 GB NVMe / 5 TB"},
    "amd_16g_4c": {"slug": "s-4vcpu-16gb-amd", "desc": "AMD • 16 GB / 4 CPUs / 200 GB NVMe / 8 TB"},
    "amd_16g_8c": {"slug": "s-8vcpu-16gb-amd", "desc": "AMD • 16 GB / 8 CPUs / 320 GB NVMe / 6 TB"},
    "amd_32g_8c": {"slug": "s-8vcpu-32gb-amd", "desc": "AMD • 32 GB / 8 CPUs / 400 GB NVMe / 10 TB"},
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- Storage Helper ----------
def ensure_files():
    for f, init in [(ACCESS_FILE, {}), (CREATED_LOG, []), (ADMIN_FILE, str(ADMIN_ID))]:
        if not os.path.exists(f):
            with open(f, "w") as x:
                if isinstance(init, (dict, list)):
                    json.dump(init, x)
                else:
                    x.write(init)

def load_admin(): return int(open(ADMIN_FILE).read().strip())
def load_access(): return json.load(open(ACCESS_FILE))
def save_access(x): json.dump(x, open(ACCESS_FILE, "w"), indent=2)

def grant_access(uid, days):
    acc = load_access()
    exp = (datetime.datetime.now() + datetime.timedelta(days=days)).timestamp()
    acc[str(uid)] = exp
    save_access(acc)
    return exp

def has_access(uid):
    if uid == load_admin(): return True
    acc = load_access()
    exp = acc.get(str(uid))
    return exp and datetime.datetime.now().timestamp() < exp

def get_expiry(uid):
    acc = load_access(); exp = acc.get(str(uid))
    return datetime.datetime.fromtimestamp(exp) if exp else None

def log_created(r):
    try: arr = json.load(open(CREATED_LOG))
    except: arr = []
    arr.append(r)
    json.dump(arr, open(CREATED_LOG, "w"), indent=2)

# ---------- DO Helper ----------
def do_create(name, size, user_data):
    payload = {"name": name,"region": REGION,"size": size,"image": IMAGE,"user_data": user_data,"backups": False,"ipv6": False,"monitoring": True}
    r = requests.post(f"{API_URL}/droplets", headers=HEADERS, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()["droplet"]["id"]

def do_get(did):
    r = requests.get(f"{API_URL}/droplets/{did}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()["droplet"]

def wait_for_ip(did, timeout=600, poll=5):
    start = time.time()
    while time.time() - start < timeout:
        try:
            nets = do_get(did)["networks"]["v4"]
            for n in nets:
                if n["type"] == "public": return n["ip_address"]
        except: pass
        time.sleep(poll)
    return None

# ---------- Bot Logic ----------
USER_MODE, USER_CUSTOM = {}, {}

async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid, username, name = user.id, f"@{user.username}" if user.username else "-", user.first_name or "-"
    access = load_access(); users_count = 1 + len(access)
    try: created_count = len(json.load(open(CREATED_LOG)))
    except: created_count = 0

    # Delay + send sticker safely
    await asyncio.sleep(0.3)
    try:
        await ctx.bot.send_sticker(chat_id=uid, sticker=STICKER_FILE_ID)
    except Exception as e:
        logger.warning(f"Gagal kirim sticker: {e}")

    # Delay + send banner
    await asyncio.sleep(0.4)
    caption = (f"🛍️ FARZ VPS🛍️\n\n"
               f"FARZ - VPS \nCREATE VPS DENGAN BOT 24 JAM ONLINE‼️\n\n"
               f"🇮🇩 Profile User\n━━━━━━━━━━━━━━\n"
               f"🆔 ID             : {uid}\n"
               f"👤 USERNAME : {username}\n"
               f"📛 NAMA        : {name}\n"
               f"🌐 TERDAFTAR : Yes ✅\n\n"
               f"🤖 Statistic Bot\n━━━━━━━━━━━━━━\n"
               f"👥 USERS      : {users_count}\n"
               f"💰 TRX SUKSES : {created_count}\n\n"
               f"👤 Developer Script : @Far9376")
    try:
        await ctx.bot.send_photo(chat_id=uid, photo=BANNER_FILE_ID, caption=caption)
    except Exception as e:
        logger.warning(f"Gagal kirim banner: {e}")
        await ctx.bot.send_message(chat_id=uid, text=caption)

    kb = [
        [InlineKeyboardButton("💻 Buat VPS", callback_data="menu::create")],
        [InlineKeyboardButton("🔑 Akses Create VPS", callback_data="menu::access")],
        [InlineKeyboardButton("📞 Hubungi Admin", url=f"tg://user?id={load_admin()}")],
    ]
    await ctx.bot.send_message(chat_id=uid, text="Pilih salah satu:", reply_markup=InlineKeyboardMarkup(kb))

async def setadmin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    admin = load_admin()
    if admin == ADMIN_ID:
        save_admin = open(ADMIN_FILE, "w")
        save_admin.write(str(caller))
        save_admin.close()
        await ctx.bot.send_message(chat_id=caller, text=f"✅ Kamu sekarang jadi admin utama (ID: {caller}).")
    else:
        await ctx.bot.send_message(chat_id=caller, text="Admin sudah diset sebelumnya.")

async def grant_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if caller != load_admin():
        await ctx.bot.send_message(chat_id=caller, text="❌ Hanya admin utama yang bisa memberi akses.")
        return
    if not ctx.args or len(ctx.args) < 2:
        await ctx.bot.send_message(chat_id=caller, text="Gunakan: /grant <user_id> <hari>")
        return
    try:
        target = int(ctx.args[0])
        days = int(ctx.args[1])
    except:
        await ctx.bot.send_message(chat_id=caller, text="Format salah. Contoh: /grant 10489382 2")
        return
    exp = grant_access(target, days)
    await ctx.bot.send_message(chat_id=caller, text=f"✅ Akses diberikan ke {target} selama {days} hari. Sampai {datetime.datetime.fromtimestamp(exp)}")
    # notify target
    try:
        await ctx.bot.send_message(chat_id=target, text=f"✅ Kamu diberi akses membuat VPS selama {days} hari (sampai {datetime.datetime.fromtimestamp(exp)}).")
    except Exception:
        pass

async def revoke_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if caller != load_admin():
        await ctx.bot.send_message(chat_id=caller, text="❌ Hanya admin utama yang bisa mencabut akses.")
        return
    if not ctx.args or len(ctx.args) < 1:
        await ctx.bot.send_message(chat_id=caller, text="Gunakan: /revoke <user_id>")
        return
    try:
        target = str(int(ctx.args[0]))
    except:
        await ctx.bot.send_message(chat_id=caller, text="Format id salah.")
        return
    access = load_access()
    if target in access:
        del access[target]
        save_access(access)
        await ctx.bot.send_message(chat_id=caller, text=f"✅ Akses {target} dicabut.")
    else:
        await ctx.bot.send_message(chat_id=caller, text="User tidak ditemukan di daftar akses.")

async def myaccess_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid == load_admin():
        await ctx.bot.send_message(chat_id=uid, text="Kamu admin utama (akses permanen).")
        return
    exp = get_expiry(uid)
    if not exp:
        await ctx.bot.send_message(chat_id=uid, text="Kamu belum punya akses.")
    else:
        await ctx.bot.send_message(chat_id=uid, text=f"Akses berlaku sampai: {exp}")

# menu callback handler
async def menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    uid = q.from_user.id

    if data == "menu::create":
        if not has_access(uid):
            await q.edit_message_text("❌ Kamu tidak punya akses membuat VPS. Hubungi admin atau minta akses.")
            return
        # choose mode: custom or auto
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧠 Custom Hostname & Password", callback_data="mode::custom")],
            [InlineKeyboardButton("⚡ Auto (FarzXD)", callback_data="mode::auto")],
            [InlineKeyboardButton("🔙 Batal", callback_data="menu::back")]
        ])
        await q.edit_message_text("Pilih mode pembuatan VPS:", reply_markup=kb)
        return

    if data == "menu::access":
        # show instructions to request access
        admin_link = f"tg://user?id={load_admin()}"
        text = ("Untuk mendapatkan akses membuat VPS, hubungi admin dan berikan ID-mu.\n\n"
                f"Contoh pesan ke admin: \"Minta akses buat VPS. ID saya: {uid}. Durasi: 2 hari\"\n\n"
                f"Atau klik Hubungi Admin: @@Far9376")
        await q.edit_message_text(text)
        return

    if data == "menu::back":
        await q.edit_message_text("Dibatalkan.")
        return

    if data.startswith("mode::"):
        mode = data.split("::", 1)[1]
        USER_MODE[uid] = mode
        # show plan choices
        keyboard = [[InlineKeyboardButton(v["desc"], callback_data=f"plan::{k}")] for k, v in SIZES.items()]
        keyboard.append([InlineKeyboardButton("🔙 Batal", callback_data="menu::back")])
        await q.edit_message_text(f"Mode dipilih: {mode}\nPilih paket VPS:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("plan::"):
        plan_key = data.split("::", 1)[1]
        plan = SIZES.get(plan_key)
        if not plan:
            await q.edit_message_text("Plan tidak ditemukan.")
            return
        # if custom mode -> ask hostname then password
        mode = USER_MODE.get(uid, "auto")
        if mode == "custom":
            USER_CUSTOM[uid] = {"step": "hostname", "plan": plan_key}
            await q.edit_message_text("🧠 Kirimkan Hostname yang kamu inginkan (contoh: my-vps-01):")
            return
        # auto mode
        hostname = f"FarzXD{random.randint(100,999)}"
        password = DEFAULT_PASS
        await q.edit_message_text(f"🚀 Membuat VPS: {plan['desc']}\nHostname: {hostname}\nMohon tunggu...")
        # create droplet (blocking IO -> run in thread to avoid blocking loop)
        asyncio.create_task(create_and_report(ctx, q.message.chat_id, uid, hostname, password, plan))
        return

# message handler for custom inputs (hostname & password)
async def custom_text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in USER_CUSTOM:
        return
    data = USER_CUSTOM[uid]
    text = (update.message.text or "").strip()
    if data["step"] == "hostname":
        data["hostname"] = text
        data["step"] = "password"
        await update.message.reply_text("🔑 Sekarang kirimkan password untuk VPS (minimal 6 karakter):")
        return
    if data["step"] == "password":
        password = text
        plan = SIZES.get(data["plan"])
        if not plan:
            await update.message.reply_text("Plan tidak ditemukan, batalkan dan coba lagi.")
            USER_CUSTOM.pop(uid, None)
            return
        hostname = data.get("hostname") or f"FarzXD{random.randint(100,999)}"
        await update.message.reply_text(f"🚀 Membuat VPS {hostname} dengan plan {plan['desc']} ...")
        USER_CUSTOM.pop(uid, None)
        asyncio.create_task(create_and_report(ctx, update.message.chat_id, uid, hostname, password, plan))
        return

# create droplet (run in background)
async def create_and_report(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, uid: int, hostname: str, password: str, plan: Dict[str, Any]):
    try:
        user_data = CLOUD_INIT_TEMPLATE.format(password=password, rdp_port=RDP_PORT)
        # run blocking IO in executor
        loop = asyncio.get_event_loop()
        droplet_id = await loop.run_in_executor(None, lambda: do_create(hostname, plan["slug"], user_data))
        # wait for IP
        ip = await loop.run_in_executor(None, lambda: wait_for_ip(droplet_id, timeout=900, poll=8))
        if ip:
            # log
            record = {
                "hostname": hostname,
                "ip": ip,
                "plan": plan["desc"],
                "user": uid,
                "password": password,
                "created_at": datetime.datetime.now().isoformat(),
                "droplet_id": droplet_id
            }
            log_created(record)
            await ctx.bot.send_message(chat_id=chat_id, text=(
                "✅ VPS AKTIF\n"
                f"Hostname: {hostname}\n"
                f"IP: {ip}\n"
                f"User: root\n"
                f"Password: {password}\n"
                f"RDP Port: {RDP_PORT}\n"
                f"Droplet ID: {droplet_id}"
            ))
        else:
            await ctx.bot.send_message(chat_id=chat_id, text="⚠️ Timeout menunggu IP publik. Cek dashboard DigitalOcean.")
    except Exception as e:
        await ctx.bot.send_message(chat_id=chat_id, text=f"❌ Error membuat droplet: {e}")

# ========== ADMIN UTIL ==========
async def list_access_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if caller != load_admin():
        await ctx.bot.send_message(chat_id=caller, text="❌ Hanya admin.")
        return
    access = load_access()
    if not access:
        await ctx.bot.send_message(chat_id=caller, text="Tidak ada akses terdaftar.")
        return
    lines = []
    for k, v in access.items():
        lines.append(f"{k} -> until {datetime.datetime.fromtimestamp(v)}")
    await ctx.bot.send_message(chat_id=caller, text="\n".join(lines))

# ========== STARTUP ==========
async def main():
    ensure_files()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("setadmin", setadmin_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("revoke", revoke_cmd))
    app.add_handler(CommandHandler("myaccess", myaccess_cmd))
    app.add_handler(CommandHandler("listaccess", list_access_cmd))

    # callbacks & messages
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_text_handler))

    logger.info("Bot starting...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
