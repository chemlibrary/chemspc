"""Offline English display labels; native IDs remain unchanged for save export."""
from pathlib import Path


_DATA = Path(__file__).resolve().parent / 'data' / 'pokemon_names'


def _load(filename: str) -> tuple[str, ...]:
    return tuple((_DATA / filename).read_text(encoding='utf-8').splitlines())


_MOVES = _load('moves.txt')
_ITEMS = _load('items.txt')
_ITEMS_GEN4 = list(_ITEMS)
_ITEMS_GEN4[137:149] = _load('mail_gen4.txt')
_ITEM_TABLES = {
    2: _load('items_gen2.txt'),
    3: _load('items_gen3.txt'),
    4: tuple(_ITEMS_GEN4),
    5: _ITEMS,
    6: _ITEMS,
    7: _ITEMS,
}
_MOVE_LIMITS = {1: 165, 2: 251, 3: 354, 4: 467, 5: 559, 6: 621, 7: 728}
_ITEM_LIMITS = {2: 249, 3: 376, 4: 536, 5: 638, 6: 775, 7: 959}


def _lookup(names: tuple[str, ...], value: int, limit: int, kind: str) -> str:
    if isinstance(value, int) and 0 <= value <= limit and value < len(names):
        name = names[value]
        if name and name != '???':
            return name
    return f'Unknown {kind} (ID {value})'


def move_name(move_id: int, generation: int) -> str:
    if move_id == 0:
        return 'None'
    return _lookup(_MOVES, move_id, _MOVE_LIMITS.get(generation, -1), 'move')


def move_names(move_ids, generation: int) -> list[str]:
    """Keep occupied move slots in their original order, including duplicates."""
    return [move_name(value, generation) for value in move_ids if value != 0]


def item_name(item_id: int, generation: int) -> str:
    if generation == 1:
        # This byte is a catch rate in Gen I, not an item ID.
        return f'No held item (Gen I catch rate: {item_id})'
    if item_id == 0:
        return 'None'
    return _lookup(_ITEM_TABLES.get(generation, ()), item_id,
                   _ITEM_LIMITS.get(generation, -1), 'item')
