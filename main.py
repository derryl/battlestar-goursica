#!/usr/bin/env python
#requires python-dateutil, redis
#recommends hiredis
# you'll need to have the redis server running, too ('brew install redis')

from dateutil.parser import parse as dateparse
from collections import OrderedDict
from getpass import getpass
from json import loads
from pprint import pprint
from subprocess import Popen, PIPE, check_output
import base64
import logging
import os
import re
import redis
import shlex
import sys
import urllib2
from time import sleep
from datetime import datetime

DISPLAY_COUNT = 2
REPO_STORE = os.path.expanduser('~/.battlestar_goursica/repos/')
PASSWORD = ''
REFRESH_RATE = 10 #seconds!

if not os.path.exists(REPO_STORE):
    os.makedirs(REPO_STORE)

gources = OrderedDict() # In order of creation time, not screen position
r = redis.StrictRedis(host='localhost', port=6379, db='battlestar_goursica')
#r.delete('last_events') #XXX - for debugging only
r.delete('last_update')

def retrieve_last_pushes():
    ''' Returns an OrderedDict (in chronological order) of key, revision for all recent pushes since last check. '''
    
    last_update = r.get('last_update') or datetime.min.isoformat() + 'Z'

    req = urllib2.Request('https://api.github.com/users/f00bot/events/orgs/ff0000', 
                          headers={'Authorization': 'Basic %s' % base64.encodestring('f00bot:%s' % PASSWORD)})
    events = loads(urllib2.urlopen(req).read()) 
    events = [e for e in events if e['type'] == u'PushEvent' and dateparse(e['created_at']) > dateparse(last_update)]
    events.reverse() # chrono order
    
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
        check_output(['git', 'clone', 'git@github.com:%s.git' % repo, path_for_key(key)])
        os.chdir(path_for_key(key))
        logging.debug('Checking out %s' % key)
        check_output(['git', 'checkout', ref])
    else:
        os.chdir(path_for_key(key))
        logging.debug('Updating repo for %s' % key)
        check_output(['git', 'pull'])

def create_gource(key, position):
    update_repo(key)
    os.chdir(path_for_key(key))
    log = check_output(['git', 'log', '--pretty=format:user:%aN%n%ct', '--reverse', '--raw', '--encoding=UTF-8', '--no-renames'])
    gource = Popen(['gource', '--log-format', 'git', '-i', '0', '-s', '0.0001', '--key', '-'], stdin=PIPE, stdout=PIPE, stderr=PIPE)

    if os.fork() == 0:
        gource.stdin.write(log)
        gource.stdin.flush()
        sys.exit()

    gources[key] = {'process': gource, 'position': position}

def update_gource(key, oldrev, newrev):
    gource = gources[key]['process']
    update_repo(key)
    os.chdir(path_for_key(key))
    log = check_output(['git', 'log', '--pretty=format:user:%aN%n%ct', '--reverse', '--raw', '--encoding=UTF-8', '--no-renames', '%s..%s' % (oldrev, newrev)])
    
    if os.fork() == 0:
        gource.stdin.write(log)
        gource.stdin.flush()
        sys.exit()

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
            events_to_show = OrderedDict([k,last_events[k]] for k in last_events.keys()[-1 * DISPLAY_COUNT:]) # if we received more than we can show, ignore the oldest
        
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
            
            sleep(REFRESH_RATE)
    finally:
        for gource in gources.values():
            gource['process'].terminate()

if __name__ == '__main__':
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    main(sys.argv[1:]) 