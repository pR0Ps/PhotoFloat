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
  var maxSize = 1024;
  var placeholderImage = "/assets/loading.gif";

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
  function showAlbum(populate) {
    var i, link, image, photos, thumbsElement, subalbums, subalbumsElement;
    if (currentPhoto === null && previousPhoto === null)
      $("html, body")
        .stop()
        .animate({ scrollTop: 0 }, "slow");

    if (populate) {
      photos = [];
      for (var i = 0; i < currentAlbum.media.length; ++i) {
        link = $(
          '<a href="/view/' +
            photoFloat.photoHash(currentAlbum, currentAlbum.media[i]) +
            '"></a>'
        );

        // Create the image with the placeholder and swap to the real one once it loads
        image = $(
          '<img title="' +
            photoFloat.trimExtension(currentAlbum.media[i].name) +
            '"' +
            'alt="' +
            photoFloat.trimExtension(currentAlbum.media[i].name) +
            '"' +
            'src="' +
            placeholderImage +
            '" height="150" width="150" />'
        );
        image.get(0).photo = currentAlbum.media[i];
        link.append(image);
        photos.push(link);
        (function(theLink, theImage, theAlbum) {
          var img = new Image();
          img.onload = function() {
            theImage.attr("src", img.src);
          };
          img.onerror = function() {
            photos.splice(photos.indexOf(theLink), 1);
            theLink.remove();
            theAlbum.media.splice(
              theAlbum.media.indexOf(theImage.get(0).photo),
              1
            );
          };
          img.src = photoFloat.photoPath(
            theAlbum,
            theAlbum.media[i],
            150,
            true
          );
        })(link, image, currentAlbum);
      }
      thumbsElement = $("#thumbs");
      thumbsElement.empty();
      thumbsElement.append.apply(thumbsElement, photos);

      subalbums = [];
      for (var i = 0; i < currentAlbum.albums.length; ++i) {
        link = $(
          '<a href="/view/' +
            photoFloat.albumHash(currentAlbum.albums[i]) +
            '"></a>'
        );
        image = $("<div>" + currentAlbum.albums[i].path + "</div>")
          .addClass("album-button")
          .attr("title", formatDate(currentAlbum.albums[i].date));
        link.append(image);
        subalbums.push(link);
        (function(theContainer, theAlbum, theImage, theLink) {
          photoFloat.albumPhoto(
            theAlbum,
            function(album, photo) {
              // Only set the background-image once it has finished loading
              var img = new Image();
              img.onload = function() {
                theImage.css("background-image", "url(" + img.src + ")");
              };
              img.onerror = function() {
                // Remove failed image from album data
                album.media.splice(album.media.indexOf(photo), 1);
                //TODO: Try next image in album?
              };
              img.src = photoFloat.photoPath(album, photo, 150, true);
            },
            function error() {
              theContainer.albums.splice(
                currentAlbum.albums.indexOf(theAlbum),
                1
              );
              theLink.remove();
              subalbums.splice(subalbums.indexOf(theLink), 1);
            }
          );
        })(currentAlbum, currentAlbum.albums[i], image, link);
      }
      subalbumsElement = $("#subalbums");
      subalbumsElement.empty();
      subalbumsElement.append.apply(subalbumsElement, subalbums);
      subalbumsElement.insertBefore(thumbsElement);
    }

    if (currentPhoto === null) {
      $("#thumbs img").removeClass("current-thumb");
      $("#album-view").removeClass("photo-view-container");
      $("#subalbums").show();
      $("#photo-view").hide();
    }
    setTimeout(scrollToThumb, 1);
  }
  function scaleImage() {
    if (currentPhoto == null) {
      return;
    }

    var image = $("#photo");
    var container;
    if (image.hasClass("fullScreen")) {
      container = $(document);
    } else {
      container = $("#photo-view");
    }

    var ir = currentPhoto.size[0] / currentPhoto.size[1];
    var cw = container.width();
    var ch = container.height();
    if (ir > cw / ch) {
      image.css("width", "100%").css("height", "auto");
    } else {
      image.css("width", "auto").css("height", "100%");
    }
  }
  function showPhoto() {
    var image, photoSrc, previousPhoto, nextPhoto, nextLink, text;
    photoSrc = photoFloat.photoPath(currentAlbum, currentPhoto, maxSize, false);
    image = $("#photo");
    image
      .attr("alt", currentPhoto.name)
      .attr("title", formatDate(currentPhoto.date))
      .attr("src", photoFloat.photoPath(currentAlbum, currentPhoto, 150, true));
    image.attr("src", photoSrc).on("load", scaleImage);
    $("head").append('<link rel="image_src" href="' + photoSrc + '" />');

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
      photoFloat.photoPath(currentAlbum, nextPhoto, maxSize, false),
      photoFloat.photoPath(currentAlbum, previousPhoto, maxSize, false)
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
      .attr("href", photoFloat.originalPhotoPath(currentAlbum, currentPhoto));

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
        $("#photo").fullScreen({
          callback: function(isFullscreen) {
            maxSize = isFullscreen ? 1600 : 1024;
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
