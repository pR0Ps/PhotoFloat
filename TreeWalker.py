import os
import os.path
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
		cache = os.path.join(self.cache_path, json_cache(path))
		cached = False
		if os.path.exists(cache) and os.path.getmtime(path) <= os.path.getmtime(cache):
			album = Album.from_cache(cache)
			cached = True
		else:
			album = Album(path)
		for entry in os.listdir(path):
			entry = os.path.join(path, entry)
			if os.path.isdir(entry):
				album.add_album(self.walk(entry))
			elif not cached and os.path.isfile(entry):
				photo = Photo(entry)
				if photo.is_valid:
					self.all_photos.append(photo)
					album.add_photo(photo)
		album.cache(self.cache_path)
		self.all_albums.append(album)
		return album
	def remove_stale(self):
		pass