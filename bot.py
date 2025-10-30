import os, requests, time, sqlite3, re, random
from datetime import datetime, timedelta

# === Konfigurasi dasar ===
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise RuntimeError("❌ Token belum diatur. Tambahkan TELEGRAM_BOT_TOKEN di Render Environment.")

API_URL = f"https://api.telegram.org/bot{TOKEN}"
DB = "toko_cat_barokah.db"
OWNER_CONTACT = "Owner: Pak Budi – WhatsApp 0812-3456-7890"

# === Setup database ===
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            nama TEXT,
            barang TEXT,
            jumlah INTEGER,
            harga INTEGER,
            alamat TEXT,
            hp TEXT,
            subtotal INTEGER,
            status TEXT DEFAULT 'pending',
            eta TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit(); conn.close()
init_db()

# === Data produk & kata kunci ===
HARGA_PRODUK = {
    "cat metalik": 250000,
    "cat putih": 180000,
    "cat hitam": 180000,
    "clear coat": 200000
}
KEYWORDS = {
    "metalik": "cat metalik",
    "putih": "cat putih",
    "hitam": "cat hitam",
    "clear": "clear coat",
    "doff": "cat hitam",
    "glossy": "cat metalik"
}

# === Fungsi utilitas ===
def send_message(chat_id, text):
    requests.post(f"{API_URL}/sendMessage",
                  json={"chat_id": chat_id, "text": text})

def cari_produk(teks):
    t = teks.lower()
    for k, p in KEYWORDS.items():
        if k in t: return p
    for p in HARGA_PRODUK.keys():
        if p in t: return p
    return None

def hitung_eta():
    return (datetime.now() + timedelta(days=random.randint(2,5))).strftime("%Y-%m-%d")

def parse_items(raw):
    items = [i.strip() for i in re.split(r',|\n', raw) if i.strip()]
    hasil = []
    for it in items:
        m = re.match(r"(.*)\((\d+)\)", it)
        if m:
            nama, jml = m.group(1).strip(), int(m.group(2))
        else:
            m2 = re.match(r"(.*)\b(\d+)\b\s*$", it)
            if m2:
                nama, jml = m2.group(1).strip(), int(m2.group(2))
            else:
                nama, jml = it, 1
        prod = cari_produk(nama)
        if prod:
            harga = HARGA_PRODUK.get(prod, 0)
        else:
            prod, harga = nama + " (tidak dikenali)", 0
        hasil.append((prod, jml, harga, harga*jml))
    return hasil

def contoh_format():
    return (
        "Silakan pesan dengan format berikut (huruf besar/kecil bebas):\n\n"
        "1. nama : rani\n"
        "2. nama barang : putih (2), clear (1), hitam doff (3)\n"
        "3. alamat : jl melati no 12 bandung\n"
        "4. no hp : 08123456789"
    )

# === Handler utama ===
def handle_text(chat_id, text):
    t = text.lower().strip()

    if t.startswith('/start') or t == 'start':
        msg = (
            "Assalamu'alaikum! Selamat datang di *Toko Cat Barokah* 🧡\n\n"
            "Terima kasih telah menghubungi kami.\n"
            "Ketik *katalog* untuk melihat daftar produk dan harga.\n\n"
            + contoh_format() + "\n\nHubungi owner jika butuh bantuan:\n" + OWNER_CONTACT
        )
        send_message(chat_id, msg); return

    if "katalog" in t or "produk" in t:
        katalog = "🎨 *Katalog Toko Cat Barokah:*\n"
        for n,h in HARGA_PRODUK.items():
            katalog += f"- {n.title()} — Rp{h:,}\n"
        katalog += "\nKetik pesanan sesuai contoh di atas."
        send_message(chat_id, katalog); return

    if re.search(r"barang", text, re.IGNORECASE) and re.search(r"alamat", text, re.IGNORECASE):
        def ambil(label):
            m = re.search(rf"{label}\s*[:\-]\s*(.*)", text, re.IGNORECASE)
            return m.group(1).strip() if m else "-"
        nama = ambil("nama")
        barang_raw = ambil(r"nama\s*barang") if re.search(r"nama\s*barang", text, re.IGNORECASE) else ambil("barang")
        alamat = ambil("alamat"); hp = ambil(r"no\s*hp") if re.search(r"no\s*hp", text, re.IGNORECASE) else ambil("hp")

        parsed = parse_items(barang_raw)
        if not parsed:
            send_message(chat_id,"Format barang tidak terbaca. Contoh: putih (2), clear (1)"); return

        eta = hitung_eta(); total = sum(p[3] for p in parsed)
        conn = sqlite3.connect(DB); c = conn.cursor()
        for p in parsed:
            c.execute("""INSERT INTO orders(chat_id,nama,barang,jumlah,harga,alamat,hp,subtotal,eta)
                         VALUES (?,?,?,?,?,?,?,?,?)""",
                      (chat_id,nama,p[0],p[1],p[2],alamat,hp,p[3],eta))
        conn.commit(); conn.close()

        daftar = "\n".join(f"- {p[0].title()} x{p[1]} = Rp{p[3]:,}" for p in parsed)
        msg = (
            f"Halo {nama}! ✅\n\nPesananmu telah diterima di *Toko Cat Barokah*.\n\n"
            f"📋 Rincian Pesanan:\n{daftar}\n\n"
            f"💰 Total Bayar: Rp{total:,}\n"
            f"🚚 Estimasi Kedatangan: sekitar {eta}\n\n"
            f"Jika ada pertanyaan atau ingin tanya stok, hubungi:\n{OWNER_CONTACT}\n\n"
            f"Setelah barang sampai, mohon kabarkan & beri review ya 🙏\n"
            f"Terima kasih telah berbelanja di *Toko Cat Barokah*! 💕"
        )
        send_message(chat_id, msg); return

    if "status" in t:
        conn = sqlite3.connect(DB); c = conn.cursor()
        c.execute("SELECT barang,jumlah,subtotal,eta,status FROM orders WHERE chat_id=? ORDER BY id DESC",(chat_id,))
        rows=c.fetchall(); conn.close()
        if not rows:
            send_message(chat_id,"Belum ada pesanan yang tercatat."); return
        teks=["📦 Riwayat Pesanan:"]
        tot=0
        for r in rows:
            teks.append(f"- {r[0].title()} x{r[1]} = Rp{r[2]:,} (ETA {r[3]}) [{r[4]}]")
            tot+=r[2]
        teks.append(f"\n💰 Total: Rp{tot:,}")
        send_message(chat_id,"\n".join(teks)); return

    send_message(chat_id,"Ketik *katalog* untuk daftar produk atau ikuti format contoh:\n"+contoh_format())

# === Polling loop ===
print("🤖 Toko Cat Barokah aktif di Render (polling mode)")
last_update_id=None
while True:
    try:
        r=requests.get(f"{API_URL}/getUpdates",
                       params={"timeout":30,"offset":(last_update_id+1) if last_update_id else None},
                       timeout=60)
        data=r.json()
        if not data.get("ok"): time.sleep(3); continue
        for up in data.get("result",[]):
            last_update_id=up["update_id"]
            msg=up.get("message")
            if not msg or "text" not in msg: continue
            handle_text(msg["chat"]["id"], msg["text"])
    except Exception as e:
        print("Loop error:",e); time.sleep(2)
    time.sleep(0.5)
