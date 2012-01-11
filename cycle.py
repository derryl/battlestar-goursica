#!/usr/bin/env python

# Linux requirements:
# apt-get install xdotool

import logging
import sys
from subprocess import call

CYCLES = 5


def main(argv):
    for x in range(0, CYCLES):
        logging.debug('Cycling...')
        call(['xdotool', 'key', 'alt+shift+j'])

if __name__ == '__main__':
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    main(sys.argv[1:])
