import os
import os.path
import sys
from datetime import datetime
from PhotoAlbum import Photo, Album, PhotoAlbumEncoder
from CachePath import *
import json

class TreeWalker:
	def __init__(self, album_path, cache_path):
		self.album_path = os.path.abspath(album_path).decode(sys.getfilesystemencoding())
		self.cache_path = os.path.abspath(cache_path).decode(sys.getfilesystemencoding())
		set_cache_path_base(self.album_path)
		self.all_albums = list()
		self.all_photos = list()
		self.walk(self.album_path)
		self.big_lists()
		self.remove_stale()
		message("complete", "")
	def walk(self, path):
		next_level()
		if not os.access(path, os.R_OK | os.X_OK):
			message("access denied", os.path.basename(path))
			back_level()
			return None
		message("walking", os.path.basename(path))
		cache = os.path.join(self.cache_path, json_cache(path))
		cached = False
		cached_album = None
		if os.path.exists(cache):
			try:
				cached_album = Album.from_cache(cache)
				if file_mtime(path) <= file_mtime(cache):
					message("full cache", os.path.basename(path))
					cached = True
					album = cached_album
					for photo in album.photos:
						self.all_photos.append(photo)
				else:
					message("partial cache", os.path.basename(path))
			except KeyboardInterrupt:
				raise
			except:
				message("corrupt cache", os.path.basename(path))
				cached_album = None
		if not cached:
			album = Album(path)
		for entry in os.listdir(path):
			if entry[0] == '.':
				continue
			try:
				entry = entry.decode(sys.getfilesystemencoding())
			except KeyboardInterrupt:
				raise
			except:
				next_level()
				message("unicode error", entry.decode(sys.getfilesystemencoding(), "replace"))
				back_level()
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
					if cached_photo and file_mtime(entry) <= cached_photo.attributes["dateTimeFile"]:
						message("cache hit", os.path.basename(entry))
						cache_hit = True
						photo = cached_photo
				if not cache_hit:
					message("metainfo", os.path.basename(entry))
					photo = Photo(entry, self.cache_path)
				if photo.is_valid:
					self.all_photos.append(photo)
					album.add_photo(photo)
				else:
					message("unreadable", os.path.basename(entry))
				back_level()
		if not album.empty:
			message("caching", os.path.basename(path))
			album.cache(self.cache_path)
			self.all_albums.append(album)
		else:
			message("empty", os.path.basename(path))
		back_level()
		return album
	def big_lists(self):
		photo_list = []
		self.all_photos.sort()
		for photo in self.all_photos:
			photo_list.append(photo.path)
		message("caching", "all photos path list")
		fp = open(os.path.join(self.cache_path, "all_photos.json"), 'w')
		json.dump(photo_list, fp, cls=PhotoAlbumEncoder)
		fp.close()
	def remove_stale(self):
		message("cleanup", "building stale list")
		all_cache_entries = { "all_photos.json": True, "latest_photos.json": True }
		for album in self.all_albums:
			all_cache_entries[album.cache_path] = True
		for photo in self.all_photos:
			for entry in photo.image_caches:
				all_cache_entries[entry] = True
		message("cleanup", "searching for stale cache entries")
		for cache in os.listdir(self.cache_path):
			try:
				cache = cache.decode(sys.getfilesystemencoding())
			except KeyboardInterrupt:
				raise
			except:
				pass
			if cache not in all_cache_entries:
				message("cleanup", os.path.basename(cache))
				os.unlink(os.path.join(self.cache_path, cache))
