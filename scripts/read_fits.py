#!/usr/bin/env python3
"""Read every fit-overview figure with GLM-5.4 twice (whole figure + half crops)
and record only what both passes agree on; disagreements are flagged, never averaged.

Input : data/sample/slides.json  (scripts/extract_deck.py)
Output: data/fits_readings.json

Each record:
 {"slide":124,"page":"103/132","burst":"250702B","image":"media/s124_rId1.png",
  "panels":[{"freq":"1–2 GHz","status":"number|not detected|data only|unclear",
             "chi2":1.7,"fvar_text":"12%","fvar_pct":12.0,
             "agree":true,"passes":[pass1,pass2a,pass2b]}]}
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glm_read import ask_image  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
SAMPLE = BASE / "data" / "sample"

PROMPT = """这是若干张射电光变曲线拟合子图拼成的图。对每一个子图（从左到右、从上到下），只输出一行：

频率标签|χ2_red|F_var原文

规则：
1) 频率标签照抄子图标题里的频率或频段（如 "4.86 GHz" 或 "1-2 GHz"）。
2) χ2_red 与 F_var 只抄参数框里的数值，不要抄 A、α1、α2、t_b。
3) 若参数框写的是 "Data only"，这一行写 频率标签|Data only|Data only。
4) 若 F_var 写 "not detected"，这一行写 频率标签|数值|not detected。
5) 看不清写 UNCLEAR。绝对不要推算、不要补全、不要总结。
只输出这些行，不要任何解释或 Markdown。"""


def parse(text):
    out = []
    for line in text.splitlines():
        line = line.strip().strip("|").strip()
        if not line or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        freq, chi, fvar = parts[0], parts[1], "|".join(parts[2:])
        if "hz" not in freq.lower():  # band labels always carry GHz; drops stray rows
            continue
        out.append({"freq": freq, "chi2_raw": chi, "fvar_raw": fvar})
    return out


def norm_freq(s):
    s = s.lower().replace("ghz", "").replace("～", "-").replace("–", "-").replace("—", "-")
    m = re.findall(r"\d+\.?\d*", s)
    return tuple(float(x) for x in m)


def num(s):
    if s is None:
        return None
    s = str(s).strip().replace("%", "")
    m = re.match(r"^[<>~]?\s*(-?\d+\.?\d*(?:[eE][+-]?\d+)?)", s)
    return float(m.group(1)) if m else None


def slide_is_fit(s):
    blob = " ".join(s.get("texts", [])) + " " + s.get("notes", "")
    return s.get("images") and ("拟合" in blob or "_fit_overview" in blob)


def image_labels(s):
    """Per-image variant label (SPL / SBPL / ...) from the notes' source filenames."""
    out = []
    for line in s.get("notes", "").splitlines():
        m = re.search(r"(\d{6}[A-Z]?)_(\w+?)_fit_overview", line)
        if m:
            out.append(m.group(2))
    return out


def read_slide(s):
    m = re.search(r"GRB\s*(\d{6}[A-Z]?)", s["title"] + " " + " ".join(s["texts"]))
    burst = m.group(1) if m else s["title"][:12]
    labels = image_labels(s)
    records = []
    for k, im in enumerate(s["images"]):
        rec = read_image(s, burst, im["exported"], labels[k] if k < len(labels) else "")
        records.append(rec)
    return records


def read_image(s, burst, exported, variant):
    img = SAMPLE / exported
    from PIL import Image
    w, h = Image.open(img).size
    passes = []
    for tag, crop in (("whole", None), ("top", (0, 0, w, int(h * 0.55))),
                      ("bottom", (0, int(h * 0.45), w, h))):
        try:
            txt = ask_image(str(img), PROMPT, crop=list(crop) if crop else None, max_tokens=1200)
        except SystemExit as e:  # rate-limit exhaustion for this image
            print(f"[skip] slide {s['index']} {tag}: {e}", file=sys.stderr)
            continue
        passes.append({"pass": tag, "raw": txt, "rows": parse(txt)})
    merged = {}
    for p in passes:
        for r in p["rows"]:
            k = norm_freq(r["freq"])
            merged.setdefault(k, {"freq": r["freq"], "seen": []})["seen"].append((p["pass"], r))
    panels = []
    for k, v in sorted(merged.items()):
        fvars, chis, statuses = [], [], []
        for tag, r in v["seen"]:
            fv = r["fvar_raw"].lower()
            st = ("data only" if "data only" in fv else
                  "not detected" if "not detected" in fv or "notdetect" in fv else
                  "unclear" if "unclear" in fv or not fv else "number")
            statuses.append(st)
            if st == "number":
                fvars.append(num(r["fvar_raw"]))
                chis.append(num(r["chi2_raw"]))
        solid = [s for s in statuses if s != "unclear"]
        def spread(xs):
            xs = [x for x in xs if x is not None]
            return (max(xs) - min(xs)) if len(xs) > 1 else 0.0
        agree = len(set(solid)) <= 1 and spread(fvars) <= max(1.0, 0.05 * max(fvars or [0] or [1]))
        panels.append({
            "freq": v["freq"],
            "status": solid[0] if solid else "unclear",
            "chi2": chis[0] if chis else None,
            "fvar_pct": fvars[0] if fvars else None,
            "fvar_text": next((r["fvar_raw"] for _, r in v["seen"]
                               if "data only" not in r["fvar_raw"].lower()
                               and "unclear" not in r["fvar_raw"].lower()), ""),
            "agree": agree,
            "spread_fvar": spread(fvars), "n_reads": len(v["seen"]),
            "variants": [f"{t}:{r['fvar_raw']}" for t, r in v["seen"]],
        })
    return {"slide": s["index"], "page": s["page_label"], "burst": burst,
            "variant": variant, "image": exported, "panels": panels,
            "passes_ok": [p["pass"] for p in passes]}


def main(workers=3):
    slides = json.loads((SAMPLE / "slides.json").read_text())["slides"]
    fits = [s for s in slides if slide_is_fit(s)]
    print(f"{len(fits)} fit slides, workers={workers}", file=sys.stderr)
    out = []
    def job(s):
        try:
            recs = read_slide(s)
            for r in recs:
                print(f"  slide {s['index']:>3} {r['burst']:<9} {r.get('variant',''):<5} "
                      f"panels={len(r['panels'])} "
                      f"disagree={sum(1 for p in r['panels'] if not p['agree'])}", file=sys.stderr)
            return recs
        except Exception as e:  # noqa: BLE001
            print(f"  [fail] slide {s['index']}: {e!r}", file=sys.stderr)
            return [{"slide": s["index"], "burst": s["title"][:14], "error": repr(e), "panels": []}]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for recs in ex.map(job, fits):
            out.extend(recs)
    (BASE / "data" / "fits_readings.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    n = sum(len(r["panels"]) for r in out)
    bad = sum(1 for r in out for p in r["panels"] if not p["agree"])
    print(f"wrote {len(out)} slides, {n} panels, {bad} with disagreement", file=sys.stderr)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
