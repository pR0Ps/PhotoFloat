#!/usr/bin/env python

import argparse
import contextlib
import sys
import os
import logging
import multiprocessing

import scanner.globals
from scanner.exiftool import ExifTool
from scanner.album import Album
from scanner.common import save_album_cache

__log__ = logging.getLogger(__name__)

def all_albums(root):
    yield root
    for a in root.albums:
        yield from all_albums(a)

def all_media(root):
    yield from root.media
    for a in root.albums:
        yield from all_media(a)

def generate_thumbs(obj):
    obj.generate_thumbs()

@contextlib.contextmanager
def log_depth():
    scanner.globals.depth += 1
    yield
    scanner.globals.depth -= 1

def remove_stale(root_album):
    config = scanner.globals.CONFIG

    all_cache_entries = set()
    for a in all_albums(root_album):
        all_cache_entries.add(a.cache_path)
        for m in a.media:
            all_cache_entries.update(m.thumbs)

    delete_count = 0
    __log__.info("[cleanup] searching for stale cache entries")
    with log_depth():
        for root, _, files in os.walk(config.cache):
            for name in files:
                fname = os.path.normpath(os.path.join(root, name))
                if fname not in all_cache_entries:
                    delete_count += 1
                    __log__.info("[cleanup] %s", fname)
                    if config.remove_stale:
                        os.unlink(fname)

    if delete_count:
        if config.remove_stale:
            out_str =  "cleaned up {} files"
        else:
            out_str = ("{} stale cache entries detected (see above), use "
                       "'--remove-stale' to delete them")
        __log__.info("[cleanup] %s", out_str.format(delete_count))
    else:
        __log__.info("[cleanup] nothing to clean")


def main():
    """Main entry point of the scanner"""
    parser = argparse.ArgumentParser()
    parser.add_argument("albums",
                        help="A directory where you store a hierarchy of album folders")
    parser.add_argument("-c", "--cache", nargs='?',
                        help="Where photofloat will generate thumbnails and other data (default: <ALBUM>/../cache)")
    parser.add_argument("-s", "--salt", nargs='?', type=argparse.FileType('rb'),
                        help="A file containing data to salt the image filenames with"),
    parser.add_argument("--remove-stale", action="store_true",
                        help="Remove stale data/thumbnails from the cache (default: just list them)")
    parser.add_argument("--no-location", action="store_true",
                        help="Don't pull any location/GPS data out of photo metadata")
    config = parser.parse_args()

    if config.salt:
        config.salt = config.salt.read()

    if not config.cache:
        config.cache = os.path.join(config.albums, os.path.pardir, "cache")

    # Set the config  and depth for global use
    scanner.globals.CONFIG = config
    scanner.globals.depth = 0
    try:
        if config.salt:
            __log__.info("Will use a salt from file '%s' to hash files", config.salt)

        os.makedirs(config.cache, exist_ok=True)

        __log__.info("[walking] Starting directory walk")
        # Instantiate the ExifTool singleton so all exif operations can reuse
        # the suprocess in batch mode.
        with ExifTool():
            root_album = Album(config.albums)

        # Save the new data to the cache
        albums = list(all_albums(root_album))
        __log__.info("[saving] Saving data for %s albums", len(albums))
        with log_depth():
            for album in albums:
                __log__.debug("[saving] %s", album.name)
                save_album_cache(album)

        # Uniquify photos by hash before processing
        uniques = {mo.hash: mo for mo in all_media(root_album)}.values()
        __log__.info("[thumbing] Ensuring thumbnails exist for %s objects", len(uniques))
        with log_depth():
            with multiprocessing.Pool() as p:
                p.map(generate_thumbs, uniques)

        remove_stale(root_album)
    except KeyboardInterrupt:
        scanner.globals.depth = 0
        __log__.critical("[keyboard] CTRL+C pressed, quitting.")
        sys.exit(1)

if __name__ == "__main__":
    main()
