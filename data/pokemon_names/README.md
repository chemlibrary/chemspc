# English Pokémon names

Bundled from [PKHeX](https://github.com/kwsch/PKHeX), commit
`038db512bda08f2abf1ba692827b40fe3a4d9a1f`, under GPL-3.0 (see
`PKHeX-LICENSE`). Upstream resources are in `PKHeX.Core/Resources/text/`:

| Local file | Upstream resource | Included IDs |
| --- | --- | --- |
| `moves.txt` | `other/en/text_Moves_en.txt` | 0–728 |
| `items.txt` | `items/text_Items_en.txt` | 0–959 |
| `items_gen2.txt` | `items/gen2/text_ItemsG2_en.txt` | 0–249 |
| `items_gen3.txt` | `items/gen3/text_ItemsG3_en.txt` | 0–376 |
| `mail_gen4.txt` | `items/gen4/text_Mail4_en.txt` | item IDs 137–148 |

Files are normalized to UTF-8 and trimmed to the app's supported ID ranges.
Line positions are significant: empty/unused entries must not be removed.
Generation IV mail overrides the later-generation mail labels, matching
PKHeX's `GameStrings` handling. The tables supply display labels only, not
item legality rules. No network access is needed at runtime.
