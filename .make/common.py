#!/usr/bin/env python3

import glob
import os
import subprocess
import sys
import yaml

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


session = None


def get(url):
    global session
    if session is None:
        session = requests.Session()
        retry = Retry(connect=5, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
    return session.get(url)


class eopkg(object):
    def __init__(self, yml):
        self.name = ''
        self.summary = ''
        self.version = ''
        self.release = 0
        self.mainainter = ''
        self.sources = []
        self.subpackages = []
        self.yml = yml
        self._parse()

    def _parse(self):
        with open(self.yml, 'r') as yml_fd:
            try:
                pkg_yml = yaml.safe_load(yml_fd)
                self.name = pkg_yml['name']
                self.summary = pkg_yml['summary']
                self.version = str(pkg_yml['version'])
                self.release = int(pkg_yml['release'])
                self.sources = pkg_yml['source']
                self.subpackages = eopkg.parse_patterns(pkg_yml)
                if 'maintainer' in pkg_yml:
                    self.mainainter = pkg_yml['maintainer']
            except yaml.YAMLError as e:
                raise e

    def glob(self):
        return '{}-{}-{}-*.eopkg'.format(self.name, self.version, self.release)

    def subglob(self):
        if len(self.subpackages) > 0:
            return '{}-{}-{}-*.eopkg'.format(self.subpackages[0], self.version, self.release)
        return self.glob()

    def check(self):
        self._check_version()
        self._check_maintainer()
        # self._check_sources()

    def _check_maintainer(self):
        if self.mainainter == '':
            raise Exception(
                'Package {} does not have an assigned maintainer'.format(self.name))

    def _check_version(self):
        import re
        if not re.match('^[0-9a-zA-Z\\._]+$', self.version):
            raise Exception(
                'Version {} contains illegal characters'.format(self.version))

    def _check_sources(self):
        for source in self.sources:
            for source_url in source.keys():
                if source_url.startswith('http') and eopkg.hash(source_url) != source[source_url]:
                    raise Exception(
                        'Source {} hash mismatches'.format(source_url))

    @staticmethod
    def parse_patterns(yml):
        subpkgs = []

        if 'patterns' in yml:
            for subpkg in yml['patterns']:
                for subpkg_name in subpkg:
                    if subpkg_name[0] == "^":
                        subpkgs.append(subpkg_name[1:])
                    else:
                        subpkgs.append(
                            '{}-{}'.format(yml['name'], subpkg_name))

        for subpkg in ['devel', 'docs', 'dbginfo']:
            subpkgs.append('{}-{}'.format(yml['name'], subpkg))

        return subpkgs

    @staticmethod
    def hash(url):
        import hashlib
        hash = hashlib.sha256()
        for data in get(url).iter_content(8192):
            hash.update(data)
        return hash.hexdigest()


def sol_build(eopkg):
    log = open(eopkg.yml.replace('yml', 'log'), 'w')
    try:
        subprocess.Popen(['sudo', 'solbuild', 'build', 'package.yml', '-p', 'theca-x86_64'], cwd=os.path.dirname(
            eopkg.yml), stdout=log, stderr=subprocess.STDOUT).communicate()
    except subprocess.CalledProcessError as e:
        print('Unable to build {}: [{}] {}'.format(
            eopkg.name, e.returncode, e.output))
        return False
    finally:
        log.close()

    packages = glob.glob(os.path.join(
        os.path.dirname(eopkg.yml), '*.eopkg'))
    if len(packages) == 0:
        return False

    for package in packages:
        os.rename(package, os.path.join(
            os.environ['BUILD_DIR'], os.path.basename(package)))
    for pspec in glob.glob(os.path.join(
            os.path.dirname(eopkg.yml), '*.xml')):
        os.remove(pspec)

    return True


def sol_index(path):
    subprocess.Popen(['sudo', 'solbuild', 'index'], cwd=path).communicate()


def package_yml(name):
    package_yml = subprocess.Popen(
        ['egrep', '-rl', '^name\\s+:\\s+{}$'.format(name), 'src'],
        stdout=subprocess.PIPE).communicate()[0].strip().decode('utf8')
    if package_yml == '':
        raise Exception('Package {}\'s manifest not found'.format(name))
    return package_yml


def series():
    with open('src/series', 'r') as series_fd:
        return list(map(lambda name: eopkg(package_yml(name)), yaml.safe_load(series_fd)))
