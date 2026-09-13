# The ops screens, driven in a real browser

## Why this exists

Three bugs reached the founder in one week. All three were invisible to the Python
tests, because all three lived **above the engine, in the screen**:

| What was hit | Underneath |
|---|---|
| A dialog with no close button | Nobody had ever checked for one |
| "Pick a way to send it", with both ticked | Send read state from a part of the page that had already been replaced |
| NP-112 "fee not paid" when it was paid | A fix that passed every unit test and still failed on the real claim, because the test built its rows differently from the way the endpoint does |

The engine tests pass on all three. Only a browser catches them.

## Running it

```
cd uitest
npm install                       # once
npx playwright install chromium   # once, ~115MB
node flow.mjs                     # against https://nidaanpartner.com
node flow.mjs --headed            # watch it work
node flow.mjs --base=http://127.0.0.1:8003   # against staging
```

It needs SSH access to the app server: it mints a real staff token there, the same
way the app does, so the session it drives is a genuine one and not a test back door.

## What it will not do

**It never sends anything to a customer and never changes a claim.** It opens the
read-back screen and does not press send; it opens the handover dialog and does not
hand over. Every check stops one step before the act. That is deliberate — a test
suite that writes to production is a worse problem than the bugs it finds.

The one thing it does write is nothing at all today; if that ever changes it goes
behind `--allow-writes`, off by default.

## What it checks

- Every panel opens, finishes loading, is not an error page, and throws no script error
- Every dialog has an ✕, has a button that leaves, and closes on Escape
- The document window: documents listed, recipients resolved, both channels, a drafted
  message; adding a person makes one card with its own Remove, and Remove removes it
- The read-back screen: the channels and the document list survive the screen being
  replaced — this is the exact bug from 13 Sep
- The handover dialog opens and does not claim the fee is unpaid on a covered claim
- A sub-super-admin is not refused from the WhatsApp inbox, and does not get the
  automation defaults or the campaign controls

## Screenshots

Each run drops PNGs in `screenshots/` — useful when a check fails and you want to see
what the page actually looked like. Not committed.
