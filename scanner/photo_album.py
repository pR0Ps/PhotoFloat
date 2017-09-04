#!/usr/bin/env python

import contextlib
from datetime import datetime
import functools
import hashlib
import json
import os

from wand.image import Image
from wand.exceptions import WandException

from scanner.utils.exiftool import ExifTool
from scanner.cache_path import (untrim_base, trim_base, trim_base_custom,
                                json_cache, image_cache, file_mtime, message)

# Format: ((attr_name, exif_tag, [alt_exif_tag, ...]), ...)
EXIF_TAGMAP = (
    ("make", "Make"), ("model", "Model"), ("focalLength", "FocalLength"),
    ("iso", "PhotographicSensitivity", "ISO", "ISOSpeedRatings"),
    ("orientation", "Orientation"),
    ("aperture", "FNumber", "ApertureValue"),
    ("exposureTime", "ExposureTime"), ("flash", "Flash"),
    ("lightSource", "LightSource"), ("exposureProgram", "ExposureProgram"),
    ("spectralSensitivity", "SpectralSensitivity"),
    ("meteringMode", "MeteringMode"), ("sensingMethod", "SensingMethod"),
    ("sceneCaptureType", "SceneCaptureType"),
    ("subjectDistanceRange", "SubjectDistanceRange"),
    ("exposureCompensation", "ExposureBiasValue", "ExposureCompensation"),
    ("dateTimeOriginal", "DateTimeOriginal", "DateTimeDigitized"),
    ("dateTime", "DateTime"),
    ("mimeType", "MIMEType"), ("fileType", "FileType")
)
TAGS_TO_EXTRACT = ("EXIF:*", "File:MIMEType", "File:FileType")

# Format: ((max_size, square?), ..)
# Note that these are generated in sequence by continually modifying the same
# buffer. Ex: 1600 -> 1024 -> 150s will work. The reverse won't.
THUMB_SIZES = ((1600, False), (1024, False), (150, True))

# TODO: Remove for performance
@functools.total_ordering
class Album(object):
    def __init__(self, path):
        self._path = trim_base(path)
        self._photos = list()
        self._albums = list()
        self._photos_sorted = True
        self._albums_sorted = True

    @property
    def photos(self):
        return self._photos

    @property
    def albums(self):
        return self._albums

    @property
    def path(self):
        return self._path

    def __str__(self):
        return self.path

    @property
    def cache_path(self):
        return json_cache(self.path)

    @property
    def date(self):
        self._sort()
        if len(self._photos) == 0 and len(self._albums) == 0:
            return datetime.min
        elif len(self._photos) == 0:
            return self._albums[-1].date
        elif len(self._albums) == 0:
            return self._photos[-1].date
        return max(self._photos[-1].date, self._albums[-1].date)

    # functools.total_ordering takes care of the rest
    def __eq__(self, other):
        return self.date == other.date
    def __lt__(self, other):
        return self.date < other.date

    def add_photo(self, photo):
        self._photos.append(photo)
        self._photos_sorted = False

    def add_album(self, album):
        self._albums.append(album)
        self._albums_sorted = False

    def _sort(self):
        if not self._photos_sorted:
            self._photos.sort()
            self._photos_sorted = True
        if not self._albums_sorted:
            self._albums.sort()
            self._albums_sorted = True

    @property
    def empty(self):
        if len(self._photos) != 0:
            return False
        if len(self._albums) == 0:
            return True
        for album in self._albums:
            if not album.empty:
                return False
        return True

    def cache(self, base_dir):
        self._sort()
        with open(os.path.join(base_dir, self.cache_path), 'w') as fp:
            json.dump(self, fp, cls=PhotoAlbumEncoder)

    @staticmethod
    def from_cache(path):
        with open(path, "r") as fp:
            return Album.from_dict(json.load(fp))

    @staticmethod
    def from_dict(dictionary, cripple=True):
        album = Album(dictionary["path"])
        for photo in dictionary["photos"]:
            album.add_photo(Photo.from_dict(photo, untrim_base(album.path)))
        if not cripple:
            for subalbum in dictionary["albums"]:
                album.add_album(Album.from_dict(subalbum), cripple)
        album._sort()
        return album

    def to_dict(self, cripple=True):
        self._sort()
        subalbums = []
        if cripple:
            for sub in self._albums:
                if not sub.empty:
                    subalbums.append({
                        "path": trim_base_custom(sub.path, self._path),
                        "date": sub.date
                    })
        else:
            for sub in self._albums:
                if not sub.empty:
                    subalbums.append(sub)
        return {
            "path": self.path,
            "date": self.date,
            "albums": subalbums,
            "photos": self._photos
        }

    def photo_from_path(self, path):
        for photo in self._photos:
            if trim_base(path) == photo._path:
                return photo
        return None

# TODO: Remove for performance
@functools.total_ordering
class Photo(object):

    def __init__(self, path, thumb_dir=None, attributes=None):
        self._path = trim_base(path)
        self.is_valid = True
        try:
            mtime = file_mtime(path)
        except OSError:
            self.is_valid = False
            return
        if attributes and attributes["dateTimeFile"] >= mtime:
            self._attributes = attributes
            return
        self._attributes = {"dateTimeFile": mtime}

        # Process exifdata into self._attributes
        self._metadata(path)
        if ("fileType" not in self._attributes or
                not self._attributes.get("mimeType", "").lower().startswith("image/")):
            self.is_valid = False
            return

        # Attempt to conserve as much memory as possible when dealing with
        # large files - read data for the hash and image directly from the
        # file. The Image object will store it memory anyway, there's no reason
        # to do it twice.
        try:
            with open(path, 'rb') as f:
                # Get hash of file
                file_hash = hashlib.sha1()
                while True:
                    buff = f.read(65536)  # 64K chunks
                    if not buff:
                        break
                    file_hash.update(buff)
                self._attributes["hash"] = file_hash.hexdigest()

                f.seek(0)

                # Passing the file type as the format is required in some cases
                # to differentiate between file types. Ex: CR2 files are
                # incorrectly identified as TIFF files (and error out during
                # processing) unless the format is specified.
                with Image(file=f, format=self._attributes["fileType"]) as img:
                    # Rotation and conversion to jpeg
                    img.auto_orient()
                    img.format = 'jpeg'
                    img.compression_quality = 85
                    self._thumbnails(img, thumb_dir, path)
        except (OSError, WandException):
            self.is_valid = False

    def _metadata(self, img_path):
        """Get metadata about the image via exiftool"""

        info = ExifTool().process_files(img_path, tags=TAGS_TO_EXTRACT)[0]

        exif = {}
        for tag, value in info.items():
            *tag_type, tag_name = tag.split(":", 1)

            if isinstance(value, str) and tag_name.startswith("DateTime"):
                try:
                    value = datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                except (TypeError, ValueError):
                    continue
            exif[tag_name] = value

        # Pull out exif data into self._attributes
        for attr, *tags in EXIF_TAGMAP:
            for tag in tags:
                with contextlib.suppress(LookupError):
                    self._attributes[attr] = exif[tag]
                    break


    def _thumbnails(self, img, thumb_dir, original_path):
        """Generate thumbnails"""

        self._attributes["size"] = img.size

        # Taken sideways, invert the dimensions
        if "rotated 90" in self._attributes.get("orientation", "").lower():
            self._attributes["size"] = self._attributes["size"][::-1]

        for size, square in THUMB_SIZES:

            thumb_path = os.path.join(thumb_dir,
                                      image_cache(self._path, size, square))
            info_str = "{} -> {}px".format(os.path.basename(original_path), size)
            if square:
                info_str += ", square"
            message("thumbing", info_str)

            if (os.path.exists(thumb_path) and
                file_mtime(thumb_path) >= self._attributes["dateTimeFile"]):
                continue

            if square:
                crop = min(*img.size)
                img.crop(width=crop, height=crop, gravity='center')

            img.transform(resize="{0}x{0}>".format(size))

            try:
                img.save(filename=thumb_path)
            except IOError as e:
                message("save failure", os.path.basename(thumb_path))
                with contextlib.suppress(OSError):
                    os.remove(thumb_path)
            except KeyboardInterrupt:
                with contextlib.suppress(OSError):
                    os.remove(thumb_path)
                raise

    @property
    def name(self):
        return os.path.basename(self._path)

    def __str__(self):
        return self.name

    @property
    def path(self):
        return self._path

    @property
    def image_caches(self):
        return [image_cache(self._path, size, square) for size, square in THUMB_SIZES]

    @property
    def date(self):
        if not self.is_valid:
            return datetime.min
        for x in ("dateTimeOriginal", "dateTime", "dateTimeFile"):
            with contextlib.suppress(KeyError):
                return self._attributes[x]
        raise AssertionError("Photo has no date attribute")

    # functools.total_ordering takes care of the rest
    def __eq__(self, other):
        return self.date == other.date and self.name == other.name
    def __lt__(self, other):
        return self.date < other.date or (self.date == other.date and
                                          self.name < other.name)

    @property
    def attributes(self):
        return self._attributes

    @staticmethod
    def from_dict(dictionary, basepath):
        dictionary.pop("date")
        path = os.path.join(basepath, dictionary.pop("name"))
        for key, value in dictionary.items():
            if key.startswith("dateTime"):
                with contextlib.suppress(TypeError, ValueError):
                    dictionary[key] = datetime.strptime(value,
                                                        "%a %b %d %H:%M:%S %Y")
        return Photo(path, None, dictionary)

    def to_dict(self):
        return {"name": self.name, "date": self.date, **self.attributes}

class PhotoAlbumEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime("%a %b %d %H:%M:%S %Y")
        if isinstance(obj, Album) or isinstance(obj, Photo):
            return obj.to_dict()
        return json.JSONEncoder.default(self, obj)

