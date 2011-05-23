#!/usr/bin/env python

from TreeWalker import TreeWalker
from sys import argv, exit
from CachePath import message

def main():
	if len(argv) != 3:
		print "usage: %s ALBUM_PATH CACHE_PATH" % argv[0]
		return
	try:
		TreeWalker(argv[1], argv[2])
	except KeyboardInterrupt:
		message("keyboard", "CTRL+C pressed, quitting.")
		exit(-97)
	
if __name__ == "__main__":
	main()