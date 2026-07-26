#!/usr/bin/env python3
"""Le dry-run peut-il envoyer un ordre ? La reponse doit rester non.

C'est la seule propriete de ce mode qui compte vraiment. Elle est verifiee en
remplacant ccxt par un faux exchange qui LEVE UNE EXCEPTION si une methode
d'ecriture est appelee - donc un test qui echoue bruyamment plutot qu'un test
qui verifie poliment un compteur a zero.

    python3 tests/test_dryrun.py
"""

import os
import sys
import tempfile
import types

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class OrderAttempted(AssertionError):
    """Levee si le code tente d'ecrire sur la place."""


class FakeExchange:
    """Exchange minimal : lectures servies, ecritures interdites."""

    timeframes = {"1h": "1h", "15m": "15m"}
    rateLimit = 1

    def __init__(self, opts=None):
        self.opts = opts or {}
        self.reads = 0

    # --- lectures ---
    def load_markets(self):
        self.reads += 1
        return {f"{b}/USDT:USDT": {
            "symbol": f"{b}/USDT:USDT",
            "precision": {"amount": 6},
            "limits": {"amount": {"min": 1e-6}, "cost": {"min": 1.0}},
        } for b in ("BTC", "ETH")}

    def fetch_ohlcv(self, symbol, timeframe, limit=None, since=None, params=None):
        self.reads += 1
        n = min(limit or 1000, 1000)
        # Les bougies doivent finir MAINTENANT : le preflight verifie la
        # fraicheur, et une serie figee dans le passe le ferait echouer a juste
        # titre. La derniere barre est la barre en cours, que le broker retire.
        import time as _t
        last = int(_t.time() // 3600) * 3600 * 1000
        # Tendance haussiere franche : garantit une cassure, donc une tentative
        # d'ordre. Un marche plat testerait le chemin ou rien ne se passe.
        out = []
        for i in range(n):
            px = 100.0 + i * 0.5
            ts = last - (n - 1 - i) * 3600000
            out.append([ts, px, px * 1.01, px * 0.99, px, 1.0])
        return out

    def fetch_ticker(self, symbol):
        self.reads += 1
        return {"last": 1000.0}

    def fetch_balance(self):
        self.reads += 1
        return {"total": {"USDT": 1000.0}}

    def fetch_positions(self, symbols=None):
        self.reads += 1
        return []

    def fetch_open_orders(self, symbol):
        self.reads += 1
        return []

    # --- ecritures : toutes interdites ---
    def create_order(self, *a, **k):
        raise OrderAttempted(f"create_order appele : {a} {k}")

    def cancel_order(self, *a, **k):
        raise OrderAttempted(f"cancel_order appele : {a} {k}")


def install_fake_ccxt():
    fake = types.ModuleType("ccxt")
    fake.exchanges = ["fakeex"]
    fake.fakeex = FakeExchange
    sys.modules["ccxt"] = fake
    return fake


def main():
    install_fake_ccxt()
    from live.broker import DryRunBroker
    from live.bot import Bot
    from live.config import Config
    from live import preflight

    state_file = tempfile.mktemp(suffix=".json")
    cfg = Config(exchange="fakeex", market_type="swap", quote="USDT",
                 symbols=("BTC", "ETH"), entry_period=200, exit_period=80,
                 atr_period=14, risk_pct=1.0, max_concurrent=4,
                 initial_equity=1000.0, mode="dryrun", state_file=state_file)

    print("=" * 70)
    print("DRY-RUN : UN ORDRE PEUT-IL PARTIR ?")
    print("=" * 70)

    broker = DryRunBroker(cfg)

    # 1. l'appel direct ne doit pas atteindre l'exchange
    broker.create_market_order("BTC/USDT:USDT", "buy", 0.01)
    broker.cancel_all("BTC/USDT:USDT")
    assert len(broker.would_send) == 1, broker.would_send
    print("\n  [OK] create_market_order enregistre l'intention sans l'envoyer")
    print("  [OK] cancel_all n'atteint pas la place")

    # 2. le preflight complet ne doit rien ecrire
    checks = preflight.run_checks(cfg, broker)
    preflight.report(checks)
    for c in checks:
        assert c.ok or not c.fatal, f"verification bloquante : {c.name} {c.detail}"
    print("  [OK] preflight complet, aucune ecriture")

    # 3. un cycle de decision complet sur une tendance qui casse : le bot DOIT
    #    vouloir ouvrir, et ne DOIT PAS y arriver.
    broker.would_send.clear()
    bot = Bot(cfg, broker=broker)
    bot.step()
    assert broker.would_send, ("le marche de test monte franchement : le bot "
                               "aurait du vouloir ouvrir, donc ce test ne prouve "
                               "rien en l'etat")
    print(f"  [OK] cycle complet : {len(broker.would_send)} ordre(s) voulu(s), "
          f"0 envoye(s)")
    for o in broker.would_send:
        print(f"        {o['side']} {o['symbol']} {o['amount']:.8g} @ {o['price']:.6g}")

    # 4. le mode live, lui, doit bien passer par create_order - sinon le test
    #    ci-dessus ne prouverait que l'absence de chemin, pas son blocage.
    from live.broker import CcxtBroker
    live_cfg = Config(exchange="fakeex", market_type="swap", quote="USDT",
                      symbols=("BTC",), mode="paper", state_file=state_file)
    real = CcxtBroker(live_cfg)
    try:
        real.create_market_order("BTC/USDT:USDT", "buy", 0.01)
    except OrderAttempted:
        print("  [OK] temoin : le broker normal, lui, atteint bien create_order")
    else:
        raise AssertionError("le temoin n'a pas atteint create_order : le test "
                             "du dry-run ne prouve rien")

    os.path.exists(state_file) and os.unlink(state_file)
    print("\nREUSSITE : aucun chemin du mode dry-run n'atteint la place en ecriture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
