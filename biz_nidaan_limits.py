# -*- coding: utf-8 -*-
"""HOW BIG A DOCUMENT MAY BE - one place for every door (founder, 3 Oct 2026: "100 MB each doc").

Staff receive papers from many people, each in their own format - big scans, phone photos,
merged PDFs. The limit used to be 25 MB in about ten separate places (30 in the splitter, 20 for
the bot, 48 at the scanner, 50 at nginx), so a file could pass one door and be refused at the
next. Every door now reads it from here.

WHY 95 MB AND NOT 100: Cloudflare, in front of every request, refuses a request over 100 MB - and
a request carries the file plus a little form data. The document and request limits are counted in
DECIMAL megabytes (1 MB = 1,000,000 bytes), so they pass however Cloudflare counts its 100.

WHAT WE CANNOT RAISE (other companies' rules), each named so the message can say why:
  * Telegram bots cannot download a file over 20 MB.
  * WhatsApp delivers photos up to 5 MB, videos and audio up to 16 MB, documents up to 100 MB.
  * Email (Gmail and most others) carries up to 25 MB.

Above us: nginx (client_max_body_size 100M) and the virus scanner (110M) - set by
deploy/server-upload-limits.sh. The scanner must stay ABOVE DOC_MAX_BYTES: a file it cannot finish
is refused, never waved through.

static/nidaan_limits.js carries the same numbers for the pages; deploy/verify-limits.py fails
the build if the two disagree.
"""
MB = 1024 * 1024                           # binary megabyte - the scanner's and Telegram's unit
MB_DEC = 1000 * 1000                       # decimal megabyte - what people (and Cloudflare) mean

DOC_MAX_MB = 95
DOC_MAX_BYTES = DOC_MAX_MB * MB_DEC        # one document, at any door
REQUEST_MAX_BYTES = 99 * MB_DEC            # one upload request (one or more files) - under Cloudflare's 100
SCAN_MAX_BYTES = 105 * MB                  # what we hand the scanner (110 MB); clamd allows 110M

TELEGRAM_BOT_MAX_BYTES = 20 * MB           # Telegram's own rule for bots
WHATSAPP_MAX_BYTES = {"image": 5 * MB, "video": 16 * MB, "audio": 16 * MB,
                      "document": 100 * MB, "sticker": 1 * MB}
EMAIL_MAX_BYTES = 25 * MB


def mb(n: int) -> str:
    """'95 MB' for messages - decimal, as people count."""
    return "%d MB" % round(n / MB_DEC)


def too_big(name: str, size: int, limit: int = DOC_MAX_BYTES) -> dict:
    """The refusal, in both languages, saying what to do - not just 'too large'."""
    n = (name or "This file")[:80]
    return {
        "en": "%s is %s - the limit is %s. Send it as a PDF, or split it into parts."
              % (n, mb(size), mb(limit)),
        "hi": "%s %s की है - सीमा %s है। इसे PDF में भेजें, या हिस्सों में बाँटें।"
              % (n, mb(size), mb(limit)),
    }
