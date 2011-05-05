from datetime import datetime
import json
import os.path
from PIL import Image
from PIL.ExifTags import TAGS

def set_cache_path_base(base):
	trim_base.base = base
def untrim_base(path):
	return os.path.join(trim_base.base, path)
def trim_base(path):
	if path.startswith(trim_base.base):
		path = path[len(trim_base.base):]
	if path.startswith('/'):
		path = path[1:]
	return path
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
			subalbums = [ { "path": sub.path, "date": sub.date } for sub in self._albums ]
		else:
			subalbums = self._albums
		return { "path": self.path, "date": self.date, "albums": subalbums, "photos": self._photos }
	def photo_from_path(self, path):
		for photo in self._photos:
			if trim_base(path) == photo._path:
				print "cache hit %s" % path
				return photo
		return None
	
class Photo(object):
	def __init__(self, path, thumb_path=None, attributes=None):
		self._path = trim_base(path)
		self.is_valid = True
		mtime = datetime.fromtimestamp(os.path.getmtime(path))
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
		if square:
			suffix = str(size) + "s"
		else:
			suffix = str(size)
		thumb_path = os.path.join(thumb_path, image_cache(self._path, suffix))
		if os.path.exists(thumb_path) and datetime.fromtimestamp(os.path.getmtime(thumb_path)) >= self._attributes["DateTimeFile"]:
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
		image.save(thumb_path, "JPEG")
		print "saving %s" % thumb_path
		
	def _thumbnails(self, image, thumb_path):
		orientation = self._attributes["Orientation"]
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
		self._thumbnail(mirror, thumb_path, 100, True)
		self._thumbnail(mirror, thumb_path, 640)
		self._thumbnail(mirror, thumb_path, 1024)
	@property
	def name(self):
		return os.path.basename(self._path)
	def __str__(self):
		return self.name
	@property
	def date(self):
		if "DateTimeOriginal" in self._attributes:
			return self._attributes["DateTimeOriginal"]
		elif "DateTime" in self._attributes:
			return self._attributes["DateTime"]
		else:
			return self._attributes["DateTimeFile"]
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
		for key, value in dictionary.items():
			if key.startswith("DateTime"):
				try:
					dictionary[key] = datetime.strptime(dictionary[key], "%a %b %d %H:%M:%S %Y")
				except:
					pass
		return Photo(path, dictionary)
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
		