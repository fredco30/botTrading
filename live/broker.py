"""Couche d'acces au marche : ccxt en live, simulation en paper.

Les deux implementations exposent la meme interface, donc `bot.py` ne sait pas
laquelle il utilise. C'est ce qui permet de faire tourner exactement le meme
code de decision en paper pendant des semaines avant de basculer.
"""

import logging
import time

import numpy as np

log = logging.getLogger(__name__)


class BrokerError(RuntimeError):
    pass


class CcxtBroker:
    """Acces reel au marche via ccxt."""

    def __init__(self, cfg):
        import ccxt
        if cfg.exchange not in ccxt.exchanges:
            raise BrokerError(f"place inconnue de ccxt : {cfg.exchange}")
        klass = getattr(ccxt, cfg.exchange)
        opts = {"enableRateLimit": True,
                "options": {"defaultType": cfg.market_type}}
        if cfg.api_key:
            opts.update(apiKey=cfg.api_key, secret=cfg.api_secret)
        self.ex = klass(opts)
        self.cfg = cfg
        self._markets = None

    def markets(self):
        if self._markets is None:
            self._markets = self.ex.load_markets()
        return self._markets

    def ohlcv(self, symbol, timeframe, limit):
        """Bougies closes, les plus anciennes en premier.

        ccxt renvoie la bougie en cours en derniere position ; on la retire pour
        ne jamais decider sur une barre incomplete - c'est la source d'ecart la
        plus courante entre un backtest et un bot.
        """
        rows = []
        remaining = limit + 1
        end = None
        while remaining > 0:
            batch = self.ex.fetch_ohlcv(symbol, timeframe,
                                        limit=min(1000, remaining), since=None,
                                        params={"until": end} if end else {})
            if not batch:
                break
            rows = batch + rows
            remaining -= len(batch)
            if len(batch) < 2:
                break
            end = batch[0][0] - 1
            time.sleep(self.ex.rateLimit / 1000.0)
        arr = np.array(rows, dtype=np.float64)
        if arr.size == 0:
            raise BrokerError(f"aucune bougie pour {symbol}")
        arr = arr[np.argsort(arr[:, 0])]
        _, keep = np.unique(arr[:, 0], return_index=True)
        arr = arr[np.sort(keep)]
        return arr[:-1]     # la derniere barre est encore ouverte

    def equity(self):
        bal = self.ex.fetch_balance()
        total = bal.get("total", {}).get(self.cfg.quote)
        if total is None:
            raise BrokerError(f"solde {self.cfg.quote} introuvable")
        return float(total)

    def position(self, symbol):
        if self.cfg.market_type != "swap":
            base = symbol.split("/")[0]
            bal = self.ex.fetch_balance().get("total", {})
            return float(bal.get(base, 0.0))
        for p in self.ex.fetch_positions([symbol]):
            amt = float(p.get("contracts") or 0.0)
            if amt:
                return amt if p.get("side") == "long" else -amt
        return 0.0

    def price(self, symbol):
        return float(self.ex.fetch_ticker(symbol)["last"])

    def create_market_order(self, symbol, side, amount, reduce_only=False):
        params = {"reduceOnly": True} if reduce_only and self.cfg.market_type == "swap" else {}
        log.info("ORDRE %s %s %.8f %s", side, symbol, amount,
                 "(reduce-only)" if reduce_only else "")
        return self.ex.create_order(symbol, "market", side, amount, None, params)

    def cancel_all(self, symbol):
        try:
            for o in self.ex.fetch_open_orders(symbol):
                self.ex.cancel_order(o["id"], symbol)
        except Exception as exc:               # noqa: BLE001
            log.warning("annulation impossible sur %s : %s", symbol, exc)


class PaperBroker:
    """Simulation : vraies bougies, execution fictive.

    Les prix viennent de la place reelle, seuls les ordres sont simules. C'est
    la seule facon d'avoir un paper trading dont les ecarts avec le live
    proviennent de l'execution et non des donnees.
    """

    def __init__(self, cfg, live_source=None):
        self.cfg = cfg
        self.src = live_source or CcxtBroker(cfg)
        self._equity = cfg.initial_equity
        self._pos = {}

    def markets(self):
        return self.src.markets()

    def ohlcv(self, symbol, timeframe, limit):
        return self.src.ohlcv(symbol, timeframe, limit)

    def price(self, symbol):
        return self.src.price(symbol)

    def equity(self):
        return self._equity

    def position(self, symbol):
        return self._pos.get(symbol, 0.0)

    def create_market_order(self, symbol, side, amount, reduce_only=False):
        px = self.price(symbol)
        signed = amount if side == "buy" else -amount
        prev = self._pos.get(symbol, 0.0)
        self._pos[symbol] = prev + signed
        log.info("[PAPER] %s %s %.8f @ %.6f", side, symbol, amount, px)
        return {"id": f"paper-{time.time():.0f}", "price": px,
                "amount": amount, "side": side}

    def settle(self, symbol, pnl):
        """Applique le P&L d'une position fermee a l'equity simulee."""
        self._equity += pnl
        self._pos[symbol] = 0.0

    def cancel_all(self, symbol):
        pass


def make_broker(cfg):
    if cfg.mode == "live":
        if not cfg.api_key:
            raise BrokerError(
                f"mode live demande mais {cfg.exchange.upper()}_API_KEY est vide")
        return CcxtBroker(cfg)
    return PaperBroker(cfg)
