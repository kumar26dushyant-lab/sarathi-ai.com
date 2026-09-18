# -*- coding: utf-8 -*-
"""Journeys: does the product still work for the person using it?

A component being healthy proves nothing. On 18 Sep every component check was green while no
complainant could open their claim page, because a renamed function was still being called by the
first thing the portal touches. No component check can see that. A journey sees it in milliseconds.

A journey performs the real steps a real person takes, in order, against a COPY of live data with
outbound disabled, and reports the exact step where it stopped. Nothing here can reach a customer.
"""
from __future__ import annotations

import time
import traceback

OK, FAIL, SKIP = "ok", "fail", "skip"

_C = {"g": "\033[32m", "r": "\033[31m", "y": "\033[33m",
      "d": "\033[90m", "b": "\033[1m", "x": "\033[0m"}


class Skip(Exception):
    """Raised by a step when the live data cannot exercise it (no such claim, nobody on duty).

    A skip is not a pass and not a failure: it says this journey could not be tested right now,
    which is itself worth printing rather than hiding.
    """


class Journey:
    """One thing a real person does, start to finish."""

    def __init__(self, key: str, name: str, who: str):
        self.key, self.name, self.who = key, name, who
        self.steps: list = []

    def step(self, label: str):
        def deco(fn):
            self.steps.append((label, fn))
            return fn
        return deco

    async def run(self, ctx: dict) -> dict:
        out = {"key": self.key, "journey": self.name, "who": self.who,
               "steps": [], "state": OK, "broke_at": None, "why": "", "trace": ""}
        for label, fn in self.steps:
            t0 = time.time()
            try:
                await fn(ctx)
                out["steps"].append({"label": label, "state": OK,
                                     "ms": int((time.time() - t0) * 1000)})
            except Skip as s:
                out["steps"].append({"label": label, "state": SKIP, "ms": 0, "why": str(s)})
                out["state"] = SKIP
                out["broke_at"] = label
                out["why"] = str(s)
                break
            except Exception as e:  # noqa: BLE001
                out["steps"].append({"label": label, "state": FAIL,
                                     "ms": int((time.time() - t0) * 1000),
                                     "why": "%s: %s" % (type(e).__name__, e)})
                out["state"] = FAIL
                out["broke_at"] = label
                out["why"] = "%s: %s" % (type(e).__name__, str(e)[:200])
                out["trace"] = traceback.format_exc()[-800:]
                break                      # a journey stops where a person would stop
        return out


def render(results: list, *, verbose: bool = True) -> dict:
    """Print what a person would see. Returns the tally."""
    failed = [r for r in results if r["state"] == FAIL]
    skipped = [r for r in results if r["state"] == SKIP]
    passed = [r for r in results if r["state"] == OK]

    for r in results:
        head = {OK: _C["g"] + "PASS" + _C["x"],
                FAIL: _C["r"] + "FAIL" + _C["x"],
                SKIP: _C["y"] + "SKIP" + _C["x"]}[r["state"]]
        print("%s  %s  %s(%s)%s" % (head, r["journey"], _C["d"], r["who"], _C["x"]))
        if verbose or r["state"] != OK:
            for s in r["steps"]:
                mark = {OK: _C["g"] + "  ok  " + _C["x"],
                        FAIL: _C["r"] + "  XX  " + _C["x"],
                        SKIP: _C["y"] + "  --  " + _C["x"]}[s["state"]]
                print("  %s %s %s(%dms)%s" % (mark, s["label"], _C["d"], s.get("ms", 0), _C["x"]))
                if s.get("why"):
                    col = _C["r"] if s["state"] == FAIL else _C["y"]
                    print("        %s%s%s" % (col, s["why"], _C["x"]))
        if r["state"] == FAIL:
            print("    %s-> a person would be stuck at: %s%s" % (_C["r"], r["broke_at"], _C["x"]))
        print()

    print("%s%d passed  %d failed  %d skipped%s"
          % (_C["b"], len(passed), len(failed), len(skipped), _C["x"]))
    if failed:
        print("%sBLOCKED%s — %s" % (_C["r"], _C["x"], "; ".join(
            "%s (at '%s')" % (r["journey"], r["broke_at"]) for r in failed)))
    return {"passed": len(passed), "failed": len(failed), "skipped": len(skipped),
            "failing": [r["key"] for r in failed]}
