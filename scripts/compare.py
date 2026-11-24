#!/usr/bin/env python3
"""Join the deck readings with the October ISS predictions and run the checks that
decide whether a band can carry a size constraint.

Inputs : data/fits_readings.json, data/october_tables.json, data/sample/slides.json
Outputs: data/matched_table.csv, data/compare_summary.json

Rules
  * A panel whose label is a single frequency is matched to the October row within 10%.
  * A panel whose label is a band (e.g. "4-7.5 GHz") is matched to every October row
    inside the band; if more than one, the row is flagged "band" because the wide bin
    averages over the diagnostic axis.
  * F_var / m_p is only a size inversion when 0.15 < F_var/m_p < 1 AND the panel is a
    single frequency AND the two independent reads agreed.
"""
import csv
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def freqs(label):
    nums = [float(x) for x in re.findall(r"\d+\.?\d*", str(label))]
    if not nums:
        return None
    return (nums[0], nums[-1]) if len(nums) > 1 else (nums[0], nums[0])


def main():
    fits = json.loads((BASE / "data" / "fits_readings.json").read_text())
    octo = json.loads((BASE / "data" / "october_tables.json").read_text())
    slides = json.loads((BASE / "data" / "sample" / "slides.json").read_text())["slides"]

    pred = {}
    for r in octo["predictions"]:
        pred.setdefault(r["grb"], []).append(r)

    rows = []
    for f in fits:
        if not re.fullmatch(r"\d{6}[A-Z]?", f["burst"]):
            continue  # method slide, not a burst
        for p in f["panels"]:
            rng = freqs(p["freq"])
            if not rng:
                continue
            lo, hi = rng
            cands = [r for r in pred.get(f["burst"], [])
                     if lo * 0.9 <= r["nu"] <= hi * 1.1 and r["regime"] in ("SR", "W")]
            band = hi > lo * 1.05
            for r in cands or [None]:
                mp = r["mp"] if r else None
                fv = (p["fvar_pct"] or 0) / 100 if p["status"] == "number" else None
                ratio = (fv / mp) if (fv and mp) else None
                invertible = bool(ratio and 0.15 < ratio < 1 and not band and p["agree"])
                rows.append({
                    "burst": f["burst"], "page": f["page"], "panel": p["freq"],
                    "band": band, "status": p["status"],
                    "chi2": p["chi2"], "fvar_pct": p["fvar_pct"], "agree": p["agree"],
                    "model": r["model"] if r else "",
                    "nu": r["nu"] if r else "", "regime": r["regime"] if r else "",
                    "mp": mp or "", "tp_hr": r["tp"] if r else "",
                    "theta_scatt_uas": r["theta_scatt"] if r else "",
                    "size_1e16cm": r["size"] if r else "",
                    "fvar_over_mp": round(ratio, 3) if ratio else "",
                    "invertible": invertible,
                })

    out = BASE / "data" / "matched_table.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ---- summary checks
    deck_bursts = sorted({f["burst"] for f in fits})
    oct_bursts = sorted({r["grb"] for r in octo["predictions"]})
    deck_all = sorted({re.search(r"GRB\s*(\d{6}[A-Z]?)", s["title"]).group(1)
                       for s in slides if re.search(r"GRB\s*(\d{6}[A-Z]?)", s["title"])})
    numeric = [r for r in rows if r["status"] == "number"]
    summary = {
        "deck_bursts": len(deck_all), "fit_pages": len(fits), "bursts_with_fit": len(deck_bursts),
        "panels": sum(len(f["panels"]) for f in fits),
        "panels_numeric": len(numeric),
        "panels_not_detected": sum(1 for r in rows if r["status"] == "not detected"),
        "panels_data_only": sum(1 for r in rows if r["status"] == "data only"),
        "panels_disagreeing": sum(1 for f in fits for p in f["panels"] if not p["agree"]),
        "invertible_rows": sum(1 for r in rows if r["invertible"]),
        "fvar_exceeds_mp": sum(1 for r in rows if r["fvar_over_mp"] not in ("", None)
                               and float(r["fvar_over_mp"]) >= 1.0),
        "october_bursts": len(oct_bursts),
        "in_deck_not_in_october": [b for b in deck_all if b not in oct_bursts],
        "in_october_not_in_deck": [b for b in oct_bursts if b not in deck_all],
        "unmatched_fit_bursts": sorted({f["burst"] for f in fits
                                        if f["burst"] not in oct_bursts}),
    }
    (BASE / "data" / "compare_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1))
    for k, v in summary.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    sys.exit(main())
