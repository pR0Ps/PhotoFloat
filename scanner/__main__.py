#!/usr/bin/env python

from scanner.TreeWalker import TreeWalker
from scanner.CachePath import message
import sys
import os

def main():
    reload(sys)
    sys.setdefaultencoding("UTF-8")

    if len(sys.argv) < 2:
        print """usage: %s <album> [ <cache> ]

<album>: a directory where you store a hierarchy of album folders
<cache>: where photofloat will generate thumbnails and other data (default: <album>/../cache)
""" % sys.argv[0]
        return

    album = sys.argv[1]
    if len(sys.argv) < 3:
        cache = os.path.join(album, "..", "cache")
    else:
        cache = sys.argv[2]

    try:
        os.umask(022)
        TreeWalker(album, cache)
    except KeyboardInterrupt:
        message("keyboard", "CTRL+C pressed, quitting.")
        sys.exit(-97)

if __name__ == "__main__":
    main()
