#!/usr/bin/env python3
"""
Surveille la dispo en retrait de l'iPhone 18 Pro Max 256 Go Bordeaux
dans plusieurs Apple Store (Cap 3000, Opéra).

Mode GitHub Actions : écrit alert/stores/quote dans GITHUB_OUTPUT.
Le workflow déclenche alors un job "alerte" qui échoue volontairement :
GitHub t'envoie un email, rien à installer.

Usage :
    python3 stock_iphone_cap3000.py --once
    python3 stock_iphone_cap3000.py --loop 55 --interval 60   # boucle 55 min, check/60 s
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

PART = "MJXQ4F/A"                      # iPhone 18 Pro Max 256 Go Bordeaux
NAME = "iPhone 18 Pro Max 256 Go Bordeaux"
STORES = {                             # numéro Apple -> (nom affiché, code postal proche)
    "R395": ("Cap 3000", "06700"),
    "R277": ("Opéra", "75009"),
}
STATE_FILE = "state.json"              # magasins déjà notifiés (évite le spam)

URL = "https://www.apple.com/fr/shop/retail/pickup-message"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36",
    "Accept": "application/json",
}


def check_store(store_id, location):
    params = {"parts.0": PART, "location": location}
    req = urllib.request.Request(f"{URL}?{urllib.parse.urlencode(params)}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    store = next((s for s in data["body"]["stores"] if s["storeNumber"] == store_id), None)
    if store is None:
        raise RuntimeError(f"Magasin {store_id} absent de la réponse Apple")
    info = store["partsAvailability"][PART]
    return info.get("pickupDisplay") == "available", info.get("pickupSearchQuote", "")


def load_state():
    try:
        with open(STATE_FILE) as f:
            d = json.load(f)
        n = d.get("notified", [])
        if n is True:                  # ancien format (Cap 3000 seul)
            return {"R395"}
        return set(n) if isinstance(n, list) else set()
    except (FileNotFoundError, ValueError, AttributeError):
        return set()


def save_state(notified):
    with open(STATE_FILE, "w") as f:
        json.dump({"notified": sorted(notified)}, f)


def write_outputs(new, now):
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    stores = " et ".join(STORES[s][0] for s, _ in new)
    quote = " / ".join(f"{STORES[s][0]} : {q}" for s, q in new)
    with open(out, "a") as f:
        f.write(f"alert={'true' if new else 'false'}\n")
        f.write(f"stores={stores}\n")
        f.write(f"quote={quote}\n")
        f.write(f"checked_at={now}\n")


def arg(name, default):
    return int(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    loop_min = arg("--loop", 0)            # 0 = un seul passage
    interval = arg("--interval", 60)
    deadline = time.time() + loop_min * 60
    notified = load_state()
    errors = {s: 0 for s in STORES}
    now = ""

    while True:
        now = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M:%S")
        new = []
        for sid, (label, loc) in STORES.items():
            try:
                ok, quote = check_store(sid, loc)
                errors[sid] = 0
                print(f"[{now}] {'✅' if ok else '❌'} {label} - {NAME} : {quote}", flush=True)
                if ok and sid not in notified:
                    new.append((sid, quote))
                    notified.add(sid)
                elif not ok:
                    notified.discard(sid)  # ré-alerter si le stock revient
            except Exception as e:
                errors[sid] += 1
                print(f"[{now}] ⚠️ Erreur {label} ({errors[sid]}/5) : {e}", flush=True)
                if errors[sid] >= 5:       # vraie panne -> job "vérif" en échec -> email
                    save_state(notified)
                    raise
        if new:
            save_state(notified)
            write_outputs(new, now)
            return                          # sortie immédiate -> job alerte -> email
        if time.time() + interval > deadline:
            break
        time.sleep(interval)

    save_state(notified)
    write_outputs([], now)


if __name__ == "__main__":
    main()
