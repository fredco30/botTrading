#!/usr/bin/env python3
"""Rejoue de vraies bougies a travers Bot.step() et compare au backtest.

Les tests precedents utilisaient un marche synthetique. Ils ont trouve deux bugs
reels - un stop place du mauvais cote, un SIGTERM qui tuait le bot en plein
cycle - mais ils ne prouvent pas que le portage trade la meme strategie que
celle qui a ete validee.

Ce test-la le prouve : memes bougies, memes parametres, deux chemins de code
completement differents (boucle numba du backtest contre boucle live avec etat
persistant et broker), et on compare.

Ce qui DOIT correspondre :
  - le nombre de trades
  - la barre de declenchement de chaque entree
  - le sens de chaque trade

Ce qui NE PEUT PAS correspondre, et c'est mesure plutot que masque :
  - les prix. Le backtest entre au niveau du canal via un ordre stop et sort au
    niveau du stop ; le bot detecte le franchissement sur la barre close puis
    passe au marche. Le bot est donc toujours en retard, jamais en avance.

L'ecart de P&L qui en resulte est le cout reel du portage. Le connaitre chiffre
evite de decouvrir en live que le bot rend la moitie de ce que le backtest
promettait.

    python3 tests/test_integration_replay.py
    python3 tests/test_integration_replay.py --symbol ETHUSD --bars 20000
"""

import argparse
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import instruments as I, trend                      # noqa: E402
from live.bot import Bot                                        # noqa: E402
from live.config import Config                                  # noqa: E402
from live.notify import Notifier                                # noqa: E402
from live.state import State                                    # noqa: E402
import live.broker as B                                         # noqa: E402


class ReplaySource:
    """Sert les bougies historiques jusqu'a un curseur deplacable."""

    def __init__(self, bars, symbol):
        self.bars = bars
        self.symbol = symbol
        self.i = 0

    def markets(self):
        return {self.symbol: {"precision": {"amount": 8},
                              "limits": {"amount": {"min": 1e-8}}}}

    def ohlcv(self, symbol, timeframe, limit):
        # Comme le vrai broker : uniquement des barres closes, fenetre glissante.
        lo = max(0, self.i - limit)
        return self.bars[lo:self.i]

    def price(self, symbol):
        # Le bot passe au marche apres la cloture : le close de la derniere
        # barre close est l'approximation la plus honnete du prix obtenu.
        return float(self.bars[self.i - 1, 4])

    def equity(self):
        return 0.0

    def position(self, symbol):
        return 0.0

    def create_market_order(self, *a, **k):
        return {}

    def cancel_all(self, symbol):
        pass


def replay(symbol, cfg, bars):
    src = ReplaySource(bars, cfg.market(symbol.replace("USD", "")))
    state_file = tempfile.mktemp(suffix=".json")
    bot = Bot.__new__(Bot)
    bot.cfg = cfg
    bot._stopping = False
    bot.broker = B.PaperBroker(cfg, live_source=src)
    bot.state = State(state_file)
    bot.markets = bot.broker.markets()
    # Alertes neutralisees : le rejeu declenche des centaines de trades, et ce
    # test mesure la fidelite du signal, pas la notification.
    bot.notify = Notifier(token="", chat_id="", enabled=False)

    warm = cfg.entry_period + cfg.atr_period + 5
    for i in range(warm, len(bars)):
        src.i = i
        bot.step()

    trades = list(bot.state.data["history"])
    os.unlink(state_file)
    return trades


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="BTCUSD")
    ap.add_argument("--bars", type=int, default=25000,
                    help="nombre de barres H1 rejouees (0 = tout)")
    args = ap.parse_args(argv)

    cfg = Config(symbols=(args.symbol.replace("USD", ""),),
                 entry_period=1440, exit_period=480, atr_period=14,
                 atr_stop_mult=3.0, atr_trail_mult=6.0,
                 risk_pct=0.5, max_concurrent=1, initial_equity=10000.0,
                 max_drawdown_pct=100.0)

    series = I.load_h1(args.symbol, entry_period=cfg.entry_period,
                       exit_period=cfg.exit_period, atr_period=cfg.atr_period)
    bars = np.column_stack([series["ts"] * 1000, series["o"], series["h"],
                            series["l"], series["c"],
                            np.ones(series["ts"].size)])
    if args.bars:
        bars = bars[-args.bars:]

    print("=" * 74)
    print(f"REJEU D'INTEGRATION  {args.symbol}  {len(bars)} barres H1")
    print(f"canal {cfg.entry_period}/{cfg.exit_period}  stop {cfg.atr_stop_mult} ATR"
          f"  trailing {cfg.atr_trail_mult} ATR")
    print("=" * 74)

    live_trades = replay(args.symbol, cfg, bars)

    # Backtest sur exactement les memes barres.
    sub = {k: (v[-len(bars):] if isinstance(v, np.ndarray) and v.size >= len(bars)
               else v) for k, v in series.items()}
    bt = I.run(sub, risk_pct=cfg.risk_pct, atr_stop_mult=cfg.atr_stop_mult,
               atr_trail_mult=cfg.atr_trail_mult, initial_equity=cfg.initial_equity)

    ts = sub["ts"]
    # Le rejeu ne peut pas decider avant d'avoir assez de barres pour calculer
    # le canal et l'ATR. Comparer le backtest depuis la barre 0 lui donnerait
    # des trades que le bot n'avait aucun moyen de voir : ce serait un faux
    # echec, pas une divergence de strategie.
    # La boucle de rejeu demarre a l'indice `warm` et sert les barres [.. warm),
    # donc la premiere barre sur laquelle le bot decide est `warm - 1`.
    warm = cfg.entry_period + cfg.atr_period + 5
    warm_ts = int(ts[min(warm - 1, len(ts) - 1)])
    print(f"\npremiere decision du bot : {np.datetime64(warm_ts, 's')}")

    # A ce premier reveil, le canal peut deja etre franchi depuis des heures :
    # le bot ouvre alors une position que le backtest avait prise plus tot. Ce
    # trade de rattrapage n'est pas une divergence de strategie, c'est un
    # artefact de demarrage - les deux cotes sont donc coupes au meme instant.
    live_trades = [lv for lv in live_trades
                   if lv.get("bar_ts") is not None and lv["bar_ts"] > warm_ts]

    bt_rows = [{"entry_ts": int(ts[int(r[trend.R_ENTRY_IDX])]),
                "exit_ts": int(ts[int(r[trend.R_EXIT_IDX])]),
                "side": int(r[trend.R_DIR]),
                "entry": r[trend.R_ENTRY], "exit": r[trend.R_EXIT],
                "pnl": r[trend.R_PNL]} for r in bt
               if int(ts[int(r[trend.R_ENTRY_IDX])]) >= warm_ts]

    print(f"\ntrades backtest : {len(bt_rows)}")
    print(f"trades bot      : {len(live_trades)}")

    # Appariement sur la date d'entree, tolerance de six barres H1. Le bot agit
    # a la cloture, le backtest au moment du franchissement, et un ecart de prix
    # d'entree modifie le stop, donc la date de sortie, donc la date a laquelle
    # le suivant peut s'ouvrir. Sur SOL un signal identique - meme sens, meme
    # sortie - est arrive trois heures plus tard : une tolerance de deux heures
    # l'aurait compte comme un trade fantome.
    tol = 6 * 3600
    matched, only_bt = [], []
    used = set()
    for b in bt_rows:
        # Appariement au PLUS PROCHE, pas au premier trouve. Avec une fenetre
        # large, prendre le premier candidat laisse un trade voisin consommer la
        # place du bon, et le vrai correspondant ressort ensuite comme fantome.
        cands = [(abs(lv["bar_ts"] - b["entry_ts"]), j)
                 for j, lv in enumerate(live_trades)
                 if j not in used and lv["side"] == b["side"]
                 and lv.get("bar_ts") is not None
                 and abs(lv["bar_ts"] - b["entry_ts"]) <= tol]
        if not cands:
            only_bt.append(b)
            continue
        _, j = min(cands)
        used.add(j)
        matched.append((b, live_trades[j]))

    only_live = [lv for j, lv in enumerate(live_trades) if j not in used]

    # Un trade du backtest sans equivalent direct n'est pas forcement manque :
    # si le bot detenait une position du meme sens couvrant cette periode, c'est
    # que son stop legerement different ne l'a pas sorti et qu'il a traverse ce
    # que le backtest a decoupe en deux. Meme exposition, un trade au lieu de
    # deux. C'est une consequence attendue de l'entree au marche, pas une
    # divergence de strategie - et il faut le distinguer d'un signal rate.
    # Symetrique de l'absorption : un trade du bot sans equivalent peut etre un
    # decoupage. Le bot s'est fait sortir la ou le backtest a tenu, puis il est
    # rentre a nouveau - meme exposition, deux trades au lieu d'un. A distinguer
    # d'un signal invente, qui lui serait une vraie divergence.
    splits, phantom = [], []
    for lv in only_live:
        inside = [b for b in bt_rows
                  if b["side"] == lv["side"]
                  and b["entry_ts"] <= lv["bar_ts"] <= b["exit_ts"]]
        (splits if inside else phantom).append(lv)

    absorbed, missed = [], []
    for b in only_bt:
        cover = [lv for lv in live_trades
                 if lv["side"] == b["side"]
                 and lv.get("bar_ts") is not None
                 and lv.get("exit_bar_ts") is not None
                 and lv["bar_ts"] <= b["entry_ts"] <= lv["exit_bar_ts"]]
        (absorbed if cover else missed).append(b)

    total = max(len(bt_rows), 1)
    print(f"\napparies        : {len(matched)}/{len(bt_rows)} "
          f"({len(matched)/total*100:.0f}%)")
    print(f"backtest seul   : {len(only_bt)}"
          f"  (dont {len(absorbed)} absorbe(s) dans une position du bot)")
    print(f"bot seul        : {len(only_live)}"
          f"  (dont {len(splits)} decoupage(s) d'un trade du backtest)")
    if missed:
        print(f"SIGNAUX RATES   : {len(missed)}   <- divergence reelle")
        for m in missed:
            print(f"    {np.datetime64(m['entry_ts'], 's')} sens {m['side']:+d}")
    if phantom:
        print(f"SIGNAUX INVENTES: {len(phantom)}   <- divergence reelle")
        for p in phantom:
            print(f"    {np.datetime64(p['bar_ts'], 's')} sens {p['side']:+d}")

    if matched:
        d_entry = np.array([(lv["entry"] - b["entry"]) / b["entry"] * 1e4
                            for b, lv in matched])
        bt_pnl = sum(b["pnl"] for b, _ in matched)
        lv_pnl = sum(lv["pnl"] for _, lv in matched)
        same_side = all(b["side"] == lv["side"] for b, lv in matched)
        print(f"\nsens identique  : {'OUI' if same_side else 'NON'}")
        print(f"ecart d'entree  : median {np.median(d_entry):+.0f} bps   "
              f"moyen {d_entry.mean():+.0f} bps")
        print(f"P&L backtest    : {bt_pnl:>12,.0f}")
        print(f"P&L bot         : {lv_pnl:>12,.0f}   ({(lv_pnl/bt_pnl-1)*100:+.0f}%)")
        print("   L'ecart vient de l'execution en retard. Sur quelques dizaines")
        print("   de trades il est domine par le bruit et peut tomber des deux")
        print("   cotes ; ne pas le lire comme un avantage du bot.")

    # Le portage doit reproduire chaque signal, pas 90 % d'entre eux. Un seuil
    # laxiste laisserait passer une vraie divergence.
    # Criteres : aucun signal invente par le bot, aucun signal reellement rate,
    # et le meme sens partout. Les absorptions sont tolerees et comptees.
    ok = (not phantom and not missed
          and all(b["side"] == lv["side"] for b, lv in matched))
    print("\n" + ("REUSSITE : le bot declenche les memes trades que le backtest"
                  if ok else
                  "ECHEC : le bot ne suit pas la strategie validee"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
