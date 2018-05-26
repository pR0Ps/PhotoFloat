#!/usr/bin/env python3

import http.server
import os
import re
import socketserver
import webbrowser

class Handler(http.server.SimpleHTTPRequestHandler):
    """Simple handler with regex-based URL translation"""

    # Translations to apply in-order
    _translations = (("^/view(/.*)?$", "/index.html"), )

    def translate_path(self, path):
        for pattern, repl in self._translations:
            path = re.sub(pattern, repl, path, count=1, flags=re.IGNORECASE)
        return super().translate_path(path)

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "public"))

with socketserver.TCPServer(("localhost", 8000), Handler) as httpd:
    webbrowser.open("http://localhost:8000")
    httpd.serve_forever()
