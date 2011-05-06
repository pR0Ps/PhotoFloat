from CachePath import *
from datetime import datetime
import json
import os.path
from PIL import Image
from PIL.ExifTags import TAGS
import gc

class Album(object):
	def __init__(self, path):
		self._path = trim_base(path)
		self._photos = list()
		self._albums = list()
		self._photos_sorted = True
		self._albums_sorted = True
	@property
	def photos(self):
		return self._photos
	@property
	def albums(self):
		return self._albums
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
			return datetime(1900, 1, 1)
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
			album.add_photo(Photo.from_dict(photo, untrim_base(album.path)))
		if not cripple:
			for subalbum in dictionary["albums"]:
				album.add_album(Album.from_dict(subalbum), cripple)
		album._sort()
		return album
	def to_dict(self, cripple=True):
		self._sort()
		if cripple:
			subalbums = [ { "path": trim_base_custom(sub.path, self._path), "date": sub.date } for sub in self._albums ]
		else:
			subalbums = self._albums
		return { "path": self.path, "date": self.date, "albums": subalbums, "photos": self._photos }
	def photo_from_path(self, path):
		for photo in self._photos:
			if trim_base(path) == photo._path:
				return photo
		return None
	
class Photo(object):
	thumb_sizes = [ (150, True), (640, False), (1024, False) ]
	def __init__(self, path, thumb_path=None, attributes=None):
		self._path = trim_base(path)
		self.is_valid = True
		try:
			mtime = file_mtime(path)
		except:
			self.is_valid = False
			return
		if attributes is not None and attributes["DateTimeFile"] >= mtime:
			self._attributes = attributes
			return
		self._attributes = {}
		self._attributes["DateTimeFile"] = mtime
		
		try:
			image = Image.open(path)
		except:
			self.is_valid = False
			return
		self._metadata(image)
		self._thumbnails(image, thumb_path)
	def _metadata(self, image):
		try:
			info = image._getexif()
		except:
			return
		if not info:
			return
		for tag, value in info.items():
			decoded = TAGS.get(tag, tag)
			if not isinstance(decoded, int) and decoded not in ['JPEGThumbnail', 'TIFFThumbnail', 'Filename', 'FileSource', 'MakerNote', 'UserComment', 'ImageDescription', 'ComponentsConfiguration']:
				if isinstance(value, str):
					value = value.strip()
					if decoded.startswith("DateTime"):
						try:
							value = datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
						except:
							pass			
				self._attributes[decoded] = value
	def _thumbnail(self, image, thumb_path, size, square=False):
		gc.collect()
		thumb_path = os.path.join(thumb_path, image_cache(self._path, size, square))
		print "Thumbing %s" % thumb_path
		if os.path.exists(thumb_path) and file_mtime(thumb_path) >= self._attributes["DateTimeFile"]:
			return
		image = image.copy()
		if square:
			if image.size[0] > image.size[1]:
				left = (image.size[0] - image.size[1]) / 2
				top = 0
				right = image.size[0] - ((image.size[0] - image.size[1]) / 2)
				bottom = image.size[1]
			else:
				left = 0
				top = (image.size[1] - image.size[0]) / 2
				right = image.size[0]
				bottom = image.size[1] - ((image.size[1] - image.size[0]) / 2)
			image = image.crop((left, top, right, bottom))
		image.thumbnail((size, size), Image.ANTIALIAS)
		try:
			image.save(thumb_path, "JPEG")
		except:
			os.path.unlink(thumb_path)
		
	def _thumbnails(self, image, thumb_path):
		if "Orientation" in self._attributes:
			orientation = self._attributes["Orientation"]
		else:
			orientation = 1
		mirror = image
		if orientation == 2:
			# Vertical Mirror
			mirror = image.transpose(Image.FLIP_LEFT_RIGHT)
		elif orientation == 3:
			# Rotation 180
			mirror = image.transpose(Image.ROTATE_180)
		elif orientation == 4:
			# Horizontal Mirror
			mirror = image.transpose(Image.FLIP_TOP_BOTTOM)
		elif orientation == 5:
			# Horizontal Mirror + Rotation 270
			mirror = image.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.ROTATE_270)
		elif orientation == 6:
			# Rotation 270
			mirror = image.transpose(Image.ROTATE_270)
		elif orientation == 7:
			# Vertical Mirror + Rotation 270
			mirror = image.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.ROTATE_270)
		elif orientation == 8:
			# Rotation 90
			mirror = image.transpose(Image.ROTATE_90)
		for size in Photo.thumb_sizes:
			self._thumbnail(mirror, thumb_path, size[0], size[1])
	@property
	def name(self):
		return os.path.basename(self._path)
	def __str__(self):
		return self.name
	@property
	def image_caches(self):
		return [image_cache(self._path, size[0], size[1]) for size in Photo.thumb_sizes]
	@property
	def date(self):
		if not self.is_valid:
			return datetime(1900, 1, 1)
		if "DateTimeOriginal" in self._attributes:
			return self._attributes["DateTimeOriginal"]
		elif "DateTime" in self._attributes:
			return self._attributes["DateTime"]
		else:
			return self._attributes["DateTimeFile"]
	def __cmp__(self, other):
		date_compare = cmp(self.date, other.date)
		if date_compare == 0:
			return cmp(self.name, other.name)
		return date_compare
	@property
	def attributes(self):
		return self._attributes
	@staticmethod
	def from_dict(dictionary, basepath):
		del dictionary["date"]
		path = os.path.join(basepath, dictionary["name"])
		del dictionary["name"]
		for key, value in dictionary.items():
			if key.startswith("DateTime"):
				try:
					dictionary[key] = datetime.strptime(dictionary[key], "%a %b %d %H:%M:%S %Y")
				except:
					pass
		return Photo(path, None, dictionary)
	def to_dict(self):
		photo = { "name": self.name, "date": self.date }
		photo.update(self.attributes)
		return photo

class PhotoAlbumEncoder(json.JSONEncoder):
	def default(self, obj):
		if isinstance(obj, datetime):
			return obj.strftime("%a %b %d %H:%M:%S %Y")
		if isinstance(obj, Album) or isinstance(obj, Photo):
			return obj.to_dict()
		return json.JSONEncoder.default(self, obj)
		