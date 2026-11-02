import csv
import hashlib
import os
from datetime import datetime

from cancellation import check_cancelled
from metadata import PHOTO_EXTS, VIDEO_EXTS
from sorter import get_available_target, move_file


DUPLICATE_FOLDER_NAME = "Duplikate zum entfernen"
VIDEO_DUPLICATE_FOLDER_NAME = "Video-Duplikate zum entfernen"


def _find_media(folder, extensions, excluded_folder_name, cancel_event=None):
    media_files = []
    duplicate_folder = os.path.normcase(
        os.path.abspath(
            os.path.join(folder, excluded_folder_name)
        )
    )

    for root, dirs, files in os.walk(folder):
        check_cancelled(cancel_event)
        dirs[:] = [
            directory
            for directory in dirs
            if os.path.normcase(
                os.path.abspath(os.path.join(root, directory))
            ) != duplicate_folder
        ]

        for filename in files:
            check_cancelled(cancel_event)
            if os.path.splitext(filename)[1].lower() in extensions:
                media_files.append(os.path.join(root, filename))

    return media_files


def find_images(folder, cancel_event=None):
    return _find_media(
        folder,
        PHOTO_EXTS,
        DUPLICATE_FOLDER_NAME,
        cancel_event
    )


def find_videos(folder, cancel_event=None):
    return _find_media(
        folder,
        VIDEO_EXTS,
        VIDEO_DUPLICATE_FOLDER_NAME,
        cancel_event
    )


def hash_file(path, cancel_event=None):
    digest = hashlib.sha256()

    with open(path, "rb") as image_file:
        while True:
            check_cancelled(cancel_event)
            chunk = image_file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

    return digest.digest()


def write_duplicate_report(folder, rows, report_prefix="Duplikatbericht"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(
        folder,
        f"{report_prefix}_{timestamp}.csv"
    )
    counter = 1

    while os.path.exists(report_path):
        report_path = os.path.join(
            folder,
            f"Duplikatbericht_{timestamp}_{counter}.csv"
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


def _run_remove_duplicates(
    folder,
    test_mode,
    log,
    progress=None,
    cancel_event=None,
    find_media=find_images,
    duplicate_folder_name=DUPLICATE_FOLDER_NAME,
    media_label="Bilder",
    report_prefix="Duplikatbericht"
):
    log("")
    log("=" * 60)
    log(
        f"{media_label.upper()}-DUPLIKATE "
        f"{'TESTLAUF' if test_mode else 'ECHTLAUF'} gestartet"
    )

    media_files = find_media(folder, cancel_event)
    log(f"{len(media_files)} {media_label.lower()} gefunden.")

    groups = {}
    error_count = 0

    for index, path in enumerate(media_files, start=1):
        check_cancelled(cancel_event)
        try:
            file_size = os.path.getsize(path)
            digest = hash_file(path, cancel_event)
            modified_time = os.path.getmtime(path)
            groups.setdefault((file_size, digest), []).append(
                (modified_time, os.path.normcase(path), path)
            )
        except OSError as error:
            error_count += 1
            log(f"FEHLER bei {os.path.basename(path)}")
            log(str(error))
        finally:
            if progress:
                progress(index, len(media_files))

    duplicate_folder = os.path.join(folder, duplicate_folder_name)
    duplicate_count = 0
    kept_count = 0
    reserved_destinations = set()
    report_rows = []

    for matching_files in groups.values():
        check_cancelled(cancel_event)
        if len(matching_files) < 2:
            continue

        matching_files.sort(key=lambda item: (item[0], item[1]))
        kept_path = matching_files[0][2]
        log(f"Original behalten: {kept_path}")
        kept_count += 1

        for _, _, duplicate_path in matching_files[1:]:
            check_cancelled(cancel_event)
            try:
                destination = get_available_target(
                    duplicate_path,
                    duplicate_folder,
                    reserved_destinations
                )
                renamed = (
                    os.path.basename(destination)
                    != os.path.basename(duplicate_path)
                )
                action = (
                    "Umbenennen und verschieben"
                    if renamed
                    else "Verschieben"
                )

                check_cancelled(cancel_event)
                if test_mode:
                    reserved_destinations.add(
                        os.path.normcase(os.path.abspath(destination))
                    )
                    report_rows.append([
                        os.path.basename(duplicate_path),
                        duplicate_path,
                        action,
                        destination
                    ])
                    log(f"{action}: {duplicate_path} -> {destination}")
                else:
                    moved_path = move_file(
                        duplicate_path,
                        duplicate_folder,
                        reserved_destinations
                    )
                    log(f"{action}: {duplicate_path} -> {moved_path}")

                duplicate_count += 1
            except OSError as error:
                error_count += 1
                log(f"FEHLER beim Verschieben von {duplicate_path}")
                log(str(error))

    report_path = None
    check_cancelled(cancel_event)
    if test_mode:
        report_path = write_duplicate_report(
            folder,
            report_rows,
            report_prefix
        )
        log(f"CSV-Bericht: {report_path}")

    log("")
    log("=" * 60)
    log("ZUSAMMENFASSUNG")
    log(f"{media_label} untersucht: {len(media_files)}")
    log(f"Duplikatgruppen: {kept_count}")
    log(f"Duplikate verschoben: {duplicate_count}")
    log(f"Fehler: {error_count}")
    log("=" * 60)

    return {
        "files": len(media_files),
        "groups": kept_count,
        "duplicates": duplicate_count,
        "errors": error_count,
        "report": report_path
    }


def run_remove_duplicates(
    folder,
    test_mode,
    log,
    progress=None,
    cancel_event=None
):
    return _run_remove_duplicates(
        folder,
        test_mode,
        log,
        progress,
        cancel_event
    )


def run_remove_video_duplicates(
    folder,
    test_mode,
    log,
    progress=None,
    cancel_event=None
):
    return _run_remove_duplicates(
        folder,
        test_mode,
        log,
        progress,
        cancel_event,
        find_media=find_videos,
        duplicate_folder_name=VIDEO_DUPLICATE_FOLDER_NAME,
        media_label="Videos",
        report_prefix="Video-Duplikatbericht"
    )


def test():
    return "duplicates OK"
