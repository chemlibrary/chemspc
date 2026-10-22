"""Flask UI for selectively transferring Pokémon to/from Gen II save files."""
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
from gen2 import BOX_LIMIT, PARTY_LIMIT, Gen2_Save, encode_gen2_text
from pokemon import Pokemon

app = Flask(__name__, instance_relative_config=True)
app.secret_key = os.environ.get("CHEMSPC_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024
app.config["UPLOAD_FOLDER"] = str(Path(app.instance_path) / "staging")
app.config["EXPORT_FOLDER"] = str(Path(app.instance_path) / "exports")

Path(app.instance_path).mkdir(parents=True, exist_ok=True)
Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
Path(app.config["EXPORT_FOLDER"]).mkdir(parents=True, exist_ok=True)


def _workflow_dir() -> Path | None:
    workflow_id = session.get("workflow_id")
    if not isinstance(workflow_id, str) or not re.fullmatch(r"[0-9a-f]{32}", workflow_id):
        return None
    return Path(app.config["UPLOAD_FOLDER"]) / workflow_id


def _uploaded_save_path() -> Path:
    folder = _workflow_dir()
    if folder is None:
        raise ValueError("Upload a save file to start a transfer.")
    path = folder / "source.sav"
    if not path.is_file():
        raise ValueError("The staged save file is missing. Upload it again to continue.")
    return path


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


def _pokemon_from_row(row: dict) -> Pokemon:
    return Pokemon(**{column: row[column] for column in db.POKEMON_COLUMNS})


def compatibility_issues(pokemon: Pokemon) -> list[str]:
    """Return why a stored Pokémon cannot safely be written into an English G/S save.

    This validates the target save's generation and field/ID ranges. It cannot
    verify a Pokémon's legal learnset because the database does not store move
    provenance or a learnset database.
    """
    issues: list[str] = []
    generation = _as_int(pokemon.generation)
    if generation != 2:
        issues.append("Only Generation II Pokémon are supported by the current save writer.")
    species = _as_int(pokemon.species)
    if species is None or not 1 <= species <= 251:
        issues.append("Species ID must be a valid Generation II species (1–251).")
    item = _as_int(pokemon.held_item)
    if item is None or not 0 <= item <= 249:
        issues.append("Held item ID must be in the supported Gold/Silver range (0–249).")
    for field in ("move1", "move2", "move3", "move4"):
        move = _as_int(getattr(pokemon, field))
        if move is None or not 0 <= move <= 251:
            issues.append(f"{field} must be empty (0) or a Generation II move ID (1–251).")
    for field, max_chars in (("name", 10), ("original_trainer_name", 7)):
        value = str(getattr(pokemon, field) or "")
        if len(value) > max_chars:
            issues.append(f"{field.replace('_', ' ')} exceeds the {max_chars}-character game limit.")
        try:
            encode_gen2_text(value)
        except ValueError:
            issues.append(f"{field.replace('_', ' ')} uses a character not supported by English Generation II saves.")
    # Validate binary values here so disabled items do not fail only after selection.
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
        value = _as_int(getattr(pokemon, field))
        if value is None or not 0 <= value <= max_value:
            issues.append(f"{field.replace('_', ' ')} is outside the supported save-file range.")
    return list(dict.fromkeys(issues))


def _has_usable_party_stats(pokemon: Pokemon) -> bool:
    """Box records do not contain calculated stats; avoid writing them as party data."""
    max_hp = _as_int(pokemon.max_hp)
    current_hp = _as_int(pokemon.current_hp)
    if max_hp is None or current_hp is None or max_hp <= 0 or not 0 <= current_hp <= max_hp:
        return False
    return all((_as_int(getattr(pokemon, field)) or 0) > 0 for field in (
        "attack", "defense", "speed", "special_attack", "special_defense"
    ))


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _save_locations(save: Gen2_Save) -> list[dict]:
    entries = []
    for index, pokemon in enumerate(save.party_pokemon):
        entries.append({"locator": f"party:{index}", "position": f"Party slot {index + 1}", "pokemon": pokemon})
    for box_index, box in enumerate(save.box_pokemon):
        for slot_index, pokemon in enumerate(box):
            entries.append({
                "locator": f"box:{box_index}:{slot_index}",
                "position": f"Box {box_index + 1}, slot {slot_index + 1}",
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


@app.route("/", methods=["GET"])
def index():
    db.init_tables()
    active = db.list_pokemon(active=True)
    inactive_count = len(db.list_pokemon(active=False))
    return render_template("index.html", active=active, inactive_count=inactive_count)


@app.route("/open-save", methods=["POST"])
def open_save():
    _require_csrf()
    upload = request.files.get("save_file")
    if upload is None or not upload.filename:
        flash("Choose an English Pokémon Gold/Silver .sav file first.", "error")
        return redirect(url_for("index"))
    safe_name = secure_filename(upload.filename) or "uploaded-save.sav"
    workflow_id = uuid.uuid4().hex
    folder = Path(app.config["UPLOAD_FOLDER"]) / workflow_id
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / "source.sav"
    try:
        upload.save(path)
        # Validate size and parse before making this workflow active.
        save = Gen2_Save(path)
        del save
    except (OSError, ValueError) as exc:
        shutil.rmtree(folder, ignore_errors=True)
        flash(str(exc), "error")
        return redirect(url_for("index"))
    _cleanup_workflow()
    session["workflow_id"] = workflow_id
    session["save_display_name"] = Path(safe_name).stem[:64] or "uploaded-save"
    flash("Save loaded. Select Pokémon to import and/or export; nothing changes until you finalize.", "success")
    return redirect(url_for("manage"))


@app.route("/manage", methods=["GET"])
def manage():
    try:
        save = Gen2_Save(_uploaded_save_path())
    except (OSError, ValueError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))
    source_entries = _save_locations(save)
    active = db.list_pokemon(active=True)
    export_candidates = []
    for row in active:
        pokemon = _pokemon_from_row(row)
        export_candidates.append({"row": row, "pokemon": pokemon, "issues": compatibility_issues(pokemon)})
    return render_template(
        "manage.html", source_entries=source_entries, export_candidates=export_candidates,
        party_count=len(save.party_pokemon), box_count=sum(len(box) for box in save.box_pokemon),
        party_limit=PARTY_LIMIT, box_limit=BOX_LIMIT, display_name=_display_name(),
    )


@app.route("/finalize", methods=["POST"])
def finalize():
    _require_csrf()
    try:
        source_path = _uploaded_save_path()
        save = Gen2_Save(source_path)
        source_entries = _save_locations(save)
        source_by_locator = {entry["locator"]: entry["pokemon"] for entry in source_entries}

        import_locators = request.form.getlist("import_slot")
        if len(import_locators) != len(set(import_locators)):
            raise ValueError("The import selection contains duplicate Pokémon entries.")
        unknown_locators = sorted(set(import_locators) - set(source_by_locator))
        if unknown_locators:
            raise ValueError("One or more selected source Pokémon no longer exist in the staged save.")

        raw_uids = request.form.getlist("export_uid")
        export_uids: list[int] = []
        for raw_uid in raw_uids:
            try:
                uid = int(raw_uid)
            except ValueError as exc:
                raise ValueError("An invalid database Pokémon selection was submitted.") from exc
            if uid not in export_uids:
                export_uids.append(uid)
        if not import_locators and not export_uids:
            raise ValueError("Select at least one Pokémon to import or export before finalizing.")

        export_rows = db.get_active_pokemon(export_uids)
        missing_uids = sorted(set(export_uids) - set(export_rows))
        if missing_uids:
            raise ValueError("One or more selected database Pokémon are no longer active. Reload and try again.")
        export_pokemon: dict[int, Pokemon] = {uid: _pokemon_from_row(row) for uid, row in export_rows.items()}
        incompatibilities = {uid: compatibility_issues(p) for uid, p in export_pokemon.items()}
        incompatibilities = {uid: issues for uid, issues in incompatibilities.items() if issues}
        if incompatibilities:
            details = "; ".join(f"UID {uid}: {', '.join(issues)}" for uid, issues in incompatibilities.items())
            raise ValueError("Cannot export incompatible Pokémon. " + details)

        # Remove selected source Pokémon first; this may free party/box capacity.
        imported_pokemon = [source_by_locator[locator] for locator in import_locators]
        selected_party_indices = {
            int(locator.split(":")[1]) for locator in import_locators if locator.startswith("party:")
        }
        selected_box_slots = set()
        for locator in import_locators:
            if locator.startswith("box:"):
                _, box_index, slot_index = locator.split(":")
                selected_box_slots.add((int(box_index), int(slot_index)))
        save.party_pokemon = [p for index, p in enumerate(save.party_pokemon) if index not in selected_party_indices]
        for box_index, box in enumerate(save.box_pokemon):
            save.box_pokemon[box_index] = [p for slot_index, p in enumerate(box) if (box_index, slot_index) not in selected_box_slots]

        for uid in export_uids:
            pokemon = export_pokemon[uid]
            if len(save.party_pokemon) < PARTY_LIMIT and _has_usable_party_stats(pokemon):
                save.party_pokemon.append(pokemon)
                continue
            target_box = next((box for box in save.box_pokemon if len(box) < BOX_LIMIT), None)
            if target_box is None:
                raise ValueError("No safe storage slot is available for all selected exports. Pokémon without stored party stats must go into a box; free a box slot or reduce the export selection.")
            target_box.append(pokemon)

        export_dir = Path(app.config["EXPORT_FOLDER"])
        export_dir.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        staged_output = export_dir / f".{token}.staged.sav"
        final_output = export_dir / f"{token}.sav"
        save.write_save(staged_output)

        conn = None
        published_output = False
        try:
            conn = db.connect()
            conn.execute("BEGIN IMMEDIATE")
            for pokemon in imported_pokemon:
                db.insert_pokemon(conn, pokemon)
            for uid in export_uids:
                db.move_active_to_inactive(conn, uid)
            # Publish the prepared save before commit; any transaction failure removes it.
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
        session["last_export_name"] = f"{_display_name()}_chemspc.sav"
        _cleanup_workflow()
        return redirect(url_for("result", token=token, imported=len(imported_pokemon), exported=len(export_uids)))
    except (ValueError, OSError, sqlite3.Error) as exc:
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
    return send_file(path, as_attachment=True, download_name=session.get("last_export_name", "chemspc-save.sav"), mimetype="application/octet-stream")


@app.route("/cancel", methods=["POST"])
def cancel():
    _require_csrf()
    _cleanup_workflow()
    flash("Transfer cancelled. The database and original save were not changed.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    db.init_tables()
    # Local-only by default: save files should not be exposed on a public interface.
    app.run(host=os.environ.get("CHEMSPC_HOST", "127.0.0.1"), port=int(os.environ.get("CHEMSPC_PORT", "5000")), debug=False)
