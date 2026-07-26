"""Verifications avant mise en service : la plomberie repond-elle vraiment ?

La strategie est verifiee (`tests/test_integration_replay.py` rejoue de vraies
bougies a travers `Bot.step()`). Ce qui ne l'est pas, c'est tout ce qui se passe
entre le bot et la place : le symbole existe-t-il sous le nom qu'on lui donne,
la place rend-elle assez de bougies, la taille calculee passe-t-elle les
minimums, les cles ouvrent-elles le solde.

Chaque verification touche la VRAIE place, en lecture seule. Aucune n'envoie
d'ordre - c'est le `DryRunBroker` qui le garantit, pas ce fichier.
"""

import time
from dataclasses import dataclass

import numpy as np

from engine.channels import wilder_atr
from .signal import size_position


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fatal: bool = True      # False = avertissement, le bot peut tourner quand meme


def _suggest(markets, base, quote):
    """Noms de marches plausibles pour une base donnee, pour un message utile."""
    hits = [m for m in markets if m.startswith(f"{base}/")]
    hits.sort(key=lambda m: (quote not in m, len(m)))
    return hits[:4]


def run_checks(cfg, broker, log=None):
    out = []
    say = log.info if log else (lambda *a: None)

    # --- 1. la place repond et publie ses marches ---
    t0 = time.time()
    try:
        markets = broker.markets()
    except Exception as exc:                        # noqa: BLE001
        out.append(Check("marches", False, f"load_markets a echoue : {exc}"))
        return out
    out.append(Check("marches", True,
                     f"{len(markets)} marches charges en {time.time()-t0:.1f}s"))

    # --- 2. chaque symbole configure existe sous le nom qu'on lui donne ---
    # C'est l'echec le plus probable et le plus silencieux : `market_type`
    # "swap" fabrique "BTC/USDT:USDT", qui n'existe pas sur une place sans
    # perpetuels. Le bot planterait paire par paire sans dire pourquoi.
    resolved, missing = {}, []
    for base in cfg.symbols:
        sym = cfg.market(base)
        if sym in markets:
            resolved[base] = sym
        else:
            missing.append((base, sym, _suggest(markets, base, cfg.quote)))
    if missing:
        lines = [f"{s} introuvable" + (f" - essayer : {', '.join(alt)}" if alt
                                       else " - aucun marche pour cette base")
                 for _, s, alt in missing]
        out.append(Check("symboles", False,
                         f"{len(missing)}/{len(cfg.symbols)} manquants ; "
                         + " | ".join(lines)))
    else:
        out.append(Check("symboles", True,
                         f"{len(resolved)} symboles resolus ({cfg.market_type})"))
    if not resolved:
        return out

    # --- 3. l'unite de temps demandee est supportee ---
    tfs = getattr(getattr(broker, "ex", None), "timeframes", None) or {}
    if tfs and cfg.timeframe not in tfs:
        out.append(Check("timeframe", False,
                         f"{cfg.timeframe} non supporte ; disponibles : "
                         f"{', '.join(sorted(tfs)[:12])}"))
    else:
        out.append(Check("timeframe", True, cfg.timeframe))

    # --- 4. assez de bougies, correctement espacees, et fraiches ---
    need = cfg.entry_period + cfg.atr_period + 5
    bars_by_sym = {}
    problems, slowest = [], 0.0
    for base, sym in resolved.items():
        t1 = time.time()
        try:
            bars = broker.ohlcv(sym, cfg.timeframe, need)
        except Exception as exc:                    # noqa: BLE001
            problems.append(f"{base}: {exc}")
            continue
        slowest = max(slowest, time.time() - t1)
        bars_by_sym[base] = bars
        if len(bars) < need:
            problems.append(f"{base}: {len(bars)} bougies au lieu de {need}")
            continue
        step = np.diff(bars[-200:, 0]) / 1000.0
        if step.size and not np.allclose(step, 3600.0):
            problems.append(f"{base}: espacement irregulier "
                            f"({np.unique(step)[:3].tolist()} s)")
        age_h = (time.time() - bars[-1, 0] / 1000.0) / 3600.0
        if age_h > 3:
            problems.append(f"{base}: derniere bougie vieille de {age_h:.1f} h")
    if problems:
        out.append(Check("bougies", False, " | ".join(problems)))
    else:
        out.append(Check("bougies", True,
                         f"{need} bougies {cfg.timeframe} par paire, "
                         f"la plus lente en {slowest:.1f}s"))

    # --- 5. rythme d'un cycle complet ---
    # Un cycle doit tenir tres en dessous de poll_seconds, sinon les cycles se
    # chevauchent et le bot prend du retard sans jamais le signaler.
    est = slowest * len(resolved)
    out.append(Check("rythme", est < cfg.poll_seconds * 0.5,
                     f"~{est:.0f}s de reseau par cycle pour un intervalle de "
                     f"{cfg.poll_seconds}s",
                     fatal=False))

    # --- 6. le solde est lisible (necessite des cles) ---
    equity = None
    if cfg.api_key:
        try:
            equity = broker.equity()
            out.append(Check("solde", equity > 0,
                             f"{equity:.2f} {cfg.quote}"))
        except Exception as exc:                    # noqa: BLE001
            out.append(Check("solde", False, f"fetch_balance a echoue : {exc}"))
    else:
        out.append(Check("solde", True,
                         f"pas de cle API : solde non teste, dimensionnement "
                         f"simule sur {cfg.initial_equity:.0f} {cfg.quote}",
                         fatal=False))
    if equity is None:
        equity = cfg.initial_equity

    # --- 7. positions ouvertes lisibles ---
    if cfg.api_key:
        try:
            held = {b: broker.position(s) for b, s in resolved.items()}
            nz = {b: v for b, v in held.items() if v}
            out.append(Check("positions", True,
                             f"{len(nz)} position(s) deja ouverte(s)"
                             + (f" : {nz}" if nz else "")))
        except Exception as exc:                    # noqa: BLE001
            out.append(Check("positions", False, f"lecture impossible : {exc}"))

    # --- 8. les tailles calculees passent les minimums de la place ---
    # Un ordre sous le minimum est refuse par la place : le trade est perdu en
    # silence, et ce ne sont pas des trades au hasard - ce sont ceux au stop le
    # plus large, donc les plus volatils.
    too_small, sizes = [], []
    for base, bars in bars_by_sym.items():
        if len(bars) < cfg.atr_period + 2:
            continue
        atr = wilder_atr(bars[:, 2], bars[:, 3], bars[:, 4], cfg.atr_period)[-1]
        px = float(bars[-1, 4])
        if not np.isfinite(atr) or atr <= 0:
            continue
        stop = px - cfg.atr_stop_mult * atr
        mkt = markets[resolved[base]]
        units = size_position(equity, px, stop, cfg, mkt)
        notional = units * px
        sizes.append(notional)
        lim = (mkt.get("limits") or {})
        min_amt = ((lim.get("amount") or {}).get("min")) or 0.0
        min_cost = ((lim.get("cost") or {}).get("min")) or 0.0
        if units <= 0:
            too_small.append(f"{base}: taille nulle (notionnel < "
                             f"{cfg.min_order_value:g})")
        elif units < min_amt:
            too_small.append(f"{base}: {units:.8g} < minimum {min_amt:g}")
        elif notional < min_cost:
            too_small.append(f"{base}: {notional:.2f} {cfg.quote} < minimum "
                             f"{min_cost:g}")
    if too_small:
        out.append(Check("dimensionnement", False, " | ".join(too_small)))
    elif sizes:
        tot = float(np.median(sizes)) * cfg.max_concurrent
        out.append(Check("dimensionnement", True,
                         f"notionnel median {np.median(sizes):.2f} {cfg.quote} "
                         f"({np.median(sizes)/equity*100:.0f}% du capital), "
                         f"{cfg.max_concurrent} positions = {tot/equity:.2f}x"))
        if tot / equity > cfg.max_leverage:
            out.append(Check("levier", False,
                             f"{cfg.max_concurrent} positions font "
                             f"{tot/equity:.2f}x, au-dessus de max_leverage="
                             f"{cfg.max_leverage} : les tailles seraient rognees "
                             f"et le bot ne traderait plus la strategie mesuree"))

    return out


def report(checks, printer=print):
    """Affiche le bilan. Retourne True si rien de bloquant."""
    width = max(len(c.name) for c in checks) if checks else 12
    printer("")
    for c in checks:
        mark = "OK  " if c.ok else ("ECHEC" if c.fatal else "ATTN")
        printer(f"  [{mark:<5}] {c.name:<{width}}  {c.detail}")
    blocking = [c for c in checks if not c.ok and c.fatal]
    warned = [c for c in checks if not c.ok and not c.fatal]
    printer("")
    if blocking:
        printer(f"  {len(blocking)} probleme(s) bloquant(s) : le bot ne peut pas "
                f"tourner en l'etat.")
    elif warned:
        printer(f"  Aucun probleme bloquant, {len(warned)} avertissement(s).")
    else:
        printer("  Tout repond. La plomberie est operationnelle.")
    return not blocking
