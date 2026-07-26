"""Alertes Telegram.

Trois regles, dans cet ordre d'importance :

1. **Une panne d'alerte ne doit jamais arreter le bot.** Tout est attrape ici ;
   `send()` ne leve jamais. Perdre une notification est desagreable, perdre la
   gestion d'une position ouverte ne l'est pas.
2. **Le jeton n'est jamais dans un fichier de configuration**, seulement dans
   l'environnement - meme regle que les cles de la place. Un jeton Telegram
   permet d'usurper l'emetteur des alertes, donc de faire croire a un arret.
3. **Bibliotheque standard uniquement.** `urllib` suffit ; `requests` et
   `python-telegram-bot` ajouteraient des dizaines de megaoctets a un processus
   qui en fait 82 au total.

Limitation d'envoi : chaque alerte porte une cle et un delai de repos. Une paire
qui echoue a chaque cycle enverrait 288 messages par jour sans cela - au bout du
troisieme on ne les lit plus, et l'alerte utile passe inapercue.

    export TELEGRAM_BOT_TOKEN="123456:AA..."
    export TELEGRAM_CHAT_ID="987654321"
"""

import json
import logging
import os
import tempfile
import time
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT = 10.0

# Au-dela de cet enchainement d'echecs, on cesse d'essayer pendant un moment.
# Sans ce coupe-circuit, un DNS qui pend couterait TIMEOUT secondes par paire et
# par cycle, et le bot prendrait un retard qu'aucune alerte ne signalerait.
MAX_FAILS = 3
BACKOFF = 3600.0


def esc(v):
    return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class Notifier:
    def __init__(self, token=None, chat_id=None, throttle_file=None,
                 transport=None, enabled=True):
        self.token = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID", "")
        self.throttle_file = throttle_file
        self._transport = transport or self._post
        self._sent = self._load()
        self._fails = 0
        self._muted_until = 0.0
        self._user_enabled = enabled

    @property
    def enabled(self):
        return bool(self._user_enabled and self.token and self.chat_id)

    def why_disabled(self):
        if not self._user_enabled:
            return "desactivees dans la configuration (alerts=false)"
        if not self.token:
            return "TELEGRAM_BOT_TOKEN absent de l'environnement"
        if not self.chat_id:
            return "TELEGRAM_CHAT_ID absent de l'environnement"
        return ""

    # --- limitation d'envoi, persistee pour les processus courts ---
    def _load(self):
        if not self.throttle_file or not os.path.exists(self.throttle_file):
            return {}
        try:
            with open(self.throttle_file) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def _persist(self):
        if not self.throttle_file:
            return
        try:
            d = os.path.dirname(os.path.abspath(self.throttle_file))
            fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
            with os.fdopen(fd, "w") as fh:
                json.dump(self._sent, fh)
            os.replace(tmp, self.throttle_file)
        except OSError as exc:
            log.debug("etat de limitation non ecrit : %s", exc)

    # --- envoi ---
    def _post(self, text):
        data = urllib.parse.urlencode({
            "chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(API.format(token=self.token), data=data)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status == 200

    def send(self, text, key=None, cooldown=0.0):
        """Envoie une alerte. Ne leve jamais. Retourne True si partie."""
        if not self.enabled:
            return False
        now = time.time()
        if now < self._muted_until:
            return False
        if key and cooldown:
            last = self._sent.get(key, 0)
            if now - last < cooldown:
                return False
        try:
            ok = bool(self._transport(text))
        except Exception as exc:                    # noqa: BLE001
            # Volontairement large : une alerte ne doit jamais remonter dans la
            # boucle de trading, quelle que soit la panne (reseau, DNS, TLS,
            # reponse illisible).
            self._fails += 1
            log.warning("alerte Telegram non envoyee (%d/%d) : %s",
                        self._fails, MAX_FAILS, exc)
            if self._fails >= MAX_FAILS:
                self._muted_until = now + BACKOFF
                log.error("alertes Telegram suspendues %.0f min apres %d echecs",
                          BACKOFF / 60, self._fails)
            return False
        self._fails = 0
        if ok and key:
            self._sent[key] = now
            self._persist()
        return ok

    # --- messages metier ---
    def started(self, cfg):
        return self.send(
            f"🟢 <b>Bot demarre</b>\n"
            f"{esc(cfg.exchange)} · {esc(cfg.market_type)} · mode <b>{esc(cfg.mode)}</b>\n"
            f"{len(cfg.symbols)} paires · risque {cfg.risk_pct}% · "
            f"max {cfg.max_concurrent} positions\n"
            f"arret automatique a {cfg.max_drawdown_pct}% de drawdown")

    def stopped(self, reason="arret demande"):
        return self.send(f"⚪ <b>Bot arrete</b>\n{esc(reason)}")

    def opened(self, symbol, side, units, price, stop, atr, reason):
        r = abs(price - stop) / atr if atr else 0
        return self.send(
            f"📈 <b>Ouverture {esc(symbol)}</b>\n"
            f"{'LONG' if side == 1 else 'SHORT'} {units:.8g} a {price:.6g}\n"
            f"stop {stop:.6g} ({r:.2f} ATR, {abs(price-stop)/price*100:.1f}%)\n"
            f"<i>{esc(reason)}</i>")

    def closed(self, symbol, side, price, pnl, reason, equity=None):
        icon = "✅" if pnl >= 0 else "🔻"
        tail = f"\nequity {equity:,.2f}" if equity is not None else ""
        return self.send(
            f"{icon} <b>Cloture {esc(symbol)}</b>\n"
            f"{'LONG' if side == 1 else 'SHORT'} sorti a {price:.6g}\n"
            f"P&amp;L <b>{pnl:+,.2f}</b>\n"
            f"<i>{esc(reason)}</i>{tail}")

    def drawdown(self, dd, cap):
        """Palier de drawdown franchi. Une seule alerte par palier et par jour :
        un drawdown dure des semaines, le rappeler tous les cycles ne dit rien de
        neuf et use l'attention qu'il faudra au moment ou le seuil sera atteint."""
        step = int(dd // 10) * 10
        if step < 10:
            return False
        return self.send(
            f"⚠️ <b>Drawdown {dd:.1f}%</b>\n"
            f"arret automatique a {cap:.0f}% — il reste {cap - dd:.1f} points",
            key=f"dd{step}", cooldown=86400)

    def halted(self, dd, cap):
        return self.send(
            f"⛔ <b>ARRET AUTOMATIQUE</b>\n"
            f"drawdown {dd:.1f}% au-dela du plafond de {cap:.0f}%\n"
            f"Plus aucune ouverture. Les positions ouvertes restent gerees.\n"
            f"L'arret est definitif : remettre <code>halted</code> a "
            f"<code>false</code> dans le fichier d'etat une fois la cause comprise.",
            key="halted", cooldown=86400)

    def pair_error(self, symbol, exc):
        return self.send(
            f"⚠️ <b>Erreur sur {esc(symbol)}</b>\n<code>{esc(exc)[:300]}</code>\n"
            f"Les autres paires continuent d'etre gerees.",
            key=f"err:{symbol}", cooldown=1800)

    def stale(self, age, poll, n_open, state_path):
        h = age / 3600.0
        risk = (f"\n<b>{n_open} position(s) ouverte(s) ne sont plus surveillees</b> — "
                f"leurs stops ne remonteront plus et ne seront plus executes."
                if n_open else "\nAucune position ouverte : rien n'est expose.")
        return self.send(
            f"⛔ <b>LE BOT NE REPOND PLUS</b>\n"
            f"dernier cycle il y a <b>{h:.1f} h</b> (un cycle attendu "
            f"toutes les {poll/60:.0f} min){risk}\n"
            f"<code>systemctl status donchian-bot</code>\n"
            f"<code>journalctl -u donchian-bot -n 50</code>\n"
            f"<i>{esc(state_path)}</i>",
            key="stale", cooldown=21600)

    def recovered(self, downtime):
        return self.send(
            f"🟢 <b>Bot de nouveau actif</b>\napres {downtime/3600.0:.1f} h "
            f"d'interruption",
            key="recovered", cooldown=3600)
