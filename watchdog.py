#!/usr/bin/env python3
"""Surveille que le bot tourne encore, et alerte s'il s'est tu.

**Un processus mort ne peut pas signaler sa propre mort.** C'est la raison
d'etre de ce fichier : il s'execute separement, ne partage rien avec le bot, et
se contente de regarder l'age du fichier d'etat. Si le bot est tue par l'OOM
killer, si le VPS redemarre, si Python plante sur une exception non rattrapee -
autant de cas ou aucune alerte ne partirait du bot lui-meme.

Il ne fait AUCUN appel a la place et n'ecrit rien dans l'etat du bot : il lit un
fichier et envoie un message. C'est tout, et c'est deliberé - un surveillant qui
peut casser ce qu'il surveille est pire que pas de surveillant.

A lancer periodiquement (timer systemd ou cron), pas en continu :

    */15 * * * * cd /opt/donchian && python3 watchdog.py --quiet

    python3 watchdog.py                 # verifie et affiche
    python3 watchdog.py --test          # envoie un message d'essai
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from live.notify import Notifier                    # noqa: E402


def load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except ValueError as exc:
        return {"_error": str(exc)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="live_state.json")
    ap.add_argument("--config", default="live_config.json")
    ap.add_argument("--cycles", type=float, default=3.0,
                    help="nombre de cycles manques avant alerte (defaut 3)")
    ap.add_argument("--test", action="store_true",
                    help="envoie un message d'essai et sort")
    ap.add_argument("--quiet", action="store_true",
                    help="silencieux sauf en cas de probleme (pour cron)")
    args = ap.parse_args(argv)

    say = (lambda *a: None) if args.quiet else print

    # Fichier de limitation distinct de celui du bot : les deux processus
    # ecrivent, et partager le fichier ferait perdre des alertes au dernier qui
    # ecrit. Celui du watchdog porte ses propres cles de toute facon.
    notif = Notifier(throttle_file=args.state + ".watchdog")
    if not notif.enabled:
        print(f"  alertes indisponibles : {notif.why_disabled()}", file=sys.stderr)
        return 2

    if args.test:
        ok = notif.send("🔔 <b>Test du watchdog</b>\nSi tu lis ceci, les alertes "
                        "fonctionnent.")
        print("  message envoye" if ok else "  ECHEC de l'envoi", file=sys.stderr)
        return 0 if ok else 1

    cfg = load(args.config) or {}
    poll = cfg.get("poll_seconds") or 300
    state = load(args.state)

    if state is None:
        say(f"  {args.state} introuvable — le bot n'a jamais tourne")
        notif.send(f"⚠️ <b>Fichier d'etat introuvable</b>\n<code>{args.state}</code>\n"
                   f"Le bot n'a jamais ecrit son etat.",
                   key="nostate", cooldown=21600)
        return 1

    if state.get("_error"):
        notif.send(f"⚠️ <b>Fichier d'etat illisible</b>\n"
                   f"<code>{state['_error']}</code>", key="badstate", cooldown=21600)
        return 1

    ts = state.get("updated_ts")
    if not ts:
        # Etat ecrit par une version anterieure : on retombe sur l'horodatage du
        # fichier, moins fiable mais suffisant pour detecter un arret.
        ts = os.path.getmtime(args.state)

    age = time.time() - ts
    n_open = len(state.get("positions") or {})
    limit = poll * args.cycles

    if age > limit:
        say(f"  ALERTE : dernier cycle il y a {age/3600:.1f} h "
            f"(limite {limit/3600:.1f} h), {n_open} position(s) ouverte(s)")
        sent = notif.stale(age, poll, n_open, os.path.abspath(args.state))
        say("  alerte envoyee" if sent else "  alerte non envoyee (deja signalee)")
        return 1

    say(f"  bot actif — dernier cycle il y a {age/60:.1f} min, "
        f"{n_open} position(s) ouverte(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
