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
			success: function(album) {
				$("#debug").html("<h2>" + album.path + "</h2>");
				$("#debug").append("<h3>Photos</h3>");
				for (var i = 0; i < album.photos.length; ++i)
					$("#debug").append("<a href=\"" + imagePath(album.photos[i].name, album.path, 1024, false) + "\"><img border=0 src=\"" + imagePath(album.photos[i].name, album.path, 150, true) + "\" height=150 width=150></a>");
				if (album.albums.length)
					$("#debug").append("<h3>Sub-albums</h3>");
				for (var i = 0; i < album.albums.length; ++i) {
					var link = $("<a href=\"#" + cachePath(album.path + "/" + album.albums[i].path) + "\"><li>" + album.albums[i].path + "</li></a>");
					$("#debug").append(link);
				}
			}
		});
	}
	$(window).hashchange(function() {
		var cache = location.hash.substring(1);
		if (!cache.length)
			cache = cachePath("New York Summer 2009"); //root
		loadAlbum(cache);
	});
	$(window).hashchange();
});
