#!/usr/bin/env python

import contextlib
from datetime import datetime
import hashlib
import json
import os

from wand.image import Image
from wand.exceptions import WandException

from scanner.exiftool import ExifTool
from scanner.cache_path import (trim_base, trim_base_custom,
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
    ("mimeType", "MIMEType")
)
TAGS_TO_EXTRACT = (
    "EXIF:*", "*:ImageWidth", "*:ImageHeight", "File:MIMEType", "File:FileType"
)

# Format: ((max_size, square?), ..)
# Note that these are generated in sequence by continually modifying the same
# buffer. Ex: 1600 -> 1024 -> 150s will work. The reverse won't.
THUMB_SIZES = ((1600, False), (1024, False), (150, True))


class Album(object):
    def __init__(self, config, path):
        self._config = config
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
        if not self._photos and not self._albums:
            return datetime.min
        elif not self._photos:
            return self._albums[-1].date
        elif not self._albums:
            return self._photos[-1].date
        return max(self._photos[-1].date, self._albums[-1].date)

    def __lt__(self, other):
        return self.date < other.date
    def __le__(self, other):
        return self.date <= other.date
    def __eq__(self, other):
        return self.date == other.date
    def __ge__(self, other):
        return self.date >= other.date
    def __gt__(self, other):
        return self.date > other.date

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
    def photos_cached(self):
        return all(p.thumbs_cached for p in self.photos)

    @property
    def empty(self):
        if self._photos:
            return False
        for album in self._albums:
            if not album.empty:
                return False
        return True

    def cache(self):
        self._sort()
        with open(os.path.join(self._config.cache, self.cache_path), 'w') as fp:
            json.dump(self, fp, separators=(',', ':'), cls=PhotoAlbumEncoder)

    @staticmethod
    def from_cache(config, path):
        with open(path, "r") as fp:
            return Album.from_dict(config, json.load(fp))

    @staticmethod
    def from_dict(config, dictionary):
        album = Album(config, dictionary["path"])
        for photo in dictionary["photos"]:
            path = os.path.join(config.albums, album.path, photo['name'])
            album.add_photo(Photo.from_dict(config, path, photo))
        album._sort()
        return album

    def to_dict(self):
        self._sort()
        subalbums = [{
            "path": trim_base_custom(sub.path, self._path),
            "date": sub.date if sub.date > datetime.min else None
        } for sub in self._albums if not sub.empty]
        return {
            "path": self.path,
            "date": self.date if self.date > datetime.min else None,
            "albums": subalbums,
            "photos": self._photos
        }

    def photo_from_path(self, path):
        for photo in self._photos:
            if trim_base(path) == photo._path:
                return photo
        return None


class Photo(object):

    def __init__(self, config, orig_path, attributes=None):
        self._config = config
        self._path = trim_base(orig_path)
        self._filetype = None
        self.is_valid = True
        try:
            mtime = file_mtime(orig_path)
        except OSError:
            self.is_valid = False
            return

        # Made from previous data - don't reprocess images
        if attributes and attributes["dateTimeFile"] >= mtime:
            self._attributes = attributes
            return

        self._attributes = {"dateTimeFile": mtime}

        # Process exifdata into self._attributes
        try:
            self._extract_file_metadata(orig_path)
        except (ValueError, KeyError):
            # Failed to get exif data or a required metadata field is missing
            self.is_valid = False
            return

        # Avoid processing non-images
        if not self._attributes.get("mimeType", "").lower().startswith("image/"):
            self.is_valid = False
            return
        try:
            self._extract_file_data(orig_path)
        except (OSError, WandException):
            self.is_valid = False
            return

    def _extract_file_metadata(self, img_path):
        """Get metadata about the image via exiftool"""

        info = ExifTool().process_files(img_path, tags=TAGS_TO_EXTRACT)[0]

        exif = {}
        for tag, value in info.items():
            *tag_type, tag_name = tag.split(":", 1)
            tag_type = tag_type[0] if tag_type else None

            if tag_type == "EXIF" and tag_name.startswith("DateTime"):
                try:
                    value = datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                except (TypeError, ValueError):
                    continue

            exif[tag_name] = value

        # Pull out exif data into self._attributes
        for attr, *tags in EXIF_TAGMAP:
            for tag in tags:
                with contextlib.suppress(KeyError):
                    self._attributes[attr] = exif[tag]
                    break

        self._filetype = exif["FileType"]
        self._attributes["size"] = (exif["ImageWidth"],
                                    exif["ImageHeight"])

        # Taken sideways, invert the dimensions
        if "rotated 90" in self._attributes.get("orientation", "").lower():
            self._attributes["size"] = self._attributes["size"][::-1]

    def _extract_file_data(self, path):
        """Get data from the file - this involves reading it in its entirety"""

        # Attempt to conserve as much memory as possible when dealing with
        # large files - read data for the hash and image directly from the
        # file. The Image object will store it memory anyway, there's no reason
        # to do it twice.
        with open(path, 'rb') as fp:
            # Get a salty hash of the file
            file_hash = hashlib.sha1()
            if self._config.salt:
                file_hash.update(self._config.salt)

            while True:
                buff = fp.read(65536)  # 64K chunks
                if not buff:
                    break
                file_hash.update(buff)
            self._attributes["hash"] = file_hash.hexdigest()

            to_generate = self._missing_thumbnails(path)
            if not to_generate:
                return

            fp.seek(0)
            self._generate_thumbnails(fp, to_generate)

    def _convert_msg(self, name, size, square):
        """"""
        msg = "{} -> {}px".format(name, size)
        if square:
            msg += ", square"
        return msg

    def _missing_thumbnails(self, path):
        """Check the filesystem for missing thumbnails for this Photo

        Uses the hash of the current Photo
        """
        to_generate = []
        for size, square in THUMB_SIZES:
            name = os.path.basename(path)
            thumb = os.path.join(self._config.cache, image_cache(self.hash, size, square))
            data = (name, thumb, size, square)

            if (os.path.exists(thumb) and
                    file_mtime(thumb) >= self._attributes["dateTimeFile"]):
                message("exists", self._convert_msg(name, size, square))
                continue

            to_generate.append(data)
        return to_generate

    def _generate_thumbnails(self, img_fp, thumbnails):
        """Generate thumbnails"""

        # Passing the file type as the format is required in some cases
        # to differentiate between file types. Ex: CR2 files are
        # incorrectly identified as TIFF files (and error out during
        # processing) unless the format is specified.
        with Image(file=img_fp, format=self._filetype) as img:
            # Rotation and conversion to jpeg
            img.auto_orient()
            img.format = 'jpeg'
            img.compression_quality = 85

            for name, path, size, square in thumbnails:

                message("thumbing", self._convert_msg(name, size, square))
                thumb_dir = os.path.dirname(path)

                if square:
                    crop = min(*img.size)
                    img.crop(width=crop, height=crop, gravity='center')

                img.transform(resize="{0}x{0}>".format(size))

                try:
                    os.makedirs(thumb_dir, exist_ok=True)
                    img.save(filename=path)
                except IOError as e:
                    message("save failure", path)
                    with contextlib.suppress(OSError):
                        os.remove(path)
                except KeyboardInterrupt:
                    with contextlib.suppress(OSError):
                        os.remove(path)
                    raise

    @property
    def name(self):
        return os.path.basename(self._path)

    def __str__(self):
        return self.name

    @property
    def hash(self):
        if not self.is_valid:
            return None
        return self.attributes["hash"]

    @property
    def path(self):
        return self._path

    @property
    def thumbs_cached(self):
        return all(os.path.exists(os.path.join(self._config.cache, i))
                   for i in self.image_caches)

    @property
    def image_caches(self):
        return [image_cache(self.hash, size, square) for size, square in THUMB_SIZES]

    @property
    def date(self):
        if not self.is_valid:
            return datetime.min
        for x in ("dateTimeOriginal", "dateTime"):
            with contextlib.suppress(KeyError):
                return self._attributes[x]
        return datetime.min

    def _eq_date(self, other):
        return self.date == other.date
    def __lt__(self, other):
        return self.date < other.date or (self._eq_date(other) and self.name < other.name)
    def __le__(self, other):
        return self.date <= other.date or (self._eq_date(other) and self.name <= other.name)
    def __eq__(self, other):
        return self._eq_date(other) and self.name == other.name
    def __ge__(self, other):
        return self.date >= other.date or (self._eq_date(other) and self.name >= other.name)
    def __gt__(self, other):
        return self.date > other.date or (self._eq_date(other) and self.name > other.name)

    @property
    def attributes(self):
        return self._attributes

    @staticmethod
    def from_dict(config, path, dictionary):
        dictionary.pop("date")
        dictionary.pop("name")
        for key, value in dictionary.items():
            if key.startswith("dateTime"):
                with contextlib.suppress(TypeError, ValueError):
                    dictionary[key] = datetime.strptime(value,
                                                        "%a %b %d %H:%M:%S %Y")
        return Photo(config, path, dictionary)

    def to_dict(self):
        return {
            "name": self.name,
            "date": self.date if self.date > datetime.min else None,
            **self.attributes
        }

class PhotoAlbumEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime("%a %b %d %H:%M:%S %Y")
        if isinstance(obj, Album) or isinstance(obj, Photo):
            return obj.to_dict()
        return json.JSONEncoder.default(self, obj)

