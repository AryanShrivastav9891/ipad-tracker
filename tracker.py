#!/usr/bin/env python3
"""
iPad 11 (A16, 2025) - Wi-Fi - 128GB  |  India price watcher

Kya karta hai:
  1. Croma / Reliance Digital / Vijay Sales / Apple India / Flipkart / Amazon se live price uthata hai
  2. Bank offer laga ke "effective price" nikaalta hai
  3. price_history.json me history save karta hai (dashboard isi ko padhta hai)
  4. Telegram pe alert bhejta hai jab:
       - effective price target se neeche jaye
       - koi bhi store X% ya usse zyada gire
       - naya all-time low ban jaye
       - koi store lagataar block/fail ho raha ho

Chalane ke liye:
    export TELEGRAM_BOT_TOKEN="..."
    export TELEGRAM_CHAT_ID="..."
    python tracker.py            # normal run
    python tracker.py --test     # sirf test message bhejta hai
    python tracker.py --dry-run  # scrape karta hai, alert nahi bhejta
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ----------------------------------------------------------------------------
# Settings (env vars se override kar sakte ho)
# ----------------------------------------------------------------------------

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parent
HISTORY_FILE = ROOT / "price_history.json"
STATE_FILE = ROOT / "state.json"


def _load_local_env() -> None:
    """
    Local testing ke liye .env.local padhta hai. Ye file .gitignore me hai,
    isliye git me kabhi nahi jayegi. GitHub Actions pe ye file hoti hi nahi -
    wahan secrets environment se aate hain.
    """
    env_file = ROOT / ".env.local"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_local_env()

MRP = 49900                                                  # Apple India MRP (June 2026 hike ke baad)
TARGET_PRICE = int(os.getenv("TARGET_PRICE", "40000"))       # yahan pahunche to "kharid lo" alert
DROP_PCT = float(os.getenv("DROP_PCT", "3"))                 # itne % ki girawat pe alert
SANITY_MIN, SANITY_MAX = 15000, 95000                        # iske bahar ka number = galat scrape
FAIL_STREAK_ALERT = 6                                        # itni baar lagataar fail ho to batao
ALERT_COOLDOWN_HOURS = 12                                    # same alert dobara itne ghante baad

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
    "Cache-Control": "no-cache",
}

# ----------------------------------------------------------------------------
# Stores
#
# bank_offer   = rupees jo best bank offer se kam hote hain
# offer_label  = alert / dashboard me dikhne wala text
# patterns     = JSON-LD fail ho to ye regex try hote hain (pehla match jeetta hai)
# ----------------------------------------------------------------------------

STORES = [
    {
        "id": "croma",
        "name": "Croma",
        "url": "https://www.croma.com/apple-ipad-a16-bionic-chip-wi-fi-11-inch-128gb-silver-2025-model-/p/324285",
        "bank_offer": 6000,
        "offer_label": "₹6,000 cashback (Axis/ICICI/SBI, 6-mo EMI)",
        "patterns": [r'"sellingPrice"\s*:\s*"?([0-9][0-9,.]*)', r'"price"\s*:\s*"?([0-9][0-9,.]*)'],
    },
    {
        "id": "reliance",
        "name": "Reliance Digital",
        "url": "https://www.reliancedigital.in/product/apple-ipad-a16-11th-gen-2025-2759-cm-1086-inch-wi-fi-tablet-128-gb-silver-m7vtn8-8967038",
        "bank_offer": 6000,
        "offer_label": "₹6,000 cashback + 6-mo No-Cost EMI",
        "patterns": [
            r'"sellingPrice"\s*:\s*"?([0-9][0-9,.]*)',
            r'"finalPrice"\s*:\s*"?([0-9][0-9,.]*)',
            r'"price"\s*:\s*"?([0-9][0-9,.]*)',
        ],
    },
    {
        "id": "vijaysales",
        "name": "Vijay Sales",
        "url": "https://www.vijaysales.com/p/P238547/238543/apple-ipad-11th-gen-2025-wifi-128gb-silver-md3y4hn-a",
        "bank_offer": 6000,
        "offer_label": "Card offer + No-Cost EMI",
        "patterns": [r'"price"\s*:\s*"?([0-9][0-9,.]*)', r'₹\s*([0-9]{2},[0-9]{3})'],
    },
    {
        "id": "apple",
        "name": "Apple India",
        "url": "https://www.apple.com/in/shop/buy-ipad/ipad/128gb-silver-wifi",
        "bank_offer": 6000,
        "offer_label": "₹6,000 cashback (Axis/ICICI/SBI, 6-mo EMI)",
        "patterns": [r'"fullPrice"\s*:\s*"?([0-9][0-9,.]*)', r'"price"\s*:\s*"?([0-9][0-9,.]*)'],
    },
    {
        "id": "flipkart",
        "name": "Flipkart",
        "url": "https://www.flipkart.com/apple-2025-ipad-a16-128-gb-rom-11-0-inch-wi-fi-only-silver/p/itm12757f0d5f932",
        "bank_offer": 6000,
        "offer_label": "₹6,000 aggregate bank offer",
        "patterns": [
            r'"finalPrice"\s*:\s*\{[^}]*"value"\s*:\s*([0-9]+)',
            r'"price"\s*:\s*"?([0-9][0-9,.]*)',
            r'₹([0-9]{2},[0-9]{3})',
        ],
        "note": "Flipkart bots block karta hai - fail ho to Pricehistory/BuyHatke pe bharosa karo",
    },
    {
        "id": "amazon",
        "name": "Amazon India",
        "url": "https://www.amazon.in/Apple-iPad-11%E2%80%B3-Display-All-Day/dp/B0DZ79Q1DB",
        "bank_offer": 2037,
        "offer_label": "Amazon Pay ICICI cashback",
        "patterns": [
            r'"priceAmount"\s*:\s*([0-9.]+)',
            r'a-price-whole">([0-9,]+)',
            r'id="priceblock_ourprice"[^>]*>\s*₹\s*([0-9,]+)',
        ],
        "note": "Amazon bots block karta hai - fail ho to Keepa/Pricehistory pe bharosa karo",
    },
]


# ----------------------------------------------------------------------------
# Price extraction
# ----------------------------------------------------------------------------

def _to_number(raw) -> int | None:
    """'₹47,490.00' -> 47490"""
    if raw is None:
        return None
    text = str(raw).replace("\u20b9", "").replace(",", "").strip()
    match = re.search(r"[0-9]+(?:\.[0-9]+)?", text)
    if not match:
        return None
    try:
        return int(round(float(match.group())))
    except ValueError:
        return None


def _walk_for_price(node) -> list[int]:
    """JSON-LD ke andar kahin bhi chhupi hui price keys dhoondta hai."""
    found: list[int] = []
    price_keys = {"price", "lowprice", "sellingprice", "finalprice", "offerprice"}
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in price_keys and not isinstance(value, (dict, list)):
                number = _to_number(value)
                if number is not None:
                    found.append(number)
            else:
                found.extend(_walk_for_price(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_for_price(item))
    return found


def extract_price(html: str, patterns: list[str]) -> int | None:
    # Har source ka apna tier. Pehla tier jisme sane number mile, wahi jeetta hai.
    # Pehle teeno ko mila kar min() lete the - loose regex page pe kahin se
    # accessory/EMI/dusre model ka chhota number utha leta tha aur JSON-LD ka
    # sahi price haar jaata tha (Apple: 49900 ke bajaye 24900 aa raha tha).
    jsonld: list[int] = []
    meta_prices: list[int] = []
    fallback: list[int] = []

    # 1) JSON-LD - sabse reliable
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        try:
            jsonld.extend(_walk_for_price(json.loads(block.strip())))
        except json.JSONDecodeError:
            continue

    # 2) Standard meta tags
    for meta in re.findall(
        r'<meta[^>]+(?:itemprop|property)=["\'](?:price|product:price:amount|og:price:amount)["\'][^>]*>',
        html,
        re.IGNORECASE,
    ):
        content = re.search(r'content=["\']([^"\']+)["\']', meta)
        if content:
            number = _to_number(content.group(1))
            if number is not None:
                meta_prices.append(number)

    # 3) Site-specific fallbacks
    for pattern in patterns:
        for match in re.findall(pattern, html):
            number = _to_number(match)
            if number is not None:
                fallback.append(number)

    for tier in (jsonld, meta_prices, fallback):
        sane = [c for c in tier if SANITY_MIN <= c <= SANITY_MAX]
        if sane:
            # tier ke andar sabse kam = actual selling price (MRP/strike-through nahi)
            return min(sane)
    return None


def fetch_store(store: dict, attempts: int = 3) -> dict:
    result = {
        "id": store["id"],
        "name": store["name"],
        "url": store["url"],
        "listed": None,
        "effective": None,
        "offer": store["offer_label"],
        "error": None,
    }
    last_error = "unknown error"

    for attempt in range(attempts):
        try:
            response = requests.get(store["url"], headers=HEADERS, timeout=25)
            if response.status_code in (403, 429, 503):
                last_error = f"blocked (HTTP {response.status_code})"
                time.sleep(3 + attempt * 4)
                continue
            response.raise_for_status()
            price = extract_price(response.text, store["patterns"])
            if price is None:
                last_error = "price page pe mila nahi (layout badla?)"
                time.sleep(2)
                continue
            result["listed"] = price
            result["effective"] = max(price - store["bank_offer"], 0)
            return result
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}"
            time.sleep(2 + attempt * 3)

    result["error"] = last_error
    return result


# ----------------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------------

def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def latest_per_store(entries: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for entry in entries:
        current = latest.get(entry["store"])
        if current is None or entry["ts"] > current["ts"]:
            latest[entry["store"]] = entry
    return latest


# ----------------------------------------------------------------------------
# Telegram
# ----------------------------------------------------------------------------

def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[telegram] token/chat id set nahi hai - message skip kiya")
        print(message)
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        response.raise_for_status()
        print("[telegram] bheja")
        return True
    except requests.RequestException as exc:
        print(f"[telegram] fail: {exc}")
        return False


def rupees(amount) -> str:
    """1234567 -> 12,34,567 (Indian grouping)"""
    if amount is None:
        return "—"
    digits = str(int(amount))
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
    return f"{head},{tail}"


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="test Telegram message bhejo aur exit")
    parser.add_argument("--dry-run", action="store_true", help="scrape karo, alert mat bhejo")
    args = parser.parse_args()

    if args.test:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print("FAIL: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID set nahi hain.")
            print("Local: .env.local bana lo.  GitHub: repo secrets me daalo.")
            return 1
        # Token valid hai ya nahi, pehle wahi check karo
        try:
            who = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe", timeout=15
            ).json()
            if not who.get("ok"):
                print("FAIL: token reject ho gaya. Revoke ke baad naya token daala tha?")
                return 1
            print(f"[telegram] bot mila: @{who['result'].get('username')}")
        except requests.RequestException as exc:
            print(f"FAIL: Telegram tak pahunch nahi paaye ({exc})")
            return 1

        ok = send_telegram(
            "<b>iPad tracker zinda hai ✅</b>\n"
            f"Target: ₹{rupees(TARGET_PRICE)}\n"
            f"Drop alert: {DROP_PCT}% ya zyada\n"
            f"Stores: {len(STORES)}"
        )
        if not ok:
            print("Token to sahi hai par message nahi gaya - bot ko '/start' bheja tha?")
            print("Chat ID bhi verify kar lo.")
        return 0 if ok else 1

    now = datetime.now(IST)
    history = load_json(HISTORY_FILE, {
        "product": "iPad 11 (A16, 2025) · Wi-Fi · 128GB",
        "mrp": MRP,
        "currency": "INR",
        "target": TARGET_PRICE,
        "entries": [],
    })
    history["target"] = TARGET_PRICE
    history["mrp"] = MRP
    entries: list[dict] = history.get("entries", [])
    state = load_json(STATE_FILE, {"fail_streak": {}, "last_alert": {}})

    previous = latest_per_store(entries)
    all_time_low = min((e["effective"] for e in entries if e.get("effective")), default=None)

    results = []
    alerts: list[str] = []
    changed = False

    for store in STORES:
        print(f"[fetch] {store['name']} ...", flush=True)
        result = fetch_store(store)
        results.append(result)

        if result["error"]:
            streak = state["fail_streak"].get(store["id"], 0) + 1
            state["fail_streak"][store["id"]] = streak
            print(f"   fail ({result['error']}) - streak {streak}")
            if streak == FAIL_STREAK_ALERT:
                note = store.get("note", "")
                alerts.append(
                    f"⚠️ <b>{store['name']}</b> se {streak} baar lagataar price nahi mila "
                    f"({result['error']}).{(' ' + note) if note else ''}"
                )
            continue

        state["fail_streak"][store["id"]] = 0
        old = previous.get(store["id"])
        print(f"   listed ₹{rupees(result['listed'])} → effective ₹{rupees(result['effective'])}")

        # History me tabhi likho jab price badla ho ya aaj ki pehli entry ho
        today = now.date().isoformat()
        same_price = old and old.get("listed") == result["listed"]
        logged_today = old and old["ts"][:10] == today
        if not (same_price and logged_today):
            entries.append({
                "ts": now.isoformat(timespec="minutes"),
                "store": store["id"],
                "name": store["name"],
                "listed": result["listed"],
                "effective": result["effective"],
                "offer": result["offer"],
            })
            changed = True

        # --- Alert rules ---
        key_target = f"target:{store['id']}"
        key_drop = f"drop:{store['id']}"

        def cooled(key: str) -> bool:
            stamp = state["last_alert"].get(key)
            if not stamp:
                return True
            try:
                last = datetime.fromisoformat(stamp)
            except ValueError:
                return True
            return (now - last) > timedelta(hours=ALERT_COOLDOWN_HOURS)

        if result["effective"] <= TARGET_PRICE and cooled(key_target):
            alerts.append(
                f"🎯 <b>TARGET HIT — {store['name']}</b>\n"
                f"Effective <b>₹{rupees(result['effective'])}</b> "
                f"(listed ₹{rupees(result['listed'])}, {result['offer']})\n"
                f"<a href=\"{store['url']}\">Kharidne jao →</a>"
            )
            state["last_alert"][key_target] = now.isoformat()

        if old and old.get("listed"):
            delta = old["listed"] - result["listed"]
            pct = delta / old["listed"] * 100
            if pct >= DROP_PCT and cooled(key_drop):
                alerts.append(
                    f"📉 <b>{store['name']} pe ₹{rupees(delta)} gira</b> ({pct:.1f}%)\n"
                    f"₹{rupees(old['listed'])} → ₹{rupees(result['listed'])}\n"
                    f"Bank offer ke baad: <b>₹{rupees(result['effective'])}</b>\n"
                    f"<a href=\"{store['url']}\">Dekho →</a>"
                )
                state["last_alert"][key_drop] = now.isoformat()

        if all_time_low is not None and result["effective"] < all_time_low and cooled("atl"):
            alerts.append(
                f"🏆 <b>Naya all-time low — {store['name']}</b>\n"
                f"₹{rupees(result['effective'])} "
                f"(purana low ₹{rupees(all_time_low)})\n"
                f"<a href=\"{store['url']}\">Dekho →</a>"
            )
            state["last_alert"]["atl"] = now.isoformat()
            all_time_low = result["effective"]

    # --- Save ---
    history["entries"] = entries[-4000:]
    history["updated_at"] = now.isoformat(timespec="minutes")
    live = [r for r in results if r["effective"]]
    if live:
        best = min(live, key=lambda r: r["effective"])
        history["best"] = {
            "store": best["name"],
            "url": best["url"],
            "listed": best["listed"],
            "effective": best["effective"],
            "offer": best["offer"],
        }
    save_json(HISTORY_FILE, history)
    save_json(STATE_FILE, state)
    print(f"[save] history entries: {len(entries)} (naya data: {changed})")

    # --- Alerts bhejo ---
    if alerts and not args.dry_run:
        header = "<b>iPad 11 · Wi-Fi · 128GB</b>\n\n"
        footer = f"\n\n<i>{now.strftime('%d %b %Y, %I:%M %p IST')}</i>"
        send_telegram(header + "\n\n".join(alerts) + footer)
    elif alerts:
        print("[dry-run] alerts:\n" + "\n\n".join(alerts))
    else:
        print("[alerts] kuch naya nahi")

    return 0


if __name__ == "__main__":
    sys.exit(main())
