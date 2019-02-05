#!/usr/bin/env python

import calendar
from datetime import datetime
import functools
import json
import logging
import os.path

from wand.image import Image

import scanner.globals


__log__ = logging.getLogger(__name__)


def roundto(num, nearest):
    """Rounds a number to the nearest interval"""
    return nearest * round(float(num)/nearest)

def trim_base_custom(path, base):
    if path.startswith(base):
        path = path[len(base):]
    if path.startswith('/'):
        path = path[1:]
    return path

def trim_base(path):
    return trim_base_custom(path, scanner.globals.CONFIG.albums)

def cache_base(path):
    path = trim_base(path).replace(os.sep, '-').replace(' ', '_').\
            replace('(', '').replace('&', '').replace(',', '').\
            replace(')', '').replace('#', '').replace('[', '').\
            replace(']', '').replace('"', '').replace("'", '').\
            replace('_-_', '-').lower()
    while path.find("--") != -1:
        path = path.replace("--", "-")
    while path.find("__") != -1:
        path = path.replace("__", "_")
    if not path:
        path = "root"
    return path

def json_cache(path):
    return "{}.json".format(cache_base(path))

def file_mtime(path):
    return datetime.fromtimestamp(int(os.path.getmtime(path)))

def coroutine(func):
    """Decorator that primes a coroutine automatically"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        cr = func(*args, **kwargs)
        next(cr)
        return cr
    return wrapper

@coroutine
def resize_image(path=None, blob=None, img=None, name=None,
                 fmt='jpeg', auto_orient=True, upscale=False):
    """A coroutine that resizes a single image multiple times

    Note that the same image buffer is used across multiple operations so
    operations should be ordered from highest-quality to lowest.

    Parameters:
     - path/blob/img: Source data  (img is a Wand Image object)
     - name: The name of the file (for logging purposes only)
     - fmt: The image format of the resulting images (default: 'jpeg')
     - auto_orient: Automatically orient image before processing (default: true)
     - upscale: Upscale images to fit the desired resolution if they're too small
                (default: False)

    Receives a 4-tuple of (size, quality, square, fp)
     - size: The image will be resized so that the longest edge is this many pixels
     - quality: The JPEG quality level
     - square: If true, the images will be cropped to square before being resized
     - fp: A file-like object to write() the result into
    """
    if sum([bool(path), bool(blob), bool(img)]) != 1:
        raise ValueError("One of 'path', 'blob', or 'img' is required")
    if path:
        img = Image(filename=path)
    elif blob:
        img = Image(blob=blob)

    with img:
        # If there are multiple frames only use the first one (this
        # prevents GIFs and ICOs from exploding their frames into
        # individual images)
        if img.sequence:
            for _ in range(1, len(img.sequence)):
                img.sequence.pop()

        # Rotation and conversion to desired output format
        if auto_orient:
            img.auto_orient()
        img.format = fmt

        while True:
            size, quality, square, fp = yield

            __log__.debug(
                "[resizing] %s -> %dpx%s",
                name or "<img data>", size, ", square" if square else ""
            )

            if square:
                crop = min(img.size)
                img.crop(width=crop, height=crop, gravity='center')
                if upscale or size < crop:
                    img.resize(size, size)
            else:
                # Work around a bug in Wand's image transformation by
                # manually calculating the scaled dimensions and resizing
                ratio = size/max(img.size)
                if upscale or ratio < 1:
                    img.resize(*[round(x*ratio) for x in img.size])

            img.compression_quality = quality

            try:
                img.save(file=fp)
            except IOError as e:
                __log__.error("[error] Failed to write image: %s", e, exc_info=True)
                raise

# JSON
def load_album_cache(album):
    with open(album.cache_path, 'r') as fp:
        return json.load(fp, object_hook=object_hook)

def save_album_cache(album):
    with open(album.cache_path, 'w') as fp:
        json.dump(album, fp, separators=(',', ':'), cls=PhotoAlbumEncoder)

def object_hook(obj):
    """Make JSON parse dates properly"""
    for k in ("date", "dateModified"):
        if k in obj and obj[k]:
            obj[k] = datetime.utcfromtimestamp(obj[k])
    return obj

class PhotoAlbumEncoder(json.JSONEncoder):
    def default(self, obj):
        from scanner.media import MediaObject
        from scanner.album import Album

        if isinstance(obj, datetime):
            return calendar.timegm(obj.utctimetuple())
        if isinstance(obj, (Album, MediaObject)):
            return obj.cache_data()
        return json.JSONEncoder.default(self, obj)
