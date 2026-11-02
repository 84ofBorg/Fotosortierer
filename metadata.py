# -*- coding: utf-8 -*-

"""Ermittelt das bestmögliche Aufnahme-Datum für Fotos und Videos."""

import os
import re

from datetime import datetime


# ----------------------------------------------------------
# HEIC-Unterstützung aktivieren (optional)
# ----------------------------------------------------------

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()

except Exception:
    pass


# ----------------------------------------------------------
# Dateiformate
# ----------------------------------------------------------

PHOTO_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
    ".webp",
    ".jfif"
}

VIDEO_EXTS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".wmv",
    ".3gp",
    ".mts",
    ".flv"
}


# ----------------------------------------------------------
# Dateiname
# ----------------------------------------------------------

FILENAME_PATTERNS = [

    # 2025-01-30

    (
        re.compile(
            r"(20\d{2})[-_.](\d{2})[-_.](\d{2})"
        ),
        "Dateiname (ISO)"
    ),

    # IMG_20250130_xxxx.jpg

    (
        re.compile(
            r"(20\d{2})(\d{2})(\d{2})"
        ),
        "Dateiname (kompakt)"
    )
]


# ----------------------------------------------------------
# sichere Dateifunktionen
# ----------------------------------------------------------

def safe_mtime(path):

    try:

        return os.path.getmtime(path)

    except OSError:

        return None


# ----------------------------------------------------------
# EXIF
# ----------------------------------------------------------

def get_exif_date(path):

    try:

        from PIL import Image
        from PIL.ExifTags import TAGS

        with Image.open(path) as img:
            exif = img.getexif()

            if not exif:
                return None

            exif_data = {}

            for tag_id, value in exif.items():
                tag_name = TAGS.get(
                    tag_id,
                    str(tag_id)
                )
                exif_data[tag_name] = value

            # Aufnahmezeitpunkte befinden sich bei vielen Kameras im EXIF-Unterbereich.
            try:
                exif_ifd = exif.get_ifd(0x8769)
            except (AttributeError, KeyError, TypeError, ValueError):
                exif_ifd = {}

            for tag_id, value in exif_ifd.items():
                tag_name = TAGS.get(
                    tag_id,
                    str(tag_id)
                )
                exif_data[tag_name] = value

        candidates = [
            "DateTimeOriginal",
            "DateTimeDigitized",
            "DateTime"
        ]

        for field in candidates:
            value = exif_data.get(field)
            if not value:
                continue

            try:
                return datetime.strptime(
                    str(value).strip("\x00"),
                    "%Y:%m:%d %H:%M:%S"
                )
            except (TypeError, ValueError):
                pass

    except (ImportError, OSError, ValueError, TypeError):
        pass

    return None


# ----------------------------------------------------------
# Datum aus Dateiname
# ----------------------------------------------------------

def get_filename_date(path):

    filename = os.path.basename(path)

    for pattern, source in FILENAME_PATTERNS:

        match = pattern.search(filename)

        if not match:

            continue

        try:
            date_obj = datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3))
            )
            return date_obj, source
        except (TypeError, ValueError):
            pass

    return None, None


# ----------------------------------------------------------
# Video-Metadaten
# ----------------------------------------------------------

def get_video_date(path):

    try:

        from hachoir.metadata import extractMetadata
        from hachoir.parser import createParser

        parser = createParser(path)

        if not parser:

            return None

        with parser:

            metadata = extractMetadata(
                parser
            )

        if not metadata:

            return None

        for field in ["creation_date", "creation"]:
            if metadata.has(field):
                value = metadata.get(field)
                if isinstance(value, datetime):
                    return value.replace(
                        tzinfo=None
                    )
    except (ImportError, OSError, ValueError, TypeError):
        pass

    return None


# ----------------------------------------------------------
# Dateidatum
# ----------------------------------------------------------

def get_file_date(path):

    mtime = safe_mtime(path)

    if mtime is None:

        return None

    return datetime.fromtimestamp(
        mtime
    )


# ----------------------------------------------------------
# Hauptfunktion
# ----------------------------------------------------------

def get_best_date(path):

    ext = os.path.splitext(path)[1].lower()

    # ------------------------------------------------------
    # Foto
    # ------------------------------------------------------

    if ext in PHOTO_EXTS:

        exif_date = get_exif_date(path)

        if exif_date:

            return exif_date, "EXIF"

    # ------------------------------------------------------
    # Dateiname
    # ------------------------------------------------------

    filename_date, source = get_filename_date(
        path
    )

    if filename_date:

        return filename_date, source

    # ------------------------------------------------------
    # Video
    # ------------------------------------------------------

    if ext in VIDEO_EXTS:

        video_date = get_video_date(path)

        if video_date:

            return video_date, "Video-Metadaten"

        file_date = get_file_date(path)

        if file_date:
            return file_date, "Dateidatum"

    return None, "Kein Datum gefunden"


# ----------------------------------------------------------
# Testfunktion
# ----------------------------------------------------------

def test():

    return "metadata OK"