#!/usr/bin/env python

import calendar
from datetime import datetime
import json
import os.path

import scanner.globals


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
    if len(path) == 0:
        path = "root"
    return path

def json_cache(path):
    return "{}.json".format(cache_base(path))

def file_mtime(path):
    return datetime.fromtimestamp(int(os.path.getmtime(path)))


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
        from scanner.photo import MediaObject
        from scanner.album import Album

        if isinstance(obj, datetime):
            return calendar.timegm(obj.utctimetuple())
        if isinstance(obj, Album) or isinstance(obj, MediaObject):
            return obj.cache_data()
        return json.JSONEncoder.default(self, obj)
