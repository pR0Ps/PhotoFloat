#!/usr/bin/env python

from abc import ABC
import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
import re
import subprocess
import tempfile

from wand.exceptions import WandException

import scanner.globals
from scanner.utils import file_mtime, roundto, resize_image
from scanner.exiftool import ExifTool, extract_binary, single_command


__log__ = logging.getLogger(__name__)

# TODO: The tags, tagmap, and lambda functions need to be per-class.
# Should pull every tag possible out of the file, then based on the mimetype pass it to the proper class for processing
TAGS_TO_EXTRACT = (
    "EXIF:*", "Composite:*", "File:MIMEType", "File:FileType",
    "IPTC:Keywords", "PNG:CreationTime"
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
    "keywords": ["IPTC:Keywords", "Composite:Keywords"],
    "gps": "Composite:GPSPosition",

    # Properties of the resulting image
    "orientation": "Composite:Orientation",
    "size": "Composite:ImageSize",
    "mimeType": "File:MIMEType",

    "fileType": "File:FileType",

    # Internal use only (non-serialized)
    "_dateutc": "Composite:GPSDateTime",
    "_date": ["Composite:DateTimeOriginal", "PNG:CreationTime"],
}

# Functions to process certain fields
TIMEZONE_RE = re.compile(r"^(.*)([-+])(\d\d):(\d\d)$")
def parse_date(value):
    """Parses a string value to a datetime from a limited number of formats

    - Only needs to parse the output that `exiftool` produces
    - Accepts "Z" or "[+/-]xx:xx" for timezones
    - Returns a naive or tz-aware datetime depending on the input

    Note that we don't use the -dateFormat option when calling `exiftool` since
    it will add the local timezone to every date it doesn't know the timezone
    for. The default (unspecified) format will output the timezime in one of
    the two formats accepted by this function *only* if it actually knows the
    timezone.
    """
    # UTC datetime
    for fmt in ('%Y:%m:%d %H:%M:%SZ', '%Y:%m:%d %H:%M:%S.%fZ'):
        with contextlib.suppress(TypeError, ValueError):
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)

    # Pop a timezone off the input value and create an offset
    match = TIMEZONE_RE.fullmatch(value)
    if match:
        value, sign, hours, mins = match.groups()
        offset = timedelta(hours=int(hours), minutes=int(mins))
        if sign == "-":
            offset = -offset
    else:
        offset = None

    for fmt in ('%Y:%m:%d %H:%M:%S', '%Y:%m:%d %H:%M:%S.%f'):
        with contextlib.suppress(TypeError, ValueError):
            dt = datetime.strptime(value, fmt)
            break
    else:
        # Failed to parse a datetime
        return None

    # Naive datetime
    if offset is None:
        return dt

    # Datetime with tz offset
    return dt.replace(tzinfo=timezone(offset))

FOCAL_LENGTH_RE = re.compile(r".* mm \(35 mm equivalent: (.*) mm\)")
def parse_focal_length(x):
    """Use the 35mm equivalent if possible"""
    if not isinstance(x, str):
        return x
    m = FOCAL_LENGTH_RE.match(x)
    return m.group(1) if m else x

PIXEL2_CAPTION_RE = re.compile(r"^Maker:.*?,Date:.*?,Ver:.*?,Lens:.*?,Act:.*?,E-.*?$")
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
ensure_list = lambda x: x if isinstance(x, list) else [x]
TAG_PROCESSORS = {
    "Composite:Aperture": drop_zero,
    "Composite:DateTimeOriginal": parse_date,
    "Composite:Description": parse_description,
    "Composite:FocalLength35efl": parse_focal_length,
    "Composite:GPSDateTime": parse_date,
    "Composite:GPSPosition": lambda x: list(map(float, x.split(", "))),
    "Composite:ISO": drop_zero,
    "Composite:ImageSize": lambda x: list(map(int, x.split("x"))),
    "Composite:Keywords": ensure_list,
    "Composite:Orientation": drop_unknown,
    "Composite:ShutterSpeed": drop_zero,
    "EXIF:ExposureCompensation": drop_zero,
    "EXIF:ExposureProgram": drop_unknown,
    "EXIF:Flash": drop_unknown,
    "EXIF:LightSource": drop_unknown,
    "EXIF:MeteringMode": drop_unknown,
    "EXIF:SubjectDistanceRange": drop_unknown,
    "IPTC:Keywords": ensure_list,
    "PNG:CreationTime": parse_date,
}


class MediaObject(ABC):
    def __init__(self, path, attributes):
        self._path = path
        self._attributes = attributes

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
        # Size is always first, extension is always last
        return (image_cache(self.hash, data[0], data[-1]) for data in self.thumb_data)

    @property
    def thumb_sizes(self):
        # Normal order is big -> small, return it reversed
        return [x[0] or "full" for x in reversed(self.thumb_data)]

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
            "previews": self.thumb_sizes,
            **{k:v for k, v in self._attributes.items() if not k.startswith("_")}
        }

    @staticmethod
    def from_path(path, attributes=None):
        """Create a MediaObject subclass from a path"""
        name = os.path.basename(path)
        try:
            mtime = file_mtime(path)
        except OSError as e:
            __log__.error("[unreadable] Failed to get mtime of file '%s'", name, exc_info=True)
            return None

        fhash = None
        if not attributes or attributes["dateModified"] < mtime:
            # Test for change to actual data before rescanning
            fhash = _get_file_hash(path)
            if not attributes or fhash != attributes["hash"]:
                __log__.debug("[scanning] %s", name)
                try:
                    attributes = _extract_file_metadata(path)
                except (UnicodeEncodeError, UnicodeDecodeError):
                    __log__.warning("[unreadable] Encoding error while extracting metadata from '%s'", name, exc_info=True)
                    return None
                except (KeyError, ValueError):
                    __log__.warning("[unreadable] Failed to extract metadata from '%s'", name, exc_info=True)
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
            __log__.warning("[error] Failed to make %s: %s", cls.__name__, e, exc_info=True)
        return None

    def __repr__(self):
        return "<{} name={}, path={}>".format(self.__class__.__name__, self.name, self._path)


class Photo(MediaObject):
    def __init__(self, path, attributes):
        super().__init__(path, attributes)

        # Note that these are generated in sequence by continually modifying the same
        # buffer. Ex: 1600 -> 1024 -> 150 will work. The reverse won't.
        self.thumb_data = [(1024, 85, False, "jpg"), (150, 70, True, "jpg")]

        # Taken sideways, invert the dimensions
        orientation = self._attributes.get("orientation", "")
        if "90" in orientation or "270" in orientation:
            self._attributes["size"] = self._attributes["size"][::-1]

    def generate_thumbs_from_path(self, img_path):
        """Generate thumbnails from a path"""
        try:
            resizer = resize_image(path=img_path, name=self.name)
        except WandException as e:
            __log__.error("[error] Failed to load image: %s", e, exc_info=True)
            return
        for size, quality, square, ext in self.thumb_data:
            path = image_cache(self.hash, size, ext)
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as fp:
                    resizer.send((size, quality, square, fp))
            except Exception as e:
                with contextlib.suppress(OSError):
                    os.remove(path)
                break
            except KeyboardInterrupt:
                with contextlib.suppress(OSError):
                    os.remove(path)
                raise

    def generate_thumbs(self):
        """Generate thumbnails for this Photo"""
        if self.thumbs_exist():
            __log__.debug("[exists] %s", self.name)
            return

        __log__.info("[thumbing] %s", self.name)
        self.generate_thumbs_from_path(self._path)


DATA_SIZE_RE = re.compile(r".*Binary data (\d+) bytes.*")
class RawPhoto(Photo):
    """Custom handling for raw images"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, *kwargs)

        # Generate a full-size jpeg preview
        self.thumb_data.insert(0, (None, 95, False, "jpg"))

    def generate_thumbs(self):
        """Generate thumbnails for this RawPhoto

        Tries to extract an embedded jpeg preview first, falling back to using
        Wand to load and render the raw if one isn't found.
        """
        if self.thumbs_exist():
            __log__.debug("[exists] %s", self.name)
            return

        # Get the tag name for the largest non-thumbnail preview image
        imgs = ExifTool().process_files(self._path, tags="preview:all")[0]
        del imgs['SourceFile']
        d = {}
        for k, v in imgs.items():
            if "thumbnail" in k.lower():
                continue
            m = DATA_SIZE_RE.match(v)
            if m:
                d[int(m.group(1))] = k
            else:
                continue

        # Tag for biggest image
        tag = d[max(d)] if d else None
        if not tag:
            super().generate_thumbs()
            return

        # Extract the preview image from the raw file and use it instead
        with tempfile.NamedTemporaryFile() as fp:
            __log__.debug(
                "[extracting] Preview '%s' from raw file %s",
                tag, self.name
            )
            orientation = self._attributes.get("orientation")
            try:
                extract_binary(self._path, tag, fp)
                # If the file has a non-normal orientation, clone it to the
                # extracted preview.
                if orientation and "normal" not in orientation:
                    __log__.debug(
                        "[extracting] Cloning orientation '%s' to extracted preview of %s",
                        orientation, self.name
                    )
                    single_command(
                        "-overwrite_original", "-Orientation={}".format(orientation),
                        fp.name
                    )
            except subprocess.CalledProcessError as e:
                __log__.error(
                    "[error] Failed to extract preview from image %s: '%s' (returned %d)",
                    self.name, (e.stderr or "").strip(), e.returncode, exc_info=True
                )
                return

            __log__.info("[thumbing] Preview of raw file %s", self.name)
            self.generate_thumbs_from_path(fp.name)

class Video(MediaObject):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Shortest width, CRF, is_thumbnail
        self.thumb_data = [(480, 25, False, "mp4"), (150, 30, True, "mp4")]

        print(self._attributes)


    def generate_thumbs(self):
        """Generate thumbnails for this Photo"""
        # TODO: Pick smallest of 30 and input framerate
        if self.thumbs_exist():
            __log__.debug("[exists] %s", self.name)
            return

        __log__.info("[encoding] video '%s'", self.name)

        # Create an ffmpeg command that will create all the required files
        cmd = ["ffmpeg", "-y", "-i", self._path, "-filter_complex"]

        # Defining the filter(s) to use
        filter_complex = []
        # Filters for all outputs
        # TODO: brings fps up to 30...
        filter_complex.append("[0:v]minterpolate='fps=30:mi_mode=blend'[in]")

        # Split the stream into multiple pipelines
        n = len(self.thumb_data)
        filter_complex.append("[in] split={} {}".format(n, "".join("[in{}]".format(x) for x in range(n))))

        # Create specific filter pipelines for each output
        filters = []
        for i, (size, _, thumbnail, _) in enumerate(self.thumb_data):
            # Scale the video down (keep aspect ratio) to 480px on it's shortest
            # side (or keep the dimensions if it's smaller). Make sure that the
            # dimensions are always divisible by 2 (requirement of h.264).
            filters.append("scale='if(gt(iw, ih),-2,min(iw+mod(iw,2),{0}))':'if(gt(iw,ih),min(ih+mod(ih,2),{0}),-2)':flags=bicubic".format(size))
            if thumbnail:
                # Creating a thumbnail, crop the video to square and play at 2x
                filters.append("crop={0}:{0}".format(size))
                filters.append("setpts={}*PTS".format(1/2))
            # Push in-N -> ','-separated configured filters -> out-N
            filter_complex.append("[in{0}]{1}[out{0}]".format(i, ",".join(filters)))
        # filter_complex sections are split by a ';'
        cmd.append(";".join(filter_complex))

        # Encoding section
        for i, (size, crf, thumbnail, ext) in enumerate(self.thumb_data):
            cmd.extend(["-map", "[out{}]".format(i)])
            if thumbnail:
                # Only take the first 3 seconds of video for a thumbnail
                cmd.extend(["-t", "3"])
            # Encode the video
            cmd.extend(["-c:v", "libx264", "-preset", "slow", "-pix_fmt", "yuv420p", "-crf", str(crf)])
            if not thumbnail:
                # Add in audio (transcoded to AAC @ 160KB/s)
                cmd.extend(["-map", "0:a", "-c:a", "aac", "-b:a", "160k"])
            # Output format and path
            out_path = image_cache(self.hash, size, ext)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            cmd.extend(["-f", ext, out_path])
        import subprocess
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except Exception as e:
            print(e.cmd)
            print(e.stdout)
            print(e.stderr)


MIMETYPE_MAP = {
    "image": {
        "*":  Photo,
        "x-adobe-dng": RawPhoto,
        "x-canon-cr2": RawPhoto,
        "x-canon-cr3": RawPhoto,
        "x-canon-crw": RawPhoto,
        "x-epson-erf": RawPhoto,
        "x-fujifilm-raf": RawPhoto,
        "x-kodak-kdc": RawPhoto,
        "x-minolta-mrw": RawPhoto,
        "x-nikon-nef": RawPhoto,
        "x-olympus-orf": RawPhoto,
        "x-panasonic-rw2": RawPhoto,
        "x-pentax-pef": RawPhoto,
        "x-sigma-x3f": RawPhoto,
        "x-sony-arw": RawPhoto,
        "x-sony-sr2": RawPhoto,
    },
    "video": { "*": Video }
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
                    __log__.debug("[error] Failed to process value '%s' (%s)", val, e, exc_info=True)
                    continue
            if val is not None:
                data[attr] = val
            break

    # Process metadata
    if scanner.globals.CONFIG.no_location:
        data.pop("gps", None)

    # Calculate the effective date and timezone of the object if possible
    # from the internal '_date' and '_dateutc' attributes.
    # Note that we don't use EXIF:TimeZoneOffset not only because it's
    # non-standard, but more importantly, it only stores hours as integers
    # (no half hour time zones).
    date = data.get("_date")
    date_utc = data.get("_dateutc")

    if date and date.tzinfo is not None:
        # Get the timezone offset and remove it from the date
        offset = date.utcoffset()
        date = date.replace(tzinfo=None)
    elif date and date_utc:
        # Calculate the timezone offset from the UTC date
        if date_utc.tzinfo is not None:
            date_utc = date_utc.astimezone(timezone.utc).replace(tzinfo=None)
        offset = date - date_utc
    else:
        offset = None

    data["date"] = date
    if offset is not None:
        data["timezone"] = roundto(offset.total_seconds()/3600, nearest=0.25)
    return data

def image_cache(img_hash, size, ext):
    """Use the hash to name the file

    Output file under the cache will be:
    `thumbs/[1st 2 chars of hash]/[rest of hash]_[size].jpg`
    """
    if size is None:
        size = "full"
    return os.path.join(scanner.globals.CONFIG.cache, "thumbs", img_hash[:2], "{}_{}.{}".format(img_hash[2:], size, ext))
