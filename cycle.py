#!/usr/bin/env python

# Linux requirements:
# apt-get install xdotool

import os
import sys
from subprocess import call

os.environ['DISPLAY'] = ':0.0'

CYCLES = 5


def main(argv):
    for x in range(0, CYCLES):
        call(['xdotool', 'key', 'alt+shift+j'])

if __name__ == '__main__':
    main(sys.argv[1:])
