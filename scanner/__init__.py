"""
PhotoFloat scanner

The scanner is the Python component of PhotoFloat that traverses a directory
structure and creates the json files that the frontend uses to serve the
gallery.
"""

import logging
import re

import scanner.globals

# Set up a custom logger so log messages from the module are displayed in a
# tree as the scanner works over directories.

CATEGORY_RE = re.compile(r"\s*\[\s*([^\]]*)\s*\]\s*(.*)")

class TreeLogFormatter(logging.Formatter):
    def formatMessage(self, record):
        msg = record.getMessage()

        assert scanner.globals.depth >= 0
        prefix = scanner.globals.depth * "  |"
        prefix += "--" if scanner.globals.depth else "  "

        # Get category from extra args or message
        category = getattr(record, "category", None)
        if not category:
            m = CATEGORY_RE.fullmatch(msg)
            if m:
                category, msg = m.groups()
        if not category:
            category = "message"
        category = "[{}]".format(category)

        # Overwrite the message with the custom tree format
        record.message = "{prefix}{category:15}{message}".format(prefix=prefix,
                                                                 category=category,
                                                                 message=msg)
        # Format the new message into the format string
        return super().formatMessage(record)

handler = logging.StreamHandler()
handler.setFormatter(TreeLogFormatter("[%(levelname)8s] %(asctime)-15s %(message)s"))
logging.getLogger(__name__).addHandler(handler)
