#!/usr/bin/env python

import contextlib
from datetime import datetime
import functools
import gc
import json
import os

from exifread.tags import EXIF_TAGS
from PIL import Image
from PIL.ExifTags import TAGS

from scanner.cache_path import (untrim_base, trim_base, trim_base_custom,
                                json_cache, image_cache, file_mtime, message)

EXIF_DICT = {tag: vals[0] for tag, *vals in EXIF_TAGS.values() if vals}
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
    ("dateTimeOriginal", "DateTimeOriginal"), ("dateTime", "DateTime")
)


def exif_lookup(d, tag):
    """
    When given a dict that contains exif data and a tag, will pull out
    the proper data, converting it to a human-readable format if possible"""
    opts = EXIF_DICT.get(tag, None)
    if not opts:
        return d[tag]
    return opts[d[tag]]


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
            return datetime(1900, 1, 1)
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
    thumb_sizes = [ (75, True), (150, True), (640, False),
                    (1024, False), (1600, False) ]

    def __init__(self, path, thumb_path=None, attributes=None):
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

        try:
            image = Image.open(path)
        except OSError:
            self.is_valid = False
            return
        self._metadata(image)
        self._thumbnails(image, thumb_path, path)

    def _metadata(self, image):
        self._attributes["size"] = image.size
        self._orientation = 1
        try:
            info = image._getexif()
        except OSError:
            return
        if not info:
            return

        exif = {}
        for tag, value in info.items():
            decoded = TAGS.get(tag, tag)
            # TODO: tuple/list AND str??
            if isinstance(value, (tuple, list)) and isinstance(decoded, str) and decoded.startswith("DateTime") and len(value) >= 1:
                value = value[0]
            if isinstance(value, str):
                value = value.strip().partition("\x00")[0]
                if isinstance(decoded, str) and decoded.startswith("DateTime"):
                    try:
                        value = datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                    except (TypeError, ValueError):
                        continue
            exif[decoded] = value

        # Pull out exif data into self._attributes
        for attr, *tags in EXIF_TAGMAP:
            for tag in tags:
                with contextlib.suppress(LookupError):
                    self._attributes[attr] = exif_lookup(exif, tag)
                    break

        # Taken sideways, invert the dimensions
        if "rotated 90" in self._attributes.get("orientation", ""):
            self._attributes["size"] = self._attributes["size"][::-1]


    def _thumbnail(self, image, thumb_path, original_path, size, square=False):
        thumb_path = os.path.join(thumb_path,
                                  image_cache(self._path, size, square))
        info_str = "{} -> {}px".format(os.path.basename(original_path), size)
        if square:
            info_str += ", square"
        message("thumbing", info_str)

        if (os.path.exists(thumb_path) and
            file_mtime(thumb_path) >= self._attributes["dateTimeFile"]):
            return

        gc.collect()
        try:
            image = image.copy()
        except Exception:
            # TODO: Retry still needed?
            # try:
            #     image = image.copy() # we try again to work around PIL bug
            # except OSError as e:
            message("corrupt image", os.path.basename(original_path))
            return
        if square:
            if image.size[0] > image.size[1]:
                left = (image.size[0] - image.size[1]) / 2
                top = 0
                right = image.size[0] - ((image.size[0] - image.size[1]) / 2)
                bottom = image.size[1]
            else:
                left = 0
                top = (image.size[1] - image.size[0]) / 2
                right = image.size[0]
                bottom = image.size[1] - ((image.size[1] - image.size[0]) / 2)
            image = image.crop((left, top, right, bottom))
        image.thumbnail((size, size), Image.ANTIALIAS)
        try:
            image.save(thumb_path, "JPEG", quality=88)
        except IOError as e:
            message("save failure", os.path.basename(thumb_path))
            with contextlib.suppress(OSError):
                os.remove(thumb_path)
        except KeyboardInterrupt:
            with contextlib.suppress(OSError):
                os.remove(thumb_path)
            raise
        gc.collect()

    def _thumbnails(self, image, thumb_path, original_path):
        mirror = image
        if self._orientation == 2:
            # Vertical Mirror
            mirror = image.transpose(Image.FLIP_LEFT_RIGHT)
        elif self._orientation == 3:
            # Rotation 180
            mirror = image.transpose(Image.ROTATE_180)
        elif self._orientation == 4:
            # Horizontal Mirror
            mirror = image.transpose(Image.FLIP_TOP_BOTTOM)
        elif self._orientation == 5:
            # Horizontal Mirror + Rotation 270
            mirror = image.transpose(Image.FLIP_TOP_BOTTOM)\
                          .transpose(Image.ROTATE_270)
        elif self._orientation == 6:
            # Rotation 270
            mirror = image.transpose(Image.ROTATE_270)
        elif self._orientation == 7:
            # Vertical Mirror + Rotation 270
            mirror = image.transpose(Image.FLIP_LEFT_RIGHT)\
                          .transpose(Image.ROTATE_270)
        elif self._orientation == 8:
            # Rotation 90
            mirror = image.transpose(Image.ROTATE_90)
        for size in Photo.thumb_sizes:
            self._thumbnail(mirror, thumb_path, original_path, *size)

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
        return [image_cache(self._path, *size) for size in Photo.thumb_sizes]

    @property
    def date(self):
        if not self.is_valid:
            return datetime(1900, 1, 1)
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

