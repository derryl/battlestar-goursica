#!/usr/bin/env python

# run pip install -r requirements.txt

# Linux requirements:
# apt-get install sox
# apt-get install python-tk

from collections import OrderedDict
from datetime import datetime
from dateutil.parser import parse as dateparse
from json import loads
from subprocess import CalledProcessError, Popen, PIPE, check_output, check_call, \
    call
from time import sleep
import Tkinter
import base64
import inspect
import json
import logging
import os
import re
import sys
import urllib2

# Set current directory
CURRENT_DIR = os.path.dirname(inspect.getfile(inspect.currentframe()))

# Get screen resolution
t = Tkinter.Tk()
SCREEN_WIDTH = t.winfo_screenwidth()
SCREEN_HEIGHT = t.winfo_screenheight()

# Battlestar Goursica config
BSG_CONFIG = json.load(open(os.path.abspath('%s/bsgconfig.json' % CURRENT_DIR), 'r'))
ORGANIZATION = BSG_CONFIG.get('org')
USERNAME = BSG_CONFIG.get('user')
PASSWORD = BSG_CONFIG.get('pass')
ACTIVITY = BSG_CONFIG.get('activity')

# Gource config
GOURCE_CONFIG = os.path.abspath('%s/gourceconfig.ini' % CURRENT_DIR)

# Gravatar
GRAVATAR_SCRIPT = os.path.abspath('%s/gravatars.pl' % CURRENT_DIR)

# Sound
SOUND_FILE = os.path.abspath('%s/happykids.wav' % CURRENT_DIR)

# Global settings
ROWS = 3
COLUMNS = 2
DISPLAY_COUNT = ROWS * COLUMNS
REPO_STORE = os.path.abspath('%s/repositories' % CURRENT_DIR)
REFRESH_RATE = 10  # seconds!
GIT_LOG_OPTS = ['git', 'log', '--pretty=format:user:%aN%n%ct', '--reverse', '--raw', '--encoding=UTF-8', '--no-renames', '-n', '100']

if USERNAME and PASSWORD:
    HEADERS = {'Authorization': 'Basic %s' % base64.encodestring('%s:%s' % (USERNAME, PASSWORD))}
else:
    HEADERS = {}

if ORGANIZATION:
    if USERNAME and PASSWORD and ACTIVITY == 'all':
        GITHUB_API = 'https://api.github.com/users/%s/events/orgs/%s?per_page=100' % (USERNAME, ORGANIZATION)
    else:
        GITHUB_API = 'https://api.github.com/orgs/%s/events?per_page=100' % (ORGANIZATION)
elif USERNAME:
    GITHUB_API = 'https://api.github.com/users/%s/events?per_page=100' % USERNAME

if not os.path.exists(REPO_STORE):
    os.makedirs(REPO_STORE)

gources = OrderedDict()  # In order of creation time, not screen position
last_update = datetime.min.isoformat() + 'Z'


class RepoGoneError(Exception):
    pass


def retrieve_last_pushes():
    ''' Returns an OrderedDict (in chronological order) of key, revision for all recent pushes since last check. '''
    global last_update

    req = urllib2.Request(GITHUB_API,
                          headers=HEADERS)
    events = loads(urllib2.urlopen(req).read())
    events = [e for e in events if e['type'] == u'PushEvent' and (ACTIVITY == 'all' or e['public']) and dateparse(e['created_at']) > dateparse(last_update)]
    events.reverse()  # chrono order

    if not events:
        logging.debug('No events\n')

    last_events = OrderedDict()
    for event in events:
        # Key looks like ff0000/project/some/branch/name (removes refs/heads)
        key = '/'.join([event['repo']['name'], re.sub('^refs/heads/', '', event['payload']['ref'])])
        if key in last_events:
            del last_events[key]  # make sure to track the most recent one only
        last_events[key] = event['payload']['head']

    if events:
        last_update = events[-1]['created_at']

    return last_events


def path_for_key(key):
    return os.path.join(REPO_STORE, re.sub(r'[/.\\]', '_', key))


def clean_title(key):
    return key.split('/', 1)[-1].replace('/', ' / ')


def calculate_viewport():
    return '%sx%s' % ((SCREEN_WIDTH // COLUMNS) - COLUMNS, (SCREEN_HEIGHT // ROWS) - ROWS)


def update_repo(key):
    repo = '/'.join(key.split('/')[:2])
    ref = '/'.join(key.split('/')[2:])
    try:
        if not os.path.exists(path_for_key(key)):
            logging.debug('Cloning repo %s' % repo)
            check_output(['git', 'clone', '-b', ref, '--depth', '1', 'git@github.com:%s.git' % repo, path_for_key(key)])
            os.chdir(path_for_key(key))
        else:
            os.chdir(path_for_key(key))
            logging.debug('Updating repo for %s' % key)
            check_output(['git', 'pull', 'origin', '%s' % ref])
    except CalledProcessError:
        logging.warn('Looks like we got an error from a called git process.  Assuming repo is gone.')
        raise RepoGoneError

    # Gravatar regardless of condition
    check_output(['perl', '%s' % GRAVATAR_SCRIPT, '%s' % path_for_key(key)])

    # Yay sound.
    play_sound()


def create_gource(key, newrev, in_place_of=None, position=None):
    update_repo(key)
    if in_place_of:
        position = remove_gource(in_place_of)
    os.chdir(path_for_key(key))

    log = check_output(GIT_LOG_OPTS)
    gource = Popen(['gource', '--load-config', GOURCE_CONFIG, '--user-image-dir', '%s/.git/avatar' % path_for_key(key), '--viewport', calculate_viewport(),  '--title', clean_title(key), '-'], stdin=PIPE)

    if not os.fork():
        gource.stdin.write(log)
        gource.stdin.flush()
        sys.exit()

    gources[key] = {'process': gource, 'position': position, 'lastrev': newrev}


def update_gource(key, newrev):
    update_repo(key)
    os.chdir(path_for_key(key))

    gource = gources[key]['process']
    log = check_output(GIT_LOG_OPTS + ['%s..%s' % (gources[key]['lastrev'], newrev)])

    if not os.fork():
        gource.stdin.write(log)
        gource.stdin.flush()
        sys.exit()

    gources[key]['lastrev'] = newrev


def remove_gource(key):
    gource = gources[key]['process']
    position = gources[key]['position']
    gource.terminate()
    del gources[key]
    return position


def play_sound():
    if not os.fork():
        if call('which afplay', shell=True) == 0:
            # OS X
            check_call(['afplay', SOUND_FILE])
        elif call('which play', shell=True) == 0:
            # Linux
            print 'play', SOUND_FILE
            check_call(['play', SOUND_FILE])
        else:
            logging.warning('No compatible sound program (afplay/play) detected')
        sys.exit()


def main(argv):
    pid = os.getpid()
    try:
        while True:
            # EVENT LOOP!!!
            events = retrieve_last_pushes()
            events_to_show = OrderedDict([k, events[k]] for k in events.keys()[-1 * DISPLAY_COUNT:])  # if we received more than we can show, ignore the oldest
            remaining_events = OrderedDict([k, events[k]] for k in events.keys()[:-1 * DISPLAY_COUNT])

            # Now which gources do we keep and which do we replace?
            old_gources = [id for id in gources if id not in events_to_show]
            assert len(old_gources) <= [len(set(events_to_show.keys()) - set(gources.keys()))]

            for key, newrev in events_to_show.iteritems():
                try:
                    if key in gources:
                        logging.debug('Updating gource %s: -> %s' % (key, newrev))
                        update_gource(key, newrev)
                    elif old_gources:
                        oldest = old_gources.pop(0)
                        logging.debug('Replacing gource %s with %s' % (oldest, key))
                        create_gource(key, newrev, in_place_of=oldest)
                    else:
                        logging.debug('Adding gource %s' % key)
                        create_gource(key, newrev)
                except RepoGoneError:
                    if remaining_events:
                        k, v = remaining_events.popitem(last=True)
                        events_to_show[k] = v
                    else:
                        logging.warn('No remaining events to show.')

#            for key, data in gources.iteritems():
#                print key, data['process'].poll()

            sleep(REFRESH_RATE)

    finally:
        if pid == os.getpid():
            for gource in gources.values():
                gource['process'].terminate()

if __name__ == '__main__':
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    main(sys.argv[1:])
