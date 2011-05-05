import os
import os.path
from datetime import datetime
from PhotoAlbum import Photo, Album, json_cache, set_cache_path_base

class TreeWalker:
	def __init__(self, album_path, cache_path):
		self.album_path = album_path
		self.cache_path = cache_path
		set_cache_path_base(self.album_path)
		self.all_albums = list()
		self.all_photos = list()
		self.walk(album_path)
		self.remove_stale()
	def walk(self, path):
		print "Walking %s" % path
		cache = os.path.join(self.cache_path, json_cache(path))
		cached = False
		cached_album = None
		if os.path.exists(cache):
			print "Has cache %s" % path
			cached_album = Album.from_cache(cache)
			if os.path.getmtime(path) <= os.path.getmtime(cache):
				print "Album is fully cached"
				cached = True
				album = cached_album
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
					if cached_photo and datetime.fromtimestamp(os.path.getmtime(entry)) <= cached_photo.attributes["DateTimeFile"]:
						print "Photo cache hit %s" % entry
						cache_hit = True
						photo = cached_photo
				if not cache_hit:
					print "No cache - scanning %s" % entry
					photo = Photo(entry, self.cache_path)
				if photo.is_valid:
					self.all_photos.append(photo)
					album.add_photo(photo)
		print "Writing cache of %s" % album.cache_path
		album.cache(self.cache_path)
		self.all_albums.append(album)
		return album
	def remove_stale(self):
		pass #TODO: remove left over caches