#!/usr/bin/env python

import contextlib
from datetime import datetime
import json
import logging
import os

import scanner.globals
from scanner.media import MediaObject
from scanner.common import json_cache, trim_base, trim_base_custom, load_album_cache


__log__ = logging.getLogger(__name__)


@contextlib.contextmanager
def log_depth(level, *args, category):
    """Log a message and increase the log depth for the contained code

    Will only modify the log depth if the logger is enabled for the specified level
    Will also output the same message with the category "complete" on exiting
    """
    if not __log__.isEnabledFor(level):
        yield
        return

    __log__.log(level, *args, extra=dict(category=category))
    scanner.globals.depth += 1
    yield
    scanner.globals.depth -= 1
    __log__.log(level, *args, extra=dict(category="complete"))


class Album:

    def __init__(self, path):
        self._media = []
        self._albums = []
        self._ignored = set()
        self._path = trim_base(path)
        self._name = os.path.basename(self._path)
        self._cache_path = os.path.join(scanner.globals.CONFIG.cache,
                                        json_cache(path))

        # Keep track of if the arrays are currently sorted so we don't sort
        # them repeatedly.
        # TODO: Profile this vs. inserting new things in the correct spots and
        # never sorting by using the bisect module
        self._sorted_media = False
        self._sorted_albums = False

        # Start processing the directory
        with log_depth(logging.INFO, self.name, category="walking"):

            files, dirs = [], []
            try:
                for x in os.scandir(path):
                    if x.is_file():
                        files.append(x)
                    elif x.is_dir():
                        dirs.append(x)
            except OSError as e:
                __log__.warning("[error] Can't access %s: %s", path, e)
                return

            if files:
                # Get cached data
                media_cache, self._ignored = self._load_media()

                if scanner.globals.CONFIG.rescan_ignored:
                    self._ignored = set()

                # Process files, generate thumbnails
                __log__.info("[scanning] Scanning %d files", len(files))
                for f in files:
                    if f.name in self._ignored:
                        __log__.warning("[ignored] File '%s' was previously unreadable", f.name)
                        continue

                    media_obj = MediaObject.from_path(
                        f.path, attributes=media_cache.get(f.name, None)
                    )
                    if media_obj:
                        self.add_media(media_obj)
                    else:
                        __log__.warning("[ignored] %s", f.name)
                        self._ignored.add(f.name)

            # Recurse into subfolders
            for d in dirs:
                # TODO: Add album from existing if symlink
                # May require saving the link and processing all links in a second pass
                # path = os.path.realpath(entry.path)
                self.add_album(Album(d.path))

    def __bool__(self):
        return bool(self._media) or any(self._albums)

    @property
    def cache_path(self):
        return self._cache_path

    @property
    def path(self):
        return self._path

    @property
    def name(self):
        return self._name

    @property
    def media(self):
        return self._media

    @property
    def albums(self):
        return self._albums

    # Sort by reverse date (new -> old), then alphabetical
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

    @property
    def date(self):
        """The date of the newest media object/subalbum contained in this album"""
        self._sort()
        # Newest is at end for media, the start for albums
        media_date = next((x.date for x in reversed(self._media) if x.date), None)
        album_date = next((x.date for x in self._albums if x.date), None)

        if not media_date and not album_date:
            return None
        return max(media_date or album_date, album_date or media_date)

    def _sort(self):
        """Sort the data for this album"""
        if not self._sorted_media:
            self._media.sort()
            self._sorted_media = True
        if not self._sorted_albums:
            self._albums.sort()
            self._sorted_albums = True

    def add_media(self, media):
        """Add media to this album"""
        if media:
            self._media.append(media)
            self._media_sorted = False

    def add_album(self, album):
        """Add a subalbum to this album"""
        if album:
            self._albums.append(album)
            self._sorted_albums = False

    def cache_data(self):
        self._sort()
        return {
            "path": self.path,
            "date": self.date,
            "albums": [{
                "path": trim_base_custom(x.path, self.path),
                "date": x.date
            } for x in self._albums if x],
            "media": self._media,
            "ignored": sorted(self._ignored)
        }

    def _load_media(self):
        """Load media data from the cache

        Returns a tuple of ({filename: data}, {ignored filenames})
        """
        try:
            data = load_album_cache(self)
            __log__.debug("Using cached data")
            return (
                {x["name"]: x for x in data["media"]},
                set(data.get("ignored", []))
            )
        except (FileNotFoundError) as e:
            __log__.debug("No cache exists")
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            # Catch issues with invalid dates parsed in the loading process
            __log__.warning("[error] Corrupt cache: %r", e)
        return ({}, set())

    def __repr__(self):
        return "<{} name={}, path={}>".format(self.__class__.__name__, self.name or "<root>", self.path or "<root>")
