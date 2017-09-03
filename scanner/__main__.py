#!/usr/bin/env python

import sys
import os

from scanner.tree_walker import TreeWalker
from scanner.cache_path import message


def main():

    if len(sys.argv) < 2:
        print ("""usage: {} <album> [ <cache> ]

<album>: a directory where you store a hierarchy of album folders
<cache>: where photofloat will generate thumbnails and other data (default: <album>/../cache)
""".format(sys.argv[0]))
        return

    album = sys.argv[1]
    if len(sys.argv) < 3:
        cache = os.path.join(album, "..", "cache")
    else:
        cache = sys.argv[2]

    try:
        os.umask(0x022)
        TreeWalker(album, cache)
    except KeyboardInterrupt:
        message("keyboard", "CTRL+C pressed, quitting.")
        sys.exit(-97)

if __name__ == "__main__":
    main()
