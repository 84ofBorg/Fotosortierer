# -*- coding: utf-8 -*-

import csv
import os
import shutil
from datetime import datetime

from cancellation import OperationCancelled, check_cancelled
from metadata import (
    get_best_date,
    PHOTO_EXTS,
    VIDEO_EXTS
)


# ----------------------------------------------------------
# Zielordner berechnen
# ----------------------------------------------------------

def build_target_folder(base_folder, date_obj):

    year = str(date_obj.year)

    month_folder = (
        f"{date_obj.year}-"
        f"{date_obj.month:02d}"
    )

    return os.path.join(
        base_folder,
        year,
        month_folder
    )


# ----------------------------------------------------------
# Datei verschieben
# ----------------------------------------------------------

def get_available_target(source_file, target_folder, reserved_paths=None):

    reserved_paths = reserved_paths or set()

    filename = os.path.basename(
        source_file
    )

    target_file = os.path.join(
        target_folder,
        filename
    )

    # --------------------------------------------------
    # Namenskonflikte vermeiden
    # --------------------------------------------------

    def is_available(path):
        normalized_path = os.path.normcase(
            os.path.abspath(path)
        )
        return (
            not os.path.exists(path)
            and normalized_path not in reserved_paths
        )

    if is_available(target_file):
        return target_file

    stem, ext = os.path.splitext(
        filename
    )

    counter = 1

    while True:

        alternative_name = (
            f"{stem}_{counter}{ext}"
        )

        alternative_path = os.path.join(
            target_folder,
            alternative_name
        )

        if is_available(alternative_path):
            return alternative_path

        counter += 1


def move_file(source_file, target_folder, reserved_paths=None):

    os.makedirs(
        target_folder,
        exist_ok=True
    )

    target_file = get_available_target(
        source_file,
        target_folder,
        reserved_paths
    )

    shutil.move(
        source_file,
        target_file
    )

    if reserved_paths is not None:
        reserved_paths.add(
            os.path.normcase(os.path.abspath(target_file))
        )

    return target_file


def write_test_report(folder, rows):

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(
        folder,
        f"Sortierbericht_{timestamp}.csv"
    )
    counter = 1

    while os.path.exists(report_path):
        report_path = os.path.join(
            folder,
            f"Sortierbericht_{timestamp}_{counter}.csv"
        )
        counter += 1

    with open(report_path, "x", newline="", encoding="utf-8-sig") as report_file:
        writer = csv.writer(report_file, delimiter=";")
        writer.writerow([
            "Datei-Name",
            "Datei-Ursprung",
            "Aktion",
            "Zielort"
        ])
        writer.writerows(rows)

    return report_path


# ----------------------------------------------------------
# Mediendateien suchen
# ----------------------------------------------------------

def find_media(folder, cancel_event=None):

    media_files = []

    extensions = (
        PHOTO_EXTS |
        VIDEO_EXTS
    )

    for root, dirs, files in os.walk(folder):
        check_cancelled(cancel_event)

        for file in files:
            check_cancelled(cancel_event)

            ext = os.path.splitext(
                file
            )[1].lower()

            if ext in extensions:

                media_files.append(
                    os.path.join(
                        root,
                        file
                    )
                )

    return media_files


def remove_empty_folders(folder, log, cancel_event=None):

    root_folder = os.path.normcase(
        os.path.abspath(folder)
    )
    removed_count = 0
    error_count = 0

    for current_folder, _, _ in os.walk(folder, topdown=False):
        check_cancelled(cancel_event)
        normalized_folder = os.path.normcase(
            os.path.abspath(current_folder)
        )

        if normalized_folder == root_folder:
            continue

        if os.path.islink(current_folder):
            continue

        try:
            if os.listdir(current_folder):
                continue

            os.rmdir(current_folder)
            removed_count += 1
            log(f"Leeren Ordner gelöscht: {current_folder}")
        except OSError as error:
            error_count += 1
            log(f"FEHLER beim Prüfen oder Löschen des leeren Ordners {current_folder}")
            log(str(error))

    return removed_count, error_count


# ----------------------------------------------------------
# Hauptfunktion
# ----------------------------------------------------------

def run_sort(folder, test_mode, log, progress=None, cancel_event=None):

    log("")
    log("=" * 60)

    if test_mode:

        log("TESTLAUF gestartet")

    else:

        log("ECHTLAUF gestartet")

    media_files = find_media(folder, cancel_event)

    log(
        f"{len(media_files)} Medien-Dateien gefunden."
    )

    sorted_count = 0
    skipped_count = 0
    unsortable_count = 0
    error_count = 0
    planned_destinations = set()
    report_rows = []

    for index, path in enumerate(
        media_files,
        start=1
    ):
        check_cancelled(cancel_event)
        try:
            date_obj, source = (
                get_best_date(path)
            )

            if not date_obj:
                target_folder = os.path.join(
                    folder,
                    "unsortierbar"
                )
                current_folder = os.path.normcase(
                    os.path.normpath(os.path.dirname(path))
                )
                normalized_target = os.path.normcase(
                    os.path.normpath(target_folder)
                )

                log(
                    f"[{index}] "
                    f"{os.path.basename(path)}"
                )

                if current_folder == normalized_target:
                    skipped_count += 1
                    log("   Bereits im Ordner unsortierbar")
                else:
                    log("   Kein Aufnahmedatum gefunden")
                    log(f"   Ziel   : {target_folder}")

                    check_cancelled(cancel_event)
                    if test_mode:
                        destination = get_available_target(
                            path,
                            target_folder,
                            planned_destinations
                        )
                        planned_destinations.add(
                            os.path.normcase(os.path.abspath(destination))
                        )
                        action = (
                            "Umbenennen und verschieben"
                            if os.path.basename(destination) != os.path.basename(path)
                            else "Verschieben"
                        )
                        report_rows.append([
                            os.path.basename(path),
                            path,
                            action,
                            destination
                        ])
                        log(f"   TESTLAUF -> {action} nach:")
                        log(f"   {destination}")
                    else:
                        new_path = move_file(
                            path,
                            target_folder,
                            planned_destinations
                        )
                        log("   Verschoben nach:")
                        log(f"   {new_path}")

                    unsortable_count += 1

                log("")
                continue

            target_folder = build_target_folder(
                folder,
                date_obj
            )

            current_folder = os.path.normcase(
                os.path.normpath(os.path.dirname(path))
            )
            normalized_target = os.path.normcase(
                os.path.normpath(target_folder)
            )

            if current_folder == normalized_target:
                skipped_count += 1
                continue

            log(
                f"[{index}] "
                f"{os.path.basename(path)}"
            )

            log(
                f"   Quelle : {source}"
            )

            log(
                f"   Datum  : {date_obj}"
            )

            log(
                f"   Ziel   : {target_folder}"
            )

            check_cancelled(cancel_event)
            if test_mode:
                destination = get_available_target(
                    path,
                    target_folder,
                    planned_destinations
                )
                planned_destinations.add(
                    os.path.normcase(os.path.abspath(destination))
                )
                action = (
                    "Umbenennen und verschieben"
                    if os.path.basename(destination) != os.path.basename(path)
                    else "Verschieben"
                )
                report_rows.append([
                    os.path.basename(path),
                    path,
                    action,
                    destination
                ])
                log(f"   TESTLAUF -> {action} nach:")
                log(f"   {destination}")
            else:
                new_path = move_file(
                    path,
                    target_folder,
                    planned_destinations
                )
                log("   Verschoben nach:")
                log(f"   {new_path}")

            log("")
            sorted_count += 1

        except OperationCancelled:
            raise
        except Exception as e:
            error_count += 1
            log(
                f"FEHLER bei "
                f"{os.path.basename(path)}"
            )
            log(str(e))
            log("")
        finally:
            if progress:
                progress(index, len(media_files))

    report_path = None
    check_cancelled(cancel_event)
    if test_mode:
        report_path = write_test_report(folder, report_rows)
        log(f"CSV-Bericht: {report_path}")
    else:
        removed_folders, cleanup_errors = remove_empty_folders(
            folder,
            log,
            cancel_event
        )
        error_count += cleanup_errors
        log(f"Leere Ordner gelöscht: {removed_folders}")

    log("")
    log("=" * 60)

    log("ZUSAMMENFASSUNG")

    log(
        f"Gefunden: {len(media_files)}"
    )

    log(
        f"Sortiert: {sorted_count}"
    )

    log(
        f"Bereits korrekt: {skipped_count}"
    )

    log(
        f"Nicht sortierbar: {unsortable_count}"
    )

    log(
        f"Fehler: {error_count}"
    )

    log("=" * 60)

    return {
        "files": len(media_files),
        "sorted": sorted_count,
        "skipped": skipped_count,
        "unsortable": unsortable_count,
        "errors": error_count,
        "report": report_path
    }


def test():
    return "sorter OK"