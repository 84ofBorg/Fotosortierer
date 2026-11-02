import csv
import os
import shutil
from datetime import datetime

from PIL import Image, ImageOps

from cancellation import check_cancelled
from metadata import PHOTO_EXTS, get_exif_date, get_file_date
from sorter import get_available_target


MAX_BURST_GAP_SECONDS = 120
MAX_HASH_DISTANCE = 8
MIN_SIMILAR_GROUP_SIZE = 4
GROUP_MARKER = ".fotosortierer_similar_group"


def is_group_folder(path):
    if os.path.isfile(os.path.join(path, GROUP_MARKER)):
        return True

    folder_name = os.path.basename(path)
    parent = os.path.dirname(path)

    try:
        return any(
            os.path.splitext(filename)[0] == folder_name
            and os.path.splitext(filename)[1].lower() in PHOTO_EXTS
            for filename in os.listdir(parent)
        )
    except OSError:
        return False


def find_images(folder, cancel_event=None):
    images = []

    for root, dirs, files in os.walk(folder):
        check_cancelled(cancel_event)
        dirs[:] = [
            directory
            for directory in dirs
            if not is_group_folder(os.path.join(root, directory))
        ]

        for filename in files:
            check_cancelled(cancel_event)
            if os.path.splitext(filename)[1].lower() in PHOTO_EXTS:
                images.append(os.path.join(root, filename))

    return images


def difference_hash(path):
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("L")
        image = image.resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(image.getdata())

    image_hash = 0
    for row in range(8):
        for column in range(8):
            left = pixels[row * 9 + column]
            right = pixels[row * 9 + column + 1]
            image_hash = (image_hash << 1) | (left > right)

    return image_hash


def hamming_distance(first_hash, second_hash):
    return bin(first_hash ^ second_hash).count("1")


def capture_time(path):
    return get_exif_date(path) or get_file_date(path)


def find_similar_groups(images, log, progress=None, cancel_event=None):
    images_by_folder = {}
    errors = 0

    for index, path in enumerate(images, start=1):
        check_cancelled(cancel_event)
        try:
            image_hash = difference_hash(path)
            taken_at = capture_time(path)
            if taken_at is None:
                log(f"Übersprungen (kein Aufnahme-/Dateidatum): {path}")
                continue

            folder = os.path.normcase(os.path.abspath(os.path.dirname(path)))
            images_by_folder.setdefault(folder, []).append(
                (taken_at, os.path.normcase(path), path, image_hash)
            )
        except (OSError, ValueError) as error:
            errors += 1
            log(f"FEHLER beim Lesen von {path}")
            log(str(error))
        finally:
            if progress:
                progress(index, len(images))

    groups = []
    for folder_images in images_by_folder.values():
        check_cancelled(cancel_event)
        folder_images.sort(key=lambda item: (item[0], item[1]))
        current_group = []

        for image in folder_images:
            check_cancelled(cancel_event)
            if not current_group:
                current_group = [image]
                continue

            previous = current_group[-1]
            anchor = current_group[0]
            time_gap = (image[0] - previous[0]).total_seconds()
            hash_distance = hamming_distance(image[3], anchor[3])

            if (
                0 <= time_gap <= MAX_BURST_GAP_SECONDS
                and hash_distance <= MAX_HASH_DISTANCE
            ):
                current_group.append(image)
            else:
                if len(current_group) > 1:
                    groups.append(current_group)
                current_group = [image]

        if len(current_group) > 1:
            groups.append(current_group)

    return groups, errors


def unique_group_folder(parent, first_image, reserved_folders):
    name = os.path.splitext(os.path.basename(first_image))[0]
    target_folder = os.path.join(parent, name)
    counter = 1

    while True:
        normalized = os.path.normcase(os.path.abspath(target_folder))
        if normalized in reserved_folders:
            counter += 1
            target_folder = os.path.join(parent, f"{name}_{counter}")
            continue

        if not os.path.exists(target_folder):
            reserved_folders.add(normalized)
            return target_folder

        if is_group_folder(target_folder):
            reserved_folders.add(normalized)
            return target_folder

        counter += 1
        target_folder = os.path.join(parent, f"{name}_{counter}")


def write_report(folder, rows):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(
        folder,
        f"Aehnliche_Fotos_{timestamp}.csv"
    )
    counter = 1

    while os.path.exists(report_path):
        report_path = os.path.join(
            folder,
            f"Aehnliche_Fotos_{timestamp}_{counter}.csv"
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


def run_find_similar(
    folder,
    test_mode,
    log,
    progress=None,
    cancel_event=None
):
    log("")
    log("=" * 60)
    log("ÄHNLICHE FOTOS TESTLAUF gestartet" if test_mode else "ÄHNLICHE FOTOS ECHTLAUF gestartet")

    images = find_images(folder, cancel_event)
    log(f"{len(images)} Bilder gefunden.")

    groups, error_count = find_similar_groups(
        images,
        log,
        progress,
        cancel_event
    )
    report_rows = []
    reserved_files = set()
    reserved_folders = set()
    moved_count = 0
    eligible_groups = 0
    below_threshold_groups = 0

    for group in groups:
        check_cancelled(cancel_event)
        first_image = group[0][2]
        if len(group) < MIN_SIMILAR_GROUP_SIZE:
            below_threshold_groups += 1
            log(
                f"Ähnliche Serie mit {len(group)} Bildern gefunden, "
                f"aber Mindestgröße {MIN_SIMILAR_GROUP_SIZE} nicht erreicht. "
                "Es wird nichts verschoben:"
            )
            for _, _, image_path, _ in group:
                log(f"  Ähnliches Bild: {image_path}")
            continue

        eligible_groups += 1
        target_folder = unique_group_folder(
            os.path.dirname(first_image),
            first_image,
            reserved_folders
        )
        log(f"Ähnliche Serie ({len(group)} Bilder): {target_folder}")
        log(f"  Erstes Bild bleibt am ursprünglichen Ort: {first_image}")

        for _, _, source_path, _ in group[1:]:
            check_cancelled(cancel_event)
            destination = get_available_target(
                source_path,
                target_folder,
                reserved_files
            )
            renamed = os.path.basename(destination) != os.path.basename(source_path)
            action = (
                "Umbenennen und verschieben"
                if renamed
                else "Verschieben"
            )

            check_cancelled(cancel_event)
            if test_mode:
                reserved_files.add(
                    os.path.normcase(os.path.abspath(destination))
                )
                report_rows.append([
                    os.path.basename(source_path),
                    source_path,
                    action,
                    destination
                ])
                log(f"  {action}: {source_path} -> {destination}")
                continue

            os.makedirs(target_folder, exist_ok=True)
            shutil.move(source_path, destination)
            reserved_files.add(
                os.path.normcase(os.path.abspath(destination))
            )
            moved_count += 1
            log(f"  {action}: {source_path} -> {destination}")

    report_path = None
    check_cancelled(cancel_event)
    if test_mode:
        report_path = write_report(folder, report_rows)
        log(f"CSV-Bericht: {report_path}")

    log("")
    log("=" * 60)
    log("ZUSAMMENFASSUNG")
    log(f"Bilder untersucht: {len(images)}")
    log(f"Ähnliche Serien gefunden: {len(groups)}")
    log(
        f"Serien ab {MIN_SIMILAR_GROUP_SIZE} Bildern: "
        f"{eligible_groups}"
    )
    log(f"Kleinere Serien nur protokolliert: {below_threshold_groups}")
    log(f"Zusätzliche Bilder verschoben: {moved_count if not test_mode else len(report_rows)}")
    log(f"Fehler: {error_count}")
    log("=" * 60)

    return {
        "files": len(images),
        "groups": len(groups),
        "similar": sum(len(group) - 1 for group in groups),
        "eligible_groups": eligible_groups,
        "below_threshold_groups": below_threshold_groups,
        "moved": moved_count,
        "errors": error_count,
        "report": report_path
    }


def test():
    return "similar OK"
