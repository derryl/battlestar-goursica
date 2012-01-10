#!/usr/bin/env python

# run pip install -r requirements.txt
# you'll need to have the redis server running, too ('brew install redis')

from dateutil.parser import parse as dateparse
from collections import OrderedDict
from json import loads
from subprocess import Popen, PIPE, check_output
import json
import base64
import logging
import os
import re
import redis
import sys
import urllib2
from time import sleep
from datetime import datetime

# Set current directory
CURRENT_DIR = os.getcwd()

# Battlestar Goursica config
BSG_CONFIG = json.load(open(os.path.abspath('%s/bsgconfig.json' % CURRENT_DIR), 'r'))
ORGANIZATION = BSG_CONFIG['org']
USERNAME = BSG_CONFIG['user']
PASSWORD = BSG_CONFIG['pass']

# Gource config
GOURCE_CONFIG = os.path.abspath('%s/gourceconfig.ini' % CURRENT_DIR)

# Gravatar
GRAVATAR_SCRIPT = os.path.abspath('%s/gravatars.pl' % CURRENT_DIR)

# Global settings
DISPLAY_COUNT = 4
REPO_STORE = os.path.abspath('%s/repositories' % CURRENT_DIR)
REFRESH_RATE = 10  # seconds!
GITHUB_API = 'https://api.github.com/users/%s/events/orgs/%s' % (USERNAME, ORGANIZATION)
GIT_LOG_OPTS = ['git', 'log', '--pretty=format:user:%aN%n%ct', '--reverse', '--raw', '--encoding=UTF-8', '--no-renames', '-n', '100']

if not os.path.exists(REPO_STORE):
    os.makedirs(REPO_STORE)

gources = OrderedDict()  # In order of creation time, not screen position
r = redis.StrictRedis(host='localhost', port=6379, db='battlestar_goursica')
r.delete('last_update')


def retrieve_last_pushes():
    ''' Returns an OrderedDict (in chronological order) of key, revision for all recent pushes since last check. '''

    last_update = r.get('last_update') or datetime.min.isoformat() + 'Z'

    req = urllib2.Request(GITHUB_API,
                          headers={'Authorization': 'Basic %s' % base64.encodestring('%s:%s' % (USERNAME, PASSWORD))})
    events = loads(urllib2.urlopen(req).read())
    events = [e for e in events if e['type'] == u'PushEvent' and dateparse(e['created_at']) > dateparse(last_update)]
    events.reverse()  # chrono order

    if not events:
        logging.debug('No events\n')

    last_events = OrderedDict()
    for event in events:
        # Key looks like ff0000/project/some/branch/name (removes refs/heads)
        key = '/'.join([event['repo']['name'], re.sub('^refs/heads/', '', event['payload']['ref'])])
        last_events[key] = event['payload']['head']

    if events:
        r.set('last_update', events[-1]['created_at'])

    return last_events


def path_for_key(key):
    return os.path.join(REPO_STORE, re.sub(r'[/.\\]', '_', key))


def update_repo(key):
    repo = '/'.join(key.split('/')[:2])
    ref = '/'.join(key.split('/')[2:])
    if not os.path.exists(path_for_key(key)):
        logging.debug('Cloning repo %s' % repo)
        check_output(['git', 'clone', '-b', ref, '--depth', '1', 'git@github.com:%s.git' % repo, path_for_key(key)])
        os.chdir(path_for_key(key))
    else:
        os.chdir(path_for_key(key))
        logging.debug('Updating repo for %s' % key)
        check_output(['git', 'pull', 'origin', '%s' % ref])

    # Gravatar regardless of condition
    check_output(['perl', '%s' % GRAVATAR_SCRIPT, '%s' % path_for_key(key)])


def create_gource(key, position):
    update_repo(key)
    os.chdir(path_for_key(key))
    log = check_output(GIT_LOG_OPTS)
    gource = Popen(['gource', '--load-config', GOURCE_CONFIG, '--user-image-dir', '%s/.git/avatar' % path_for_key(key), '--title', key.split('/', 1)[-1].replace('/', ' / '), '-'], stdin=PIPE, stdout=PIPE, stderr=PIPE)

    # For some reason forking here (to prevent locking by gource taking its time accepting stdin)
    # combined with depth=1 or since=date, was causing an old gource to be killed every time a new one was created.  Yikes.
    gource.stdin.write(log)
    gource.stdin.flush()

    gources[key] = {'process': gource, 'position': position}


def update_gource(key, oldrev, newrev):
    gource = gources[key]['process']
    update_repo(key)
    os.chdir(path_for_key(key))
    log = check_output(GIT_LOG_OPTS.append('%s..%s' % (oldrev, newrev)))

    gource.stdin.write(log)
    gource.stdin.flush()


def remove_gource(key):
    gource = gources[key]['process']
    position = gources[key]['position']
    gource.terminate()
    del gources[key]
    return position


def main(argv):
    try:
        while True:
            # EVENT LOOP!!!
            last_events = retrieve_last_pushes()
            events_to_show = OrderedDict([k, last_events[k]] for k in last_events.keys()[-1 * DISPLAY_COUNT:])  # if we received more than we can show, ignore the oldest

            # Now which gources do we keep and which do we replace?
            old_gources = [id for id in gources if id not in events_to_show]
            assert len(old_gources) <= [len(set(events_to_show.keys()) - set(gources.keys()))]

            for key, newrev in events_to_show.iteritems():
                if key in gources:
                    oldrev = r.hget('last_events', key)
                    logging.debug('Updating gource %s: %s -> %s' % (key, oldrev, newrev))
                    update_gource(key, oldrev, newrev)
                elif old_gources:
                    logging.debug('Removing gource %s' % key)
                    position = remove_gource(old_gources.pop(0))
                    create_gource(key, position)
                else:
                    logging.debug('Adding gource %s' % key)
                    position = 0
                    create_gource(key, position)

            # Save data
            if last_events:
                r.hmset('last_events', last_events)

#            for key, data in gources.iteritems():
#                print key, data['process'].poll()

            sleep(REFRESH_RATE)
    finally:
        for gource in gources.values():
            gource['process'].terminate()

if __name__ == '__main__':
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    main(sys.argv[1:])
