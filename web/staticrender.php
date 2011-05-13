<?php
if ($_ENV["SCRIPT_URL"] == $_ENV["SCRIPT_NAME"])
	die("Infinite loop.");
putenv('LANG=en_US.UTF-8');
passthru("utils/serverexecute ".escapeshellarg($_ENV["SCRIPT_URI"]."#!".$_GET["_escaped_fragment_"]));
?>
