# -*- coding: utf-8 -*-
"""The self-test must never again report a block as health.

On 23 Sep the guardian told the founder "✅ NOT our side" while Cloudflare was serving Razorpay a
"Just a moment..." challenge and a 403 on every retry. The test request passed because it came
from our own network with our own user agent, and an edge challenge scores the CALLER, not the
path. He spent a day with Razorpay support on the strength of that sentence.

So two properties are pinned here:

  1. A challenge page is recognised as a block whatever HTTP code carries it. Cloudflare uses
     403 and 503 for the same page, and a 503 previously read as "the webhook secret is not
     configured" - a wrong answer that sends somebody to edit a correct secret.
  2. A PASS never claims the far side is at fault. The strongest thing this test can honestly
     say is "our app answered us", and the words "not our side" must not appear in it.

No network: httpx is swapped for a stub that returns whatever the case needs.

    py -3.13 _tools/test_webhook_selftest.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import biz_nidaan_pay_guard as pg  # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


class _Resp:
    def __init__(self, code, text):
        self.status_code, self.text = code, text


class _Client:
    """Stands in for httpx.AsyncClient and answers with one canned response."""

    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **kw):
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


class _Httpx:
    def __init__(self, resp):
        self._resp = resp

    def AsyncClient(self, *a, **kw):  # noqa: N802 - matching httpx's own name
        return _Client(self._resp)


async def run(resp):
    real = pg.httpx
    pg.httpx = _Httpx(resp)
    try:
        return await pg.webhook_self_test()
    finally:
        pg.httpx = real


# The real thing Cloudflare served Razorpay, quoted from their 23 Sep reply.
CHALLENGE = ('<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title>'
             '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">')

print("\nWhat the webhook self-test is allowed to conclude\n")

# 1 - the exact page Razorpay was served, on the code they reported.
ok, why = asyncio.run(run(_Resp(403, CHALLENGE)))
check("a 403 challenge page is a block, not health", ok is False, why)
check("and it names Cloudflare, so nobody is sent to the wrong support desk",
      "cloudflare" in why.lower(), why)
check("and it names the setting to change", "bot fight mode" in why.lower(), why)

# 2 - the same page behind a 503, which used to be read as a missing secret.
ok, why = asyncio.run(run(_Resp(503, CHALLENGE)))
check("a 503 carrying the same page is still a block", ok is False, why)
check("and is NOT misreported as a missing webhook secret",
      "secret" not in why.lower(), why)

# 3 - a genuine missing secret still reads as one.
ok, why = asyncio.run(run(_Resp(503, '{"detail":"webhook secret not configured"}')))
check("a real 503 from our own app still reads as a missing secret",
      ok is False and "secret" in why.lower(), why)

# 4 - the healthy case, and what it may NOT say.
ok, why = asyncio.run(run(_Resp(400, '{"detail":"bad signature"}')))
check("a 400 to a bad signature still reads as our app answering", ok is True, why)
check("but it does NOT claim the fault is elsewhere",
      "not our side" not in why.lower(), why)
check("and it says out loud what it cannot prove",
      "cannot prove" in why.lower(), why)

# 5 - a 200 would mean we accepted an unsigned webhook. That is a security failure, not health.
ok, why = asyncio.run(run(_Resp(200, "ok")))
check("a 200 to an UNSIGNED webhook is never reported as healthy", ok is False, why)

# 6 - nothing there at all.
ok, why = asyncio.run(run(RuntimeError("connection refused")))
check("an unreachable endpoint is a failure, with the reason kept",
      ok is False and "could not be reached" in why.lower(), why)

print("\n" + ("%d failed" % FAILED if FAILED else "the self-test can no longer exonerate us"))
sys.exit(1 if FAILED else 0)
