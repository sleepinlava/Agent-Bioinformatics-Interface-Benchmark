#!/usr/bin/env python3
"""ABI-Bench Power Analysis — standalone and embeddable.

Computes statistical power for the primary inference: bootstrap 95% CI
lower bound exceeding zero (or a minimum meaningful delta).

Usage:
    python bench/scoring/power_analysis.py --n 5 --delta 12.84 --sd 8.2
    python bench/scoring/power_analysis.py --n 15 --delta 12.84 --sd 8.2 --min-delta 5
"""

import argparse
import json
import math
import sys
from pathlib import Path


def normal_quantile(p: float) -> float:
    """Approximate normal quantile (inverse CDF)."""
    # Rational approximation (Abramowitz & Stegun 26.2.23)
    if p <= 0 or p >= 1:
        return float("inf") if p >= 1 else float("-inf")
    t = math.sqrt(-2 * math.log(min(p, 1 - p)))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    num = c0 + c1 * t + c2 * t * t
    den = 1 + d1 * t + d2 * t * t + d3 * t * t * t
    z = t - num / den
    return -z if p < 0.5 else z


def normal_cdf_upper(z: float) -> float:
    """P(Z > z) for standard normal."""
    return 0.5 * (1 - math.erf(z / math.sqrt(2)))


def power_for_delta_ci(
    n: int,
    observed_delta: float,
    observed_sd: float,
    min_detectable_delta: float = 5.0,
    z_alpha: float = 1.96,
) -> float:
    """Power to detect delta >= min_delta with CI lower bound.

    Power = Φ((delta - min_delta) * sqrt(n) / sd - z_alpha)
    """
    if observed_delta <= min_detectable_delta:
        return 0.0
    se = observed_sd / math.sqrt(n)
    ncp = (observed_delta - min_detectable_delta) / se
    # Power = P(ci_lower > min_delta) = P(delta_hat - z_alpha*SE > min_delta)
    #       = P((delta_hat - true_delta)/SE + true_delta/SE - z_alpha > min_delta/SE)
    #       = Φ(ncp - z_alpha)
    return normal_cdf_upper(z_alpha - ncp)


def required_n_for_power(
    observed_delta: float,
    observed_sd: float,
    min_detectable_delta: float = 5.0,
    target_power: float = 0.80,
    z_alpha: float = 1.96,
) -> int:
    """Minimum n to achieve target power.

    n >= ((z_alpha + z_beta) * sd / (delta - min_delta))^2
    """
    if observed_delta <= min_detectable_delta:
        return None
    z_beta = normal_quantile(target_power)
    return math.ceil(((z_alpha + z_beta) * observed_sd / (observed_delta - min_detectable_delta)) ** 2)


def required_n_for_ci_above_zero(
    observed_delta: float,
    observed_sd: float,
    z_alpha: float = 1.96,
) -> int:
    """Minimum n for CI lower bound to exceed 0."""
    if observed_delta <= 0:
        return None
    return math.ceil((z_alpha * observed_sd / observed_delta) ** 2)


def power_analysis(
    n_replicates: int = 5,
    observed_delta: float = 12.84,
    observed_sd: float = 8.2,
    min_detectable_delta: float = 5.0,
    target_power: float = 0.80,
    z_alpha: float = 1.96,
    max_n: int = 30,
) -> dict:
    """Full power analysis for ABI-Bench primary inference.

    Parameters
    ----------
    n_replicates : Current number of replicates.
    observed_delta : Observed treatment effect (G3−G1 mean delta).
    observed_sd : Standard deviation of the paired delta across replicates.
    min_detectable_delta : Smallest effect considered practically meaningful.
    target_power : Desired statistical power (default 0.80).
    z_alpha : Critical value for CI (default 1.96 for 95% CI).

    Returns
    -------
    dict with power estimates, required n, power curve, and paper-ready text.
    """
    current_se = observed_sd / math.sqrt(n_replicates)
    current_ci_half = z_alpha * current_se
    achieved_power = power_for_delta_ci(n_replicates, observed_delta, observed_sd, min_detectable_delta, z_alpha)
    ci_lower = observed_delta - current_ci_half
    ci_upper = observed_delta + current_ci_half
    req_n = required_n_for_power(observed_delta, observed_sd, min_detectable_delta, target_power, z_alpha)
    n_zero = required_n_for_ci_above_zero(observed_delta, observed_sd, z_alpha)

    # Power curve
    power_curve = {}
    for n in [3, 5, 7, 10, 15, 20, 25, 30]:
        power_curve[str(n)] = round(power_for_delta_ci(n, observed_delta, observed_sd, min_detectable_delta, z_alpha), 3)

    power_pct = round(achieved_power * 100, 1)

    return {
        "design": {
            "n_replicates": n_replicates,
            "observed_delta": round(observed_delta, 2),
            "observed_sd": round(observed_sd, 2),
            "min_detectable_delta": min_detectable_delta,
            "ci_level": "95%",
            "z_alpha": z_alpha,
            "target_power": target_power,
        },
        "results": {
            "achieved_power": round(achieved_power, 3),
            "achieved_power_pct": power_pct,
            "current_se": round(current_se, 2),
            "ci_half_width": round(current_ci_half, 2),
            "ci_lower": round(ci_lower, 2),
            "ci_upper": round(ci_upper, 2),
            "ci_excludes_zero": ci_lower > 0,
            "ci_exceeds_min_delta": ci_lower > min_detectable_delta,
        },
        "sample_size": {
            "required_n_for_target_power": req_n,
            "required_n_for_ci_above_zero": n_zero,
            "required_n_interpretation": (
                f"With δ={observed_delta:.1f} and SD={observed_sd:.1f}, "
                f"n≥{req_n} replicates are needed for {target_power*100:.0f}% power "
                f"to detect δ≥{min_detectable_delta}."
                if req_n else
                f"Observed δ ({observed_delta:.1f}) does not exceed min_delta ({min_detectable_delta}); "
                f"power analysis is not meaningful."
            ),
        },
        "power_curve": power_curve,
        "recommendation": (
            f"With n={n_replicates}, δ={observed_delta:.1f}, SD={observed_sd:.1f}: "
            f"achieved power = {power_pct:.0f}% to detect δ≥{min_detectable_delta}. "
            f"95% CI: [{ci_lower:.1f}, {ci_upper:.1f}] points. "
            + (
                f"✓ CI lower bound > {min_detectable_delta} — primary claim supported."
                if ci_lower > min_detectable_delta
                else f"Need n≥{req_n} for {target_power*100:.0f}% power."
                if req_n
                else ""
            )
        ),
        "paper_methods_blurb": (
            f"With n={n_replicates} replicates per condition and an observed treatment "
            f"effect of δ={observed_delta:.1f} points (SD={observed_sd:.1f}), the study "
            f"achieves {power_pct:.0f}% power to detect a minimum meaningful effect of "
            f"δ≥{min_detectable_delta} points (bootstrap 95% CI, normal approximation). "
            f"The 95% CI half-width at n={n_replicates} is ±{current_ci_half:.1f} points. "
            f"To achieve {target_power*100:.0f}% power, n≥{req_n} replicates are required."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="ABI-Bench Power Analysis")
    parser.add_argument("--n", type=int, default=5, help="Number of replicates")
    parser.add_argument("--delta", type=float, default=12.84, help="Observed treatment effect (G3-G1)")
    parser.add_argument("--sd", type=float, default=8.2, help="SD of the paired delta")
    parser.add_argument("--min-delta", type=float, default=5.0, help="Minimum meaningful delta")
    parser.add_argument("--target-power", type=float, default=0.80, help="Target power")
    parser.add_argument("--output", type=Path, help="Write JSON output")
    args = parser.parse_args()

    pa = power_analysis(
        n_replicates=args.n,
        observed_delta=args.delta,
        observed_sd=args.sd,
        min_detectable_delta=args.min_delta,
        target_power=args.target_power,
    )

    print("\n" + "=" * 70)
    print("ABI-Bench Statistical Power Analysis")
    print("=" * 70)
    print(f"\nDesign parameters:")
    print(f"  n (replicates):     {pa['design']['n_replicates']}")
    print(f"  Observed δ (G3−G1): {pa['design']['observed_delta']} points")
    print(f"  Observed SD:         {pa['design']['observed_sd']} points")
    print(f"  Min meaningful δ:    {pa['design']['min_detectable_delta']} points")
    print(f"  CI level:            {pa['design']['ci_level']}")
    print(f"  Target power:        {pa['design']['target_power']*100:.0f}%")

    print(f"\nResults at n={args.n}:")
    print(f"  SE of delta:         ±{pa['results']['current_se']:.2f} points")
    print(f"  CI half-width:       ±{pa['results']['ci_half_width']:.2f} points")
    print(f"  95% CI:              [{pa['results']['ci_lower']:.1f}, {pa['results']['ci_upper']:.1f}]")
    print(f"  Achieved power:      {pa['results']['achieved_power_pct']:.1f}%")
    print(f"  CI excludes zero:    {'YES ✓' if pa['results']['ci_excludes_zero'] else 'NO ✗'}")
    print(f"  CI exceeds min δ:    {'YES ✓' if pa['results']['ci_exceeds_min_delta'] else 'NO ✗'}")

    print(f"\nSample size requirements:")
    print(f"  For {args.target_power*100:.0f}% power:     n≥{pa['sample_size']['required_n_for_target_power']}")
    print(f"  For CI > 0:              n≥{pa['sample_size']['required_n_for_ci_above_zero']}")

    print(f"\nPower curve (δ={args.delta}, SD={args.sd}, min_δ={args.min_delta}):")
    for n_str, power in pa["power_curve"].items():
        n = int(n_str)
        bar = "█" * min(int(power * 20), 40)
        marker = " ← current" if n == args.n else ""
        print(f"  n={n:>2}: power={power:.3f} ({power*100:.0f}%) {bar}{marker}")

    print(f"\nRecommendation:")
    print(f"  {pa['recommendation']}")

    print(f"\nPaper methods blurb:")
    print(f"  {pa['paper_methods_blurb']}")
    print()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(pa, f, indent=2)
        print(f"Written to {args.output}")


if __name__ == "__main__":
    sys.exit(main())
