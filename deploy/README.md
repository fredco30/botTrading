# Déploiement VPS

## Installation

```bash
git clone https://github.com/fredco30/botTrading.git
cd botTrading
sudo bash deploy/install.sh
sudo systemctl start donchian-bot
journalctl -u donchian-bot -f
```

Le service démarre en **mode paper**. Rien n'est envoyé au marché tant que la
config n'est pas basculée explicitement.

## Ce que fait l'installation

| Chemin | Contenu | Droits |
|---|---|---|
| `/opt/donchian-bot` | code + venv | `root:root` — le service ne peut pas se modifier |
| `/etc/donchian-bot/config.json` | configuration | `644` |
| `/etc/donchian-bot/env` | **clés API** | **`640 root:donchian`** |
| `/var/lib/donchian-bot` | état + journal | `donchian:donchian` — seul chemin inscriptible |

L'utilisateur `donchian` est un compte système sans shell ni home.

## Les choix du service, et pourquoi

**`Restart=always` + `StartLimitIntervalSec=0`**
Par défaut, systemd abandonne après 5 redémarrages rapprochés. C'est exactement
le comportement à éviter ici : un bot de tendance arrêté laisse des positions
ouvertes dont **plus personne ne surveille le stop**. Mieux vaut qu'il boucle en
échec bruyamment que de rester couché en silence.

**`TimeoutStopSec=120` + `KillSignal=SIGTERM`**
Le bot intercepte SIGTERM, termine le cycle en cours, écrit son état, puis sort.
Vérifié : sortie propre en 2 s, code 0, positions conservées. Sans ce délai
systemd enverrait SIGKILL au bout de 90 s par défaut, possiblement entre l'envoi
d'un ordre et l'écriture de l'état — donc une position réelle absente du fichier
d'état, donc un stop orphelin.

**`MemoryMax=512M`**
Garde-fou contre une fuite, pas un quota. L'empreinte mesurée est de 82 Mo.
Serrer davantage ferait risquer un OOM kill en plein envoi d'ordre, ce qui est
pire que la fuite qu'on cherche à borner.

**`ProtectSystem=strict` + `ReadWritePaths=/var/lib/donchian-bot`**
Tout le système de fichiers est en lecture seule pour le service, sauf son
répertoire d'état. Une compromission de `ccxt` ou d'une dépendance ne peut ni
modifier le code du bot ni toucher au reste de la machine.

**`After=time-sync.target`**
Les bougies sont datées en UTC. Une horloge décalée fait lire les mauvaises
barres, silencieusement.

## Exploitation

```bash
systemctl status donchian-bot          # etat du service
journalctl -u donchian-bot -f          # journaux en direct
journalctl -u donchian-bot --since today | grep -E 'OUVRE|FERME'
cat /var/lib/donchian-bot/state.json   # positions ouvertes
systemctl restart donchian-bot         # arret propre puis redemarrage
```

**Le redémarrage est sûr.** L'état est écrit de façon atomique (fichier
temporaire + renommage), et le bot reprend ses positions au démarrage — il
l'affiche dans le journal : `reprise avec N position(s) en cours`.

## Passage en live

Dans l'ordre, sans sauter d'étape :

1. **Plusieurs semaines en paper.** Comparer les trades du journal à ceux du
   backtest sur la même période.
2. Renseigner les clés dans `/etc/donchian-bot/env`.
3. Passer `"mode": "live"` dans `/etc/donchian-bot/config.json`.
4. **Descendre `risk_pct` à 0.2** pour les premières semaines. Le point de
   fonctionnement calibré est 1 %, on n'y va pas d'emblée — c'est le réglage
   qui amène le drawdown flottant à 30 %.
5. `systemctl restart donchian-bot`.

Créer les clés API **sans droit de retrait** et, si la place le permet, avec une
restriction d'IP sur celle du VPS.

## Surveillance minimale

Le bot s'arrête d'ouvrir à 30 % de drawdown mais **continue de gérer** les
positions existantes. Cet événement est journalisé en `ERROR` :

```bash
journalctl -u donchian-bot -p err --since "1 week ago"
```

Un `ARRET : drawdown ...` dans cette sortie veut dire que le système a atteint sa
limite et attend une décision humaine.
