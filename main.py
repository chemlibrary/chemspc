"""Flask UI for selective Pokémon transfers across supported Generations I–VII."""
from __future__ import annotations

import os
import re
import secrets
import shutil
import sqlite3
import uuid
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename

import db
from pokemon import Pokemon
from save_formats import (
    GAME_SPECS,
    box_record,
    choose_box_slot,
    get_game_spec,
    has_native_export_record,
    open_save,
    put_in_box,
    supported_games,
    trim_save_file,
)

app = Flask(__name__, instance_relative_config=True)
app.secret_key = os.environ.get("CHEMSPC_SECRET_KEY") or secrets.token_hex(32)
# Permit moderate emulator-added trailers; staged files are normalized to the
# selected game's known raw-save size before any parser sees them.
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(Path(app.instance_path) / "staging")
app.config["EXPORT_FOLDER"] = str(Path(app.instance_path) / "exports")

Path(app.instance_path).mkdir(parents=True, exist_ok=True)
Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
Path(app.config["EXPORT_FOLDER"]).mkdir(parents=True, exist_ok=True)

# Broad ID bounds are per-generation data-format limits, not species-specific
# learnset/legalization checks. Exact game-specific item tables can vary.
GENERATION_LIMITS = {
    1: {"species": 151, "move": 165, "item": None},
    2: {"species": 251, "move": 251, "item": 249},
    3: {"species": 386, "move": 354, "item": 376},
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


def _workflow_dir() -> Path | None:
    workflow_id = session.get("workflow_id")
    if not isinstance(workflow_id, str) or not re.fullmatch(r"[0-9a-f]{32}", workflow_id):
        return None
    return Path(app.config["UPLOAD_FOLDER"]) / workflow_id


def _uploaded_save_path() -> Path:
    folder = _workflow_dir()
    if folder is None:
        raise ValueError("Choose a game and upload a save file to start a transfer.")
    path = folder / "source.sav"
    if not path.is_file():
        raise ValueError("The staged save file is missing. Upload it again to continue.")
    return path


def _active_game() -> str:
    game = session.get("save_game")
    if not isinstance(game, str) or game not in GAME_SPECS:
        raise ValueError("The selected save game is missing. Upload the save again.")
    return game


def _open_staged_save():
    return open_save(_uploaded_save_path(), _active_game())


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


@app.context_processor
def inject_template_helpers():
    return {"csrf_token": _csrf_token}


def _require_csrf() -> None:
    supplied = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not secrets.compare_digest(supplied, expected):
        abort(400, description="Invalid form token. Reload the page and try again.")


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _pokemon_from_row(row: dict) -> Pokemon:
    # row_to_pokemon restores the JSON/base64 native record payload as well as
    # common fields. Legacy rows have no payload and remain importable but may
    # not be exportable to record-preserving generations.
    return db.row_to_pokemon(row)


def compatibility_issues(pokemon: Pokemon, target_game: str) -> list[str]:
    """Check same-generation IDs and whether a native record can be written.

    The save handlers preserve the original binary Pokémon records for most
    generations. This function therefore rejects cross-generation conversion
    and database rows that lack the native data needed for a safe export.
    """
    spec = get_game_spec(target_game)
    gen = spec.generation
    issues: list[str] = []
    stored_gen = _as_int(getattr(pokemon, "generation", None))
    if stored_gen != gen:
        issues.append(
            f"Generation {stored_gen if stored_gen is not None else '?'} Pokémon cannot be exported to Generation {gen}; cross-generation conversion is not implemented."
        )
        return issues

    limits = dict(GENERATION_LIMITS[gen])
    limits.update(TITLE_LIMITS.get(target_game, {}))
    species = _as_int(getattr(pokemon, "species", None))
    if species is None or not 1 <= species <= limits["species"]:
        issues.append(f"Species ID must be between 1 and {limits['species']} for {spec.label}.")

    # In Gen I this byte is catch rate, not a held item. Do not misinterpret it
    # as an item ID; retained Gen I binary records preserve its original meaning.
    if gen != 1:
        item = _as_int(getattr(pokemon, "held_item", None))
        if item is None or not 0 <= item <= (limits["item"] or 0):
            issues.append(f"Held-item ID must be in the supported {spec.label} range (0–{limits['item']}).")

    for field in ("move1", "move2", "move3", "move4"):
        move = _as_int(getattr(pokemon, field, None))
        if move is None or not 0 <= move <= limits["move"]:
            issues.append(f"{field} must be 0 or a valid Generation {gen} move ID (maximum {limits['move']}).")

    if gen == 2:
        from gen2 import encode_gen2_text
        for field, max_chars in (("name", 10), ("original_trainer_name", 7)):
            value = str(getattr(pokemon, field, "") or "")
            if len(value) > max_chars:
                issues.append(f"{field.replace('_', ' ')} exceeds the {max_chars}-character Gen II limit.")
            try:
                encode_gen2_text(value)
            except ValueError:
                issues.append(f"{field.replace('_', ' ')} uses a character unsupported by English Generation II saves.")
        # Gen II serializer writes these shared fields directly into fixed-width
        # records, so validate all widths before finalization.
        for field, max_value in (
            ("original_trainer", 65535), ("exp", 16777215), ("hp_ev", 65535),
            ("attack_ev", 65535), ("defense_ev", 65535), ("speed_ev", 65535),
            ("special_ev", 65535), ("iv", 65535), ("move1_pp", 255),
            ("move2_pp", 255), ("move3_pp", 255), ("move4_pp", 255),
            ("friendship", 255), ("pokerus", 255), ("caught", 65535),
            ("level", 255), ("status_condition", 255), ("current_hp", 65535),
            ("max_hp", 65535), ("attack", 65535), ("defense", 65535),
            ("speed", 65535), ("special_attack", 65535), ("special_defense", 65535),
        ):
            value = _as_int(getattr(pokemon, field, None))
            if value is None or not 0 <= value <= max_value:
                issues.append(f"{field.replace('_', ' ')} is outside the Generation II save-file range.")

    if not has_native_export_record(pokemon, gen):
        if gen == 2:
            # Gen II records are synthesized from the validated shared fields.
            pass
        else:
            issues.append(
                f"This row has no retained native Generation {gen} boxed record. Re-import it using this update before exporting it to a Generation {gen} save."
            )
    return list(dict.fromkeys(issues))


def _save_locations(save, generation: int) -> list[dict]:
    entries = []
    for index, pokemon in enumerate(save.party_pokemon):
        entries.append({
            "locator": f"party:{index}",
            "position": f"Party slot {index + 1}",
            "pokemon": pokemon,
        })
    actual_slot_attr = {3: "gen3_box_slot", 4: "gen4_box_slot", 5: "gen5_box_slot", 6: "gen6_box_slot", 7: "gen7_box_slot"}.get(generation)
    for box_index, box in enumerate(save.box_pokemon):
        for list_index, pokemon in enumerate(box):
            actual_slot = getattr(pokemon, actual_slot_attr, None) if actual_slot_attr else None
            displayed_slot = actual_slot + 1 if isinstance(actual_slot, int) and actual_slot >= 0 else list_index + 1
            entries.append({
                "locator": f"box:{box_index}:{list_index}",
                "position": f"Box {box_index + 1}, slot {displayed_slot}",
                "pokemon": pokemon,
            })
    return entries


def _display_name() -> str:
    return str(session.get("save_display_name") or "uploaded-save")


def _cleanup_workflow() -> None:
    folder = _workflow_dir()
    if folder and folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    session.pop("workflow_id", None)
    session.pop("save_display_name", None)
    session.pop("save_game", None)
    session.pop("save_extension", None)


@app.route("/", methods=["GET"])
def index():
    db.init_tables()
    active = db.list_pokemon(active=True)
    inactive_count = len(db.list_pokemon(active=False))
    return render_template("index.html", active=active, inactive_count=inactive_count, games=supported_games())


@app.route("/open-save", methods=["POST"])
def open_save_route():
    _require_csrf()
    upload = request.files.get("save_file")
    game = (request.form.get("game") or "").strip().lower()
    if game not in GAME_SPECS:
        flash("Choose the exact game/version for the uploaded save.", "error")
        return redirect(url_for("index"))
    if upload is None or not upload.filename:
        flash("Choose a save file first.", "error")
        return redirect(url_for("index"))
    safe_name = secure_filename(upload.filename) or "uploaded-save.sav"
    workflow_id = uuid.uuid4().hex
    folder = Path(app.config["UPLOAD_FOLDER"]) / workflow_id
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / "source.sav"
    try:
        upload.save(path)
        # Trim emulator-added trailers against the selected title's native format
        # before parsing. The uploaded user's original file is never modified.
        original_size, retained_size = trim_save_file(path, game)
        # Parsing validates the selected generation/layout before activation.
        save = open_save(path, game)
        del save
    except (OSError, ValueError, ImportError) as exc:
        shutil.rmtree(folder, ignore_errors=True)
        flash(str(exc), "error")
        return redirect(url_for("index"))
    _cleanup_workflow()
    session["workflow_id"] = workflow_id
    session["save_display_name"] = Path(safe_name).stem[:64] or "uploaded-save"
    session["save_game"] = game
    default_extension = ".main" if get_game_spec(game).generation in (6, 7) else ".sav"
    session["save_extension"] = Path(safe_name).suffix.lower() or default_extension
    if original_size > retained_size:
        flash(
            f"Removed {original_size - retained_size:,} trailing bytes from the upload; "
            f"kept the required {retained_size:,}-byte save for this game.",
            "info",
        )
    flash("Save loaded. Choose Pokémon to import and export; nothing changes until you finalize.", "success")
    return redirect(url_for("manage"))


@app.route("/manage", methods=["GET"])
def manage():
    try:
        save = _open_staged_save()
        game = _active_game()
        spec = get_game_spec(game)
    except (OSError, ValueError, ImportError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))
    source_entries = _save_locations(save, spec.generation)
    active = db.list_pokemon(active=True)
    export_candidates = []
    for row in active:
        pokemon = _pokemon_from_row(row)
        export_candidates.append({"row": row, "pokemon": pokemon, "issues": compatibility_issues(pokemon, game)})
    return render_template(
        "manage.html", source_entries=source_entries, export_candidates=export_candidates,
        party_count=len(save.party_pokemon), box_count=sum(len(box) for box in save.box_pokemon),
        party_limit=spec.party_capacity, box_limit=spec.box_capacity,
        display_name=_display_name(), game_label=spec.label, generation=spec.generation,
        box_count_limit=spec.box_count, game_description=spec.description,
    )


def _parse_selection_ids(raw_values: list[str]) -> list[int]:
    ids: list[int] = []
    for raw in raw_values:
        try:
            uid = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("An invalid database Pokémon selection was submitted.") from exc
        if uid not in ids:
            ids.append(uid)
    return ids


def _remove_imported_from_save(save, import_locators: list[str], source_by_locator: dict[str, Pokemon]) -> list[Pokemon]:
    selected_party_indices = {
        int(locator.split(":")[1]) for locator in import_locators if locator.startswith("party:")
    }
    selected_box_slots: set[tuple[int, int]] = set()
    for locator in import_locators:
        if locator.startswith("box:"):
            _, box_index, list_index = locator.split(":")
            selected_box_slots.add((int(box_index), int(list_index)))
    imported = [source_by_locator[locator] for locator in import_locators]
    save.party_pokemon = [p for index, p in enumerate(save.party_pokemon) if index not in selected_party_indices]
    for box_index, box in enumerate(save.box_pokemon):
        save.box_pokemon[box_index] = [
            p for list_index, p in enumerate(box)
            if (box_index, list_index) not in selected_box_slots
        ]
    return imported


def _add_exports_to_storage(save, export_pokemon: list[Pokemon], generation: int) -> None:
    spec = next((s for s in GAME_SPECS.values() if s.generation == generation and s.box_count == len(save.box_pokemon)), None)
    if spec is None:
        raise ValueError("The selected save handler reported an unsupported storage layout.")
    total_capacity = spec.box_count * spec.box_capacity
    current_count = sum(len(box) for box in save.box_pokemon)
    if current_count + len(export_pokemon) > total_capacity:
        raise ValueError(
            f"Not enough PC storage space: {len(export_pokemon)} Pokémon selected, "
            f"but only {total_capacity - current_count} free storage slots remain."
        )
    for pokemon in export_pokemon:
        placed = False
        for box_index, box in enumerate(save.box_pokemon):
            if len(box) >= spec.box_capacity:
                continue
            slot = choose_box_slot(save, generation, box_index)
            if generation in (3, 4, 5, 6, 7) and slot is None:
                continue
            put_in_box(save, pokemon, generation, box_index, slot or 0)
            placed = True
            break
        if not placed:
            raise ValueError("No safe native PC box slot is available for every selected export.")


def _write_save_copy(save, source_path: Path, staged_output: Path) -> None:
    """Use the native handler's checksum-aware writer, then copy its output."""
    native_output = None
    try:
        native_output = Path(save.write_save())
        if not native_output.is_file():
            raise ValueError("The selected save handler did not create an output save.")
        staged_output.write_bytes(native_output.read_bytes())
    finally:
        if native_output is not None and native_output != source_path and native_output.exists():
            try:
                native_output.unlink()
            except OSError:
                pass


@app.route("/finalize", methods=["POST"])
def finalize():
    _require_csrf()
    try:
        source_path = _uploaded_save_path()
        game = _active_game()
        spec = get_game_spec(game)
        save = open_save(source_path, game)
        source_entries = _save_locations(save, spec.generation)
        source_by_locator = {entry["locator"]: entry["pokemon"] for entry in source_entries}

        import_locators = request.form.getlist("import_slot")
        if len(import_locators) != len(set(import_locators)):
            raise ValueError("The import selection contains duplicate Pokémon entries.")
        unknown_locators = sorted(set(import_locators) - set(source_by_locator))
        if unknown_locators:
            raise ValueError("One or more selected source Pokémon no longer exist in the staged save.")
        export_uids = _parse_selection_ids(request.form.getlist("export_uid"))
        if not import_locators and not export_uids:
            raise ValueError("Select at least one Pokémon to import or export before finalizing.")

        export_rows = db.get_active_pokemon(export_uids)
        missing_uids = sorted(set(export_uids) - set(export_rows))
        if missing_uids:
            raise ValueError("One or more selected database Pokémon are no longer active. Reload and try again.")
        export_pokemon = {uid: _pokemon_from_row(row) for uid, row in export_rows.items()}
        incompatibilities = {
            uid: compatibility_issues(pokemon, game)
            for uid, pokemon in export_pokemon.items()
        }
        incompatibilities = {uid: issues for uid, issues in incompatibilities.items() if issues}
        if incompatibilities:
            details = "; ".join(f"UID {uid}: {', '.join(issues)}" for uid, issues in incompatibilities.items())
            raise ValueError("Cannot export incompatible Pokémon. " + details)

        imported_pokemon = _remove_imported_from_save(save, import_locators, source_by_locator)
        for pokemon in imported_pokemon:
            # Preserve source provenance alongside the retained binary record.
            if not getattr(pokemon, "game_name", None):
                pokemon.game_name = game
            pokemon.source_game = game

        # Storage-only exports are intentional: a boxed native record is the
        # common lossless representation across these save handlers. Party stats
        # are format-dependent and are not guessed from a box record.
        selected_exports = [export_pokemon[uid] for uid in export_uids]
        _add_exports_to_storage(save, selected_exports, spec.generation)

        export_dir = Path(app.config["EXPORT_FOLDER"])
        export_dir.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        staged_output = export_dir / f".{token}.staged.sav"
        final_output = export_dir / f"{token}.sav"
        _write_save_copy(save, source_path, staged_output)

        conn = None
        published_output = False
        try:
            conn = db.connect()
            conn.execute("BEGIN IMMEDIATE")
            for pokemon in imported_pokemon:
                db.insert_pokemon(conn, pokemon)
            for uid in export_uids:
                db.move_active_to_inactive(conn, uid)
            os.replace(staged_output, final_output)
            published_output = True
            conn.commit()
        except Exception:
            if conn is not None:
                conn.rollback()
            if published_output:
                try:
                    final_output.unlink()
                except OSError:
                    pass
            raise
        finally:
            if conn is not None:
                conn.close()
            try:
                staged_output.unlink()
            except OSError:
                pass

        session["last_export_token"] = token
        extension = session.get("save_extension") or (".main" if spec.generation in (6, 7) else ".sav")
        session["last_export_name"] = f"{_display_name()}_chemspc{extension}"
        _cleanup_workflow()
        return redirect(url_for("result", token=token, imported=len(imported_pokemon), exported=len(export_uids)))
    except (ValueError, OSError, sqlite3.Error, ImportError) as exc:
        flash(f"Could not finalize changes: {exc}", "error")
        return redirect(url_for("manage"))


@app.route("/result/<token>", methods=["GET"])
def result(token: str):
    if not re.fullmatch(r"[0-9a-f]{32}", token) or session.get("last_export_token") != token:
        abort(404)
    path = Path(app.config["EXPORT_FOLDER"]) / f"{token}.sav"
    if not path.is_file():
        abort(404)
    try:
        imported = int(request.args.get("imported", "0"))
        exported = int(request.args.get("exported", "0"))
    except ValueError:
        imported, exported = 0, 0
    return render_template("result.html", imported=imported, exported=exported, token=token)


@app.route("/download/<token>", methods=["GET"])
def download(token: str):
    if not re.fullmatch(r"[0-9a-f]{32}", token) or session.get("last_export_token") != token:
        abort(404)
    path = Path(app.config["EXPORT_FOLDER"]) / f"{token}.sav"
    if not path.is_file():
        abort(404)
    return send_file(
        path, as_attachment=True,
        download_name=session.get("last_export_name", "chemspc-save.sav"),
        mimetype="application/octet-stream",
    )


@app.route("/cancel", methods=["POST"])
def cancel():
    _require_csrf()
    _cleanup_workflow()
    flash("Transfer cancelled. The database and original save were not changed.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    db.init_tables()
    # Local-only by default; save files should not be exposed on a public interface.
    app.run(host=os.environ.get("CHEMSPC_HOST", "127.0.0.1"), port=int(os.environ.get("CHEMSPC_PORT", "5000")), debug=False)
