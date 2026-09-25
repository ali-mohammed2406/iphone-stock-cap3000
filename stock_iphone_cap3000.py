#!/usr/bin/env python3
"""
Surveille la dispo en retrait à l'Apple Store Cap 3000 (R395)
pour l'iPhone 18 Pro Max 256 Go Bordeaux.

Mode GitHub Actions (--once) : écrit available=true/false dans GITHUB_OUTPUT.
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
STORE = "R395"                         # Apple Cap 3000
LOCATION = "06700"
STATE_FILE = "state.json"              # évite de renvoyer un email toutes les 5 min

URL = "https://www.apple.com/fr/shop/retail/pickup-message"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36",
    "Accept": "application/json",
}


def check():
    params = {"parts.0": PART, "location": LOCATION}
    req = urllib.request.Request(f"{URL}?{urllib.parse.urlencode(params)}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    store = next((s for s in data["body"]["stores"] if s["storeNumber"] == STORE), None)
    if store is None:
        raise RuntimeError(f"Magasin {STORE} absent de la réponse Apple")
    info = store["partsAvailability"][PART]
    return info.get("pickupDisplay") == "available", info.get("pickupSearchQuote", "")


def load_state():
    try:
        with open(STATE_FILE) as f:
            return bool(json.load(f).get("notified", False))
    except (FileNotFoundError, ValueError, AttributeError):
        return False


def write_outputs(alert, quote, now):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"alert={'true' if alert else 'false'}\n")
            f.write(f"quote={quote}\n")
            f.write(f"checked_at={now}\n")


def save_state(notified):
    with open(STATE_FILE, "w") as f:
        json.dump({"notified": notified}, f)


def arg(name, default):
    return int(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    loop_min = arg("--loop", 0)            # 0 = un seul check
    interval = arg("--interval", 60)
    deadline = time.time() + loop_min * 60
    notified = load_state()
    errors, quote, now = 0, "", ""

    while True:
        now = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M:%S")
        try:
            ok, quote = check()
            errors = 0
            print(f"[{now}] {'✅' if ok else '❌'} {NAME} : {quote}", flush=True)
            if ok and not notified:
                save_state(True)
                write_outputs(True, quote, now)
                return                      # on sort tout de suite -> job alerte -> email
            notified = ok                   # si rupture, on ré-alertera au retour du stock
        except Exception as e:
            errors += 1
            print(f"[{now}] ⚠️ Erreur ({errors}/5) : {e}", flush=True)
            if errors >= 5:                 # vraie panne -> le job "vérif" échoue -> email
                save_state(notified)
                raise
        if time.time() + interval > deadline:
            break
        time.sleep(interval)

    save_state(notified)
    write_outputs(False, quote, now)


if __name__ == "__main__":
    main()
