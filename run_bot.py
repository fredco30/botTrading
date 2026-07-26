#!/usr/bin/env python3
"""Point d'entree du bot Donchian multi-paires sur ccxt.

Par defaut : PAPER. Le mode live exige --live ET des cles dans l'environnement,
les deux, volontairement.

    python3 run_bot.py --once                      # un cycle en paper
    python3 run_bot.py                             # boucle en paper
    python3 run_bot.py --dry-run-api               # vraie place, lecture seule
    python3 run_bot.py --config live_config.json
    python3 run_bot.py --live                      # ordres reels
"""

import argparse
import logging
import sys

from live.bot import Bot
from live.config import Config
from live import preflight


def setup_logging(path, verbose):
    fmt = "%(asctime)s %(levelname)-7s %(message)s"
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format=fmt, handlers=[logging.StreamHandler(sys.stdout),
                                              logging.FileHandler(path)])
    logging.getLogger("ccxt").setLevel(logging.WARNING)


def run_dry(cfg, args):
    """Verification de plomberie contre la vraie place, sans aucun ordre."""
    from live.broker import DryRunBroker

    print("=" * 74)
    print(f"DRY-RUN API   {cfg.exchange} / {cfg.market_type}   "
          f"{len(cfg.symbols)} paires")
    print("Lecture seule : aucun ordre ne peut partir, le broker n'en a pas le")
    print("chemin. Les cles ne sont pas requises - sans elles, seuls le solde et")
    print("les positions restent non testes.")
    print("=" * 74)

    broker = DryRunBroker(cfg)
    checks = preflight.run_checks(cfg, broker, log=logging.getLogger("preflight"))
    ok = preflight.report(checks)

    if not ok:
        print("  Cycle de decision non execute : corriger d'abord ce qui precede.")
        return 1

    # La plomberie repond : on fait tourner un vrai cycle de decision dessus.
    # C'est ce qui verifie le dernier maillon - que les bougies recues passent
    # bien dans `decide()` et produisent une taille executable.
    print("\n  Un cycle de decision sur donnees reelles :")
    bot = Bot(cfg, broker=broker)
    bot.step()

    if broker.would_send:
        print(f"\n  {len(broker.would_send)} ordre(s) AURAIENT ete envoyes :")
        for o in broker.would_send:
            print(f"    {o['side']:<4} {o['symbol']:<16} {o['amount']:.8g} "
                  f"@ {o['price']:.6g}   notionnel "
                  f"{o['amount']*o['price']:.2f} {cfg.quote}")
        print("  Aucun ne l'a ete.")
    else:
        print("    aucun signal sur ce cycle (le cas normal : le systeme prend")
        print("    quelques dizaines de trades par an et par paire)")
    return 0


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
    ap.add_argument("--dry-run-api", action="store_true",
                    help="interroger la vraie place en lecture seule : verifie la "
                         "plomberie (marches, bougies, cles, tailles) sans qu'aucun "
                         "ordre ne puisse partir")
    ap.add_argument("--yes", action="store_true", help="ne pas demander confirmation")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    if args.live and args.dry_run_api:
        print("  --live et --dry-run-api sont contradictoires")
        return 2

    mode = "live" if args.live else ("dryrun" if args.dry_run_api else None)
    cfg = Config.load(
        args.config,
        exchange=args.exchange,
        market_type=args.market_type,
        risk_pct=args.risk_pct,
        symbols=tuple(s.strip().upper() for s in args.symbols.split(",")) if args.symbols else None,
        mode=mode,
    )

    setup_logging(cfg.log_file, args.verbose)

    if cfg.mode == "dryrun":
        return run_dry(cfg, args)

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
