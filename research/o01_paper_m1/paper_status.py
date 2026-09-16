#!/usr/bin/env python3
"""O01 paper engine status CLI (mission 15). Usage: python paper_status.py"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
snap = HERE / "state_replay" / "engine_state.json"
jl = HERE / "state_replay" / "paper_journal.jsonl"
status = {"O01_STATUS": {"PAPER_ONLY": True, "ACTIVE": False,
                          "NOTE": "no live feed authorized; run replay or connect an authorized adapter"}}
if snap.exists():
    s = json.loads(snap.read_text())
    status["O01_STATUS"].update({
        "CURRENT_CONTRACT": s.get("contract"),
        "ENGINE_STATE": s.get("state"),
        "MARKET_TIME": s.get("day"),
        "POSITION": ("FLAT" if not s.get("pos_data", {}).get("side")
                     else ("LONG" if s["pos_data"]["side"] == 1 else "SHORT")),
        "ENTRY": s.get("pos_data", {}).get("entry"),
        "STOP": s.get("pos_data", {}).get("stop"),
        "CHANDELIER": s.get("pos_data", {}).get("trail"),
        "LAST_EVENT": s.get("seq"),
        "TRADES": len(s.get("trades", [])),
    })
if "--journal" in sys.argv and jl.exists():
    lines = jl.read_text().splitlines()
    status["JOURNAL_TAIL"] = [json.loads(x) for x in lines[-10:]]
print(json.dumps(status, indent=1, default=str))
