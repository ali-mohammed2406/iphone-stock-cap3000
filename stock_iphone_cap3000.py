#!/usr/bin/env python3
"""
Surveille la dispo en retrait à l'Apple Store Cap 3000 (R395)
pour l'iPhone 18 Pro Max 256 Go Bordeaux.

Mode GitHub Actions (--once) : écrit available=true/false dans GITHUB_OUTPUT.
Le workflow déclenche alors un job "alerte" qui échoue volontairement :
GitHub t'envoie un email, rien à installer.

Usage local : python3 stock_iphone_cap3000.py --once
"""
import json
import os
import sys
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


def main():
    now = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M")
    already = load_state()
    ok, quote = check()
    print(f"[{now}] {'✅' if ok else '❌'} {NAME} : {quote}")

    alert = ok and not already
    with open(STATE_FILE, "w") as f:
        json.dump({"notified": ok}, f)   # si rupture, on ré-alertera au retour du stock

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"alert={'true' if alert else 'false'}\n")
            f.write(f"quote={quote}\n")
            f.write(f"checked_at={now}\n")


if __name__ == "__main__":
    main()
