#!/usr/bin/env python

from datetime import datetime
import json
import os
import sys

from scanner.photo_album import Photo, Album, PhotoAlbumEncoder
from scanner.cache_path import (next_level, back_level, set_cache_path_base,
                                json_cache, message, file_mtime)
from scanner.utils import ExifTool


class TreeWalker:
    def __init__(self, config):
        self._config = config

        message("info", "Starting directory walk")
        if config.salt:
            message("info", "Using a salt to hash files")

        set_cache_path_base(config.album)
        self.all_albums = []
        self.all_photos = []

        # Instantiate the ExifTool singleton so all exif operations can reuse
        # the suprocess in batch mode.
        with ExifTool():
            self.walk(config.album)

        self.remove_stale()
        message("complete", "")

    def walk(self, path):
        next_level()
        if not os.access(path, os.R_OK | os.X_OK):
            message("access denied", os.path.basename(path))
            back_level()
            return None

        message("walking", os.path.basename(path))
        cache = os.path.join(self._config.cache, json_cache(path))
        cached = False
        cached_album = None
        if os.path.exists(cache):
            try:
                cached_album = Album.from_cache(self._config, cache)
            except (OSError, TypeError, ValueError) as e:
                message("corrupt cache", os.path.basename(path))
                cached_album = None
            else:
                # Check if json or images are out of date
                if (file_mtime(path) <= file_mtime(cache) and
                        cached_album.photos_cached):
                    message("full cache", os.path.basename(path))
                    cached = True
                    album = cached_album
                    for photo in album.photos:
                        self.all_photos.append(photo)
                else:
                    message("partial cache", os.path.basename(path))
        if not cached:
            album = Album(self._config, path)

        for entry in os.listdir(path):
            if entry[0] == '.':
                continue

            entry = os.path.join(path, entry)

            if os.path.isdir(entry):
                next_walked_album = self.walk(entry)
                if next_walked_album is not None:
                    album.add_album(next_walked_album)
            elif not cached and os.path.isfile(entry):
                next_level()
                cache_hit = False
                if cached_album:
                    cached_photo = cached_album.photo_from_path(entry)
                    if (cached_photo and
                            file_mtime(entry) <= cached_photo.attributes["dateTimeFile"] and
                            cached_photo.thumbs_cached):
                        message("cache hit", os.path.basename(entry))
                        cache_hit = True
                        photo = cached_photo
                if not cache_hit:
                    message("metainfo", os.path.basename(entry))
                    photo = Photo(self._config, entry)
                if photo.is_valid:
                    self.all_photos.append(photo)
                    album.add_photo(photo)
                else:
                    message("unreadable", os.path.basename(entry))
                back_level()
        if not album.empty:
            message("caching", os.path.basename(path))
            album.cache()
            self.all_albums.append(album)
        else:
            message("empty", os.path.basename(path))
        back_level()
        return album

    def remove_stale(self):
        message("cleanup", "building stale list")
        all_cache_entries = set()
        for album in self.all_albums:
            all_cache_entries.add(album.cache_path)
        for photo in self.all_photos:
            for entry in photo.image_caches:
                all_cache_entries.add(entry)

        message("cleanup", "searching for stale cache entries")
        for root, _, files in os.walk(self._config.cache):
            for name in files:
                fname = os.path.normpath(os.path.join(os.path.relpath(root, self._config.cache), name))
                if fname not in all_cache_entries:
                    message("cleanup", fname)
                    os.unlink(os.path.join(self._config.cache, fname))
