"""Shared generation/title ID bounds used by display and export validation.

Species IDs are National Pokédex IDs except in Generation III, whose parser
and writer use native IDs: 1–251 and 277–411 (252–276 are unused placeholders).
These bounds describe formats, not species-specific legality.
"""

# Broad ID bounds are per-generation data-format limits, not species-specific
# learnset/legalization checks. Exact game-specific item tables can vary.
GENERATION_LIMITS = {
    1: {"species": 151, "move": 165, "item": None},
    2: {"species": 251, "move": 251, "item": 249},
    3: {"species": 411, "move": 354, "item": 376},
    4: {"species": 493, "move": 467, "item": 536},
    5: {"species": 649, "move": 559, "item": 638},
    6: {"species": 721, "move": 621, "item": 775},
    7: {"species": 807, "move": 728, "item": 959},
}
# Narrow titles whose usable species/item index range differs within one
# generation. These caps reject known newer-title IDs; they do not encode every
# game-specific gap in an item's catalog.
TITLE_LIMITS = {
    "x": {"species": 721, "item": 717, "move": 617},
    "y": {"species": 721, "item": 717, "move": 617},
    "omegaruby": {"species": 721, "item": 775, "move": 621},
    "alphasapphire": {"species": 721, "item": 775, "move": 621},
    "sun": {"species": 802, "item": 920},
    "moon": {"species": 802, "item": 920},
    "ultrasun": {"species": 807, "item": 959},
    "ultramoon": {"species": 807, "item": 959},
}

