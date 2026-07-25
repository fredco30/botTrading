"""Etat persistant du bot.

Ecrit a chaque changement, relu au demarrage. Un bot de tendance garde ses
positions plusieurs jours : sans persistance, un simple redemarrage lui fait
oublier ses stops et ses extremes de trailing, et il repartirait a zero sur une
position deja ouverte.

L'ecriture passe par un fichier temporaire puis un renommage atomique, pour
qu'une coupure en plein ecrit ne laisse pas un JSON tronque.
"""

import json
import os
import tempfile
import time


class State:
    def __init__(self, path):
        self.path = path
        self.data = {"positions": {}, "peak_equity": 0.0, "halted": False,
                     "history": [], "updated": None}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path) as fh:
                self.data.update(json.load(fh))
        return self

    def save(self):
        self.data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        d = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # --- positions ---
    def get(self, symbol):
        return self.data["positions"].get(symbol)

    def open(self, symbol, side, units, entry, stop, atr):
        self.data["positions"][symbol] = {
            "side": side, "units": units, "entry": entry, "stop": stop,
            "stop0": stop, "extreme": entry, "atr": atr,
            "opened": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.save()

    def update(self, symbol, **kw):
        if symbol in self.data["positions"]:
            self.data["positions"][symbol].update(kw)
            self.save()

    def close(self, symbol, exit_price, pnl):
        pos = self.data["positions"].pop(symbol, None)
        if pos:
            self.data["history"].append(
                {**pos, "symbol": symbol, "exit": exit_price, "pnl": pnl,
                 "closed": time.strftime("%Y-%m-%d %H:%M:%S")})
            self.data["history"] = self.data["history"][-500:]
        self.save()
        return pos

    @property
    def n_open(self):
        return len(self.data["positions"])

    # --- garde-fou de drawdown ---
    def check_drawdown(self, equity, max_dd_pct):
        peak = max(self.data.get("peak_equity", 0.0), equity)
        self.data["peak_equity"] = peak
        dd = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
        if dd > max_dd_pct:
            self.data["halted"] = True
        self.save()
        return dd, self.data["halted"]
