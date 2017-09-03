#!/usr/bin/env python

import os.path
from datetime import datetime

def message(category, text):
    if message.level <= 0:
        sep = "  "
    else:
        sep = "--"
    print ("{} {}{}[{}]{}{}".format(datetime.now().isoformat(),
                                    max(0, message.level) * "  |",
                                    sep, category,
                                    max(1, (14 - len(category))) * " ", text))

message.level = -1
def next_level():
    message.level += 1

def back_level():
    message.level -= 1

def set_cache_path_base(base):
    trim_base.base = base

def untrim_base(path):
    return os.path.join(trim_base.base, path)

def trim_base_custom(path, base):
    if path.startswith(base):
        path = path[len(base):]
    if path.startswith('/'):
        path = path[1:]
    return path

def trim_base(path):
    return trim_base_custom(path, trim_base.base)

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

def image_cache(path, size, square=False):
    if square:
        suffix = "{}s".format(size)
    else:
        suffix = size
    return "{}_{}.jpg".format(cache_base(path), suffix)

def file_mtime(path):
    #TODO: timezone?
    return datetime.fromtimestamp(int(os.path.getmtime(path)))
