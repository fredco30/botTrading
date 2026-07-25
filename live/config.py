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
    risk_pct: float = 0.5            # % de l'equity par trade
    max_concurrent: int = 3          # positions simultanees, toutes paires
    max_leverage: float = 2.0        # garde-fou ; le systeme en utilise ~0.13x
    allow_long: bool = True
    allow_short: bool = True         # force a False si market_type == "spot"

    # --- garde-fous ---
    max_drawdown_pct: float = 30.0   # au-dela, le bot arrete d'ouvrir
    max_position_notional_pct: float = 100.0   # notionnel max par position
    min_order_value: float = 10.0    # sous ce montant, on n'envoie pas d'ordre

    # --- exploitation ---
    mode: str = "paper"              # "paper" ou "live"
    poll_seconds: int = 300
    state_file: str = "live_state.json"
    log_file: str = "live_bot.log"
    initial_equity: float = 10000.0  # utilise en paper uniquement

    def __post_init__(self):
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
