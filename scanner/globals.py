#!/usr/bin/env python3

"""
This file stores global state for the scanner
"""

# The read-only config options that the scanner was started with.
# This is so a config option doesn't have to keep being passed around.
CONFIG = None

# The current scraping level. This should ONLY be used for displaying log msgs
depth = 0
