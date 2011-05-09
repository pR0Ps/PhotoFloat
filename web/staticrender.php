<?php
putenv('LANG=en_US.UTF-8');
passthru("utils/serverexecute ".escapeshellarg($_ENV["SCRIPT_URI"]."#!".$_GET["_escaped_fragment_"]));
?>
