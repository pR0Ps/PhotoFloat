#!/usr/bin/env python

from datetime import datetime
import os
import sys

from scanner.exiftool import ExifTool
from scanner.cache_path import (next_level, back_level, set_cache_path_base,
                                json_cache, message, file_mtime)
from scanner.photo_album import Photo, Album, PhotoAlbumEncoder


class TreeWalker:
    def __init__(self, config):
        self._config = config

        message("info", "starting directory walk")
        if config.salt:
            message("info", "using a salt to hash files")

        set_cache_path_base(config.albums)
        os.makedirs(config.cache, exist_ok=True)

        self.all_albums = []
        self.all_photos = []

        # Instantiate the ExifTool singleton so all exif operations can reuse
        # the suprocess in batch mode.
        with ExifTool():
            self.walk(config.albums)

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
                            file_mtime(entry) <= cached_photo.attributes["dateModified"] and
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
        all_cache_entries = set()
        for album in self.all_albums:
            all_cache_entries.add(album.cache_path)
        for photo in self.all_photos:
            for entry in photo.image_caches:
                all_cache_entries.add(entry)

        delete_count = 0
        message("cleanup", "searching for stale cache entries")
        for root, _, files in os.walk(self._config.cache):
            for name in files:
                fname = os.path.normpath(os.path.join(os.path.relpath(root, self._config.cache), name))
                if fname not in all_cache_entries:
                    delete_count += 1
                    message("cleanup", fname)
                    if self._config.remove_stale:
                        os.unlink(os.path.join(self._config.cache, fname))


        if self._config.remove_stale:
            out_str =  "cleaned up {} files"
        else:
            out_str = ("{} stale cache entries detected (see above), use "
                       "'--remove-stale' to delete them")

        if delete_count:
            message("cleanup", out_str.format(delete_count))
