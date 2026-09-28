#!/usr/bin/env python3
"""
Surveille la dispo en retrait de l'iPhone 18 Pro Max 256 Go Bordeaux
à Cap 3000 et dans les Apple Store de Paris / Île-de-France.

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
# Une requête Apple par zone renvoie tous les magasins proches : on en surveille plusieurs
# sans ajouter de requêtes. Zones interrogées en alternance (1 requête / intervalle).
ZONES = {
    "06700": {"R395": "Cap 3000"},
    "75009": {                         # Paris et Île-de-France (pour ta sœur)
        "R277": "Opéra", "R675": "Champs-Élysées", "R566": "Marché Saint-Germain",
        "R178": "Les Quatre Temps", "R536": "Rosny 2", "R315": "Vélizy 2",
        "R374": "Parly 2", "R425": "Val d'Europe", "R438": "Carré Sénart",
    },
}
STORES = {sid: name for z in ZONES.values() for sid, name in z.items()}
STATE_FILE = "state.json"              # magasins déjà notifiés (évite le spam)
OUTAGE_MIN = 45                        # email de panne si Apple ne répond plus depuis 45 min

URL = "https://www.apple.com/fr/shop/retail/pickup-message"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36",
    "Accept": "application/json",
}


def check_zone(location):
    """Retourne {store_id: (dispo, message)} pour les magasins surveillés de la zone."""
    params = {"parts.0": PART, "location": location}
    req = urllib.request.Request(f"{URL}?{urllib.parse.urlencode(params)}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    res = {}
    for s in data["body"]["stores"]:
        if s["storeNumber"] in ZONES[location]:
            info = s["partsAvailability"][PART]
            res[s["storeNumber"]] = (info.get("pickupDisplay") == "available",
                                     info.get("pickupSearchQuote", ""))
    if not res:
        raise RuntimeError(f"Aucun magasin surveillé dans la réponse ({location})")
    return res


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
    stores = ", ".join(STORES[s] for s, _ in new)
    quote = " / ".join(f"{STORES[s]} : {q}" for s, q in new)
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
    zones = list(ZONES)
    i, backoff, now = 0, 0, ""

    while True:
        now = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M:%S")
        loc = zones[i % len(zones)]
        label = "Paris" if loc == "75009" else "Cap 3000"
        i += 1
        try:
            res = check_zone(loc)
            backoff, fail_since, outage_notified = 0, 0.0, False
            dispo = [STORES[sid] for sid, (ok, _) in res.items() if ok]
            print(f"[{now}] {'✅' if dispo else '❌'} {label} ({len(res)} magasins) - {NAME} : "
                  f"{', '.join(dispo) if dispo else 'aucun dispo'}", flush=True)
            new = []
            for sid, (ok, quote) in res.items():
                if ok and sid not in notified:
                    notified.add(sid)
                    new.append((sid, quote))
                elif not ok:
                    notified.discard(sid)  # ré-alerter si le stock revient
            if new:
                save_state(notified, fail_since, outage_notified)
                write_outputs(new, now)
                return                      # sortie immédiate -> job alerte -> email
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
                return
        wait = interval + backoff
        if time.time() + wait > deadline:
            break
        time.sleep(wait)

    save_state(notified, fail_since, outage_notified)
    write_outputs([], now)


if __name__ == "__main__":
    main()
