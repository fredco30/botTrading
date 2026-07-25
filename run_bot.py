#!/usr/bin/env python3
"""Point d'entree du bot Donchian multi-paires sur ccxt.

Par defaut : PAPER. Le mode live exige --live ET des cles dans l'environnement,
les deux, volontairement.

    python3 run_bot.py --once                      # un cycle en paper
    python3 run_bot.py                             # boucle en paper
    python3 run_bot.py --config live_config.json
    python3 run_bot.py --live                      # ordres reels
"""

import argparse
import logging
import sys

from live.bot import Bot
from live.config import Config


def setup_logging(path, verbose):
    fmt = "%(asctime)s %(levelname)-7s %(message)s"
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format=fmt, handlers=[logging.StreamHandler(sys.stdout),
                                              logging.FileHandler(path)])
    logging.getLogger("ccxt").setLevel(logging.WARNING)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="live_config.json")
    ap.add_argument("--exchange", default=None)
    ap.add_argument("--market-type", default=None, choices=["spot", "swap"])
    ap.add_argument("--risk-pct", type=float, default=None)
    ap.add_argument("--symbols", default=None, help="ex: BTC,ETH,SOL")
    ap.add_argument("--once", action="store_true", help="un seul cycle puis sortie")
    ap.add_argument("--live", action="store_true",
                    help="envoyer de vrais ordres au lieu de simuler")
    ap.add_argument("--yes", action="store_true", help="ne pas demander confirmation")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    cfg = Config.load(
        args.config,
        exchange=args.exchange,
        market_type=args.market_type,
        risk_pct=args.risk_pct,
        symbols=tuple(s.strip().upper() for s in args.symbols.split(",")) if args.symbols else None,
        mode="live" if args.live else None,
    )

    setup_logging(cfg.log_file, args.verbose)

    if cfg.mode == "live" and not args.yes:
        print(f"\n  MODE LIVE : {cfg.exchange} / {cfg.market_type}")
        print(f"  {len(cfg.symbols)} paires, {cfg.risk_pct}% de risque par trade")
        print(f"  short {'autorise' if cfg.allow_short else 'desactive'}, "
              f"arret automatique a {cfg.max_drawdown_pct}% de drawdown")
        if input("\n  Des ordres reels vont etre envoyes. Taper LIVE pour confirmer : ") != "LIVE":
            print("  annule")
            return 1

    Bot(cfg).run(once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
