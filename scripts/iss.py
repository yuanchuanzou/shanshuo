#!/usr/bin/env python3
"""Walker (1998) ISS relations as used by the 250702B / 210702A papers.

All angles in microarcseconds, frequencies in GHz, D_scr in kpc.

    theta_F      = 8.11 / sqrt(nu * D)                angular radius of the Fresnel zone
    strong refr: theta_scatt = theta_F(nu0) (nu0/nu)^{11/5}
                 m_p         = (nu/nu0)^{17/30}
                 t_scint     = t_ref (nu0/nu)^{11/5}
    weak:        theta_scatt = theta_F(nu),  m_p <~ (nu/nu0)^{-17/12}
    resolved:    m = m_p (theta_scatt/theta_s)^{7/6},  t = t_p (theta_s/theta_scatt)
    inversion:   theta_s = theta_scatt (m_p/m)^{6/7}          (m <= m_p)
    size:        R_perp = D_A theta_s

Self-test: `python scripts/iss.py --test` checks the constants against values
printed in the two reference papers.
"""
import math
import sys

K_THETA_F = 8.11  # muas * sqrt(GHz * kpc)


def theta_f(nu_ghz, d_kpc):
    return K_THETA_F / math.sqrt(nu_ghz * d_kpc)


def theta_scatt_strong(nu_ghz, nu0, d_kpc, exp=11 / 5):
    """Scattering-disk angular radius in the strong (refractive) regime."""
    return theta_f(nu0, d_kpc) * (nu0 / nu_ghz) ** exp


def mp_strong(nu_ghz, nu0, exp=17 / 30):
    return (nu_ghz / nu0) ** exp


def mp_weak(nu_ghz, nu0, exp=-17 / 12):
    return (nu_ghz / nu0) ** exp


def t_strong(nu_ghz, nu0, t_ref_hr, exp=11 / 5):
    return t_ref_hr * (nu0 / nu_ghz) ** exp


def m_resolved(mp, theta_scatt, theta_s):
    """Modulation of a source larger than the scattering disk."""
    return mp * (theta_scatt / theta_s) ** (7 / 6)


def theta_s_from_m(mp, m, theta_scatt):
    """Partially resolved inversion; only valid for m < mp (source larger than screen)."""
    if m >= mp:
        raise ValueError("m >= mp: source is unresolved, inversion gives no size, only a ceiling")
    return theta_scatt * (mp / m) ** (6 / 7)


def t_resolved(t_p, theta_scatt, theta_s):
    return t_p * (theta_s / theta_scatt)


def r_perp_cm(theta_uas, d_a_cm):
    return theta_uas * 4.848136811e-12 * d_a_cm  # 1 uas in rad


def d_a_cm(z, h0=67.4, om=0.315, n=2000):
    """Flat LCDM angular diameter distance in cm (Planck 2018), Simpson integration."""
    c_kms = 299792.458

    def e(x):
        return 1 / math.sqrt(om * (1 + x) ** 3 + (1 - om))

    n = n + (n % 2)  # Simpson needs an even number of intervals
    h = z / n
    s = e(0) + e(z)
    s += 4 * sum(e(i * h) for i in range(1, n, 2))
    s += 2 * sum(e(i * h) for i in range(2, n, 2))
    d_c = c_kms / h0 * s * h / 3  # Mpc
    return d_c / (1 + z) * 3.0856775814913673e24  # cm


def regime(nu_ghz, nu0):
    return "SR" if nu_ghz < nu0 else "W"


def _test():
    ok = True

    def chk(label, got, want, tol):
        nonlocal ok
        good = abs(got - want) <= tol
        ok &= good
        print(f"{'PASS' if good else 'FAIL'} {label}: got {got:.3g}, paper {want:.3g}")

    # --- 250702B (arXiv 2608.03205), NE2025: nu0=6.7 GHz, theta_F=0.5 uas at nu0
    d_250702 = (K_THETA_F / 0.5) ** 2 / 6.7  # implied screen distance, kpc
    for nu, th, mp in ((1.25, 20, 0.39), (3.0, 3, 0.63), (5.5, 0.77, 0.89)):
        chk(f"250702B theta_scatt @{nu} GHz", theta_scatt_strong(nu, 6.7, d_250702), th, 0.12 * th)
        chk(f"250702B m_p @{nu} GHz", mp_strong(nu, 6.7), mp, 0.02)
    chk("250702B t_scint @3 GHz", t_strong(3.0, 6.7, 2.0), 11.7, 1.0)
    chk("250702B t_scint @1.25 GHz", t_strong(1.25, 6.7, 2.0), 80, 10)

    # --- 210702A (arXiv 2211.11212), RISS19: nu0=7.66 GHz, D=0.66 kpc
    for nu, th in ((9.0, 3.4), (16.7, 2.4), (21.2, 2.2)):
        chk(f"210702A theta_F(w) @{nu} GHz", theta_f(nu, 0.66), th, 0.15 * th)

    # --- inversion consistency: 250702B 3 GHz row.
    # Table 2 prints 5.67 uas; reproducing it requires m=0.30, not the 3 GHz value 0.26
    # (0.26 would give 6.25 uas). Recorded here as a known 10% internal inconsistency.
    m63 = 0.63
    th26 = theta_s_from_m(m63, 0.26, theta_scatt_strong(3.0, 6.7, d_250702))
    th30 = theta_s_from_m(m63, 0.30, theta_scatt_strong(3.0, 6.7, d_250702))
    chk("250702B theta_source @3 GHz, m=0.26", th26, 6.25, 0.2)
    chk("250702B theta_source @3 GHz, m=0.30 (matches Table 2 5.67)", th30, 5.67, 0.2)
    # a value above m_p must not be inverted
    try:
        theta_s_from_m(0.30, 0.39, 20.0)
        print("FAIL inversion guard: accepted m>mp")
        ok = False
    except ValueError:
        print("PASS inversion guard rejects m > m_p")

    print("ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(_test())
    print(__doc__)
