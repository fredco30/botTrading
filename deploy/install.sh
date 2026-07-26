#!/usr/bin/env bash
# Installe le bot en service systemd. A lancer en root sur le VPS.
set -euo pipefail

APP=/opt/donchian-bot
CFG=/etc/donchian-bot
DATA=/var/lib/donchian-bot
USER=donchian

echo "==> utilisateur systeme"
id -u "$USER" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$USER"

echo "==> arborescence"
mkdir -p "$APP" "$CFG" "$DATA"

echo "==> code"
# Depuis le depot clone : rsync du contenu utile, sans les CSV de backtest.
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rsync -a --delete \
  --exclude '.git' --exclude '__pycache__' --exclude '*.csv' \
  --exclude '*.txt' --exclude '.venv' \
  "$SRC/live" "$SRC/engine" "$SRC/run_bot.py" "$APP/"

echo "==> environnement python"
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install --quiet --upgrade pip
"$APP/.venv/bin/pip" install --quiet ccxt numpy

echo "==> configuration"
if [ ! -f "$CFG/config.json" ]; then
  cp "$SRC/live_config.json" "$CFG/config.json"
  # L'etat et le journal doivent pointer vers le repertoire inscriptible.
  python3 - "$CFG/config.json" "$DATA" <<'PY'
import json, sys
p, d = sys.argv[1], sys.argv[2]
c = json.load(open(p))
c["state_file"] = f"{d}/state.json"
c["log_file"] = f"{d}/bot.log"
json.dump(c, open(p, "w"), indent=2)
PY
  echo "    config creee : $CFG/config.json (mode paper)"
fi

if [ ! -f "$CFG/env" ]; then
  cat > "$CFG/env" <<'ENVEOF'
# Cles API. Laisser vide tant que le bot tourne en paper.
BITVAVO_API_KEY=
BITVAVO_API_SECRET=

# Alertes Telegram. Creer un bot avec @BotFather, puis recuperer l'identifiant
# de salon en lui envoyant un message et en lisant
#   https://api.telegram.org/bot<JETON>/getUpdates
# Laisser vide desactive les alertes sans rien casser.
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ENVEOF
  echo "    fichier de cles cree : $CFG/env"
fi

echo "==> permissions"
chown -R root:root "$APP"
chown -R "$USER:$USER" "$DATA"
chown root:"$USER" "$CFG/env" "$CFG/config.json"
chmod 640 "$CFG/env"          # les cles ne sont lisibles que par le service
chmod 644 "$CFG/config.json"

echo "==> rotation des journaux"
cat > /etc/logrotate.d/donchian-bot <<LOGEOF
$DATA/bot.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
    su $USER $USER
}
LOGEOF

echo "==> service systemd"
cp "$SRC/deploy/donchian-bot.service" /etc/systemd/system/
# Le watchdog est un service separe, declenche par un timer : un processus mort
# ne peut pas signaler sa propre mort, donc le surveillant doit survivre au
# surveille.
cp "$SRC/deploy/donchian-watchdog.service" /etc/systemd/system/
cp "$SRC/deploy/donchian-watchdog.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable donchian-bot
systemctl enable --now donchian-watchdog.timer

cat <<MSG

Installation terminee.

  Verifier la config      : cat $CFG/config.json
  Tester la plomberie     : sudo -u $USER $APP/.venv/bin/python \\
                              $APP/run_bot.py --dry-run-api --config $CFG/config.json
  Demarrer (paper)        : systemctl start donchian-bot
  Suivre les journaux     : journalctl -u donchian-bot -f
  Etat des positions      : cat $DATA/state.json
  Arreter                 : systemctl stop donchian-bot

  Tester les alertes      : sudo -u $USER $APP/.venv/bin/python $APP/watchdog.py --test
  Etat du surveillant     : systemctl list-timers donchian-watchdog.timer

Avant de passer en live :
  1. lancer --dry-run-api et corriger ce qu'il signale
  2. laisser tourner plusieurs semaines en paper
  3. renseigner les cles dans $CFG/env
  4. passer "mode": "live" dans $CFG/config.json
  5. baisser "risk_pct" a 0.2 pour les premieres semaines
  6. systemctl restart donchian-bot

MSG
