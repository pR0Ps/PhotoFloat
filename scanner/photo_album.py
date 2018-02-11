#!/usr/bin/env python

import contextlib
from datetime import datetime
import hashlib
import json
import os
import re

from wand.image import Image
from wand.exceptions import WandException

from scanner.exiftool import ExifTool
from scanner.cache_path import (trim_base, trim_base_custom,
                                json_cache, image_cache, file_mtime, message)

TAGS_TO_EXTRACT = (
    "EXIF:*", "Composite:*", "File:MIMEType", "File:FileType"
)
TAGMAP = {
    # Camera properties
    "make": "EXIF:Make",
    "model": "EXIF:Model",
    "lens": "Composite:LensID",

    # How the photo was taken
    "aperture": "Composite:Aperture",
    "exposureCompensation": "EXIF:ExposureCompensation",
    "exposureProgram": "EXIF:ExposureProgram",
    "flash": "EXIF:Flash",
    "focalLength": "Composite:FocalLength35efl",
    "fov": "Composite:FOV",
    "iso": "Composite:ISO",
    "lightSource": "EXIF:LightSource",
    "meteringMode": "EXIF:MeteringMode",
    "shutter": "Composite:ShutterSpeed",
    "subjectDistanceRange": "EXIF:SubjectDistanceRange",

    # Photo metadata
    "creator": "Composite:Creator",
    "caption": "Composite:Description",
    "keywords": "Composite:Keywords",
    "gps": "Composite:GPSPosition",

    # Properties of the resulting image
    "orientation": "Composite:Orientation",
    "size": "Composite:ImageSize",
    "mimeType": "File:MIMEType",
    "date": ("Composite:GPSDateTime", "Composite:DateTimeOriginal"),
}

# Functions to process certain fields
def parse_date(x):
    # TODO: Is parsing any timezones other than 'Z' required?
    for fmt in ('%Y:%m:%d %H:%M:%S', '%Y:%m:%d %H:%M:%SZ',
                '%Y:%m:%d %H:%M:%S.%f', '%Y:%m:%d %H:%M:%S.%fZ'):
        with contextlib.suppress(TypeError, ValueError):
            return datetime.strptime(x, fmt)
    return None

def parse_focal_length(x):
    """Use the 35mm equivalent if possible"""
    if not isinstance(x, str):
        return x
    m = re.match("(.*) mm \(35 mm equivalent: (.*) mm\)", x)
    return m.group(2) if m else x

def parse_description(x):
    """Strip whitespace and ignore some auto-generated descriptions"""
    x = x.strip()
    # Olympus misuses the description field...
    if x == "OLYMPUS DIGITAL CAMERA":
        return None
    return x

drop_unknown = lambda x: x if not x.lower().startswith("unknown") else None
drop_zero = lambda x: x if x != 0 else None
TAG_PROCESSORS = {
    "Composite:Aperture": drop_zero,
    "Composite:DateTimeOriginal": parse_date,
    "Composite:Description": parse_description,
    "Composite:FocalLength35efl": parse_focal_length,
    "Composite:GPSDateTime": parse_date,
    "Composite:GPSPosition": lambda x: list(map(float, x.split(", "))),
    "Composite:ISO": drop_zero,
    "Composite:ImageSize": lambda x: list(map(int, x.split("x"))),
    "Composite:ShutterSpeed": drop_zero,
    "EXIF:ExposureCompensation": drop_zero,
    "EXIF:ExposureProgram": drop_unknown,
    "EXIF:LightSource": drop_unknown,
    "EXIF:MeteringMode": drop_unknown,
    "EXIF:SubjectDistanceRange": drop_unknown,
}

# Format: ((max_size, square?), ..)
# Note that these are generated in sequence by continually modifying the same
# buffer. Ex: 1600 -> 1024 -> 150s will work. The reverse won't.
THUMB_SIZES = ((1600, 85, False), (1024, 85, False), (150, 70, True))


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
        """The date of the newest photo/subalbum contained in this album"""
        self._sort()
        # Newest is at end for photos, the start for albums
        photo_date = next((x.date for x in reversed(self._photos) if x.date), None)
        album_date = next((x.date for x in self._albums if x.date), None)

        if not photo_date and not album_date:
            return None
        return max(photo_date or album_date, album_date or photo_date)

    # Sort by reverse date taken (new -> old), alphabetical
    @property
    def _sort_data(self):
        return (datetime.max - (self.date or datetime.min), self.path)

    def __lt__(self, other):
        return self._sort_data < other._sort_data
    def __le__(self, other):
        return self._sort_data <= other._sort_data
    def __eq__(self, other):
        return self._sort_data == other._sort_data
    def __ge__(self, other):
        return self._sort_data >= other._sort_data
    def __gt__(self, other):
        return self._sort_data > other._sort_data

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
            "path": trim_base_custom(sub.path, self.path),
            "date": sub.date
        } for sub in self._albums if not sub.empty]
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
        if attributes and attributes["dateModified"] >= mtime:
            self._attributes = attributes
            return

        self._attributes = {"dateModified": mtime}

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

        # Pull metadata into self._attributes
        for attr, tags in TAGMAP.items():
            if isinstance(tags, str):
                tags = [tags]
            for t in tags:
                if t not in info:
                    continue
                val = info[t]
                # Run any processing on the value
                if t in TAG_PROCESSORS:
                    try:
                        val = TAG_PROCESSORS[t](val)
                    except (TypeError, ValueError):
                        continue
                if val is not None:
                    self._attributes[attr] = val
                break

        self._filetype = info["File:FileType"]

        if self._config.no_location:
            self._attributes.pop("gps", None)

        # Taken sideways, invert the dimensions
        if "rotated 90" in self._attributes.get("orientation", "").lower():
            self._attributes["size"] = self._attributes["size"][::-1]

    def _extract_file_data(self, path):
        """Get data from the file - this involves reading it in its entirety"""

        # Attempt to conserve as much memory as possible when dealing with
        # large files - read data for the hash and image directly from the
        # file. The Image object will store it in memory anyway, there's no
        # reason to do it twice.
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
        for size, quality, square in THUMB_SIZES:
            name = os.path.basename(path)
            thumb = os.path.join(self._config.cache, image_cache(self.hash, size, square))
            data = (name, thumb, size, quality, square)

            if (os.path.exists(thumb) and
                    file_mtime(thumb) >= self._attributes["dateModified"]):
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

            for name, path, size, quality, square in thumbnails:

                message("thumbing", self._convert_msg(name, size, square))
                thumb_dir = os.path.dirname(path)

                if square:
                    crop = min(*img.size)
                    img.crop(width=crop, height=crop, gravity='center')

                img.transform(resize="{0}x{0}>".format(size))
                img.compression_quality = quality

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
        return self.is_valid and all(
            os.path.exists(os.path.join(self._config.cache, i)) for i in self.image_caches
        )

    @property
    def image_caches(self):
        if not self.is_valid:
            return None
        return [image_cache(self.hash, size, square) for size, _, square in THUMB_SIZES]

    @property
    def date(self):
        if not self.is_valid:
            return None
        return self._attributes.get("date", None)

    # Sort by date taken (old -> new), alphabetical
    @property
    def _sort_data(self):
        return (self.date or datetime.min, self.name)

    def __lt__(self, other):
        return self._sort_data < other._sort_data
    def __le__(self, other):
        return self._sort_data <= other._sort_data
    def __eq__(self, other):
        return self._sort_data == other._sort_data
    def __ge__(self, other):
        return self._sort_data >= other._sort_data
    def __gt__(self, other):
        return self._sort_data > other._sort_data

    @property
    def attributes(self):
        return self._attributes

    @staticmethod
    def from_dict(config, path, dictionary):
        dictionary.pop("name")
        for k in ("date", "dateModified"):
            if k in dictionary:
                with contextlib.suppress(TypeError, ValueError):
                    dictionary[k] = datetime.strptime(dictionary[k],
                                                        "%a %b %d %H:%M:%S %Y")
        return Photo(config, path, dictionary)

    def to_dict(self):
        return {
            "name": self.name,
            "date": self.date,
            **self.attributes
        }

class PhotoAlbumEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime("%a %b %d %H:%M:%S %Y")
        if isinstance(obj, Album) or isinstance(obj, Photo):
            return obj.to_dict()
        return json.JSONEncoder.default(self, obj)

