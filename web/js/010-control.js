$(document).ready(function() {
	function cachePath(path) {
		if (path == "")
			return "root";
		if (path[0] == '/')
			path = path.substring(1);
		path = path
			.replace(/ /g, "_")
			.replace(/\//g, "-")
			.replace(/\(/g, "")
			.replace(/\)/g, "")
			.replace(/#/g, "")
			.replace(/\[/g, "")
			.replace(/\]/g, "")
			.replace(/"/g, "")
			.replace(/'/g, "")
			.replace(/_-_/g, "-")
			.toLowerCase();
		while (path.indexOf("--") != -1)
			path = path.replace(/--/g, "-");
		while (path.indexOf("__") != -1)
			path = path.replace(/__/g, "_");
		return path;
	}
	function imagePath(image, path, size, square) {
		var suffix;
		if (square)
			suffix = size.toString() + "s";
		else
			suffix = size.toString();
		return "cache/" + cachePath(path + "/" + image + "_" + suffix + ".jpg");
	}
	function escapeId(id) {
		return id.replace(/\./g, "\\.").replace(/,/g, "\\,");
	}
	function loadAlbum() {
		if (current_album_cache in album_cache) {
			albumLoaded(album_cache[current_album_cache]);
			return;
		}
		$("#loading").show();
		$.ajax({
			type: "GET",
			url: "cache/" + current_album_cache + ".json",
			error: function() { $(document.body).html("Couldn't fetch it."); },
			success: albumLoaded
		});
	}
	function albumLoaded(album) {
		$("#loading").hide();
		album_cache[cachePath(album.path)] = album;
		current_album = album;
		if (cachePath(album.path) == current_album_cache)
			showAlbum();
		if (current_photo_cache != null)
			showPhoto();
		setTitle();
	}
	function trimExtension(title) {
		var index = title.lastIndexOf(".");
		if (index != -1)
			return title.substring(0, index)
		return title;
	}
	function setTitle() {
		var title = "";
		var components;
		if (current_album.path.length == 0)
			components = [document.title];
		else {
			components = current_album.path.split("/");
			components.unshift(document.title);
		}
		var last = "";
		for (var i = 0; i < components.length; ++i) {
			if (i)
				last += "/" + components[i];
			if (i < components.length - 1 || current_photo_cache != null)
				title += "<a href=\"#" + (i == 0 ? "" : cachePath(last.substring(1))) + "\">";
			title += components[i];
			if (i < components.length - 1 || current_photo_cache != null) {
				title += "</a>";
				title += " &raquo; ";
			}
		}
		if (current_photo_cache != null)
			title += trimExtension(current_photo.name);
		$("#title").html(title);
	}
	function showAlbum() {
		$("html, body").animate({ scrollTop: 0 }, "slow");
		var photos = "";
		for (var i = 0; i < current_album.photos.length; ++i)
			photos += "<a href=\"#" + current_album_cache + "/" + cachePath(current_album.photos[i].name) + "\"><img title=\"" + trimExtension(current_album.photos[i].name) + "\" alt=\"" + trimExtension(current_album.photos[i].name) + "\" id=\"thumb-" + cachePath(current_album.photos[i].name) + "\" src=\"" + imagePath(current_album.photos[i].name, current_album.path, 150, true) + "\" height=\"150\" width=\"150\"></a>";
		$("#thumbs").html(photos);
		if (current_album.albums.length)
			$("#subalbums-title").show();
		else
			$("#subalbums-title").hide();
		var subalbums = "";
		var thumbFinderList = new Array();
		for (var i = current_album.albums.length - 1; i >= 0; --i) {
			var path = cachePath(current_album.path + "/" + current_album.albums[i].path);
			var id = "album-" + path;
			subalbums += "<a href=\"#" + path + "\"><div title=\"" + current_album.albums[i].date + "\" id=\"" + id + "\" class=\"album-button\">" + current_album.albums[i].path + "</div></a>";
			thumbFinderList.push({ path: path, id: escapeId(id) });
		}
		$("#subalbums").html(subalbums);
		for (var i = 0; i < thumbFinderList.length; ++i)
			(function(thumb) {
				albumThumbFinder(thumb.path, function(photo, album) {
					$("#" + thumb.id).css("background-image", "url(" + imagePath(photo.name, album.path, 150, true) + ")");
				});
			})(thumbFinderList[i]);
		
		$("#album-view").removeClass("photo-view-container");
		$("#subalbums").show();
		$("#photo-view").hide();
	}
	function showPhoto() {
		currentPhoto();
		if (current_photo == null) {
			$(document.body).html("Wrong picture.");
			return;
		}
		var maxSize = 800;
		var width = current_photo.size[0];
		var height = current_photo.size[1];
		if (width > height) {
			height = height / width * maxSize;
			width = maxSize;
		} else {
			width = width / height * maxSize;
			height = maxSize;
		}
		$("#photo")
			.attr("width", width).attr("height", height)
			.attr("src", imagePath(current_photo.name, current_album.path, maxSize, false))
			.attr("alt", current_photo.name)
			.attr("title", current_photo.date)
			.load(function() { $(this).css("width", "auto").css("height", "100%"); });
		var nextLink = "#" + current_album_cache + "/" + cachePath(current_album.photos[
			(current_photo_index + 1 >= current_album.photos.length) ? 0 : (current_photo_index + 1)
		].name);
		$("#next-photo").attr("href", nextLink);
		$("#next").attr("href", nextLink);
		$("#back").attr("href", "#" + current_album_cache + "/" + cachePath(current_album.photos[
			(current_photo_index - 1 < 0) ? (current_album.photos.length - 1) : (current_photo_index - 1)
		].name));
		
		$("#album-view").addClass("photo-view-container");
		$("#subalbums").hide();
		$("#photo-view").show();
		var thumb = $("#thumb-" + escapeId(current_photo_cache));
		var scroller = $("#album-view");
		scroller.stop();
		scroller.animate({ scrollLeft: thumb.position().left + scroller.scrollLeft() - scroller.width() / 2 + thumb.width() / 2 }, "slow");
	}
	function currentPhoto() {
		for (current_photo_index = 0; current_photo_index < current_album.photos.length; ++current_photo_index) {
			if (cachePath(current_album.photos[current_photo_index].name) == current_photo_cache)
				break;
		}
		if (current_photo_index >= current_album.photos.length) {
			current_photo = null;
			current_photo_index = -1;
			return;
		}
		current_photo = current_album.photos[current_photo_index];
	}
	
	function albumForThumbIteration(album, callback) {
		album_cache[cachePath(album.path)] = album;
		var index = Math.floor(Math.random() * (album.photos.length + album.albums.length));
		if (index >= album.photos.length) {
			index -= album.photos.length;
			fetchAlbumForThumb(cachePath(album.path + "/" + album.albums[index].path), function(fetchedAlbum) {
				albumForThumbIteration(fetchedAlbum, callback);
			});
		} else
			callback(album.photos[index], album);
	}
	function fetchAlbumForThumb(album, callback) {
		if (album in album_cache) {
			callback(album_cache[album]);
			return;
		}
		$.ajax({
			type: "GET",
			url: "cache/" + album + ".json",
			error: function() { $(document.body).html("Couldn't fetch it."); },
			success: callback
		});
	}
	function albumThumbFinder(album, callback) {
		fetchAlbumForThumb(album, function(fetchedAlbum) { albumForThumbIteration(fetchedAlbum, callback); });
	}
	
	var current_album_cache = null;
	var current_photo_cache = null;
	var current_album = null;
	var current_photo = null;
	var current_photo_index = -1;
	var album_cache = new Array();
	$(window).hashchange(function() {
		var new_album_cache = location.hash.substring(1);
		var index = new_album_cache.lastIndexOf("/");
		if (index != -1 && index != new_album_cache.length - 1) {
			current_photo_cache = new_album_cache.substring(index + 1);
			new_album_cache = new_album_cache.substring(0, index);
		} else
			current_photo_cache = null;
		if (!new_album_cache.length)
			new_album_cache = cachePath("root");
		if (new_album_cache != current_album_cache) {
			current_album_cache = new_album_cache;
			loadAlbum();
		} else if (current_photo_cache != null) {
			showAlbum();
			showPhoto();
			setTitle();
		} else {
			showAlbum();
			setTitle();
		}
	});
	$(window).hashchange();
	$(document).keydown(function(e){
		if (current_photo_cache == null)
			return true;
		if (e.keyCode == 39) {
			window.location.href = $("#next").attr("href");
			return false;
		} else if (e.keyCode == 37) {
			window.location.href = $("#back").attr("href");
			return false;
		}
		return true;
	});
});
