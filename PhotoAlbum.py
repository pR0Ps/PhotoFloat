from datetime import datetime
import json
import os.path
from PIL import Image
from PIL.ExifTags import TAGS

def set_cache_path_base(base):
	trim_base.base = base
def trim_base(path):
	if path.startswith(trim_base.base):
		path = path[len(trim_base.base):]
	if path.startswith('/'):
		path = path[1:]
	return path
def untrim_base(path):
	return os.path.join(trim_base.base, path)
def cache_base(path):
	path = trim_base(path).replace('/', '-').replace(' ', '_')
	if len(path) == 0:
		path = "root"
	return path
def json_cache(path):
	return cache_base(path) + ".json"
def image_cache(path, suffix):
	return cache_base(path) + "_" + suffix + ".jpg"

class Album(object):
	def __init__(self, path):
		self._path = trim_base(path)
		self._photos = list()
		self._albums = list()
		self._photos_sorted = True
		self._albums_sorted = True
	@property
	def path(self):
		return self._path
	def __str__(self):
		return self.path
	@property
	def cache_path(self):
		return json_cache(self.path)
	@property
	def date(self):
		self._sort()
		if len(self._photos) == 0 and len(self._albums) == 0:
			return datetime.min
		elif len(self._photos) == 0:
			return self._albums[-1].date
		elif len(self._albums) == 0:
			return self._photos[-1].date
		return max(self._photos[-1].date, self._albums[-1].date)
	def __cmp__(self, other):
		return cmp(self.date, other.date)
	def add_photo(self, photo):
		self._photos.append(photo)
		self._photos_sorted = False
	def add_album(self, album):
		self._albums.append(album)
		self._photos_sorted = False
	def _sort(self):
		if not self._photos_sorted:
			self._photos.sort()
			self._photos_sorted = True
		if not self._albums_sorted:
			self._albums.sort()
			self._albums_sorted = True
	def cache(self, base_dir):
		self._sort()
		fp = open(os.path.join(base_dir, self.cache_path), 'w')
		json.dump(self, fp, cls=PhotoAlbumEncoder)
		fp.close()
	@staticmethod
	def from_cache(path):
		fp = open(path, "r")
		dictionary = json.load(fp)
		fp.close()
		return Album.from_dict(dictionary)
	@staticmethod
	def from_dict(dictionary, cripple=True):
		album = Album(dictionary["path"])
		for photo in dictionary["photos"]:
			album.add_photo(Photo.from_dict(photo, album.path))
		if not cripple:
			for subalbum in dictionary["albums"]:
				album.add_album(Album.from_dict(subalbum), cripple)
		album._sort()
		return album
	def to_dict(self, cripple=True):
		self._sort()
		if cripple:
			subalbums = [ { "path": sub.path, "date": sub.date } for sub in self._albums ]
		else:
			subalbums = self._albums
		return { "path": self.path, "date": self.date, "albums": subalbums, "photos": self._photos }
	
class Photo(object):
	def __init__(self, path, attributes=None):
		self._path = trim_base(path)
		self.is_valid = True
		if attributes is not None:
			self._attributes = attributes
			return
		else:
			self._attributes = {}
		try:
			i = Image.open(path)
		except:
			self.is_valid = False
			return
		try:
			info = i._getexif()
		except:
			info = None
		if info:
			for tag, value in info.items():
				decoded = TAGS.get(tag, tag)
				if not isinstance(decoded, int) and decoded not in ['JPEGThumbnail', 'TIFFThumbnail', 'Filename', 'FileSource', 'MakerNote', 'UserComment', 'ImageDescription', 'ComponentsConfiguration']:
					if isinstance(value, str):
						value = value.strip()
					self._attributes[decoded] = value
	@property
	def name(self):
		return os.path.basename(self._path)
	def __str__(self):
		return self.name
	@property
	def cache_paths(self):
		return [image_cache(self.path, size) for size in [100, 640, 1024]]
	@property
	def date(self):
		if "DateTime" in self._attributes:
			return datetime.strptime(self._attributes["DateTime"], '%Y:%m:%d %H:%M:%S')
		else:
			return datetime.fromtimestamp(os.path.getmtime(untrim_base(self._path)))
	def __cmp__(self, other):
		return cmp(self.date, other.date)
	@property
	def attributes(self):
		return self._attributes
	@staticmethod
	def from_dict(dictionary, basepath):
		del dictionary["date"]
		path = os.path.join(basepath, dictionary["name"])
		del dictionary["name"]
		return Photo(path, dictionary)
	def to_dict(self):
		photo = { "name": self.name, "date": self.date }
		photo.update(self.attributes)
		return photo

class PhotoAlbumEncoder(json.JSONEncoder):
	def default(self, obj):
		if isinstance(obj, datetime):
			return obj.isoformat()
		if isinstance(obj, Album) or isinstance(obj, Photo):
			return obj.to_dict()
		return json.JSONEncoder.default(self, obj)
		