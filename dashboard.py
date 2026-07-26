#!/usr/bin/env python3
"""Suivi du bot dans un navigateur.

Lit `live_state.json` et `live_bot.log` - rien d'autre. Aucun appel a la place,
aucune ecriture : ce serveur ne peut pas influencer le bot, il ne fait que le
regarder. C'est deliberé, un tableau de bord qui peut passer des ordres est une
surface d'attaque pour zero benefice.

Bibliotheque standard uniquement : pas de Flask, pas de npm. Le bot tourne sur
un Raspberry Pi ou un petit VPS, et l'interet d'un tableau de bord disparait
s'il pese plus que ce qu'il surveille.

    python3 dashboard.py                 # http://127.0.0.1:8000
    python3 dashboard.py --port 8080
    python3 dashboard.py --state /var/lib/donchian-bot/live_state.json

Par defaut il n'ecoute QUE sur 127.0.0.1 : il n'y a pas d'authentification, donc
il ne doit jamais etre expose. Pour le consulter depuis un VPS, passer par un
tunnel SSH plutot que par --host :

    ssh -L 8000:localhost:8000 user@vps
"""

import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


def read_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {"_error": f"{path} introuvable - le bot n'a pas encore tourne"}
    except json.JSONDecodeError as exc:
        return {"_error": f"JSON illisible : {exc}"}


def tail(path, n=120):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            block = min(size, 64 * 1024)
            fh.seek(size - block)
            lines = fh.read().decode("utf-8", "replace").splitlines()
        return lines[-n:]
    except FileNotFoundError:
        return []


def build_payload(cfg_path, state_path, log_path):
    state = read_json(state_path)
    cfg = read_json(cfg_path) if os.path.exists(cfg_path) else {}

    positions = state.get("positions", {}) or {}
    history = state.get("history", []) or []
    curve = state.get("equity_curve", []) or []

    # P&L latent : le bot enregistre le dernier prix vu a chaque cycle, donc le
    # tableau de bord n'a pas besoin d'interroger la place.
    open_rows = []
    unrealized = 0.0
    for sym, p in positions.items():
        last = p.get("last_price")
        side = p.get("side", 0)
        units = p.get("units", 0.0)
        entry = p.get("entry", 0.0)
        stop = p.get("stop", 0.0)
        stop0 = p.get("stop0", stop)
        pnl = ((last - entry) * side * units) if last else None
        risk0 = abs(entry - stop0) * units if stop0 else 0.0
        open_rows.append(dict(
            symbol=sym, side=side, units=units, entry=entry, stop=stop,
            stop0=stop0, last=last, atr=p.get("atr"), opened=p.get("opened"),
            bar_ts=p.get("bar_ts"), last_ts=p.get("last_ts"), pnl=pnl,
            r=(pnl / risk0) if (pnl is not None and risk0 > 0) else None,
            # Distance au stop en % : a quel point la position est menacee.
            to_stop=((last - stop) * side / last * 100.0) if last else None,
        ))
        if pnl:
            unrealized += pnl

    realized = sum(h.get("pnl", 0.0) for h in history)
    wins = [h for h in history if h.get("pnl", 0.0) > 0]
    equity = curve[-1][1] if curve else None
    peak = state.get("peak_equity", 0.0)
    dd = ((peak - equity) / peak * 100.0) if (equity and peak) else 0.0

    return dict(
        updated=state.get("updated"),
        error=state.get("_error"),
        halted=bool(state.get("halted")),
        equity=equity, peak=peak, dd=dd,
        max_dd_pct=cfg.get("max_drawdown_pct"),
        realized=realized, unrealized=unrealized,
        n_open=len(open_rows), n_closed=len(history),
        win_rate=(len(wins) / len(history) * 100.0) if history else None,
        positions=open_rows,
        history=history[-100:][::-1],
        curve=curve,
        config={k: cfg.get(k) for k in
                ("exchange", "market_type", "mode", "risk_pct", "max_concurrent",
                 "max_drawdown_pct", "entry_period", "exit_period",
                 "atr_stop_mult", "atr_trail_mult", "symbols")},
        log=tail(log_path),
        server_time=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


class Handler(BaseHTTPRequestHandler):
    paths = {}

    def _send(self, code, body, ctype):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            payload = build_payload(self.paths["config"], self.paths["state"],
                                    self.paths["log"])
            self._send(200, json.dumps(payload), "application/json")
        elif self.path == "/favicon.ico":
            self.send_response(204)     # evite un 404 dans la console
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "dashboard.html")) as fh:
                self._send(200, fh.read(), "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

    def log_message(self, *a):
        pass        # le journal du bot suffit ; celui-ci ne ferait que du bruit


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="live_state.json")
    ap.add_argument("--log", default="live_bot.log")
    ap.add_argument("--config", default="live_config.json")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1",
                    help="127.0.0.1 par defaut ; il n'y a AUCUNE authentification, "
                         "utiliser un tunnel SSH plutot que d'ouvrir sur le reseau")
    args = ap.parse_args(argv)

    Handler.paths = {"state": args.state, "log": args.log, "config": args.config}
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"  suivi sur http://{args.host}:{args.port}")
    print(f"  etat   : {args.state}")
    print(f"  journal: {args.log}")
    if args.host not in ("127.0.0.1", "localhost"):
        print("\n  ATTENTION : ecoute hors de localhost et sans authentification.")
        print("  Preferer   ssh -L 8000:localhost:8000 user@vps")
    print("  Ctrl-C pour arreter")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  arret")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
