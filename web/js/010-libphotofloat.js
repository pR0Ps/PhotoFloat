(function() {
  /* constructor */
  function PhotoFloat() {
    this.albumCache = [];
  }

  /* public member functions */
  PhotoFloat.prototype.album = function(subalbum, callback, error) {
    var cacheKey, ajaxOptions, self, parent;
    if (typeof subalbum.media !== "undefined" && subalbum.media !== null) {
      callback(subalbum);
      return;
    }
    if (Object.prototype.toString.call(subalbum).slice(8, -1) === "String") {
      cacheKey = subalbum;
      parent = null;
    } else {
      parent = subalbum.parent;
      cacheKey = PhotoFloat.cachePath(parent.path + "/" + subalbum.path);
    }
    if (this.albumCache.hasOwnProperty(cacheKey)) {
      album = this.albumCache[cacheKey];
      callback(album);
      return;
    }
    self = this;
    ajaxOptions = {
      type: "GET",
      dataType: "json",
      url: "/cache/" + cacheKey + ".json",
      success: function(album) {
        for (var i = 0; i < album.albums.length; ++i)
          album.albums[i].parent = album;
        for (var i = 0; i < album.media.length; ++i)
          album.media[i].parent = album;
        if (parent != null) {
          album.parent = parent;
        }
        self.albumCache[cacheKey] = album;
        callback(album);
      }
    };
    if (typeof error !== "undefined" && error !== null) {
      ajaxOptions.error = function(jqXHR, textStatus, errorThrown) {
        error(jqXHR.status);
      };
    }
    $.ajax(ajaxOptions);
  };
  PhotoFloat.prototype.albumPhoto = function(subalbum, callback, error) {
    var nextAlbum, self;
    self = this;
    nextAlbum = function(album) {
      // Photos in albums are ordered oldest to newest
      // Albums are ordered newest to oldest
      if (album.media.length > 0) {
        // Take the oldest photo in the album (first photo shown)
        callback(album, album.media[0]);
      } else if (album.albums.length > 0) {
        // Delegate picking thumb to newest subalbum (first one shown)
        self.album(album.albums[0], nextAlbum, error);
      } else {
        // No photos or subalbums (empty)
        error();
      }
    };
    if (typeof subalbum.media !== "undefined" && subalbum.media !== null)
      nextAlbum(subalbum);
    else this.album(subalbum, nextAlbum, error);
  };

  PhotoFloat.prototype.removePhoto = function(photo, album) {
    album = typeof album !== "undefined" ? album : photo.parent;
    if (typeof album === "undefined") {
      return;
    }
    idx = album.media.indexOf(photo);
    if (idx !== -1) album.media.splice(idx, 1);
    if (album.media.length == 0 && album.albums.length == 0) {
      this.removeAlbum(album);
    }
  };
  PhotoFloat.prototype.removeAlbum = function(album, parent) {
    parent = typeof parent !== "undefined" ? parent : album.parent;
    if (typeof parent === "undefined") {
      return;
    }
    idx = parent.albums.indexOf(album);
    if (idx !== -1) parent.albums.splice(idx, 1);
    if (parent.media.length == 0 && parent.albums.length == 0) {
      this.removeAlbum(parent);
    }
  };

  PhotoFloat.prototype.parseLocation = function(location, callback, error) {
    var index, album, photo;
    path = location.pathname;

    // trim off "/view" and leading/trailing slashes
    path = path.replace(/^\/view\/*/, "").replace(/\/+$/, "");
    index = path.lastIndexOf("/");
    if (!path.length) {
      album = "root";
      photo = null;
    } else if (index !== -1 && index !== path.length - 1) {
      photo = path.substring(index + 1);
      album = path.substring(0, index);
    } else {
      album = path;
      photo = null;
    }
    this.album(
      album,
      function(theAlbum) {
        var i = -1;
        if (photo !== null) {
          for (var i = 0; i < theAlbum.media.length; ++i) {
            if (PhotoFloat.cachePath(theAlbum.media[i].name) === photo) {
              photo = theAlbum.media[i];
              break;
            }
          }
          if (i >= theAlbum.media.length) {
            photo = null;
            i = -1;
          }
        }
        callback(theAlbum, photo, i);
      },
      error
    );
  };
  PhotoFloat.prototype.authenticate = function(password, result) {
    $.ajax({
      type: "GET",
      dataType: "text",
      url: "auth?username=photos&password=" + password,
      success: function() {
        result(true);
      },
      error: function() {
        result(false);
      }
    });
  };

  /* static functions */
  PhotoFloat.cachePath = function(path) {
    if (path.charAt(0) === "/") path = path.substring(1);
    if (!path.length) return "root";
    path = path
      .replace(/ /g, "_")
      .replace(/\//g, "-")
      .replace(/\(/g, "")
      .replace(/\)/g, "")
      .replace(/#/g, "")
      .replace(/&/g, "")
      .replace(/,/g, "")
      .replace(/\[/g, "")
      .replace(/\]/g, "")
      .replace(/"/g, "")
      .replace(/'/g, "")
      .replace(/_-_/g, "-")
      .toLowerCase();
    while (path.indexOf("--") !== -1) path = path.replace(/--/g, "-");
    while (path.indexOf("__") !== -1) path = path.replace(/__/g, "_");
    return encodeURIComponent(path);
  };
  PhotoFloat.photoHash = function(album, photo) {
    return PhotoFloat.albumHash(album) + "/" + PhotoFloat.cachePath(photo.name);
  };
  PhotoFloat.albumHash = function(album) {
    if (typeof album.media !== "undefined" && album.media !== null)
      return PhotoFloat.cachePath(album.path);
    return PhotoFloat.cachePath(album.parent.path + "/" + album.path);
  };
  PhotoFloat.photoPath = function(album, photo, size) {
    var ext = "jpg";
    if (photo.mimeType.split("/")[0] === "video") {
      ext = "mp4";
    }
    return (
      "/cache/thumbs/" +
      photo.hash.slice(0, 2) +
      "/" +
      photo.hash.slice(2) +
      "_" +
      size.toString() +
      "." +
      ext
    );
  };
  PhotoFloat.originalPhotoPath = function(album, photo) {
    return "/albums/" + album.path + "/" + photo.name;
  };
  PhotoFloat.trimExtension = function(name) {
    var index = name.lastIndexOf(".");
    if (index !== -1) return name.substring(0, index);
    return name;
  };

  /* make static methods callable as member functions */
  PhotoFloat.prototype.cachePath = PhotoFloat.cachePath;
  PhotoFloat.prototype.photoHash = PhotoFloat.photoHash;
  PhotoFloat.prototype.albumHash = PhotoFloat.albumHash;
  PhotoFloat.prototype.photoPath = PhotoFloat.photoPath;
  PhotoFloat.prototype.originalPhotoPath = PhotoFloat.originalPhotoPath;
  PhotoFloat.prototype.trimExtension = PhotoFloat.trimExtension;

  /* expose class globally */
  window.PhotoFloat = PhotoFloat;
})();
