#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import sys
import json
import platform

sys.path.insert(0, os.path.abspath('..'))

from clint import resources
from clint import args
from clint.textui import puts, colored, indent

from collections import OrderedDict
from datetime import datetime
from dateutil.parser import parse as dateparse
from json import loads
from subprocess import CalledProcessError, Popen, PIPE, check_output, check_call, call
from time import sleep
import Tkinter
import base64
import inspect
import logging
import os
import re
import sys
import md5
import urllib2

t = Tkinter.Tk()

# Set current directory
CONFIG_URL = 'config.json'
CURRENT_DIR = os.path.dirname(inspect.getfile(inspect.currentframe()))
UTILS = {
    'required': ['git', 'gource'],
    'optional': {
        'darwin': [{
            'call': 'afplay'
        }],
        'linux': [{
            'call': 'play',
            'req': 'apt-get install sox'
        }, {
            'call': 'xdotool',
            'req': 'apt-get install xdotool'
        }, {
            'call': 'xmonad',
            'req': 'apt-get install xmonad'
        }]
    }
}

DEFAULTS = {
    'rows': 3,
    'columns': 2,
    'refresh_rate': 10,
    'gravatar_size': 90,
    'git_log_limit': 100,
    'api_url': 'https://api.github.com',
    'screen_width': t.winfo_screenwidth(),
    'screen_height': t.winfo_screenheight(),
    'repo_store': os.path.abspath('%s/repositories' % CURRENT_DIR),
    'gource_options': ['gource', '--load-config', os.path.abspath('%s/gourceconfig.ini' % CURRENT_DIR)],
    'git_log_options': ['git', 'log', '--pretty=format:user:%aN%n%ct', '--reverse', '--raw', '--encoding=UTF-8', '--no-renames'],
    'sound_file': os.path.abspath('%s/happykids.wav' % CURRENT_DIR)
}

DEFAULTS.update({
    'max_gources': DEFAULTS.get('rows') * DEFAULTS.get('columns')
})

OPTS = dict()

resources.init('ff0000', 'Battlestar Goursica')


class RepoGoneError(Exception):
    pass


def debugger(msg):
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        try:
            puts(msg)
        except UnicodeDecodeError, e:
            debugger(colored.red('%s' % e))


def retrieve_last_pushes():
    ''' Returns an OrderedDict (in chronological order) of key, revision for all recent pushes since last check. '''
    # global OPTS
    last_update = OPTS.get('last_update')

    req = urllib2.Request(OPTS.get('github_api'),
                          headers=OPTS.get('headers'))
    events = loads(urllib2.urlopen(req).read())
    events = [e for e in events if e['type'] == u'PushEvent' and (OPTS.get('activity') == 'all' or e['public']) and dateparse(e['created_at']) > dateparse(last_update)]
    events.reverse()  # chrono order

    if not events:
        debugger(colored.magenta('No events\n'))

    last_events = OrderedDict()
    for event in events:
        key = '/'.join([event['repo']['name'], re.sub('^refs/heads/', '', event['payload']['ref'])])
        if key in last_events:
            del last_events[key]  # make sure to track the most recent one only
        last_events[key] = event['payload']['head']

    if events:
        last_update = events[-1]['created_at']
        OPTS['last_update'] = last_update

    return last_events


def path_for_key(key):
    return os.path.join(OPTS.get('repo_store'), re.sub(r'[/.\\]', '_', key))


def clean_title(key):
    return key.split('/', 1)[-1].replace('/', ' / ')


def calculate_viewport():
    return '%sx%s' % ((OPTS.get('screen_width') // OPTS.get('columns')) - OPTS.get('columns'), (OPTS.get('screen_height') // OPTS.get('rows')) - OPTS.get('rows'))


def update_repo(key):
    repo = '/'.join(key.split('/')[:2])
    ref = '/'.join(key.split('/')[2:])
    try:
        if not os.path.exists(path_for_key(key)):
            logging.debug('Cloning repo %s' % repo)
            check_output(['git', 'clone', '-b', ref, 'git@github.com:%s.git' % repo, path_for_key(key)])
            os.chdir(path_for_key(key))
        else:
            os.chdir(path_for_key(key))
            logging.debug('Updating repo for %s' % key)
            check_output(['git', 'pull', 'origin', '%s' % ref])
    except CalledProcessError:
        logging.debug('Looks like we got an error from a called git process.  Assuming repo is gone.')
        raise RepoGoneError

    # Gravatar regardless of condition
    download_gravatars(path_for_key(key))

    # Yay sound.
    play_sound()


def create_gource(key, newrev, in_place_of=None, position=None):
    update_repo(key)
    if in_place_of:
        position = remove_gource(in_place_of)
    os.chdir(path_for_key(key))

    log = check_output(OPTS.get('git_log_options'))
    gource_opts = OPTS.get('gource_options') + ['--user-image-dir', '%s/.git/avatar' % path_for_key(key), '--viewport', calculate_viewport(),  '--title', clean_title(key)]

    if not OPTS.get('pretty'):
        gource_opts.append('-')
    else:
        gource_opts.append('--loop')

    gource = Popen(gource_opts, stdin=PIPE)

    if not OPTS.get('pretty') and not os.fork():
        gource.stdin.write(log)
        gource.stdin.flush()
        sys.exit()

    OPTS.get('gources')[key] = {'process': gource, 'position': position, 'lastrev': newrev}


def update_gource(key, newrev):
    update_repo(key)
    os.chdir(path_for_key(key))

    gource = OPTS.get('gources')[key]['process']
    log = check_output(OPTS.get('git_log_options') + ['%s..%s' % (OPTS.get('gources')[key]['lastrev'], newrev)])

    if not os.fork():
        gource.stdin.write(log)
        gource.stdin.flush()
        sys.exit()

    OPTS.get('gources')[key]['lastrev'] = newrev


def remove_gource(key):
    gource = OPTS.get('gources')[key]['process']
    position = OPTS.get('gources')[key]['position']
    gource.terminate()
    del OPTS.get('gources')[key]
    return position


def generate_gources():
    events = retrieve_last_pushes()
    events_to_show = OrderedDict([k, events[k]] for k in events.keys()[-1 * (OPTS.get('max_gources')):])  # if we received more than we can show, ignore the oldest
    remaining_events = OrderedDict([k, events[k]] for k in events.keys()[:-1 * (OPTS.get('max_gources'))])

    # Now which gources do we keep and which do we replace?
    old_gources = [id for id in OPTS.get('gources') if id not in events_to_show]
    assert len(old_gources) <= [len(set(events_to_show.keys()) - set(OPTS.get('gources').keys()))]

    for key, newrev in events_to_show.iteritems():
        try:
            if key in OPTS.get('gources'):
                debugger(colored.cyan('Updating gource %s: -> %s' % (key, newrev)))
                update_gource(key, newrev)
            elif old_gources:
                oldest = old_gources.pop(0)
                debugger(colored.cyan('Replacing gource %s with %s' % (oldest, key)))
                create_gource(key, newrev, in_place_of=oldest)
            else:
                debugger(colored.cyan('Adding gource %s' % key))
                create_gource(key, newrev)
        except RepoGoneError:
            if remaining_events:
                k, v = remaining_events.popitem(last=True)
                events_to_show[k] = v
            else:
                debugger(colored.yellow('No remaining events to show.'))


def play_sound():
    if not os.fork():
        if call('which afplay', shell=True) == 0:
            # OS X
            check_call(['afplay', OPTS.get('sound_file')])
        elif call('which play', shell=True) == 0:
            # Linux
            check_call(['play', OPTS.get('sound_file')])
        else:
            logging.warn('No compatible sound program (afplay/play) detected')
        sys.exit()


def filter_authors(authors):
    seen = set()
    seen_add = seen.add
    return [x for x in authors if x not in seen and not seen_add(x)]


def fetch_gravatars(path, lines):
    authors = filter_authors(lines)

    while authors:
        line = authors[0]
        email, author = line.split('|')
        author_image_file = '%s/%s.png' % (path, author)

        # Download the file if it does not exist
        if not os.path.isfile(author_image_file):
            gravatar_url = 'http://www.gravatar.com/avatar/%s?d=404&size=%s' % (md5.new(email).hexdigest(), OPTS.get('gravatar_size'))
            debugger(colored.cyan('Fetching Gravatar for "%s"' % (author)))

            try:
                url = urllib2.urlopen(gravatar_url)
                urlcode = url.getcode()

                if urlcode == 200:
                    debugger(colored.green('Found new image.'))
                    f = open(author_image_file, 'wb')
                    f.write(url.read())
                    f.close()
                    url.close()
                else:
                    debugger(colored.red('Server returned error code %s' % urlcode))
            except urllib2.HTTPError, e:
                logging.debug(e)
        else:
            debugger(colored.green('Gravatar exists for "%s" %s' % (author, email)))

        authors.remove(line)


def parse_git_authors(path):
    authors = ['git', 'log', '--pretty=format:%ae|%an']
    if OPTS.get('git_log_limit'):
        authors.extend(['-n', '%s' % OPTS.get('git_log_limit')])

    log = check_output(authors)
    lines = log.split('\n')

    fetch_gravatars(path, lines)


def download_gravatars(path):
    os.chdir(path)
    abspath = '%s/.git/avatar' % os.getcwd()

    if not os.path.exists(abspath):
        os.makedirs(abspath)

    parse_git_authors(abspath)


class RequirementsNotMetError(Exception):
    pass


def check_first_run():
    return resources.user.read(CONFIG_URL) == None


def check_requirements():
    requirements_met = True
    required = UTILS['required']
    optional = UTILS['optional'][platform.system().lower()]

    puts(colored.cyan('Checking requirements'))
    with indent(4, quote='>>>'):
        for util in required:
            try:
                check_output('which %s' % util, shell=True).strip()
                puts(colored.cyan('%s is installed' % util))
            except Exception:
                puts(colored.red('ERROR: %s is required but not found.' % util))
                requirements_met = False

        for util in optional:
            try:
                check_output('which %s' % util['call'], shell=True).strip()
                puts(colored.cyan('%s is installed' % util['call']))
            except Exception:
                warning = 'WARNING: %s is recommended but not found.' % util['call']
                if util['req']:
                    warning = warning + ' Try \'%s\'' % util['req']
                puts(colored.yellow(warning))
                requirements_met = False
    print
    return requirements_met


def create_config():
    puts(colored.cyan('Checking requirements'))
    with indent(4, quote='>>>'):
        org = raw_input('GitHub organization (optional): ')
        puts(colored.magenta(org))

        user = raw_input('GitHub username (optional): ')
        puts(colored.magenta(user))

        password = raw_input('GitHub password (optional): ')
        puts(colored.magenta(password))

        activity = raw_input('GitHub activity level (all, private): ')
        puts(colored.magenta(activity))
    print

    if (org or user or password) and activity:
        DEFAULTS.update({
            'org': org,
            'user': user,
            'pass': password,
            'activity': activity
        })

        resources.user.write(CONFIG_URL, json.dumps(DEFAULTS))


def setup():
    reqs = check_requirements()
    if reqs:
        create_config()
        main()
    else:
        raise RequirementsNotMetError


def check_flags():
    global OPTS

    if ('-p', '--oh-so-pretty') in args.flags:
        OPTS['pretty'] = True


def load_settings():
    global DEFAULTS, OPTS

    OPTS = DEFAULTS.copy()
    OPTS.update(json.loads(resources.user.read(CONFIG_URL)))

    check_flags()

    if OPTS.get('user') and OPTS.get('pass'):
        OPTS['headers'] = {'Authorization': 'Basic %s' % base64.encodestring('%s:%s' % (OPTS.get('user'), OPTS.get('pass')))}
    else:
        OPTS['headers'] = {}

    if OPTS.get('org'):
        if OPTS.get('user') and OPTS.get('pass') and OPTS.get('activity') == 'all':
            OPTS['github_api'] = '%s/users/%s/events/orgs/%s' % (OPTS.get('api_url'), OPTS.get('user'), OPTS.get('org'))
        else:
            OPTS['github_api'] = '%s/orgs/%s/events' % (OPTS.get('api_url'), OPTS.get('org'))
    elif OPTS.get('user'):
        OPTS['github_api'] = '%s/users/%s/events' % (OPTS.get('api_url'), OPTS.get('user'))

    if not os.path.exists(OPTS.get('repo_store')):
        os.makedirs(OPTS.get('repo_store'))

    if OPTS.get('git_log_limit'):
        OPTS.get('git_log_options').extend(['-n', '%s' % OPTS.get('git_log_limit')])

    OPTS['gources'] = OrderedDict()  # In order of creation time, not screen position
    OPTS['last_update'] = datetime.min.isoformat() + 'Z'


def main():
    load_settings()
    pid = os.getpid()

    if not OPTS.get('pretty'):
        try:
            while True:
                # EVENT LOOP!!!
                generate_gources()
                sleep(OPTS.get('refresh_rate'))

        finally:
            if OPTS.get('gources') and pid == os.getpid():
                for gource in OPTS.get('gources').values():
                    gource['process'].terminate()
    else:
        debugger(colored.green('I\'m so pretty. Oh so pretty.'))
        generate_gources()


if __name__ == '__main__':
    # log = logging.getLogger()
    # log.setLevel(logging.DEBUG)

    if check_first_run():
        setup()
    else:
        main()
