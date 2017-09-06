#!/usr/bin/env python

import argparse
import sys
import os

from scanner.tree_walker import TreeWalker
from scanner.cache_path import message


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("album",
                        help="A directory where you store a hierarchy of album folders")
    parser.add_argument("cache", nargs='?',
                        help="where photofloat will generate thumbnails and other data (default: <album>/../cache)")
    parser.add_argument("--salt", nargs='?', type=argparse.FileType('rb'),
                        help="A file containing data to salt the image filenames with"),
    parser.add_argument("--remove-stale", action="store_true",
                        help="Remove stale data/thumbnails from the cache (default: just list them)")
    config = parser.parse_args()

    if config.salt:
        config.salt = config.salt.read()

    if not config.cache:
        config.cache = os.path.join(config, os.path.pardir, "cache")

    try:
        os.umask(0x022)
        TreeWalker(config)
    except KeyboardInterrupt:
        message("keyboard", "CTRL+C pressed, quitting.")
        sys.exit(-97)

if __name__ == "__main__":
    main()
