#!/usr/bin/env python3
"""Audit the October prediction tables (data/october_tables.json).

Three independent checks, each reported as a count of failures, never fixed in place:

A. The "measured" columns (m, t_scint) must be identical wherever the same burst
   appears at the same frequency in the RISS19 and NE2025 tables. A measurement
   cannot depend on the Galactic electron model.
B. Point-source predictions must follow the relations implemented in iss.py from
   the same burst's SM, nu0 and D_scr (strong-refractive and weak rows only).
C. The Size column must equal D_A(z) * theta_scatt in units of 1e16 cm.

Output: data/october_audit.json and a short markdown summary on stdout.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import iss  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
D = json.loads((BASE / "data" / "october_tables.json").read_text())


def rel(a, b):
    return abs(a - b) / b if b else float("inf")


def main():
    sight = {s["grb"]: s for s in D["sightlines"]}
    rows = D["predictions"]

    # ---------- A: measured column must not depend on the model ----------
    meas = defaultdict(dict)
    for r in rows:
        if r["m"] is not None:
            meas[(r["grb"], r["nu"])][r["model"]] = (r["m"], r["t"], r["regime"])
    a_fail = []
    for (grb, nu), per in meas.items():
        vals = {mm: v for mm, v in per.items()}
        if len(vals) > 1:
            ms = {mm: v[0] for mm, v in vals.items()}
            ts = {mm: v[1] for mm, v in vals.items()}
            if (max(ms.values()) - min(ms.values())) > 0.005 or \
               (None not in ts.values() and max(ts.values()) - min(ts.values()) > 0.05):
                a_fail.append({"grb": grb, "nu": nu, "values": vals})
    # same frequency present in both tables but measured in one only
    a_missing = []
    for (grb, nu), per in meas.items():
        if len(per) == 1:
            model = next(iter(per))
            other = "NE2025" if model == "RISS19" else "RISS19"
            if any(r["grb"] == grb and r["nu"] == nu and r["model"] == other for r in rows):
                a_missing.append({"grb": grb, "nu": nu, "measured_in": model})

    # ---------- B: predictions from SM / nu0 / D_scr ----------
    b = []
    for r in rows:
        s = sight.get(r["grb"])
        if not s or r["regime"] not in ("SR", "W"):
            continue
        m = "RISS19" if r["model"] == "RISS19" else "NE2025"
        nu0, d = s[f"nu0_{m}"], s[f"Dscr_{m}"]
        if not nu0 or not d:
            continue
        if r["regime"] == "W":
            th_exp = iss.theta_f(r["nu"], d)
            ratio = rel(r["theta_scatt"], th_exp)
            b.append({"grb": r["grb"], "model": r["model"], "nu": r["nu"], "regime": "W",
                      "theta_tab": r["theta_scatt"], "theta_exp": round(th_exp, 2),
                      "rel": round(ratio, 3), "mp_tab": r["mp"], "mp_exp": None})
        else:
            th_exp = iss.theta_scatt_strong(r["nu"], nu0, d)
            mp_exp = iss.mp_strong(r["nu"], nu0)
            b.append({"grb": r["grb"], "model": r["model"], "nu": r["nu"], "regime": "SR",
                      "theta_tab": r["theta_scatt"], "theta_exp": round(th_exp, 2),
                      "rel": round(rel(r["theta_scatt"], th_exp), 3),
                      "mp_tab": r["mp"], "mp_exp": round(mp_exp, 3),
                      "mp_rel": round(rel(r["mp"], mp_exp), 3)})

    # ---------- C: Size = D_A * theta_scatt ----------
    c_fail = []
    for r in rows:
        s = sight.get(r["grb"])
        if not s or not s.get("z") or not r["theta_scatt"]:
            continue
        exp = r["theta_scatt"] * 4.848136811e-12 * iss.d_a_cm(s["z"]) / 1e16
        got = r["size"].replace("<", "").replace("≲", "").strip()
        try:
            got = float(got)
        except ValueError:
            continue
        if rel(got, exp) > 0.02:
            c_fail.append({"grb": r["grb"], "model": r["model"], "nu": r["nu"],
                           "regime": r["regime"], "size_tab": got, "size_exp": round(exp, 2),
                           "rel": round(rel(got, exp), 3)})

    bad_theta = [x for x in b if x["rel"] > 0.05]
    bad_mp = [x for x in b if x.get("mp_rel") is not None and x["mp_rel"] > 0.05]
    out = {
        "A_measured_differs_between_models": a_fail,
        "A_measured_in_one_model_only": a_missing,
        "B_theta_mismatch": bad_theta, "B_mp_mismatch": bad_mp,
        "B_checked": len(b), "C_size_mismatch": c_fail,
    }
    (BASE / "data" / "october_audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))

    print(f"A. 同一暴同一频率的实测列不一致: {len(a_fail)} 处；只在一个模型表里有实测: {len(a_missing)} 处")
    for x in a_fail:
        print("   ", x["grb"], x["nu"], "GHz ->", x["values"])
    for x in a_missing:
        print("    只有", x["measured_in"], "给了实测:", x["grb"], x["nu"], "GHz")
    print(f"B. 自洽性检查了 {len(b)} 行（SR/W）：θ_scatt 偏差>5% 的 {len(bad_theta)} 行，m_p 偏差>5% 的 {len(bad_mp)} 行")
    for x in (bad_theta[:8] + bad_mp[:8]):
        print("   ", x)
    print(f"C. Size ≠ D_A θ_scatt (>2%) 的 {len(c_fail)} 行")
    for x in c_fail[:5]:
        print("   ", x)


if __name__ == "__main__":
    main()
