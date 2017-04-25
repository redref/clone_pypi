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
import re
from multiprocessing import Process, Queue, active_children
from xml.etree import ElementTree

#
# GLOBALS
#
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPOSITORY = os.path.join(BASE_DIR, 'packages')
INDEX = os.path.join(BASE_DIR, 'index')

# number of package processes to run in parallel
PROCESSES = 20

# number of files processes to run in parallel
FILE_PROCESSES = 20

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
        text = a.text
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
        if hashlib.md5(resp.content).hexdigest() != md5_digest:
            raise Exception('md5 failed')

        logging.info(
            'Downloaded: %-80s Ok pid:%s' % (filename, pid))
    except Exception as ex:
        logging.error('Failed    : %s. %s' % (download_url, ex))


def file_worker(queue):
    pid = os.getpid()

    while True:
        package, url = queue.get(True)

        # Exit processes (cascade)
        if package is None:
            queue.put((None, None))
            return

        get_file(package, url)


def package_worker(queue, results, file_queue):
    pid = os.getpid()

    regexp = re.compile(
        r'[-\.]macosx[-_][0-9\._]+[-_](intel|x86_64).(egg|whl)$')

    while True:
        name, lower = queue.get(True)

        # Exit processes (cascade)
        if name is None:
            queue.put((None, None))
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
            if 'Not Found' in repr(ex):
                logging.error('%s: %s' % (json_url, ex))
                continue

        info = package['info']
        if info and info['version']:
            version = info['version']
        else:
            version = ""
        if info and info['summary']:
            summary = info['summary'].replace("\n", ".")
        else:
            summary = ""

        # Get version min
        version_min = None
        if os.path.exists('%s/%s/version' % (REPOSITORY, name)):
            with open('%s/%s/version' % (REPOSITORY, name)) as f:
                version_min = f.read().strip()

        files = ['desc.json', 'version']
        for ver in package['releases']:
            # Filter minimum version
            try:
                if int(ver[0]) < int(version_min):
                    continue
            except:
                pass

            for url in package['releases'][ver]:
                filename = url['filename']
                if 'win32' in filename:
                    continue
                if '-win_amd64' in filename:
                    continue
                if '-win-amd64' in filename:
                    continue
                if re.search(regexp, filename):
                    continue

                ext = ''
                if '.' in filename:
                    ext = filename.split('.')[-1]
                if ext not in EXTENSIONS:
                    logging.debug(
                        'Skipping extension %s: %s...' % (ext, filename))
                    continue

                logging.debug('Found %s' % filename)
                files.append(filename)

                file_queue.put((name, url))

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
        level=logging.INFO,
        format="%(asctime)s:%(levelname)s: %(message)s")

    start = time.time()

    # Get Packages List / Prepare the queue
    q = Queue(maxsize=100)
    r = Queue(maxsize=100)
    f = Queue(maxsize=1000)

    # Start Workers
    for i in range(FILE_PROCESSES):
        p = Process(target=file_worker, args=(f,))
        p.start()

    for i in range(PROCESSES):
        p = Process(target=package_worker, args=(q, r, f))
        p.start()

    # Supply names to workers
    with open(INDEX, 'w') as index_f:
        count = 0

        def callback():
            global count
            res = r.get()
            count += 1
            index_f.write("%s\n" % ' | '.join(res))

        count = 0
        for package in get_names():
            logging.debug("Put %s" % package[0])
            q.put(package)

            if not r.empty():
                callback()

            # Test
            # count += 1
            # if count > 10:
            #     break

        # Barrierq
        while not q.empty():
            callback()

        q.put((None, None))

        # Catch remaining results
        while not r.empty():
            callback()

        f.put((None, None))

    logging.info("Packages found : %s" % count)
    logging.info("Time elapsed : %s", (time.time() - start))
