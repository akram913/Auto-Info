# rss_to_telegram.py
import os
import time
import json
import feedparser
import requests
from datetime import datetime

# ---------- KONFIG ----------
FEED_URL = os.getenv("FEED_URL", "https://www.disnakerja.com/feed/")
SEEN_FILE = os.getenv("SEEN_FILE", "seen_feed.json")
BOT_TOKEN = os.getenv("BOT_TOKEN")   # wajib: isi di GitHub Secrets
CHAT_ID   = os.getenv("CHAT_ID")     # wajib: isi di GitHub Secrets
MAX_SEND_PER_RUN = int(os.getenv("MAX_SEND_PER_RUN", "200"))  # batas item per run
MSG_CHAR_LIMIT = 3800  # buffer sebelum batas Telegram 4096

# ---------- HELPERS ----------
def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception as e:
        print("Gagal load seen file:", e)
        return set()

def save_seen(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Gagal save seen file:", e)

def send_telegram(text, parse_mode="Markdown"):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("BOT_TOKEN atau CHAT_ID belum diset.")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False
    }
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def format_entry_short(entry):
    title = entry.get("title", "Lowongan")
    link = entry.get("link", "")
    published = entry.get("published", "")
    # gunakan format ringkas per item
    return f"• {title}\n{link}\n"

def chunk_messages(header, items_texts, limit=MSG_CHAR_LIMIT):
    """Gabungkan items_texts ke beberapa pesan agar tiap pesan tidak melebihi limit"""
    messages = []
    current = header + "\n"
    for it in items_texts:
        if len(current) + len(it) > limit:
            messages.append(current.strip())
            current = header + "\n" + it
        else:
            current += it
    if current.strip():
        messages.append(current.strip())
    return messages

# ---------- UTAMA ----------
def check_and_notify():
    print(f"[{datetime.utcnow().isoformat()}] Mengecek feed: {FEED_URL}")
    feed = feedparser.parse(FEED_URL)
    if feed.bozo:
        print("Warning: parsing feed bermasalah:", getattr(feed, "bozo_exception", None))

    seen = load_seen()
    new_items = []
    for entry in feed.entries:
        uid = entry.get("id") or entry.get("link") or entry.get("title")
        if not uid:
            continue
        if uid not in seen:
            new_items.append((uid, entry))

    if not new_items:
        print("Tidak ada item baru.")
        return 0

    # urut dari lama ke baru supaya masuk Telegram berurutan
    new_items.sort(key=lambda x: x[1].get("published_parsed") or 0)
    # batasi jumlah yang diproses per run
    new_items = new_items[:MAX_SEND_PER_RUN]

    # buat teks per item
    item_texts = [format_entry_short(entry) for uid, entry in new_items]

    # header pesan
    header = f"💼 Ada {len(item_texts)} lowongan baru dari {FEED_URL}\nDiperiksa: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"

    # gabungkan jadi beberapa pesan jika perlu
    messages = chunk_messages(header, item_texts)

    sent = 0
    for msg in messages:
        try:
            send_telegram(msg)
            time.sleep(1)
            sent += 1
        except Exception as e:
            print("Gagal kirim pesan gabungan:", e)
            # jika gagal, jangan tandai seen supaya bisa dicoba lagi run berikutnya
            return sent

    # jika semua pesan gabungan terkirim, tandai semua uid sebagai seen
    for uid, entry in new_items:
        seen.add(uid)
    save_seen(seen)
    print(f"Terkirim {len(new_items)} item dalam {len(messages)} pesan.")
    return len(new_items)

if __name__ == "__main__":
    if not BOT_TOKEN or not CHAT_ID:
        print("Error: BOT_TOKEN dan CHAT_ID harus diset sebagai env vars.")
        exit(1)
    check_and_notify()
