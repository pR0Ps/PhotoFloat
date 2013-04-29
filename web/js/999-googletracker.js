$(window).load(function () {
	window._gaq = window._gaq || [];
	window._gaq.push(['_setAccount', 'UA-XXXXXX-XXX']);
	var ga = document.createElement('script');
	ga.type = 'text/javascript';
	ga.async = true;
	ga.src = ('https:' == document.location.protocol ? 'https://ssl' : 'http://www') + '.google-analytics.com/ga.js';
	var s = document.getElementsByTagName('script')[0];
	s.parentNode.insertBefore(ga, s);
});
$(window).hashchange(function() {
	window._gaq = window._gaq || [];
	window._gaq.push(['_trackPageview']);
	window._gaq.push(['_trackPageview', PhotoFloat.cleanHash(location.hash)]);
});
