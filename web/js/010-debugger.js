$(document).ready(function() {
	function cachePath(path) {
		return path.replace(/ /g, "_").replace(/\//g, "-");
	}
	function imagePath(image, path, size, square) {
		var suffix;
		if (square)
			suffix = size.toString() + "s";
		else
			suffix = size.toString();
		return "cache/" + cachePath(path + "/" + image + "_" + suffix + ".jpg");
	}
	function loadAlbum(path) {
		$.ajax({
			type: "GET",
			url: "cache/" + path + ".json",
			error: function() { $(document.body).html("Couldn't fetch it."); },
			success: function(album) {
				current_album = album;
				if (current_image_cache != null)
					showPhoto();
				else
					showAlbum();
			}
		});
	}
	function showAlbum() {
		$("html, body").animate({ scrollTop: 0 }, "slow");
		var title = "";
		var components = current_album.path.split("/");
		var last = "";
		for (var i = 0; i < components.length; ++i) {
			last += "/" + components[i];
			if (i < components.length - 1)
				title += "<a href=\"#" + cachePath(last.substring(1)) + "\">";
			title += components[i];
			if (i < components.length - 1) {
				title += "</a>";
				title += " &raquo; ";
			}
		}
		$("#title").html(title);
		var photos = "";
		for (var i = 0; i < current_album.photos.length; ++i)
			photos += "<a href=\"#" + current_album_cache + "/" + cachePath(current_album.photos[i].name) + "\"><img border=0 src=\"" + imagePath(current_album.photos[i].name, current_album.path, 150, true) + "\" height=150 width=150></a>";
		$("#photos").html(photos);
		if (current_album.albums.length)
			$("#subalbums-title").show();
		else
			$("#subalbums-title").hide();
		var subalbums = "";
		for (var i = 0; i < current_album.albums.length; ++i)
			subalbums += "<a href=\"#" + cachePath(current_album.path + "/" + current_album.albums[i].path) + "\"><li>" + current_album.albums[i].path + "</li></a>";
		$("#subalbums").html(subalbums);
		
		$("#album").fadeIn();
		$("#photo").fadeOut();
	}
	function showPhoto() {
		var index;
		for (index = 0; index < current_album.photos.length; ++index) {
			if (cachePath(current_album.photos[index].name) == current_image_cache)
				break;
		}
		if (index >= current_album.photos.length) {
			$(document.body).html("Wrong picture.");
			return;
		}
		$("#photo").html("<a href=\"javascript:history.back(-1)\"><img src=\"" + imagePath(current_album.photos[index].name, current_album.path, 640, false) + "\"></a>");
		$("#album").fadeOut();
		$("#photo").fadeIn();
	}
	var current_album_cache = "";
	var current_image_cache = "";
	var current_album = null;
	$(window).hashchange(function() {
		var new_album_cache = location.hash.substring(1);
		var index = new_album_cache.lastIndexOf("/");
		if (index != -1 && index != new_album_cache.length - 1) {
			current_image_cache = new_album_cache.substring(index + 1);
			new_album_cache = new_album_cache.substring(0, index);
		} else
			current_image_cache = null;
		if (!new_album_cache.length)
			new_album_cache = cachePath("New York Summer 2009"); //root
		if (new_album_cache != current_album_cache) {
			current_album_cache = new_album_cache;
			loadAlbum(current_album_cache);
		} else if (current_image_cache != null)
			showPhoto();
		else
			showAlbum();
	});
	$(window).hashchange();
});
