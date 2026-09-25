#!/usr/bin/env python3
"""
Surveille la dispo en retrait à l'Apple Store Cap 3000 (R395)
pour l'iPhone 18 Pro Max Bordeaux, et envoie une notif ntfy sur ton téléphone.

Usage :
    python3 stock_iphone_cap3000.py            # boucle locale toutes les 2 min
    python3 stock_iphone_cap3000.py --once     # un seul check (mode GitHub Actions)

Le topic ntfy est lu dans la variable d'environnement NTFY_TOPIC
(secret GitHub), sinon dans la constante ci-dessous.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

# --- Config ---------------------------------------------------------------
PARTS = {
    "MJXQ4F/A": "Pro Max 256 Go Bordeaux",
    "MJXV4F/A": "Pro Max 512 Go Bordeaux",
    # "MJY04F/A": "Pro Max 1 To Bordeaux",
}
STORE = "R395"            # Apple Cap 3000
LOCATION = "06700"        # Saint-Laurent-du-Var
INTERVAL_SEC = 120        # mode local uniquement
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")  # ex: "ali-iphone-cap3000-x7k2"
NTFY_EMAIL = os.environ.get("NTFY_EMAIL", "")  # optionnel : copie de la notif par email
STATE_FILE = "state.json" # mémorise ce qui a déjà été notifié entre deux runs
# -------------------------------------------------------------------------

URL = "https://www.apple.com/fr/shop/retail/pickup-message"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36",
    "Accept": "application/json",
}


def check():
    params = {f"parts.{i}": p for i, p in enumerate(PARTS)}
    params["location"] = LOCATION
    req = urllib.request.Request(f"{URL}?{urllib.parse.urlencode(params)}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    store = next((s for s in data["body"]["stores"] if s["storeNumber"] == STORE), None)
    if store is None:
        raise RuntimeError(f"Magasin {STORE} absent de la réponse")
    return {
        part: (info.get("pickupDisplay") == "available", info.get("pickupSearchQuote", ""))
        for part, info in store["partsAvailability"].items()
    }


def notify(msg):
    print("\a", end="")
    if not NTFY_TOPIC:
        print("  (NTFY_TOPIC vide : pas de push envoyé)")
        return
    headers = {
        "Title": "iPhone dispo a Cap 3000",
        "Priority": "urgent",
        "Click": "https://www.apple.com/fr/shop/buy-iphone/iphone-18-pro",
    }
    if NTFY_EMAIL:
        headers["Email"] = NTFY_EMAIL
    req = urllib.request.Request(f"https://ntfy.sh/{NTFY_TOPIC}", data=msg.encode(), headers=headers)
    urllib.request.urlopen(req, timeout=10)
    print(f"  📲 Notif envoyée (push{' + email' if NTFY_EMAIL else ''})")


def load_state():
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, ValueError):
        return set()


def save_state(notified):
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(notified), f)


def run_once(notified):
    now = datetime.now().strftime("%H:%M:%S")
    for part, (ok, quote) in check().items():
        name = PARTS.get(part, part)
        print(f"[{now}] {'✅' if ok else '❌'} {name} : {quote}")
        if ok and part not in notified:
            notify(f"{name} : {quote}. Réserve vite dans l'app Apple Store !")
            notified.add(part)
        elif not ok:
            notified.discard(part)  # re-notifier si ça revient


def main():
    notified = load_state()
    if "--once" in sys.argv:
        run_once(notified)          # une erreur fait échouer le run (visible sur GitHub)
        save_state(notified)
        return
    while True:
        try:
            run_once(notified)
        except Exception as e:
            print(f"⚠️ Erreur : {e}")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
