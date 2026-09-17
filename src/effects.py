from __future__ import annotations

import math


def map_intellipan(mode: str, x: float, y: float) -> dict[str, float | str]:
    """Map normalized XY coordinates to the public IntelliPan state contract."""
    x = max(-1.0, min(float(x), 1.0))
    y = max(-1.0, min(float(y), 1.0))

    if mode == "Color":
        return {
            "bass": round(max(0.0, -x) * 100),
            "mid": round(max(0.0, x) * 100),
            "treble": round(max(0.0, y) * 100),
            "warmth": round(max(0.0, -y) * 100),
            "reverb": round(max(0.0, y) * 35),
        }
    if mode == "Modulation":
        return {
            "family": "modulation" if y >= 0 else "chorus / phaser",
            "feedback": round(max(0.0, -x) * 100),
            "simple": round(max(0.0, x) * 100),
            "depth": round(min(1.0, math.hypot(x, y)) * 100),
        }
    if mode == "Position":
        return {
            "pan": round(x * 100),
            "distance": round(max(0.0, y) * 100),
            "width": round(max(0.0, -y) * 100),
        }
    raise ValueError(f"Unknown IntelliPan mode: {mode}")


def format_intellipan(mode: str, parameters: dict[str, float | str]) -> str:
    p = parameters
    if mode == "Color":
        return (
            f"Bass {p['bass']}  Mid {p['mid']}  Treble {p['treble']}\n"
            f"Warmth {p['warmth']}  Reverb {p['reverb']}"
        )
    if mode == "Modulation":
        return (
            f"{str(p['family']).title()}  Depth {p['depth']}\n"
            f"Feedback {p['feedback']}  Simple {p['simple']}"
        )
    if mode == "Position":
        pan = int(p["pan"])
        side = "Center" if pan == 0 else f"{'R' if pan > 0 else 'L'} {abs(pan)}"
        return f"Pan {side}  Distance {p['distance']}\nWidth {p['width']}"
    raise ValueError(f"Unknown IntelliPan mode: {mode}")
