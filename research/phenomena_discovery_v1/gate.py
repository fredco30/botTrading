#!/usr/bin/env python3
"""Central validation-window gate (mission J).

Technical prevention: split windows other than DISCOVERY are inaccessible
unless `authorize()` was explicitly called first. Every authorization is
appended to gate_audit.log (versioned evidence: decision frozen BEFORE the
window is opened). Phase 2 screens may only call `window("DISCOVERY")`.
"""
import os
from datetime import datetime, timezone

import p000_lib as P

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "gate_audit.log")

_AUTHORIZED = set()


class ValidationGateError(RuntimeError):
    """Raised when a protected window is accessed without authorization."""


def window(name):
    """Return (lo, hi) bounds for a split; raises for unauthorized windows."""
    if name not in P.SPLITS:
        raise ValidationGateError(f"unknown split {name!r}")
    if name != "DISCOVERY" and name not in _AUTHORIZED:
        raise ValidationGateError(
            f"window {name!r} is locked: authorize() must be called first "
            f"(gate decision must be frozen BEFORE opening validation)")
    return P.SPLITS[name]


def authorize(split_name, reason):
    """Explicitly unlock a validation window; logged to gate_audit.log."""
    if split_name not in P.SPLITS:
        raise ValidationGateError(f"unknown split {split_name!r}")
    _AUTHORIZED.add(split_name)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} "
                f"AUTHORIZE {split_name} REASON={reason}\n")


def authorized():
    return sorted(_AUTHORIZED)
