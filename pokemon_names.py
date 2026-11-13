"""Offline English display labels; native IDs remain unchanged for save export."""
from pathlib import Path

from generation_data import GENERATION_LIMITS


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


def _lookup(names: tuple[str, ...], value: int, limit: int, kind: str) -> str:
    if isinstance(value, int) and 0 <= value <= limit and value < len(names):
        name = names[value]
        if name and name != '???':
            return name
    return f'Unknown {kind} (ID {value})'


def move_name(move_id: int, generation: int) -> str:
    if move_id == 0:
        return 'None'
    return _lookup(_MOVES, move_id, GENERATION_LIMITS.get(generation, {}).get('move', -1), 'move')


def move_names(move_ids, generation: int) -> list[str]:
    """Keep occupied move slots in their original order, including duplicates."""
    return [move_name(value, generation) for value in move_ids if value != 0]


def item_name(item_id: int, generation: int) -> str:
    if generation == 1:
        # The stored byte is a catch rate, not a held item. Preserve it in the
        # native record without exposing it in the held-item display.
        return 'None'
    if item_id == 0:
        return 'None'
    return _lookup(_ITEM_TABLES.get(generation, ()), item_id,
                   GENERATION_LIMITS.get(generation, {}).get('item', -1), 'item')
