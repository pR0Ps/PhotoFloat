<?php
function cachePath($path) {
	if ($path[0] == '/')
		$path = substr($path, 1);
	if ($path[strlen($path) - 1] == '/')
		$path = substr($path, 0, strlen($path) - 1);
	$path = str_replace('_-_', '-', str_replace('/', '-', str_replace(' ', '_', str_replace('(', '', str_replace(')', '', str_replace('#', '', str_replace('[', '', str_replace(']', '', str_replace('"', '', str_replace("'", '', strtolower($path)))))))))));
	while (strpos($path, "--") !== false)
		$path = str_replace("--", "-", $path);
	while (strpos($path, "__") !== false)
		$path = str_replace("__", "_", $path);
	if (strlen(path) == 0)
		$path = "root";
	
	return $path;
}

$url = $_SERVER["SCRIPT_URL"];
if ($url[strlen($url) - 1] == '/')
	$url = substr($url, 0, strlen($url) - 1);

if (strpos(strtolower($url), ".php") == strlen($url) - 4) {
	$url = substr($url, 0, strlen($url) - 4);
	$index = strrpos($url, "/");
	$redirect = "/#".cachePath(substr($url, 0, $index))."/".cachePath(substr($url, $index));
} else
	$redirect = "/#".cachePath($url);
	
header("Location: $redirect");

?>