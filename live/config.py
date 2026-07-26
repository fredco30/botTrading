"""Configuration du bot live.

Les cles API ne sont JAMAIS dans ce fichier ni dans le JSON de config : elles
sont lues depuis l'environnement. Un fichier de config peut finir dans un depot
git, une variable d'environnement beaucoup moins facilement.
"""

import json
import os
from dataclasses import asdict, dataclass, field, replace


@dataclass
class Config:
    # --- place ---
    exchange: str = "bitvavo"        # identifiant ccxt
    market_type: str = "swap"        # "swap" (perp, long+short) ou "spot" (long seul)
    quote: str = "USDT"
    symbols: tuple = ("BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "LTC", "LINK")

    # --- strategie : identique au backtest valide, ne pas diverger ---
    timeframe: str = "1h"
    entry_period: int = 1440         # canal Donchian d'entree, en barres H1
    exit_period: int = 480           # canal de sortie
    atr_period: int = 14
    atr_stop_mult: float = 3.0
    atr_trail_mult: float = 6.0

    # --- risque ---
    # Calibre sur un drawdown FLOTTANT de 30% : c'est ce que le compte affiche,
    # donc le seul chiffre qui compte pour tenir la position. A ce plafond, ce
    # reglage donne x12-13 sur 2021-2026 (la pire fenetre de 5 ans du jeu de
    # donnees), soit 1 000 EUR -> environ 13 000 EUR.
    risk_pct: float = 1.0            # % de l'equity par trade
    # 4 plutot que 3 : +18% de resultat pour +0.9 point de DD, et surtout 26% des
    # signaux etaient refuses par le plafond dans le simple ordre d'arrivee.
    max_concurrent: int = 4          # positions simultanees, toutes paires
    # Le notionnel median d'une position vaut 29% du capital (85% au 99e
    # centile) : 4 positions ouvertes font 1.17x, 8 feraient 2.34x et seraient
    # rognees en silence par ce plafond. C'est ce qui interdit d'augmenter
    # max_concurrent sans y toucher.
    max_leverage: float = 2.0
    allow_long: bool = True
    allow_short: bool = True         # force a False si market_type == "spot"

    # --- garde-fous ---
    # Un disjoncteur, pas un outil de gestion du risque - c'est le sizing a 1%
    # qui joue ce role. Il doit attraper une panne (flux corrompu, boucle
    # d'ordres), donc se declencher nettement au-dessus du pire DD attendu.
    # A 30% de DD flottant attendu, un plafond a 30% couperait en plein
    # fonctionnement normal, au creux, juste avant la reprise qui paie.
    max_drawdown_pct: float = 45.0   # au-dela, le bot arrete d'ouvrir
    max_position_notional_pct: float = 100.0   # notionnel max par position
    min_order_value: float = 10.0    # sous ce montant, on n'envoie pas d'ordre

    # --- exploitation ---
    # "paper"  : donnees reelles, execution simulee
    # "dryrun" : place reelle en LECTURE, aucun ordre possible (verif plomberie)
    # "live"   : ordres reels
    mode: str = "paper"
    poll_seconds: int = 300
    state_file: str = "live_state.json"
    log_file: str = "live_bot.log"
    initial_equity: float = 1000.0   # utilise en paper uniquement

    def __post_init__(self):
        if self.mode not in ("paper", "dryrun", "live"):
            raise ValueError(
                f"mode inconnu : {self.mode!r} (attendu paper, dryrun ou live)")
        if self.market_type == "spot" and self.allow_short:
            # Vendre a decouvert est impossible en spot. Mesure : cela coute
            # environ 60% du resultat, mais mieux vaut le savoir que decouvrir
            # des rejets d'ordres en production.
            object.__setattr__(self, "allow_short", False)

    @property
    def api_key(self):
        return os.environ.get(f"{self.exchange.upper()}_API_KEY", "")

    @property
    def api_secret(self):
        return os.environ.get(f"{self.exchange.upper()}_API_SECRET", "")

    def market(self, base):
        """Symbole ccxt unifie : BTC/USDT pour le spot, BTC/USDT:USDT pour un perp."""
        pair = f"{base}/{self.quote}"
        return f"{pair}:{self.quote}" if self.market_type == "swap" else pair

    @classmethod
    def load(cls, path=None, **overrides):
        data = {}
        if path and os.path.exists(path):
            with open(path) as fh:
                data = json.load(fh)
        data.update({k: v for k, v in overrides.items() if v is not None})
        if "symbols" in data:
            data["symbols"] = tuple(data["symbols"])
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"cles de config inconnues : {sorted(unknown)}")
        return cls(**data)

    def save(self, path):
        with open(path, "w") as fh:
            json.dump(asdict(self), fh, indent=2)
