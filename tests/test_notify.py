#!/usr/bin/env python3
"""Les alertes ne doivent jamais pouvoir nuire au bot.

Un systeme d'alerte est du code qui tourne dans la boucle de trading sans lui
apporter la moindre valeur en cas de succes. Le seul risque qu'il porte est donc
asymetrique : il ne peut que faire du mal. Ce test verifie les trois proprietes
qui garantissent qu'il n'en fera pas.

    python3 tests/test_notify.py
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.notify import BACKOFF, MAX_FAILS, Notifier      # noqa: E402


class Spy:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def __call__(self, text):
        if self.fail:
            raise ConnectionError("reseau injoignable")
        self.sent.append(text)
        return True


def main():
    print("=" * 70)
    print("ALERTES : PEUVENT-ELLES NUIRE AU BOT ?")
    print("=" * 70)

    # 1. Une panne reseau ne doit jamais remonter dans la boucle de trading.
    spy = Spy(fail=True)
    n = Notifier(token="t", chat_id="c", transport=spy)
    for _ in range(MAX_FAILS + 2):
        assert n.send("test") is False        # ne leve pas, retourne False
    print("\n  [OK] une panne d'envoi ne leve pas, elle retourne False")

    # 2. Apres MAX_FAILS echecs, on cesse d'essayer : sinon un DNS qui pend
    #    coute TIMEOUT secondes par paire et par cycle, et le bot prend un
    #    retard que rien ne signale.
    assert n._muted_until > time.time() + BACKOFF - 60
    spy.fail = False
    assert n.send("apres coupe-circuit") is False
    assert not spy.sent, "le coupe-circuit n'a pas tenu"
    print(f"  [OK] coupe-circuit apres {MAX_FAILS} echecs, suspension "
          f"{BACKOFF/60:.0f} min")

    # 3. Sans jeton, tout est un no-op silencieux - pas une exception au premier
    #    trade sur une machine ou l'environnement n'est pas renseigne.
    quiet = Notifier(token="", chat_id="", transport=Spy())
    assert quiet.enabled is False
    assert quiet.send("rien") is False
    assert "TELEGRAM_BOT_TOKEN" in quiet.why_disabled()
    off = Notifier(token="t", chat_id="c", transport=Spy(), enabled=False)
    assert off.enabled is False and "alerts=false" in off.why_disabled()
    print("  [OK] sans jeton ou desactivees : no-op, et la raison est explicite")

    # 4. Limitation d'envoi : une paire qui echoue a chaque cycle enverrait 288
    #    messages par jour. Au troisieme on ne les lit plus.
    spy = Spy()
    n = Notifier(token="t", chat_id="c", transport=spy)
    for _ in range(50):
        n.pair_error("BTC/USDT:USDT", RuntimeError("timeout"))
    assert len(spy.sent) == 1, f"{len(spy.sent)} messages au lieu d'un seul"
    n.pair_error("ETH/USDT:USDT", RuntimeError("timeout"))
    assert len(spy.sent) == 2, "la limitation doit etre par cle, pas globale"
    print("  [OK] 50 erreurs sur une paire = 1 message ; une autre paire passe")

    # 5. La limitation survit a un processus qui se termine - le watchdog est
    #    relance toutes les 15 minutes, une limitation en memoire ne servirait
    #    a rien.
    f = tempfile.mktemp(suffix=".json")
    spy = Spy()
    a = Notifier(token="t", chat_id="c", transport=spy, throttle_file=f)
    a.stale(7200, 300, 2, "/tmp/s.json")
    b = Notifier(token="t", chat_id="c", transport=spy, throttle_file=f)
    b.stale(7300, 300, 2, "/tmp/s.json")
    assert len(spy.sent) == 1, "la limitation ne survit pas au redemarrage"
    os.path.exists(f) and os.unlink(f)
    print("  [OK] la limitation persiste entre deux executions du watchdog")

    # 6. Le contenu doit etre echappe : un message d'erreur contenant du HTML
    #    casserait le rendu Telegram, et le message ne partirait pas du tout.
    spy = Spy()
    n = Notifier(token="t", chat_id="c", transport=spy)
    n.pair_error("BTC<b>/USDT", RuntimeError("<script>alert(1)</script>"))
    assert "<script>" not in spy.sent[0], "HTML non echappe"
    assert "&lt;script&gt;" in spy.sent[0]
    print("  [OK] le contenu dynamique est echappe")

    # 7. Temoin : sans ces protections, le transport EST bien appele. Sinon les
    #    tests ci-dessus ne prouveraient qu'une absence de chemin.
    spy = Spy()
    n = Notifier(token="t", chat_id="c", transport=spy)
    assert n.send("message normal") is True and len(spy.sent) == 1
    print("  [OK] temoin : un envoi normal atteint bien le transport")

    print("\nREUSSITE : les alertes ne peuvent ni lever, ni bloquer, ni inonder")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
