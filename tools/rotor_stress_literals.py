"""Literal values of tests/post/test_rotor_stress.py and test_rotor_growth.py, computed from the formulas of
docs/r5-sources.md section 5 without any srmcore code, so the tests compare two routes. Standard library only:

    python tools/rotor_stress_literals.py
"""
import math

RHO, NU, E = 7490.0, 0.33, 200e9
C1, C2, C3, C4, C5, C6 = 0.049, 1.97, 0.682, 0.265, 0.472, 0.197
Q, Q_SLOPE = 0.4555, 0.1


def shoulder(x):
    s = math.sqrt(x)
    return 1.006 + 1.008 * s - 0.044 * x if x <= 2 else 1.02 + 1.009 * s - 0.048 * x


def flank_y(big, beta, taper, r):
    """Pole half width where the flank crosses radius r, by bisection along the flank from the face end."""
    fx, fy = big * math.cos(beta / 2), big * math.sin(beta / 2)
    lo, hi = 0.0, big
    for _ in range(200):
        s = (lo + hi) / 2
        if math.hypot(fx - s * math.cos(taper), fy + s * math.sin(taper)) > r:
            lo = s
        else:
            hi = s
    return fy + lo * math.sin(taper)


def pole_force(big, b, beta, taper, omega, steps=4000):
    return RHO * omega**2 * sum(2 * r * flank_y(big, beta, taper, r) * (big - b) / steps
                                for r in (b + (big - b) * (i + 0.5) / steps for i in range(steps)))


def model(n, big, a, b, beta, taper, r, rpm):
    omega = 2 * math.pi * rpm / 60
    d = 2 * flank_y(big, beta, taper, b)
    force = (RHO * omega**2 * (d / 2) * (big**2 - b**2) if taper == 0 else pole_force(big, b, beta, taper, omega))
    pitch = 2 * math.pi * b / n
    rim = n * force / (2 * math.pi * b)
    relief = 1 - C1 * d / pitch
    gamma = math.pi / n - math.asin(d / 2 / b) - r / (2 * b)
    t, mean = b - a, (a + b) / 2
    neutral = t / math.log(b / a)
    offset = mean - neutral
    axial = force / (2 * math.sin(math.pi / n))
    inner = axial * mean * (1 - math.sin(gamma) / gamma) * (neutral - a) / (t * offset * a)
    outer = axial * mean * (math.sin(gamma) / gamma - math.cos(gamma)) * (b - neutral) / (t * offset * b)
    bore = (RHO * omega**2 / 4 * ((3 + NU) * b**2 + (1 - NU) * a**2) + 2 * b**2 / (b**2 - a**2) * rim * relief
            + C2 * inner)
    hoop = RHO * omega**2 / 4 * ((1 - NU) * b**2 + (3 + NU) * a**2) + rim * (b**2 + a**2) / (b**2 - a**2)
    q = Q - Q_SLOPE * taper
    length = 1 / math.sqrt(1 / d**2 + 1 / (C5 * t)**2)
    stem = C3 * (pitch / d)**C4 * ((length / r)**q - 1)
    x = C6 * d * math.tanh((big - b) / (C6 * d)) / r
    factor = shoulder(x) * x**(-Q_SLOPE * taper)
    root = stem * force / d + factor * (hoop + 0.5 * outer)
    return dict(relief=relief, half_span=gamma, inner=inner, outer=outer, bore=bore, stem=stem, shoulder=factor,
                root=root, concentration=root / (force / d))


def growth(rpm, taper=0.0, n=6, big=0.04, a=0.01, b=0.022, beta=math.radians(22.0)):
    """Disc and pole elongation at the tip."""
    omega = 2 * math.pi * rpm / 60
    d = 2 * flank_y(big, beta, taper, b)
    rim = n * pole_force(big, b, beta, taper, omega) / (2 * math.pi * b) * (1 - C1 * d / (2 * math.pi * b / n))
    hoop = RHO * omega**2 / 4 * ((1 - NU) * b**2 + (3 + NU) * a**2) + rim * (b**2 + a**2) / (b**2 - a**2)
    disc = b / E * (hoop - NU * rim)
    steps = 800
    pole = 0.0
    for i in range(steps):
        r = b + (big - b) * (i + 0.5) / steps
        moment = sum(s * 2 * flank_y(big, beta, taper, s) * (big - r) / 200
                     for s in (r + (big - r) * (j + 0.5) / 200 for j in range(200)))
        pole += RHO * omega**2 * moment / (2 * flank_y(big, beta, taper, r)) / E * (big - b) / steps
    return disc, pole, disc + pole


def main():
    machine_8_6 = dict(n=6, big=0.04, a=0.01, b=0.022, beta=math.radians(22.0))
    print("8/6, 24000 r/min:", model(**machine_8_6, taper=0.0, r=0.001, rpm=24000))
    print("8/6, taper 0.06:", model(**machine_8_6, taper=0.06, r=0.001, rpm=24000))
    print("6/4 short pole:", model(4, 0.04, 0.012, 0.034, math.radians(36.0), 0.0, 0.003, 24000))
    print("growth 20000 r/min:", growth(20000))
    print("growth, taper 0.1:", growth(20000, 0.1))


if __name__ == "__main__":
    main()
