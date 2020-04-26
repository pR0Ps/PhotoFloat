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
from scanner.utils import save_album_cache

__log__ = logging.getLogger(__name__)
LOG_LEVELS = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG)

# Attempt to get number of usable CPUs (limited by LXC/Docker/cgroups/other)
# Only available on some UNIX platforms so fall back to number of CPUs in the system
try:
    NUM_CPUS = len(os.sched_getaffinity(0))
except AttributeError:
    NUM_CPUS = os.cpu_count()


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
            out_str = "cleaned up {} files"
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
                        help="A file containing data to salt the image filenames with")
    parser.add_argument("-p", "--processes", type=int, default=NUM_CPUS,
                        help="Number of processes to use for processing photos (default {}). "\
                             "Depending on the photo, each process can use upwards of 500MB of RAM. "\
                             "If you find processes are being killed due to memory constraints, scale this down.".format(NUM_CPUS))
    parser.add_argument("--remove-stale", action="store_true",
                        help="Remove stale data/thumbnails from the cache (default: just list them)")
    parser.add_argument("--no-location", action="store_true",
                        help="Don't pull any location/GPS data out of photo metadata")
    parser.add_argument("--rescan-ignored", action="store_true",
                        help="Force a re-scan of files that were previously ignored")
    parser.add_argument("-v", "--verbose", dest="verbose_count",
                        action="count", default=0,
                        help="Increase log verbosity for each occurence up to 4 (default: ERROR)")
    config = parser.parse_args()

    # Set the package-wide logging level
    logging.getLogger(scanner.__name__).setLevel(
        LOG_LEVELS[min(3, max(0, config.verbose_count))]
    )
    config.show_tracebacks = config.verbose_count > 3

    # Store the salt, not the filename in config.salt
    saltfile = config.salt or None
    if saltfile:
        config.salt = saltfile.read()

    if not config.cache:
        config.cache = os.path.join(config.albums, os.path.pardir, "cache")

    # Set the config  and depth for global use
    scanner.globals.CONFIG = config
    scanner.globals.depth = 0

    # Warn if we will be changing the system locale to one that supports UTF-8
    # so subprocesses won't break with non-ascii characters. In Python 3.6+
    # this is instead fixed by specifying the encoding when executing the subprocess.
    if sys.version_info < (3, 6):
        import locale
        encoding = locale.getpreferredencoding(False)
        if encoding.lower().replace("-", "") != 'utf8':
            __log__.warning(
                "The system locale specified a text encoding of '%s' - "
                "setting it to 'UTF-8'", encoding
            )
            for l in ("C.UTF-8", "C.utf8", "UTF-8"):
                try:
                    locale.setlocale(locale.LC_CTYPE, l)
                    break
                except locale.Error:
                    pass
            else:
                __log__.error(
                    "Failed to set the current locale's text encoding - you "
                    "may encounter issues while scanning files."
                )

    try:
        if config.salt:
            __log__.info("Will use a salt from file '%s' to hash files", saltfile.name)

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
        __log__.debug("[thumbing] Using %d processes for thumbnailing", config.processes)
        with log_depth():
            with multiprocessing.Pool(processes=config.processes) as p:
                p.map(generate_thumbs, uniques)

        remove_stale(root_album)
    except KeyboardInterrupt:
        scanner.globals.depth = 0
        __log__.critical("[keyboard] CTRL+C pressed, quitting.")
        sys.exit(1)

if __name__ == "__main__":
    main()
