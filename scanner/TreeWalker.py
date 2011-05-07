import os
import os.path
from datetime import datetime
from PhotoAlbum import Photo, Album, PhotoAlbumEncoder
from CachePath import json_cache, set_cache_path_base, file_mtime
import json

class TreeWalker:
	def __init__(self, album_path, cache_path):
		self.album_path = os.path.abspath(album_path)
		self.cache_path = os.path.abspath(cache_path)
		set_cache_path_base(self.album_path)
		self.all_albums = list()
		self.all_photos = list()
		self.walk(self.album_path)
		self.big_lists()
		self.remove_stale()
	def walk(self, path):
		print "Walking %s" % path
		cache = os.path.join(self.cache_path, json_cache(path))
		cached = False
		cached_album = None
		if os.path.exists(cache):
			print "Has cache %s" % path
			cached_album = Album.from_cache(cache)
			if file_mtime(path) <= file_mtime(cache):
				print "Album is fully cached"
				cached = True
				album = cached_album
				for photo in album.photos:
					self.all_photos.append(photo)
		if not cached:
			album = Album(path)
		for entry in os.listdir(path):
			entry = os.path.join(path, entry)
			if os.path.isdir(entry):
				album.add_album(self.walk(entry))
			elif not cached and os.path.isfile(entry):
				cache_hit = False
				if cached_album:
					cached_photo = cached_album.photo_from_path(entry)
					if cached_photo and file_mtime(entry) <= cached_photo.attributes["DateTimeFile"]:
						print "Photo cache hit %s" % entry
						cache_hit = True
						photo = cached_photo
				if not cache_hit:
					print "No cache, scanning %s" % entry
					photo = Photo(entry, self.cache_path)
				if photo.is_valid:
					self.all_photos.append(photo)
					album.add_photo(photo)
		if not album.empty:
			print "Writing cache of %s" % album.cache_path
			album.cache(self.cache_path)
			self.all_albums.append(album)
		else:
			print "Not writing cache of %s because it's empty" % album.cache_path
		return album
	def big_lists(self):
		photo_list = []
		self.all_photos.sort()
		for photo in self.all_photos:
			photo_list.append(photo.path)
		print "Writing all photos list."
		fp = open(os.path.join(self.cache_path, "all_photos.json"), 'w')
		json.dump(photo_list, fp, cls=PhotoAlbumEncoder)
		fp.close()
		photo_list.reverse()
		print "Writing latest photos list."
		fp = open(os.path.join(self.cache_path, "latest_photos.json"), 'w')
		json.dump(photo_list[0:27], fp, cls=PhotoAlbumEncoder)
		fp.close()
		
	def remove_stale(self):
		print "Building list of all cache entries."
		all_cache_entries = { "all_photos.json": True, "latest_photos.json": True }
		for album in self.all_albums:
			all_cache_entries[album.cache_path] = True
		for photo in self.all_photos:
			for entry in photo.image_caches:
				all_cache_entries[entry] = True
		print "Searching stale cache entries."
		for cache in os.listdir(self.cache_path):
			if cache not in all_cache_entries:
				print "Removing stale cache %s" % cache
				os.unlink(os.path.join(self.cache_path, cache))
