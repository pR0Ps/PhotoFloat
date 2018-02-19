#!/usr/bin/env python

from datetime import datetime
import os
import sys
import logging

from scanner.exiftool import ExifTool
from scanner.cache_path import (next_level, back_level, set_cache_path_base,
                                json_cache, message, file_mtime)
from scanner.photo_album import Photo, Album, PhotoAlbumEncoder

logger = logging.getLogger(__name__)

class AlbumDirectory:
    def __init__(self, path, contents):
        self.path = path
        self.contents = contents

    def __repr__(self):
        return "%s(%s, %s)" % (self.__class__, self.path, self.contents)

class TreeWalker:
    def __init__(self, config):
        self._config = config

        logger.info("Starting directory walk")
        if config.salt:
            logger.info("Using provided salt %s to hash files" % (config.salt))

        set_cache_path_base(config.albums)
        os.makedirs(config.cache, exist_ok=True)

        self.all_albums = []
        self.all_photos = []
        self.albums_to_process = []

        self.generate_album_directory_list()
        # Instantiate the ExifTool singleton so all exif operations can reuse
        # the suprocess in batch mode.
        with ExifTool():
            self.generate_albums()

        self.remove_stale()
        logger.info("Completed walk")

    def generate_album_directory_list(self):
        for root, _, files in os.walk(self._config.albums):
            if not os.access(root, os.R_OK | os.X_OK):
                print("Access denied", os.path.basename(root))
                continue

            self.albums_to_process.append(AlbumDirectory(root, files))
        logger.info("Finished generating album listing")

    def _get_album_from_cache(self, ad):
        cache_path = os.path.join(self._config.cache, json_cache(ad.path))
        cached_album = None

        if os.path.exists(cache_path):
            try:
                cached_album = Album.from_cache(self._config, cache_path)
            except (OSError, TypeError, ValueError) as e:
                logger.warning("Corrupt cache - %s" % (os.path.basename(ad.path)))
                return (None, False)
            else:
                if (file_mtime(ad.path) <= file_mtime(cache_path) and
                        cached_album.photos_cached):
                    logger.info("Full cache - %s" % (ad.path))
                    for photo in cached_album.photos:
                        self.all_photos.append(photo)
                    return (cached_album, True)
                else:
                    logger.info("Partial cache - %s" % (ad.path))
                    return (cached_album, False)
        else:
            return (None, False)

    def _get_cached_item(self, item_path, album):
        cached_photo = album.photo_from_path(item_path)
        if (cached_photo and
            file_mtime(item_path) <= cached_photo.attributes["dateModified"] and
            cached_photo.thumbs_cached):
            logger.info("Cache hit - %s" % (item_path))
            return cached_photo
        return None

    def generate_albums(self):
        for ad in self.albums_to_process:
            album, is_album_fully_cached = self._get_album_from_cache(ad)
            if not is_album_fully_cached:
                album = Album(self._config, ad.path)
            for file in ad.contents:
                photo = None
                if file[0] == ".":
                    continue
                file_path = os.path.join(ad.path, file)
                logger.debug("Album is cached %s" % (is_album_fully_cached))
                if not is_album_fully_cached:
                    photo = self._get_cached_item(file_path, album)
                    if not photo:
                        logger.info("Metainfo - %s" % (file_path))
                        photo = Photo(self._config, file_path)
                    if photo.is_valid:
                        self.all_photos.append(photo)
                        album.add_photo(photo)
                    else:
                        logger.warning("Unreadable photo %s" % (file_path))
            logger.info("Caching - %s" % (ad.path))
            album.cache()
            self.all_albums.append(album)

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
