#!/usr/bin/env python

from TreeWalker import TreeWalker
from sys import argv

def main():
	if len(argv) != 3:
		print "usage: %s ALBUM_PATH CACHE_PATH" % argv[0]
		return
	TreeWalker(argv[1], argv[2])
	
if __name__ == "__main__":
	main()