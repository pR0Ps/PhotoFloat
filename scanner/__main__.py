#!/usr/bin/env python

import argparse
import sys
import os
import logging

from scanner.tree_walker import TreeWalker
from scanner.cache_path import message

logging.basicConfig(format="%(asctime)-15s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("albums",
                        help="A directory where you store a hierarchy of album folders")
    parser.add_argument("-c", "--cache", nargs='?',
                        help="Where photofloat will generate thumbnails and other data (default: <ALBUM>/../cache)")
    parser.add_argument("-s", "--salt", nargs='?', type=argparse.FileType('rb'),
                        help="A file containing data to salt the image filenames with"),
    parser.add_argument("--remove-stale", action="store_true",
                        help="Remove stale data/thumbnails from the cache (default: just list them)")
    parser.add_argument("--no-location", action="store_true",
                        help="Don't pull any location/GPS data out of photo metadata")
    config = parser.parse_args()

    if config.salt:
        config.salt = config.salt.read()

    if not config.cache:
        config.cache = os.path.join(config.albums, os.path.pardir, "cache")

    try:
        os.umask(0x022)
        logger.info("Starting walk")
        TreeWalker(config)
        logger.info("Finished walk")
    except KeyboardInterrupt:
        message("keyboard", "CTRL+C pressed, quitting.")
        sys.exit(-97)

if __name__ == "__main__":
    main()
