var analyticsId = "";

if (analyticsId) {
  window.dataLayer = window.dataLayer || [];
  function gtag() {
    dataLayer.push(arguments);
  }
  gtag("js", new Date());
  $.ajax("https://www.googletagmanager.com/gtag/js?id=" + analyticsId, {
    dataType: "script",
    cache: true
  });
  $(window).on("pageload", function() {
    gtag("config", analyticsId, {
      page_title: document.title,
      page_location: location.toString(),
      page_path: location.pathname
    });
  });
}
