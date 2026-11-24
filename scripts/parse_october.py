#!/usr/bin/env python3
"""Parse the October PDF (RISS19 vs NE2025 prediction tables) into JSON.

Input : <pdf>  (converted with pdftotext -layout)
Output: data/october_tables.json
  {"sightlines":[{grb,z,SM_RISS19,nu0_RISS19,Dscr_RISS19,SM_NE2025,...}],
   "predictions":[{model,grb,nu,m,t,regime,theta_scatt,mp,tp,size,page_line}]}

Column order (both prediction tables):
  GRB | nu(GHz) | m | t_scint(hr) | Regime | theta_scatt(uas) | m_p | t_scint,p(hr) | Size
Burst name is printed only on the first row of each burst.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PDF = BASE.parent / "20261123" / "RISS19及NE2025模型的限制结果.pdf"
NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"


def text_of(pdf):
    txt = Path("/tmp/oct.txt")
    if not txt.exists() or txt.stat().st_mtime < Path(pdf).stat().st_mtime:
        subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)], check=True)
    return txt.read_text()


def f(s):
    s = s.replace("−", "-").replace("<", "").replace("≲", "").replace("~", "").strip()
    m = re.search(NUM, s)
    return float(m.group()) if m else None


def sightlines(text):
    out = []
    for line in text.splitlines():
        m = re.match(r"\s*GRB\s+(\d{6}[A-Z]?)\s+(.*)$", line)
        if not m:
            continue
        rest = m.group(2)
        if "×" not in rest:  # prediction tables, not Table 1
            continue
        cols = re.split(r"\s{2,}", rest.strip())
        if len(cols) < 7:
            continue
        try:
            out.append({
                "grb": m.group(1), "z": f(cols[0]),
                "SM_RISS19": cols[1], "nu0_RISS19": f(cols[2]), "Dscr_RISS19": f(cols[3]),
                "SM_NE2025": cols[4], "nu0_NE2025": f(cols[5]), "Dscr_NE2025": f(cols[6]),
            })
        except Exception:  # noqa: BLE001
            continue
    return out


def predictions(text):
    lines = text.splitlines()
    model, out, cur = None, [], None
    for ln, line in enumerate(lines):
        cap = re.search(r"Table\s*\d+:\s*(.*)", line)
        if cap:
            window = " ".join([cap.group(1)] + lines[ln + 1:ln + 3])
            if "NE2025" in window:
                model = "NE2025"
            elif "RIS-" in window or "RISS19" in window:
                model = "RISS19"
            continue
        if "Regime" in line:
            continue
        m = re.match(r"\s*(GRB\s+(\d{6}[A-Z]?)|)\s+(" + NUM + r")\s+(.*)$", line)
        if not m or model is None:
            continue
        nu = f(m.group(3))
        rest = m.group(4).strip()
        cols = re.split(r"\s{2,}", rest.strip())
        if len(cols) < 6:
            continue
        if m.group(2):
            cur = m.group(2)
        if cur is None:
            continue
        out.append({
            "model": model, "grb": cur, "line": ln + 1,
            "nu": nu,
            "m": f(cols[0]) if cols[0].strip() not in ("–", "-") else None,
            "t": f(cols[1]) if cols[1].strip() not in ("–", "-") else None,
            "regime": cols[2].strip(),
            "theta_scatt": f(cols[3]), "mp": f(cols[4]), "tp": f(cols[5]),
            "size": cols[6].strip() if len(cols) > 6 else "",
        })
    return out


def main():
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else PDF
    text = text_of(pdf)
    preds = predictions(text)
    data = {"pdf": str(pdf), "sightlines": sightlines(text), "predictions": preds}
    (BASE / "data" / "october_tables.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    bursts = sorted({p["grb"] for p in preds})
    print(f"sightlines={len(data['sightlines'])} rows={len(preds)} bursts={len(bursts)}")
    print("models:", {m: sum(1 for p in preds if p["model"] == m) for m in {p["model"] for p in preds}})
    meas = [p for p in preds if p["m"] is not None]
    print("rows with a measured m:", len(meas))
    for p in meas:
        print(f"  {p['model']:<7} {p['grb']:<9} nu={p['nu']:<6} m={p['m']} t={p['t']} {p['regime']}")


if __name__ == "__main__":
    main()
