# iPad 11 price tracker

**Product:** iPad 11 (A16, 2025) · Wi-Fi · 128GB
**Aaj ka best effective price:** ~₹41,490 (Croma / Reliance Digital, Axis-ICICI-SBI 6-mo EMI pe ₹6,000 cashback)
**Target:** ₹40,000 — yahan pahunchte hi Telegram pe ping

---

## Setup — ek command

```bash
chmod +x setup.sh
./setup.sh
```

Script sab kuch khud kar degi: token verify, chat ID dhoondhna, local test, GitHub repo, secrets, Pages, aur pehla run. Aapko sirf token paste karna hai aur bot ko `/start` bhejna hai.

**Zaroori:** token type karte waqt screen pe kuch nahi dikhega. Ye galti nahi hai — password fields aise hi hote hain. Paste karke Enter dabao.

Pehle ye ready rakho:
- Telegram bot ka token — BotFather → `/newbot` (ya `/revoke` agar purana leak ho gaya ho)
- `gh auth login` ho chuka ho ([GitHub CLI](https://cli.github.com))

---

## Security — ye padh lo

Token = bot ka poora control. Jisko mil gaya, wo aapke naam pe kuch bhi bhej sakta hai.

**Kabhi mat karo**
- Chat, email ya kisi AI assistant ko token bhejna
- Screenshot lena jisme token dikh raha ho
- Kisi file me likhna jo git me jaayegi
- Command line argument me daalna: `gh secret set TOKEN --body "123:ABC"` ← shell history me chala jayega

**Ye karo**
- `./setup.sh` chalao — wo `read -rs` use karta hai, kuch dikhta nahi, kahin save nahi hota
- Ya manually: `gh secret set TELEGRAM_BOT_TOKEN` (interactively maangega)
- Local test ke liye: `cp .env.example .env.local`, wahan values daalo — `.env.local` gitignore me hai

Galti se kahin dikh jaye to turant BotFather → `/revoke`. Purana token us second dead ho jata hai. Sharam ki baat nahi, sabke saath hota hai — bas revoke karna yaad rahe.

Setup script commit se pehle do check karti hai: koi secret file stage to nahi hui, aur kisi file me token jaisa pattern to nahi hai. Kuch mila to wahin ruk jati hai.

---

## Kya-kya chal raha hai

| Layer | Kaam |
|---|---|
| **Bot** (`tracker.py` + Actions) | Har 4 ghante Croma / Reliance / Vijay Sales / Apple ka price, Telegram alert |
| **Dashboard** (`index.html`) | "Abhi lo ya ruko", rate ladder, history chart, bank calculator |
| **Backup trackers** | Amazon aur Flipkart ke liye — wo bots ko block karte hain |

Bot un stores ko dekhta hai jo scrape hone dete hain; ready-made trackers baaki do sambhalte hain. Isliye koi drop miss nahi hota.

Alert kab aata hai:
- 🎯 effective price **₹40,000 ya neeche**
- 📉 kisi store pe **3%+ girawat**
- 🏆 **naya all-time low**
- ⚠️ koi store lagataar 6 baar fail (layout badla ya block hua)

Same alert 12 ghante tak repeat nahi hoga.

---

## Backup trackers (5 min, ab bhi karna hai)

Amazon aur Flipkart datacenter IPs block karte hain — bot wahan fail hoga aur aapko bata dega. Unke liye:

| Kahan | Kya |
|---|---|
| **Pricehistory.app** | Amazon URL → ₹40,000 ka alert |
| **BuyHatke** | Flipkart ke liye sabse achha |
| **Keepa** | Amazon price history |
| **Smartprix** | Sab stores ek page pe |

Links dashboard ke "Backup trackers" section me hain.

---

## Sale week tuning

Big Billion Days (~23 Sept) aur Great Indian Festival (~2–7 Oct) me price kuch ghanton ke liye hi girta hai. Sale se ek din pehle `.github/workflows/track.yml` me:

```yaml
- cron: "0 */4 * * *"     # normal
- cron: "0 * * * *"       # sale week - har ghanta
```

Target badalna ho: usi file ke `env:` block me `TARGET_PRICE`.

---

## Settings

| Setting | Default | Matlab |
|---|---|---|
| `TARGET_PRICE` | `40000` | Is price pe "abhi kharido" alert |
| `DROP_PCT` | `3` | Itne % girne pe alert |

`tracker.py` ki `STORES` list me store add/hata sakte ho — `url`, `bank_offer`, `offer_label` bharo. 256GB track karna ho to sirf URLs badlo.

---

## Kuch gadbad ho to

**Telegram pe kuch nahi aaya** → bot ko `/start` bheja tha? `python3 tracker.py --test` chalao, wo token aur chat ID dono alag-alag check karke exact problem batata hai.

**Kisi store ka price nahi mil raha** → site ne layout badla. Us store ki `patterns` list me naya regex add karo. Sanity check (₹15k–₹95k) lagi hai, isliye galat number kabhi history me nahi jayega.

**Actions 60 din baad ruk gaya** → GitHub inactive repos me schedules band kar deta hai. Ek manual run se chalu ho jata hai.

**Dashboard purana data dikha raha** → hard refresh (Ctrl/Cmd + Shift + R).

---

## Yaad rakhna

- ₹6,000 cashback **6-month EMI transaction** pe milta hai eligible Axis/ICICI/SBI credit card se — simple swipe pe nahi. Schemes badalti rehti hain, checkout pe confirm karna.
- Bank offers **pincode aur card BIN specific** hote hain — Delhi pincode se verify karo.
- ₹34,900 wali listings **purani** hain. June 2026 hike ke baad MRP ₹49,900 hai.
- Sale dates (23 Sept, 2–7 Oct) **expected** hain, officially confirm nahi hui.
