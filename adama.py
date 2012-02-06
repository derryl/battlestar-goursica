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
import logging
import os
import re
import sys
import md5
import urllib2
import getpass

t = Tkinter.Tk()

# Set current directory
CONFIG_URL = 'config.json'
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
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
    'delay': 0.5,
    'refresh_rate': 10,
    'gravatar_size': 90,
    'git_log_limit': 100,
    'api_url': 'https://api.github.com',
    'screen_width': t.winfo_screenwidth(),
    'screen_height': t.winfo_screenheight(),
    'repo_store': os.path.abspath('%s/repositories' % CURRENT_DIR),
    'gource_options': ['gource', '--load-config', os.path.abspath('%s/config/gourceconfig.ini' % CURRENT_DIR)],
    'git_log_options': ['git', 'log', '--pretty=format:user:%aN%n%ct', '--reverse', '--raw', '--encoding=UTF-8', '--no-renames'],
    'sound_file': os.path.abspath('%s/audio/happykids.wav' % CURRENT_DIR)
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


def initial_xmonad_layout():
    sleep(OPTS['delay'])

    if OPTS.get('xmonad') and OPTS.get('xdotool'):
        keystrokes = ['alt+m', 'alt+k', 'alt+shift+j', 'alt+shift+j',
                      'alt+shift+j', 'alt+j', 'alt+j', 'alt+Return']

        while keystrokes:
            key = keystrokes[0]
            check_call(['xdotool', 'key', key])
            keystrokes.remove(key)
    pass


def update_xmonad_layout():
    sleep(OPTS['delay'])

    if OPTS.get('xmonad') and OPTS.get('xdotool'):
        check_call(['xdotool', 'key', 'alt+m'])
        for x in range(0, 3):
            call(['xdotool', 'key', 'alt+shift+j'])


def retrieve_last_pushes():
    ''' Returns an OrderedDict (in chronological order) of key, revision for all recent pushes since last check. '''
    # global OPTS
    last_update = OPTS.get('last_update')

    try:
        req = urllib2.Request(OPTS.get('github_api'),
                              headers=OPTS.get('headers'))
        events = loads(urllib2.urlopen(req).read())
        events = [e for e in events if e['type'] == u'PushEvent' and (OPTS.get('activity') == 'all' or e['public']) and dateparse(e['created_at']) > dateparse(last_update)]
        events.reverse()  # chrono order
    except urllib2.HTTPError, e:
        debugger(colored.red('%s' % e))

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


def clean_title(key, mode):
    key = key.split('/', 1)[-1].replace('/', ' / ')

    if mode == 'dual' and '_clone' in key:
        key = key.replace('_clone', ' (replay)')
    else:
        key = key + ' (realtime)'

    return key


def calculate_viewport():
    return '%sx%s' % ((OPTS.get('screen_width') // OPTS.get('columns')) - OPTS.get('columns'), (OPTS.get('screen_height') // OPTS.get('rows')) - OPTS.get('rows'))


def update_repo(key):
    repo = '/'.join(key.split('/')[:2])
    ref = '/'.join(key.split('/')[2:])

    if not '_clone' in key:
        try:
            if not os.path.exists(path_for_key(key)):
                debugger(colored.cyan('Cloning repo %s' % repo))
                check_output(['git', 'clone', '-b', ref, 'git@github.com:%s.git' % repo, path_for_key(key)])
                os.chdir(path_for_key(key))
            else:
                os.chdir(path_for_key(key))
                debugger(colored.cyan('Updating repo for %s' % key))
                check_output(['git', 'pull', 'origin', '%s' % ref])
        except CalledProcessError:
            debugger(colored.red('Looks like we got an error from a called git process.  Assuming repo is gone.'))
            raise RepoGoneError

    # Gravatar regardless of condition
    download_gravatars(path_for_key(key))

    # Yay sound.
    play_sound()


def create_gource(key, newrev, in_place_of=None, position=None, mode=None):
    update_repo(key)

    mode = mode if mode else OPTS.get('mode')
    realkey = key.replace('_clone', '')

    if in_place_of:
        position = remove_gource(in_place_of)

    os.chdir(path_for_key(realkey))

    log = check_output(OPTS.get('git_log_options'))
    gource_opts = OPTS.get('gource_options') + ['--user-image-dir', '%s/.git/avatar' % path_for_key(realkey), '--viewport', calculate_viewport(),  '--title', clean_title(key, mode)]

    if mode == 'pretty' or '_clone' in key:
        gource_opts.append('--loop')
    else:
        gource_opts.append('-')

    gource = Popen(gource_opts, stdin=PIPE)

    if mode != 'pretty' and not '_clone' in key and not os.fork():
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
    global OPTS

    events = retrieve_last_pushes()
    mode = OPTS.get('mode')
    number_of_gources = OPTS.get('max_gources') // (2 if mode == 'dual' else 1)
    events_to_show = OrderedDict([k, events[k]] for k in events.keys()[-1 * (number_of_gources):])  # if we received more than we can show, ignore the oldest
    remaining_events = OrderedDict([k, events[k]] for k in events.keys()[:-1 * (number_of_gources)])

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

                if mode == 'dual':
                    sleep(OPTS['delay'])
                    debugger(colored.cyan('Replacing clone of %s with %s' % (oldest + '_clone', key + '_clone')))
                    create_gource(key + '_clone', newrev, in_place_of=oldest + '_clone')
                    debugger(colored.red("Run xmonad layout update"))
                    update_xmonad_layout()
            else:
                debugger(colored.cyan('Adding gource %s' % key))
                create_gource(key, newrev)

                if mode == 'dual':
                    sleep(OPTS['delay'])
                    debugger(colored.cyan('Adding clone of %s' % key + '_clone'))
                    create_gource(key + '_clone', newrev)

        except RepoGoneError:
            if remaining_events:
                k, v = remaining_events.popitem(last=True)
                events_to_show[k] = v
            else:
                debugger(colored.yellow('No remaining events to show.'))

    if not OPTS.get('runonce') and mode == 'dual':
        debugger(colored.red("Run initial xmonad layout"))
        initial_xmonad_layout()
        OPTS['runonce'] = True


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
        author_missing_file = '%s/%s_404.png' % (path, author)

        # Download the file if it does not exist
        if not os.path.isfile(author_image_file) and not os.path.isfile(author_missing_file):
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
                debugger(colored.red('%s' % e))
                f = open(author_missing_file, 'wb')
                f.write('%s' % e)
                f.close()
        elif not os.path.isfile(author_missing_file):
            debugger(colored.yellow('Gravatar missing for "%s" %s' % (author, email)))
        else:
            debugger(colored.green('Gravatar exists for "%s" %s' % (author, email)))

        authors.remove(line)


def parse_git_authors(path, clone):
    authors = ['git', 'log', '--pretty=format:%ae|%an']
    if OPTS.get('git_log_limit') and not clone:
        authors.extend(['-n', '%s' % OPTS.get('git_log_limit')])

    log = check_output(authors)
    lines = log.split('\n')

    fetch_gravatars(path, lines)


def download_gravatars(path):
    realpath = path.replace('_clone', '')
    os.chdir(realpath)
    abspath = '%s/.git/avatar' % os.getcwd()

    if not os.path.exists(abspath):
        os.makedirs(abspath)

    parse_git_authors(abspath, '_clone' in path)


class RequirementsNotMetError(Exception):
    pass


def check_first_run():
    return resources.user.read(CONFIG_URL) == None


def check_requirements():
    requirements_met = True
    required = UTILS['required']
    optional = UTILS['optional'][platform.system().lower()]

    puts(colored.cyan('\nChecking requirements'))
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
    puts(colored.cyan('\nTime to create a config file. We need some credentials to access the GitHub API.'))
    with indent(4, quote='>>>'):
        org = raw_input('GitHub organization (optional): ')
        user = raw_input('GitHub username (optional): ')
        password = getpass.getpass('GitHub password (optional): ')

        activity = raw_input('GitHub activity level (all [default] or public): ')
        if not activity:
            activity = 'all'
    print

    if (org or user or password) and activity:
        DEFAULTS.update({
            'org': org,
            'user': user,
            'pass': password,
            'activity': activity
        })

        resources.user.write(CONFIG_URL, json.dumps(DEFAULTS, sort_keys=True, indent=4))


def setup():
    reqs = check_requirements()
    if reqs:
        create_config()
        main()
    else:
        raise RequirementsNotMetError


def check_flags():
    global OPTS

    if ('-m', '--mode') in args.flags:
        g = args.grouped

        if g.get('-m'):
            OPTS['mode'] = g.get('-m').get(0)
        elif g.get('--mode'):
            OPTS['mode'] = g.get('--mode').get(0)


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

    try:
        OPTS['xmonad'] = check_output('which xmonad', shell=True).strip()
    except Exception:
        pass

    try:
        OPTS['xdotool'] = check_output('which xdotool', shell=True).strip()
    except Exception:
        pass


def main():
    load_settings()
    pid = os.getpid()

    if OPTS.get('mode') != 'pretty':
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
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)

    if check_first_run():
        setup()
    else:
        main()
