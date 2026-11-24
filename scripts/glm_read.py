#!/usr/bin/env python3
"""Minimal GLM-5.4 vision client: retries on HTTP 429 / 5xx, caches by content hash.

Only glm-5.4 is used. On rate limiting the call sleeps and retries instead of
falling back to another model.

CLI:
  python scripts/glm_read.py IMAGE PROMPT [--crop x1,y1,x2,y2] [--max-tokens N]

Python:
  from glm_read import ask_image
  text = ask_image(path, prompt, crop=(x1,y1,x2,y2), max_tokens=1500)
"""
import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "glm-5.4"
URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
CACHE = Path(os.environ.get("GLM_CACHE", "data/cache"))
MAX_TRIES = int(os.environ.get("GLM_MAX_TRIES", "10"))


def api_key():
    if os.environ.get("ZHIPU_API_KEY"):
        return os.environ["ZHIPU_API_KEY"]
    env = Path.home() / ".hermes" / ".env"
    m = re.search(r"^ZHIPU_API_KEY=(.*)$", env.read_text(), re.M)
    if not m:
        raise SystemExit("ZHIPU_API_KEY not found")
    return m.group(1).strip().strip('"')


def encode(path, crop=None, max_side=2600):
    """Return base64 PNG payload; crop in ORIGINAL pixel coords."""
    from PIL import Image
    im = Image.open(path)
    if crop:
        im = im.crop(tuple(int(v) for v in crop))
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode(), im.size


def ask_image(path, prompt, crop=None, max_tokens=1500, temperature=0.0, use_cache=True):
    b64, size = encode(path, crop)
    key = hashlib.sha1(f"{MODEL}|{prompt}|{b64[:0]}{size}".encode() + b64.encode()).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"{key}.json"
    if use_cache and cf.exists():
        return json.loads(cf.read_text())["text"]
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
            {"type": "text", "text": prompt},
        ]}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    data = json.dumps(payload).encode()
    delay = 20
    last = None
    for attempt in range(1, MAX_TRIES + 1):
        req = urllib.request.Request(
            URL, data=data,
            headers={"Authorization": "Bearer " + api_key(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.load(r)
            txt = d["choices"][0]["message"].get("content") or ""
            cf.write_text(json.dumps({"text": txt, "model": MODEL, "size": size,
                                      "prompt": prompt, "crop": crop}, ensure_ascii=False))
            return txt
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:400]
            last = f"HTTP {e.code}: {body}"
            if e.code in (429, 500, 502, 503, 504, 529):
                print(f"[rate-limit/server {e.code}] wait {delay}s (try {attempt}/{MAX_TRIES})",
                      file=sys.stderr)
                time.sleep(delay)
                delay = min(delay * 2, 240)
                continue
            raise
        except Exception as e:  # noqa: BLE001  network hiccup
            last = repr(e)
            time.sleep(delay)
            delay = min(delay * 2, 240)
    raise SystemExit(f"glm-5.4 failed after {MAX_TRIES} tries: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("prompt")
    ap.add_argument("--crop", default=None, help="x1,y1,x2,y2 in original pixels")
    ap.add_argument("--max-tokens", type=int, default=1500)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    crop = [int(v) for v in a.crop.split(",")] if a.crop else None
    print(ask_image(a.image, a.prompt, crop=crop, max_tokens=a.max_tokens,
                    use_cache=not a.no_cache))


if __name__ == "__main__":
    main()
