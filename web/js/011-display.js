$(document).ready(function() {
  /* 
   * The display is not yet object oriented. It's procedural code
   * broken off into functions. It makes use of libphotofloat's
   * PhotoFloat class for the network and management logic.
   *
   * All of this could potentially be object oriented, but presently
   * it should be pretty readable and sufficient. The only thing to
   * perhaps change in the future would be to consolidate calls to
   * jQuery selectors. And perhaps it'd be nice to move variable
   * declarations to the top, to stress that JavaScript scope is
   * for an entire function and always hoisted.
   *
   * None of the globals here polutes the global scope, as everything
   * is enclosed in an anonymous function.
   *
   */

  /* Globals */

  var currentAlbum = null;
  var currentPhoto = null;
  var currentPhotoIndex = -1;
  var previousAlbum = null;
  var previousPhoto = null;
  var originalTitle = document.title;
  var photoFloat = new PhotoFloat();
  var fullscreen = false;
  var placeholderImage = "/assets/loading.gif";

  /* Image selectors */
  function getThumbnailSize(media) {
    /* The image to use for the thumbnail */
    var n = media.previews.length;
    for (var i = 0; i < n; i++) {
      var c = media.previews[i];
      if (c != "full" && c >= 100 && c < 400) {
        return c;
      }
    }
    return null;
  }

  function getPreviewSize(media, fullscreen) {
    /* The image to use for the preview */
    var n = media.previews.length;
    for (var i = n - 1; i >= 0; i--) {
      var c = media.previews[i];
      if (c != "full" && c < 1600) {
        return c;
      }
    }
    return null;
  }

  /* Utils */
  function formatDate(timestamp) {
    //Requires milliseconds instead of seconds
    var date = new Date(timestamp * 1000);

    // Input timestamps have unknown/mixed timezones
    // parse using browsers timezone, convert back to "UTC", strip the UTC text off
    return date.toUTCString().replace(" GMT", "");
  }

  function zeroPad(num, len, char) {
    //Pad a number to a certain length with leading 0s
    // zeroPad(4, 5) -> "00004"
    var pad = new Array(1 + len).join("0");
    return (pad + num).slice(-pad.length);
  }

  function getType(media) {
    return media.mimeType.split("/")[0];
  }

  function unloadVideo() {
    var v = $("#video");
    v.removeAttr("src")[0].load();
    return v;
  }

  /* Displays */
  function setTitle() {
    var title = "",
      documentTitle = "",
      last = "",
      components,
      i;
    if (!currentAlbum.path.length) components = [originalTitle];
    else {
      components = currentAlbum.path.split("/");
      components.unshift(originalTitle);
    }
    if (currentPhoto !== null)
      documentTitle += photoFloat.trimExtension(currentPhoto.name);
    for (var i = 0; i < components.length; ++i) {
      if (i || currentPhoto !== null) documentTitle += " \u00ab ";
      if (i) last += "/" + components[i];
      if (i < components.length - 1 || currentPhoto !== null)
        title +=
          '<a href="/view/' +
          (i ? photoFloat.cachePath(last.substring(1)) : "") +
          '">';
      title += components[i];
      documentTitle += components[components.length - 1 - i];
      if (i < components.length - 1 || currentPhoto !== null) {
        title += "</a>";
        title += " &raquo; ";
      }
    }
    if (currentPhoto !== null)
      title += photoFloat.trimExtension(currentPhoto.name);
    $("#title").html(title);
    document.title = documentTitle;
  }
  function scrollToThumb() {
    var photo, thumb;
    photo = currentPhoto;
    if (photo === null) {
      photo = previousPhoto;
      if (photo === null) return;
    }
    $("#thumbs img").each(function() {
      if (this.photo === photo) {
        thumb = $(this);
        return false;
      }
    });
    if (typeof thumb === "undefined") return;
    if (currentPhoto !== null) {
      var scroller = $("#album-view");
      scroller.stop().animate(
        {
          scrollLeft:
            thumb.position().left +
            scroller.scrollLeft() -
            scroller.width() / 2 +
            thumb.width() / 2
        },
        "slow"
      );
    } else
      $("html, body")
        .stop()
        .animate(
          {
            scrollTop:
              thumb.offset().top - $(window).height() / 2 + thumb.height()
          },
          "slow"
        );

    if (currentPhoto !== null) {
      $("#thumbs img").removeClass("current-thumb");
      thumb.addClass("current-thumb");
    }
  }

  function populateImage(media) {}
  function populateVideo(media) {}

  function makeMediaThumbnail(album, media) {
    // Create the image with the placeholder and swap to the real one once it loads
    var link = $("<a>")
      .attr("href", "/view/" + photoFloat.photoHash(currentAlbum, media))
      .append(
        $("<div>")
          .addClass("thumbnail")
          .addClass("media")
      );

    var title = photoFloat.trimExtension(media.name);
    var size = getThumbnailSize(media);

    // TODO: same as the the replaceWith below, clone all attrs
    var item;
    if (getType(media) == "video") {
      item = $("<video loop autoplay muted>");
    } else {
      item = $("<img>").attr("src", placeholderImage);
    }
    item
      .attr("title", title)
      .attr("alt", title)
      .attr("height", size)
      .attr("width", size);
    item.appendTo($(".media", link));
    (function(theLink, theImage, theAlbum, theMedia) {
      var img, evt;
      // Load image/video into the cache and replace it when it loads
      if (getType(media) == "image") {
        img = $("<img>");
        event = "load";
      } else {
        img = $("<video>");
        event = "loadeddata";
      }
      img.on(event, function() {
        theImage.attr("src", img.attr("src"));
      });
      img.on("error", function(e) {
        theLink.remove();
        photoFloat.removePhoto(theMedia, theAlbum);
      });
      img.attr(
        "src",
        photoFloat.photoPath(theAlbum, theMedia, getThumbnailSize(theMedia))
      );
    })(link, item, currentAlbum, media);

    return link;
  }

  function makeAlbumThumbnail(parent, album) {
    var link = $("<a>")
      .attr("href", "/view/" + photoFloat.albumHash(album))
      .append(
        $("<div>")
          .addClass("thumbnail")
          .addClass("album")
          .append($("<p>").html(album.path))
      );
    var item = $("<img>").attr("src", placeholderImage);

    item.prependTo($(".album", link));
    (function(theParent, theAlbum, theImage, theLink) {
      function callback(album, photo) {
        var img, evt;
        // Load image/video into the cache and replace it when it loads
        if (getType(photo) == "image") {
          img = $("<img>");
          img.on("load", function() {
            theImage.replaceWith(
              $("<img>")
                .attr("src", img.attr("src"))
                .attr("title", formatDate(album.date))
            );
          });
        } else {
          img = $("<video>");
          img.on("loadeddata", function() {
            theImage.replaceWith(
              $("<video loop autoplay muted playsinline>")
                .attr("src", img.attr("src"))
                .attr("type", "video/mp4")
                .attr("title", formatDate(album.date))
            );
          });
        }
        img.onerror = function() {
          // Remove failed image from album data and try again
          photoFloat.removePhoto(photo, album);
          photoFloat.albumPhoto(theAlbum, callback, error);
        };
        img.attr(
          "src",
          photoFloat.photoPath(album, photo, getThumbnailSize(photo))
        );
      }
      function error() {
        theLink.remove();
        photoFloat.removeAlbum(theAlbum, theParent);
      }
      photoFloat.albumPhoto(theAlbum, callback, error);
    })(parent, album, item, link);
    return link;
  }

  function showAlbum(populate) {
    if (currentPhoto === null && previousPhoto === null)
      $("html, body")
        .stop()
        .animate({ scrollTop: 0 }, "slow");

    if (populate) {
      var thumbsElement = $("#thumbs");
      thumbsElement.empty();
      for (var i = 0; i < currentAlbum.media.length; ++i) {
        thumbsElement.append(
          makeMediaThumbnail(currentAlbum, currentAlbum.media[i])
        );
      }

      var subalbumsElement = $("#subalbums");
      subalbumsElement.empty();
      for (var i = 0; i < currentAlbum.albums.length; ++i) {
        subalbumsElement.append(
          makeAlbumThumbnail(currentAlbum, currentAlbum.albums[i])
        );
      }
      subalbumsElement.insertBefore(thumbsElement);
    }

    if (currentPhoto === null) {
      $("#thumbs img").removeClass("current-thumb");
      $("#album-view").removeClass("photo-view-container");
      $("#subalbums").show();
      $("#photo-view").hide();
      $("#media").hide();
      unloadVideo();
    }
    setTimeout(scrollToThumb, 1);
  }
  function scaleImage() {
    if (currentPhoto == null) {
      return;
    }

    var media = $(getType(currentPhoto) == "video" ? "#video" : "#photo");
    var container = $("#media");
    var ir = currentPhoto.size[0] / currentPhoto.size[1];
    var cw = container.width();
    var ch = container.height();
    if (ir > cw / ch) {
      media.css("width", "100%").css("height", "auto");
    } else {
      media.css("width", "auto").css("height", "100%");
    }
  }
  function showPhoto() {
    var image, photoSrc, previousPhoto, nextPhoto, nextLink, text;
    photoSrc = photoFloat.photoPath(
      currentAlbum,
      currentPhoto,
      getPreviewSize(currentPhoto, fullscreen)
    );

    /* enable/disable fullsize JPG download */
    if (currentPhoto.previews.includes("full")) {
      $("#jpg-link-divider").show();
      $("#jpg-link")
        .show()
        .attr("target", "_blank")
        .attr("href", photoFloat.photoPath(currentAlbum, currentPhoto, "full"))
        .attr("download", currentPhoto.name + ".jpg");
    } else {
      $("#jpg-link-divider").hide();
      $("#jpg-link").hide();
    }

    thumbSrc = photoFloat.photoPath(
      currentAlbum,
      currentPhoto,
      getThumbnailSize(currentPhoto)
    );
    if (getType(currentPhoto) == "video") {
      $("#video").show();
      $("#photo").hide();

      media = $("#video");
      media.attr("src", photoSrc).on("loadeddata", scaleImage);
    } else {
      unloadVideo().hide();
      $("#photo").show();

      image = $("#photo");
      image
        .css("opacity", "")
        .attr("alt", currentPhoto.name)
        .attr("title", formatDate(currentPhoto.date))
        .attr("src", thumbSrc);
      image
        .attr("src", photoSrc)
        .on("load", scaleImage)
        .on("error", function() {
          image.attr("src", thumbSrc).css("opacity", "0.50");
        });
      $("head").append('<link rel="image_src" href="' + photoSrc + '" />');
    }
    $("#media").show();

    previousPhoto =
      currentAlbum.media[
        currentPhotoIndex - 1 < 0
          ? currentAlbum.media.length - 1
          : currentPhotoIndex - 1
      ];
    nextPhoto =
      currentAlbum.media[
        currentPhotoIndex + 1 >= currentAlbum.media.length
          ? 0
          : currentPhotoIndex + 1
      ];
    $.preloadImages(
      photoFloat.photoPath(
        currentAlbum,
        nextPhoto,
        getPreviewSize(nextPhoto, fullscreen)
      ),
      photoFloat.photoPath(
        currentAlbum,
        previousPhoto,
        getPreviewSize(previousPhoto, fullscreen)
      )
    );

    nextLink = "/view/" + photoFloat.photoHash(currentAlbum, nextPhoto);
    $("#next-photo").attr("href", nextLink);
    $("#next").attr("href", nextLink);
    $("#back").attr(
      "href",
      "/view/" + photoFloat.photoHash(currentAlbum, previousPhoto)
    );
    $("#original-link")
      .attr("target", "_blank")
      .attr("href", photoFloat.originalPhotoPath(currentAlbum, currentPhoto))
      .attr("download", currentPhoto.name);

    text = "<table>";
    if (typeof currentPhoto.make !== "undefined")
      text +=
        "<tr><td>Camera Maker</td><td>" + currentPhoto.make + "</td></tr>";
    if (typeof currentPhoto.model !== "undefined")
      text +=
        "<tr><td>Camera Model</td><td>" + currentPhoto.model + "</td></tr>";
    if (typeof currentPhoto.lens !== "undefined")
      text += "<tr><td>Camera Lens</td><td>" + currentPhoto.lens + "</td></tr>";
    if (typeof currentPhoto.date !== "undefined" && currentPhoto.date != null) {
      text += "<tr><td>Time Taken</td><td>" + formatDate(currentPhoto.date);
      if (typeof currentPhoto.timezone !== "undefined") {
        var tz = currentPhoto.timezone;
        if (tz == 0) {
          text += "Z";
        } else {
          var sign = tz < 0 ? "-" : "+";
          tz = Math.abs(tz);
          var hours = Math.floor(tz);
          var minutes = Math.floor((tz - hours) * 60);
          text += sign + zeroPad(hours, 2) + ":" + zeroPad(minutes, 2);
        }
      }
      text += "</td></tr>";
    }
    if (typeof currentPhoto.size !== "undefined")
      text +=
        "<tr><td>Resolution</td><td>" +
        currentPhoto.size[0] +
        " x " +
        currentPhoto.size[1] +
        "</td></tr>";
    if (typeof currentPhoto.aperture !== "undefined")
      text +=
        "<tr><td>Aperture</td><td> f/" + currentPhoto.aperture + "</td></tr>";
    if (typeof currentPhoto.focalLength !== "undefined")
      text +=
        "<tr><td>Focal Length</td><td>" +
        currentPhoto.focalLength +
        "</td></tr>";
    if (typeof currentPhoto.subjectDistanceRange !== "undefined")
      text +=
        "<tr><td>Subject Distance Range</td><td>" +
        currentPhoto.subjectDistanceRange +
        "</td></tr>";
    if (typeof currentPhoto.iso !== "undefined")
      text += "<tr><td>ISO</td><td>" + currentPhoto.iso + "</td></tr>";
    if (typeof currentPhoto.fov !== "undefined")
      text += "<tr><td>FOV</td><td>" + currentPhoto.fov + "</td></tr>";
    if (typeof currentPhoto.shutter !== "undefined")
      text +=
        "<tr><td>Shutter Speed</td><td>" +
        currentPhoto.shutter +
        " sec</td></tr>";
    if (typeof currentPhoto.exposureProgram !== "undefined")
      text +=
        "<tr><td>Exposure Program</td><td>" +
        currentPhoto.exposureProgram +
        "</td></tr>";
    if (typeof currentPhoto.exposureCompensation !== "undefined")
      text +=
        "<tr><td>Exposure Compensation</td><td>" +
        currentPhoto.exposureCompensation +
        "</td></tr>";
    if (typeof currentPhoto.meteringMode !== "undefined")
      text +=
        "<tr><td>Metering Mode</td><td>" +
        currentPhoto.meteringMode +
        "</td></tr>";
    if (typeof currentPhoto.lightSource !== "undefined")
      text +=
        "<tr><td>Light Source</td><td>" +
        currentPhoto.lightSource +
        "</td></tr>";
    if (typeof currentPhoto.flash !== "undefined")
      text += "<tr><td>Flash</td><td>" + currentPhoto.flash + "</td></tr>";
    if (typeof currentPhoto.orientation !== "undefined")
      text +=
        "<tr><td>Orientation</td><td>" +
        currentPhoto.orientation +
        "</td></tr>";
    if (typeof currentPhoto.mimeType !== "undefined")
      text +=
        "<tr><td>MIME Type</td><td>" + currentPhoto.mimeType + "</td></tr>";
    if (typeof currentPhoto.creator !== "undefined")
      text +=
        "<tr><td>Photographer</td><td>" + currentPhoto.creator + "</td></tr>";
    if (typeof currentPhoto.caption !== "undefined")
      text += "<tr><td>Caption</td><td>" + currentPhoto.caption + "</td></tr>";
    if (typeof currentPhoto.keywords !== "undefined")
      text +=
        "<tr><td>Keywords</td><td>" +
        currentPhoto.keywords.join(", ") +
        "</td></tr>";
    if (typeof currentPhoto.gps !== "undefined") {
      var lat = currentPhoto.gps[0];
      var lon = currentPhoto.gps[1];
      text +=
        "<tr><td>Location</td><td>" +
        "<a target='_blank' href='https://www.openstreetmap.org/?mlat=" +
        lat +
        "&mlon=" +
        lon +
        "#map=15/" +
        lat +
        "/" +
        lon +
        "'>OpenStreetMap</a>, " +
        "<a target='_blank' href='https://www.google.com/maps/search/?api=1&query=" +
        lat +
        "," +
        lon +
        "'>Google Maps</a>" +
        "</td></tr>";
    }
    text += "</table>";
    $("#metadata").html(text);

    $("#album-view").addClass("photo-view-container");
    $("#subalbums").hide();
    $("#photo-view").show();
  }

  /* Error displays */

  function die(error) {
    if (error == 403) {
      $("#auth-text").fadeIn(1000);
      $("#password").focus();
    } else $("#error-text").fadeIn(2500);
    $("#error-overlay").fadeTo(500, 0.8);
    $("body, html").css("overflow", "hidden");
  }
  function undie() {
    $("#error-text, #error-overlay, #auth-text").fadeOut(500);
    $("body, html").css("overflow", "auto");
  }

  /* Entry point for most events */

  function locationParsed(album, photo, photoIndex) {
    undie();
    $("#loading").hide();
    if (album === currentAlbum && photo === currentPhoto) return;
    previousAlbum = currentAlbum;
    previousPhoto = currentPhoto;
    currentAlbum = album;
    currentPhoto = photo;
    currentPhotoIndex = photoIndex;
    setTitle();
    if (photo !== null) showPhoto();
    showAlbum(previousAlbum !== currentAlbum);
  }

  function loadPage(event) {
    $(window).trigger("pageload");
    $("#loading").show();
    $("link[rel=image_src]").remove();
    photoFloat.parseLocation(location, locationParsed, die);
  }

  /* Event listeners */
  $(window).on("popstate", loadPage);
  $(window).on("resize", scaleImage);
  $(document).on("click", "a[href][target!='_blank']", function(e) {
    target = e.currentTarget;
    if (location.host == target.host) {
      e.preventDefault();
      if (location.href !== target.href) {
        history.pushState(null, null, target.href);
        loadPage(null);
      }
    }
  });
  $(document).keydown(function(e) {
    if (currentPhoto !== null) {
      key = e.key;
      if (key == "ArrowLeft" || key == "Left") {
        $("#back").click();
        return false;
      } else if (key == "ArrowRight" || key == "Right") {
        $("#next").click();
        return false;
      }
    }
    return true;
  });
  $("#photo-box").mouseenter(function() {
    $("#photo-links")
      .stop()
      .fadeTo("slow", 0.5)
      .css("display", "inline");
  });
  $("#photo-box").mouseleave(function() {
    $("#photo-links")
      .stop()
      .fadeOut("slow");
  });
  $("#next, #back").mouseenter(function() {
    $(this)
      .stop()
      .fadeTo("slow", 1);
  });
  $("#next, #back").mouseleave(function() {
    $(this)
      .stop()
      .fadeTo("slow", 0.35);
  });
  if ($.support.fullscreen) {
    $("#fullscreen-divider").show();
    $("#fullscreen")
      .show()
      .click(function() {
        $("#media").fullScreen({
          callback: function(isFullscreen) {
            fullscreen = isFullscreen;
            showPhoto();
          }
        });
      });
  }
  $("#metadata-link").click(function() {
    if (!$("#metadata").is(":visible"))
      $("#metadata")
        .stop()
        .css("height", 0)
        .css("padding-top", 0)
        .css("padding-bottom", 0)
        .show()
        .animate(
          {
            height: $("#metadata > table").height(),
            paddingTop: 3,
            paddingBottom: 3
          },
          "slow",
          function() {
            $(this).css("height", "auto");
            $("#metadata-link").text(
              $("#metadata-link")
                .text()
                .replace("show", "hide")
            );
          }
        );
    else
      $("#metadata")
        .stop()
        .animate(
          { height: 0, paddingTop: 0, paddingBottom: 0 },
          "slow",
          function() {
            $(this).hide();
            $("#metadata-link").text(
              $("#metadata-link")
                .text()
                .replace("hide", "show")
            );
          }
        );
  });
  $("#auth-form").submit(function() {
    var password = $("#password");
    password.css("background-color", "rgb(128, 128, 200)");
    photoFloat.authenticate(password.val(), function(success) {
      password.val("");
      if (success) {
        password.css("background-color", "rgb(200, 200, 200)");
        setTimeout(loadPage);
      } else {
        password.css("background-color", "rgb(255, 64, 64)");
      }
    });
    return false;
  });

  // Initial page load
  if (location.pathname == "/") {
    // Causes the page to redirect and reload
    location.href += "view";
  } else {
    setTimeout(loadPage);
  }
});
