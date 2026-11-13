"""Boxed levels for Generations I–VII, using factual species growth IDs.

National Dex growth rates from PKHeX personal_bw, personal_xy, personal_uu
resources (verified identical for overlapping species), byte 0x15 of entries
sized 0x3C, 0x40, 0x54 respectively:
https://github.com/kwsch/PKHeX/tree/master/PKHeX.Core/Resources/byte/personal
Gen III uses its native species numbering, from these FireRed tables:
https://github.com/pret/pokefirered/blob/master/src/data/pokemon/species_info.h
https://github.com/pret/pokefirered/blob/master/include/constants/species.h
Only growth-rate numbers are bundled; no runtime downloads are needed.
"""
from bisect import bisect_right

# The same six experience curves apply across all supported generations.
from gen4_growth import EXPERIENCE_TABLES

NATIONAL_GROWTH_RATES = (
    "03333333330000003330000000000333333440044003330000"
    "00000000553333333333335533300000000000005533300000"
    "00550000000554000000550000055555000000000055555555"
    "53333333333000044440550444400333344033334330000030"
    "40000003044003530000554004555500005400000545555555"
    "53333333333000000000333333330055500225551113332240"
    "44345550055001232255220004443333311124400220011111"
    "10344445430003331115455555555555555553333333333330"
    "03333333111100033000000042200434440000004305555335"
    "55500511555300500040003505040055555555555535533333"
    "33330033300000000443330033300004333333003333330000"
    "03333300000000000000334433333300555000000000400003"
    "33555003335550000003300000055550055555555555555555"
    "33333333300333000330000000000000000000000055000000"
    "00055554000000005555553333333330000000000000004000"
    "00000000000333455000045535000000555555555555555555"
    "55555555"
)

GEN3_GROWTH_RATES = (
    "03333333330000003330000000000333333440044003330000"
    "00000000553333333333335533300000000000005533300000"
    "00550000000554000000550000055555000000000055555555"
    "53333333333000044440550444400333344033334330000030"
    "40000003044003530000554004555500005400000545555555"
    "53?????????????????????????33333333300000000033333"
    "31113322400002244300003004221155333225500333330044"
    "44400400110443555225333111344215555012111155555555"
    "555555555554"
)


SPECIES_LIMITS = {1: 151, 2: 251, 3: 411, 4: 493, 5: 649, 6: 721, 7: 807}


def level_from_experience(generation: int, species: int, exp: int) -> int | None:
    """Return level 1–100; unknown species/unused native IDs remain unknown."""
    if generation not in SPECIES_LIMITS or not 1 <= species <= SPECIES_LIMITS[generation]:
        return None
    rates = GEN3_GROWTH_RATES if generation == 3 else NATIONAL_GROWTH_RATES
    growth = rates[species]
    if growth == '?':  # Gen III's unused legacy Unown placeholders (252–276)
        return None
    if exp < 0:
        raise ValueError("Experience cannot be negative")
    return min(100, bisect_right(EXPERIENCE_TABLES[int(growth)], exp))
