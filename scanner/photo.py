#!/usr/bin/env python

import contextlib
from datetime import datetime
import hashlib
import json
import logging
import os
import re

from wand.image import Image
from wand.exceptions import WandException

import scanner.globals
from scanner.common import file_mtime
from scanner.exiftool import ExifTool

__log__ = logging.getLogger(__name__)

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

    "fileType": "File:FileType",
}

# Functions to process certain fields
def parse_date(x):
    # TODO: Is parsing any timezones other than 'Z' required?
    for fmt in ('%Y:%m:%d %H:%M:%S', '%Y:%m:%d %H:%M:%SZ',
                '%Y:%m:%d %H:%M:%S.%f', '%Y:%m:%d %H:%M:%S.%fZ'):
        with contextlib.suppress(TypeError, ValueError):
            return datetime.strptime(x, fmt)
    return None

FOCAL_LENGTH_RE = re.compile(".* mm \(35 mm equivalent: (.*) mm\)")
def parse_focal_length(x):
    """Use the 35mm equivalent if possible"""
    if not isinstance(x, str):
        return x
    m = FOCAL_LENGTH_RE.match(x)
    return m.group(1) if m else x

PIXEL2_CAPTION_RE = re.compile("^Maker:.*?,Date:.*?,Ver:.*?,Lens:.*?,Act:.*?,E-.*?$")
def parse_description(x):
    """Strip whitespace and ignore some auto-generated descriptions"""
    x = x.strip()
    # Olympus misuses the description as an advertising opportunity
    if x == "OLYMPUS DIGITAL CAMERA":
        return None
    # Pixel 2 fills the description with redundant technical info
    if PIXEL2_CAPTION_RE.match(x):
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
    "Composite:Orientation": drop_unknown,
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


class MediaObject(object):
    def __init__(self, path, attributes):
        self._path = path
        self._attributes = attributes

        self._thumb_paths = [
            os.path.join(scanner.globals.CONFIG.cache,
                         image_cache(self.hash, size, square))
            for size, _, square in THUMB_SIZES
        ]

    # Sort by date (old -> new), then alphabetical
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
    def name(self):
        return os.path.basename(self._path)

    @property
    def hash(self):
        return self._attributes["hash"]

    @property
    def date(self):
        return self._attributes.get("date", None)

    @property
    def file_date(self):
        return self._attributes["dateModified"]

    @property
    def thumbs(self):
        return self._thumb_paths

    def thumbs_exist(self):
        """Check if all thumbnails exist and are new enough"""
        try:
            return all(file_mtime(x) >= self.file_date for x in self.thumbs)
        except OSError:
            return False

    def generate_thumbs(self):
        """Generate the thumbnails for this media object"""
        raise NotImplementedError()

    def cache_data(self):
        return {
            "name": self.name,
            "date": self.date,
            **self._attributes
        }

    @staticmethod
    def from_path(path, attributes=None):
        """Create a MediaObject subclass from a path"""
        name = os.path.basename(path)
        try:
            mtime = file_mtime(path)
        except OSError as e:
            __log__.error("[unreadable] Failed to get mtime of file '%s'", name)
            return None

        fhash = None
        if not attributes or attributes["dateModified"] >= mtime:
            # Test for change to actual data before rescanning
            fhash = _get_file_hash(path)
            if not attributes or fhash != attributes["hash"]:
                __log__.debug("[scanning] %s", name)
                try:
                    attributes = _extract_file_metadata(path)
                except (KeyError, ValueError):
                    __log__.warning("[unreadable] Failed to extract metadata from '%s'", name)
                    return None

        if "hash" not in attributes:
            attributes["hash"] = fhash or _get_file_hash(path)
        else:
            __log__.debug("[cached] %s", name)

        attributes["dateModified"] = mtime
        try:
            mimetype, subtype = attributes["mimeType"].lower().split("/", 1)
        except KeyError:
            __log__.warning("[unreadable] Couldn't get mimetype of file '%s'", name)
            return None

        try:
            temp = MIMETYPE_MAP[mimetype]
            cls = temp.get(subtype, temp["*"])
        except KeyError:
            __log__.info("[unreadable] Not processing file with mimetype %s/%s", mimetype, subtype)
            return None

        try:
            return cls(path, attributes)
        except Exception as e:
            __log__.warning("[error] Failed to make %s: %s", cls.__name__, e)
        return None


    def __repr__(self):
        return "<{} name={}, path={}>".format(self.__class__.__name__, self.name, self._path)


class Photo(MediaObject):
    def __init__(self, path, attributes):
        super().__init__(path, attributes)

        # Taken sideways, invert the dimensions
        if "rotated 90" in self._attributes.get("orientation", "").lower():
            self._attributes["size"] = self._attributes["size"][::-1]

    def generate_thumbs(self):
        """Generate thumbnails for this Photo"""

        if self.thumbs_exist():
            __log__.debug("[exists] %s", self.name)
            return

        __log__.info("[thumbing] %s", self.name)
        with Image(filename=self._path) as img:

            # If there are multiple frames only use the first one (this
            # prevents GIFs and ICOs from exploding their frames into
            # individual images)
            if img.sequence:
                for _ in range(1, len(img.sequence)):
                    img.sequence.pop()

            # Rotation and conversion to jpeg
            img.auto_orient()
            img.format = 'jpeg'

            for path, (size, quality, square) in zip(self.thumbs, THUMB_SIZES):
                __log__.debug("[thumbing] %s", _thumb_msg(self.name, size, square))

                thumb_dir = os.path.dirname(path)

                if square:
                    crop = min(img.size)
                    img.crop(width=crop, height=crop, gravity='center')
                    img.resize(size, size)
                else:
                    # Work around a bug in Wand's image transformation by
                    # manually calculating the scaled dimensions and resizing
                    ratio = size/max(img.size)
                    img.resize(*[round(x*ratio) for x in img.size])

                img.compression_quality = quality

                try:
                    os.makedirs(thumb_dir, exist_ok=True)
                    img.save(filename=path)
                except IOError as e:
                    __log__.error("[error] Failed to save thumbnail")
                    __log__.debug("[error] %s", e)
                    with contextlib.suppress(OSError):
                        os.remove(path)
                except KeyboardInterrupt:
                    with contextlib.suppress(OSError):
                        os.remove(path)
                    raise


MIMETYPE_MAP = {
    "image": {"*":  Photo}
}

def _get_file_hash(path):
    """Get data from the file - this involves reading it in its entirety"""
    with open(path, 'rb') as fp:
        # Get a salty hash of the file
        file_hash = hashlib.sha1()
        if scanner.globals.CONFIG.salt:
            file_hash.update(scanner.globals.CONFIG.salt)

        while True:
            buff = fp.read(65536)  # 64K chunks
            if not buff:
                break
            file_hash.update(buff)
        return file_hash.hexdigest()

def _extract_file_metadata(path):
    """Get metadata about the file via exiftool"""

    data = {}

    # Get metadata of the file
    info = ExifTool().process_files(path, tags=TAGS_TO_EXTRACT)[0]
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
                except (TypeError, ValueError) as e:
                    __log__.debug("[error] Failed to process value '%s' (%s)", val, e)
                    continue
            if val is not None:
                data[attr] = val
            break

    if scanner.globals.CONFIG.no_location:
        data.pop("gps", None)

    return data

def _thumb_msg(name, size, square):
    """Generate a thumbnail message"""
    msg = "{} -> {}px".format(name, size)
    if square:
        msg += ", square"
    return msg

def image_cache(img_hash, size, square=False):
    """Use the hash to name the file

    Output file under the cache will be:
    `thumbs/[1st 2 chars of hash]/[rest of hash]_[size][square?].jpg`
    """
    if square:
        suffix = "{}s".format(size)
    else:
        suffix = size
    return os.path.join("thumbs", img_hash[:2], "{}_{}.jpg".format(img_hash[2:], suffix))
