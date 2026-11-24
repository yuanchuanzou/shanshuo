#!/usr/bin/env python3
"""Join the deck readings with the October ISS predictions and run the checks that
decide whether a band can carry a size constraint.

Inputs : data/fits_readings.json, data/october_tables.json, data/sample/slides.json
Outputs: data/matched_table.csv, data/compare_summary.json

Rules
  * A panel whose label is a single frequency is matched to the October row within 10%.
  * A panel whose label is a band (e.g. "4-7.5 GHz") is matched to every October row
    inside the band and flagged `band=True`: a wide bin averages over the diagnostic axis.
  * `verdict` is one of
      fit_failed       chi2_red > CHI2_MAX   -> the trend model did not describe the data
      not_detected     no F_var value in the panel
      data_only        the panel carries no numbers at all
      no_prediction    the burst is not in the October table
      incompatible     F_var >= m_p          -> cannot be inverted, report model tension
      ceiling          0.7 <= ratio < 1      -> point source, only an upper limit
      invertible       0.15 < ratio < 0.7, single frequency, reads agreed, fit OK
      dilute           ratio <= 0.15         -> resolved or diluted, needs the dilution check
      unresolved       band panel, or the reads disagreed
  * `theta_s_uas` / `size_inv_1e16cm` are filled only for `invertible`:
      theta_s = theta_scatt * (m_p/m)^(6/7);  size = theta_s * D_A.
"""
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import iss  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
CHI2_MAX = 10.0


def freqs(label):
    nums = [float(x) for x in re.findall(r"\d+\.?\d*", str(label))]
    if not nums:
        return None
    return (nums[0], nums[-1]) if len(nums) > 1 else (nums[0], nums[0])


def verdict(p, r, band, ratio):
    if r is None:
        return "no_prediction"
    if p["status"] == "data only":
        return "data_only"
    if p["status"] == "not detected":
        return "not_detected"
    if p["chi2"] is not None and p["chi2"] > CHI2_MAX:
        return "fit_failed"
    if ratio is None or not p["agree"]:
        return "unresolved"
    if ratio >= 1.0:
        return "incompatible"
    if band:
        return "unresolved"
    if ratio >= 0.7:
        return "ceiling"
    if ratio > 0.15:
        return "invertible"
    return "dilute"


def main():
    fits = json.loads((BASE / "data" / "fits_readings.json").read_text())
    octo = json.loads((BASE / "data" / "october_tables.json").read_text())
    slides = json.loads((BASE / "data" / "sample" / "slides.json").read_text())["slides"]

    pred, zs = {}, {}
    for r in octo["predictions"]:
        pred.setdefault(r["grb"], []).append(r)
    for s in octo["sightlines"]:
        zs[s["grb"]] = s.get("z")

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
                v = verdict(p, r, band, ratio)
                th_s = size = ""
                if v == "invertible":
                    th = iss.theta_s_from_m(mp, fv, r["theta_scatt"])
                    th_s = round(th, 3)
                    z = zs.get(f["burst"])
                    if z:  # 980519 / 170105A / 230217A have no redshift in Table 1
                        size = round(iss.r_perp_cm(th, iss.d_a_cm(z)) / 1e16, 2)
                rows.append({
                    "burst": f["burst"], "page": f["page"], "panel": p["freq"],
                    "variant": f.get("variant", ""), "band": band, "status": p["status"],
                    "chi2": p["chi2"], "fvar_pct": p["fvar_pct"], "agree": p["agree"],
                    "model": r["model"] if r else "", "nu": r["nu"] if r else "",
                    "regime": r["regime"] if r else "", "mp": mp or "",
                    "tp_hr": r["tp"] if r else "", "theta_scatt_uas": r["theta_scatt"] if r else "",
                    "size_student_1e16cm": r["size"] if r else "",
                    "fvar_over_mp": round(ratio, 3) if ratio else "",
                    "theta_s_uas": th_s, "size_inv_1e16cm": size,
                    "verdict": v,
                })

    out = BASE / "data" / "matched_table.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ---- summary
    def bursts_in(slides):
        out = set()
        for s in slides:
            blob = s["title"] + " " + " ".join(s["texts"])
            m = re.search(r"GRB\s*(\d{6}[A-Z]?)", blob)
            if m:
                out.add(m.group(1))
        return out

    deck_all = sorted(bursts_in(slides))
    oct_bursts = sorted(pred)
    by_verdict = {}
    for r in rows:
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
    summary = {
        "deck_bursts": len(deck_all),
        "fit_figures": len(fits),
        "bursts_with_fit": len({f["burst"] for f in fits
                                if re.fullmatch(r"\d{6}[A-Z]?", f["burst"])}),
        "panels": sum(len(f["panels"]) for f in fits),
        "panels_numeric": sum(1 for f in fits for p in f["panels"] if p["status"] == "number"),
        "panels_disagreeing": sum(1 for f in fits for p in f["panels"] if not p["agree"]),
        "october_bursts": len(oct_bursts),
        "rows": len(rows), "by_verdict": by_verdict, "chi2_max": CHI2_MAX,
        "in_deck_not_in_october": [b for b in deck_all if b not in oct_bursts],
        "in_october_not_in_deck": [b for b in oct_bursts if b not in deck_all],
    }
    (BASE / "data" / "compare_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1))

    # ---- size consistency: one burst has one source size, so theta_s must not
    # depend on the observing frequency.  A large spread means F_var is not a pure
    # scintillation modulation in at least one band (dilution / averaging / intrinsic).
    per = {}
    for r in rows:
        if r["verdict"] != "invertible":
            continue
        per.setdefault(r["burst"], []).append(
            {"panel": r["panel"], "model": r["model"], "theta_s_uas": r["theta_s_uas"],
             "size_inv_1e16cm": r["size_inv_1e16cm"], "ratio": r["fvar_over_mp"]})
    cons = {}
    for b, v in per.items():
        th = [x["theta_s_uas"] for x in v]
        cons[b] = {"n_freq": len({x["panel"] for x in v}), "n_rows": len(v),
                   "theta_min": min(th), "theta_max": max(th),
                   "spread": round(max(th) / min(th), 2), "rows": v}
    (BASE / "data" / "size_consistency.json").write_text(
        json.dumps(cons, ensure_ascii=False, indent=1))
    worst = sorted(cons.items(), key=lambda kv: -kv[1]["spread"])[:5]
    print("theta_s spread per burst (max/min):",
          {k: v["spread"] for k, v in worst})

    for k, v in summary.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    sys.exit(main())
