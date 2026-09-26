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
OUTAGE_MIN = 45                        # email de panne si Apple ne répond plus depuis 45 min

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
            n = ["R395"]
        notified = set(n) if isinstance(n, list) else set()
        return notified, float(d.get("fail_since") or 0), bool(d.get("outage_notified"))
    except (FileNotFoundError, ValueError, AttributeError, TypeError):
        return set(), 0.0, False


def save_state(notified, fail_since, outage_notified):
    with open(STATE_FILE, "w") as f:
        json.dump({"notified": sorted(notified), "fail_since": fail_since,
                   "outage_notified": outage_notified}, f)


def write_outputs(new, now, outage=False):
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    stores = " et ".join(STORES[s][0] for s, _ in new)
    quote = " / ".join(f"{STORES[s][0]} : {q}" for s, q in new)
    with open(out, "a") as f:
        f.write(f"alert={'true' if new else 'false'}\n")
        f.write(f"outage={'true' if outage else 'false'}\n")
        f.write(f"stores={stores}\n")
        f.write(f"quote={quote}\n")
        f.write(f"checked_at={now}\n")


def arg(name, default):
    return int(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    loop_min = arg("--loop", 0)            # 0 = un seul passage
    interval = arg("--interval", 60)       # 1 requête Apple par intervalle, magasins en alternance
    deadline = time.time() + loop_min * 60
    notified, fail_since, outage_notified = load_state()
    store_ids = list(STORES)
    i, backoff, now = 0, 0, ""

    while True:
        now = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M:%S")
        sid = store_ids[i % len(store_ids)]
        label, loc = STORES[sid]
        i += 1
        try:
            ok, quote = check_store(sid, loc)
            backoff, fail_since, outage_notified = 0, 0.0, False
            print(f"[{now}] {'✅' if ok else '❌'} {label} - {NAME} : {quote}", flush=True)
            if ok and sid not in notified:
                notified.add(sid)
                save_state(notified, fail_since, outage_notified)
                write_outputs([(sid, quote)], now)
                return                      # sortie immédiate -> job alerte -> email
            if not ok:
                notified.discard(sid)      # ré-alerter si le stock revient
        except Exception as e:
            # Apple limite parfois les requêtes (HTTP 541) : on ralentit au lieu d'insister.
            fail_since = fail_since or time.time()
            backoff = min(max(backoff * 2, 120), 600)
            down_min = int((time.time() - fail_since) / 60)
            print(f"[{now}] ⚠️ {label} : {e} -> pause {backoff // 60} min "
                  f"(erreurs depuis {down_min} min)", flush=True)
            if down_min >= OUTAGE_MIN and not outage_notified:
                outage_notified = True
                save_state(notified, fail_since, outage_notified)
                write_outputs([], now, outage=True)
                return                      # un seul email de panne, puis on continue au run suivant
        wait = interval + backoff
        if time.time() + wait > deadline:
            break
        time.sleep(wait)

    save_state(notified, fail_since, outage_notified)
    write_outputs([], now)


if __name__ == "__main__":
    main()
