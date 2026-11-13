"""Generation IV species growth rates and integer experience thresholds.

Growth IDs for National Dex species 0–493 (0 is unused): medium fast,
erratic, fluctuating, medium slow, fast, slow. Factual species IDs/rates
extracted from the Platinum personal table (44-byte entries, byte 0x13):
https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Resources/byte/personal/personal_pt
https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/PersonalInfo/Info/PersonalInfo4.cs
Forms share their species' growth rate. No runtime data downloads are needed.
"""
from bisect import bisect_right

# Each line contains 50 consecutive species IDs, beginning at species 0.
SPECIES_GROWTH_RATES = (
    "03333333330000003330000000000333333440044003330000"
    "00000000553333333333335533300000000000005533300000"
    "00550000000554000000550000055555000000000055555555"
    "53333333333000044440550444400333344033334330000030"
    "40000003044003530000554004555500005400000545555555"
    "53333333333000000000333333330055500225551113332240"
    "44345550055001232255220004443333311124400220011111"
    "10344445430003331115455555555555555553333333333330"
    "03333333111100033000000042200434440000004305555335"
    "55500511555300500040003505040055555555555535"
)


def experience_threshold(level: int, growth: int) -> int:
    """Minimum EXP for a level (1–100), using the games' integer rounding."""
    if not 1 <= level <= 100 or not 0 <= growth <= 5:
        raise ValueError("Expected level 1–100 and growth rate 0–5")
    if level == 1:
        return 0
    cube = level ** 3
    if growth == 0:  # Medium fast
        return cube
    if growth == 1:  # Erratic
        if level <= 50:
            return cube * (100 - level) // 50
        if level <= 68:
            return cube * (150 - level) // 100
        if level <= 98:
            return cube * ((1911 - 10 * level) // 3) // 500
        return cube * (160 - level) // 100
    if growth == 2:  # Fluctuating
        if level <= 15:
            return cube * ((level + 1) // 3 + 24) // 50
        if level <= 36:
            return cube * (level + 14) // 50
        return cube * (level // 2 + 32) // 50
    if growth == 3:  # Medium slow
        return 6 * cube // 5 - 15 * level ** 2 + 100 * level - 140
    if growth == 4:  # Fast
        return 4 * cube // 5
    return 5 * cube // 4  # Slow


EXPERIENCE_TABLES = tuple(
    tuple(experience_threshold(level, growth) for level in range(1, 101))
    for growth in range(6)
)


def level_from_experience(species: int, exp: int) -> int | None:
    """Calculate boxed levels; leave unknown species unknown rather than guessing."""
    if not 1 <= species < len(SPECIES_GROWTH_RATES):
        return None
    if exp < 0:
        raise ValueError("Experience cannot be negative")
    growth = int(SPECIES_GROWTH_RATES[species])
    return min(100, bisect_right(EXPERIENCE_TABLES[growth], exp))
