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
import signal
import time

from .broker import PaperBroker, make_broker
from .notify import Notifier
from .signal import decide, size_position
from .state import State

log = logging.getLogger(__name__)


class Bot:
    def __init__(self, cfg, broker=None):
        self.cfg = cfg
        # `broker` injectable : le dry-run et les tests reutilisent une instance
        # deja construite plutot que d'en ouvrir une seconde vers la place.
        self.broker = broker if broker is not None else make_broker(cfg)
        self.state = State(cfg.state_file)
        self.markets = self.broker.markets()
        self._stopping = False
        self.notify = Notifier(
            throttle_file=cfg.state_file + ".alerts",
            enabled=cfg.alerts)
        if cfg.alerts and not self.notify.enabled:
            log.info("alertes Telegram inactives : %s", self.notify.why_disabled())

    def _install_signal_handlers(self):
        """Arret propre sur SIGTERM.

        systemd envoie SIGTERM a chaque `stop` et a chaque `restart`. Sans
        handler, Python meurt sur-le-champ : potentiellement entre l'envoi d'un
        ordre et l'ecriture de l'etat, ce qui laisse une position ouverte que le
        fichier d'etat ignore - donc un stop que plus personne ne surveille.

        Ici le signal ne fait que lever un drapeau ; le cycle en cours se
        termine et l'etat est ecrit avant la sortie.
        """
        def handler(signum, _frame):
            log.info("signal %s recu, arret apres le cycle en cours",
                     signal.Signals(signum).name)
            self._stopping = True

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, handler)
            except ValueError:
                pass    # pas dans le thread principal (tests)

    def _market(self, symbol):
        return self.markets.get(symbol, {})

    def _pnl(self, pos, exit_price):
        return (exit_price - pos["entry"]) * pos["side"] * pos["units"]

    def close_position(self, symbol, pos, reason, bar_ts=None):
        side = "sell" if pos["side"] == 1 else "buy"
        px = self.broker.price(symbol)
        self.broker.create_market_order(symbol, side, abs(pos["units"]),
                                        reduce_only=True)
        pnl = self._pnl(pos, px)
        if isinstance(self.broker, PaperBroker):
            self.broker.settle(symbol, pnl)
        self.state.close(symbol, px, pnl, bar_ts=bar_ts)
        log.info("FERME %s a %.6g | %s | P&L %+.2f", symbol, px, reason, pnl)
        if self.cfg.alert_on_trades:
            self.notify.closed(symbol, pos["side"], px, pnl, reason,
                               equity=self.broker.equity())

    def open_position(self, symbol, dec, equity, bar_ts=None):
        px = self.broker.price(symbol)
        # Le stop est recalcule depuis le prix REELLEMENT paye, pas depuis le
        # niveau theorique du canal. Le backtest entre au niveau via un ordre
        # stop ; ici on entre au marche apres coup, et le prix a bouge. Garder
        # le stop derive du niveau donnerait un risque different de 3 ATR, et
        # si le prix a reflue au-dela du niveau il le placerait carrement du
        # mauvais cote de l'entree - un long avec un stop au-dessus.
        stop = px - dec.side * self.cfg.atr_stop_mult * dec.atr
        if (px - stop) * dec.side <= 0:
            log.error("%s : stop du mauvais cote (entree %.6g, stop %.6g), "
                      "trade abandonne", symbol, px, stop)
            return
        units = size_position(equity, px, stop, self.cfg, self._market(symbol))
        if units <= 0:
            log.info("%s : taille nulle apres arrondis, on passe", symbol)
            return
        side = "buy" if dec.side == 1 else "sell"
        self.broker.create_market_order(symbol, side, units)
        self.state.open(symbol, dec.side, units, px, stop, dec.atr,
                        bar_ts=bar_ts)
        log.info("OUVRE %s %s %.8f a %.6g | stop %.6g (%.2f ATR) | %s",
                 side, symbol, units, px, stop,
                 abs(px - stop) / dec.atr if dec.atr else 0, dec.reason)
        if self.cfg.alert_on_trades:
            self.notify.opened(symbol, dec.side, units, px, stop, dec.atr,
                               dec.reason)

    def step(self):
        equity = self.broker.equity()
        dd, halted = self.state.check_drawdown(equity, self.cfg.max_drawdown_pct)
        if halted:
            log.error("ARRET : drawdown %.1f%% au-dela du plafond de %.1f%%. "
                      "Plus aucune ouverture ; les positions ouvertes sont "
                      "toujours gerees.", dd, self.cfg.max_drawdown_pct)
            self.notify.halted(dd, self.cfg.max_drawdown_pct)
        else:
            self.notify.drawdown(dd, self.cfg.max_drawdown_pct)

        for base in self.cfg.symbols:
            symbol = self.cfg.market(base)
            try:
                need = self.cfg.entry_period + self.cfg.atr_period + 5
                bars = self.broker.ohlcv(symbol, self.cfg.timeframe, need)
                pos = self.state.get(symbol)
                dec = decide(bars, self.cfg, pos)
                bar_ts = int(bars[-1, 0] // 1000)   # barre close qui a decide

                # Dernier prix vu, conserve dans l'etat pour que le suivi puisse
                # afficher le P&L latent sans redemander la place.
                if pos:
                    self.state.update(symbol, last_price=float(bars[-1, 4]),
                                      last_ts=bar_ts)

                if dec.action == "close" and pos:
                    self.close_position(symbol, pos, dec.reason, bar_ts)
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
                    self.open_position(symbol, dec, equity, bar_ts)
            except Exception as exc:            # noqa: BLE001
                # Une paire en erreur ne doit pas empecher les autres d'etre
                # gerees : une position ouverte non surveillee est bien pire
                # qu'un signal manque.
                log.exception("%s : %s", symbol, exc)
                self.notify.pair_error(symbol, exc)

        self.state.record_equity(equity)
        self.state.save()
        log.info("equity %.2f | drawdown %.1f%% | %d position(s)",
                 equity, dd, self.state.n_open)

    def run(self, once=False):
        self._install_signal_handlers()
        log.info("demarrage | %s | %s | %s | risque %.2f%% | %d paires",
                 self.cfg.exchange, self.cfg.market_type, self.cfg.mode.upper(),
                 self.cfg.risk_pct, len(self.cfg.symbols))
        if self.cfg.mode == "live":
            log.warning("MODE LIVE : des ordres reels vont etre envoyes")
        if self.state.n_open:
            log.info("reprise avec %d position(s) en cours : %s",
                     self.state.n_open, ", ".join(self.state.data["positions"]))
        if not once:
            # Pas d'alerte de demarrage sur --once : ce mode sert aux
            # verifications manuelles, il en enverrait une a chaque essai.
            self.notify.started(self.cfg)
            # Le watchdog a pu signaler une panne ; c'est ici, et seulement ici,
            # qu'on sait que le bot est reparti.
            down = self.state.downtime()
            if down:
                self.notify.recovered(down)
        while not self._stopping:
            try:
                self.step()
            except Exception as exc:            # noqa: BLE001
                log.exception("erreur du cycle : %s", exc)
            if once:
                break
            # Sommeil fractionne pour reagir a SIGTERM en une seconde au lieu
            # d'attendre la fin du cycle de poll.
            for _ in range(self.cfg.poll_seconds):
                if self._stopping:
                    break
                time.sleep(1)
        self.state.save()
        log.info("arrete proprement | %d position(s) conservee(s) dans %s",
                 self.state.n_open, self.cfg.state_file)
        if not once:
            self.notify.stopped(
                f"arret propre · {self.state.n_open} position(s) conservee(s)")
