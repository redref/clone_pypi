#!/usr/bin/env python3
#
# download all source packages from https://pypi.python.org
import sys
import os
import time
import hashlib
import logging
import json
import requests
from multiprocessing import Process, Queue, active_children
from xml.etree import ElementTree

#
# GLOBALS
#
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPOSITORY = os.path.join(BASE_DIR, 'packages')
INDEX = os.path.join(BASE_DIR, 'index')

# number of processes to run in parallel
PROCESSES = 50

# filters, only interested in this types
EXTENSIONS = ['bz2', 'egg', 'gz', 'tgz', 'whl', 'zip']

# available options in pypi

# I had to do this to setup max_retries in requests
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(max_retries=1)
session.mount('https://', adapter)


def get_names():
    # use simple API
    resp = requests.get('https://pypi.python.org/simple')
    tree = ElementTree.fromstring(resp.content)
    for a in tree.iter('a'):
        text = a.text.encode('utf8')
        yield (text, text.lower())


def get_file(package, url):
    pid = os.getpid()

    filename = url['filename']
    download_url = url['url']
    size = url['size']
    md5_digest = url['md5_digest']

    # Skip if OK
    path = '%s/%s/%s' % (REPOSITORY, package, filename)
    if os.path.exists(path) and os.lstat(path).st_size == size:
        return

    try:
        resp = session.get(download_url, timeout=300)
        if not resp.status_code == requests.codes.ok:
            resp.raise_for_status()
        with open(path, 'wb') as w:
            w.write(resp.content)

        # verify with md5
        if hashlib.md5(resp.content).hexdigest() == md5_digest:
            check = 'Ok'
        else:
            check = 'md5 failed'

        logging.warning(
            'Downloaded: %-80s %s pid:%s' % (filename, check, pid))
    except Exception as ex:
        logging.error('Failed    : %s. %s' % (download_url, ex))


def worker(queue, results):
    pid = os.getpid()

    while True:
        name, lower = queue.get(True)
        if name is None:
            return
        logging.info("Working on package %s" % name)

        # Create directories and links
        if not os.path.isdir(os.path.join(REPOSITORY, name)):
            os.mkdir(os.path.join(REPOSITORY, name))
        if (
            name != lower and
            not os.path.islink(os.path.join(REPOSITORY, lower))
        ):
            try:
                os.symlink(name, os.path.join(REPOSITORY, lower))
            except:
                pass

        # Get and write "desc.json"
        try:
            json_url = 'https://pypi.python.org/pypi/%s/json' % name
            resp = session.get(json_url, timeout=30)
            if not resp.status_code == requests.codes.ok:
                resp.raise_for_status()
            package = resp.json()
            with open('%s/%s/desc.json' % (REPOSITORY, name), 'w') as f:
                f.write(json.dumps(package, indent=3))
        except Exception as ex:
            if 'Not Found' not in repr(ex):
                logging.error('%s: %s' % (json_url, ex))
                continue

        info = package['info']
        if info and info['version']:
            version = info['version'].encode('utf8')
        else:
            version = ""
        if info and info['summary']:
            summary = info['summary'].encode('utf8').replace("\n", ".")
        else:
            summary = ""

        files = ['desc.json']
        for ver in package['releases']:
            for url in package['releases'][ver]:

                filename = url['filename']
                ext = ''
                if '.' in filename:
                    ext = filename.split('.')[-1]
                if ext not in EXTENSIONS:
                    logging.debug(
                        'Skipping extension %s: %s...' % (ext, filename))
                    continue

                logging.debug('Found %s' % filename)
                files.append(filename)

                get_file(name, url)

        # Purge files not found in "desc.json"
        for f in os.listdir(os.path.join(REPOSITORY, name)):
            if f not in files:
                os.unlink(os.path.join(REPOSITORY, name, f))

        results.put((name, version, summary))


if __name__ == '__main__':
    assert REPOSITORY
    assert PROCESSES
    if not os.path.isdir(REPOSITORY):
        os.mkdir(REPOSITORY)
    assert os.path.isdir(REPOSITORY)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s:%(levelname)s: %(message)s")

    start = time.time()

    # Get Packages List / Prepare the queue
    q = Queue(maxsize=10)
    r = Queue(maxsize=10)

    # Start Workers
    for i in range(PROCESSES):
        p = Process(target=worker, args=(q, r))
        p.start()

    # Supply names to workers
    with open(INDEX, 'w') as index_f:
        count = 0

        def callback():
            global count
            res = r.get()
            count += 1
            index_f.write("%s\n" % ' | '.join(res))

        for package in get_names():
            logging.debug("Put %s" % package[0])
            q.put(package)

            if not r.empty():
                callback()

        # Barrier
        while not q.empty() or not r.empty():
            callback()

        # Shutdown workers
        while len(active_children()) != 0:
            q.put_nowait((None, None))

        # Catch remaining results
        while not r.empty():
            callback()

    logging.info("Packages found : %s" % count)
    logging.info("Time elapsed : %s", (time.time() - start))
