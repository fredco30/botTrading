"""Boucle principale.

Deroulement a chaque tour, par paire :
  1. recuperer les bougies H1 closes
  2. calculer la decision avec le meme code que le backtest
  3. agir : ouvrir, fermer, ou remonter le stop

Le stop est suivi cote bot et execute au marche quand la barre close le
franchit. C'est plus lent qu'un ordre stop laisse sur le marche - le prix peut
avoir depasse le niveau dans l'heure - mais c'est robuste : aucun ordre orphelin
si le bot tombe, et pas de divergence entre l'etat local et le carnet.
"""

import logging
import time

from .broker import PaperBroker, make_broker
from .signal import decide, size_position
from .state import State

log = logging.getLogger(__name__)


class Bot:
    def __init__(self, cfg):
        self.cfg = cfg
        self.broker = make_broker(cfg)
        self.state = State(cfg.state_file)
        self.markets = self.broker.markets()

    def _market(self, symbol):
        return self.markets.get(symbol, {})

    def _pnl(self, pos, exit_price):
        return (exit_price - pos["entry"]) * pos["side"] * pos["units"]

    def close_position(self, symbol, pos, reason):
        side = "sell" if pos["side"] == 1 else "buy"
        px = self.broker.price(symbol)
        self.broker.create_market_order(symbol, side, abs(pos["units"]),
                                        reduce_only=True)
        pnl = self._pnl(pos, px)
        if isinstance(self.broker, PaperBroker):
            self.broker.settle(symbol, pnl)
        self.state.close(symbol, px, pnl)
        log.info("FERME %s a %.6g | %s | P&L %+.2f", symbol, px, reason, pnl)

    def open_position(self, symbol, dec, equity):
        px = self.broker.price(symbol)
        # Le niveau de cassure est deja franchi : on entre au prix courant, pas
        # au niveau theorique. L'ecart est le cout de ne pas laisser d'ordre
        # stop sur le marche, et il est comptabilise tel quel.
        units = size_position(equity, px, dec.stop, self.cfg, self._market(symbol))
        if units <= 0:
            log.info("%s : taille nulle apres arrondis, on passe", symbol)
            return
        side = "buy" if dec.side == 1 else "sell"
        self.broker.create_market_order(symbol, side, units)
        self.state.open(symbol, dec.side, units, px, dec.stop, dec.atr)
        log.info("OUVRE %s %s %.8f a %.6g | stop %.6g | %s",
                 side, symbol, units, px, dec.stop, dec.reason)

    def step(self):
        equity = self.broker.equity()
        dd, halted = self.state.check_drawdown(equity, self.cfg.max_drawdown_pct)
        if halted:
            log.error("ARRET : drawdown %.1f%% au-dela du plafond de %.1f%%. "
                      "Plus aucune ouverture ; les positions ouvertes sont "
                      "toujours gerees.", dd, self.cfg.max_drawdown_pct)

        for base in self.cfg.symbols:
            symbol = self.cfg.market(base)
            try:
                need = self.cfg.entry_period + self.cfg.atr_period + 5
                bars = self.broker.ohlcv(symbol, self.cfg.timeframe, need)
                pos = self.state.get(symbol)
                dec = decide(bars, self.cfg, pos)

                if dec.action == "close" and pos:
                    self.close_position(symbol, pos, dec.reason)
                elif dec.action == "trail" and pos:
                    self.state.update(symbol, stop=dec.stop,
                                      extreme=dec.level, atr=dec.atr)
                    log.info("%s : stop remonte a %.6g", symbol, dec.stop)
                elif dec.action == "open" and not pos:
                    if halted:
                        continue
                    if self.state.n_open >= self.cfg.max_concurrent:
                        log.info("%s : signal ignore, %d positions deja ouvertes",
                                 symbol, self.state.n_open)
                        continue
                    self.open_position(symbol, dec, equity)
            except Exception as exc:            # noqa: BLE001
                # Une paire en erreur ne doit pas empecher les autres d'etre
                # gerees : une position ouverte non surveillee est bien pire
                # qu'un signal manque.
                log.exception("%s : %s", symbol, exc)

        log.info("equity %.2f | drawdown %.1f%% | %d position(s)",
                 equity, dd, self.state.n_open)

    def run(self, once=False):
        log.info("demarrage | %s | %s | %s | risque %.2f%% | %d paires",
                 self.cfg.exchange, self.cfg.market_type, self.cfg.mode.upper(),
                 self.cfg.risk_pct, len(self.cfg.symbols))
        if self.cfg.mode == "live":
            log.warning("MODE LIVE : des ordres reels vont etre envoyes")
        while True:
            try:
                self.step()
            except KeyboardInterrupt:
                log.info("arret demande")
                return
            except Exception as exc:            # noqa: BLE001
                log.exception("erreur du cycle : %s", exc)
            if once:
                return
            time.sleep(self.cfg.poll_seconds)
