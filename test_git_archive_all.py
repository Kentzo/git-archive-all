# -*- coding: utf-8 -*-

from __future__ import print_function
from __future__ import unicode_literals

from copy import deepcopy
import errno
from functools import partial
import os
from subprocess import check_call
import sys
from tarfile import TarFile, PAX_FORMAT

import pycodestyle
import pytest

import git_archive_all
from git_archive_all import GitArchiver, fsencode, fsdecode


def makedirs(p):
    """
    Backward compatible os.makedirs with implied exist_ok=True
    """
    try:
        os.makedirs(p)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def as_posix(p):
    """
    Path with forward slashes preserving byte representation.
    """
    if os.sep == '\\':
        p = p.replace('\\', '/') if isinstance(p, str) else p.replace(b'\\', b'/')

    return p


def path_join(*paths):
    """
    Join components preserving byte representation.
    """
    if any(map(lambda p: isinstance(p, bytes), paths)):
        return os.path.join(*[fsencode(p) for p in paths])
    else:
        return os.path.join(*paths)


@pytest.fixture
def git_env(tmpdir_factory):
    """
    Return ENV git configured for tests:

    1. Both system and user configs are ignored
    2. Custom git user
    3. .gitmodules file is ignored by default
    """
    e = {
        'GIT_CONFIG_NOSYSTEM': 'true',
        'HOME': str(tmpdir_factory.getbasetemp())
    }

    with tmpdir_factory.getbasetemp().join('.gitconfig').open('w+') as f:
        f.writelines([
            '[core]\n',
            'attributesfile = {0}\n'.format(as_posix(tmpdir_factory.getbasetemp().join('.gitattributes'))),
            '[user]\n',
            'name = git-archive-all\n',
            'email = git-archive-all@example.com\n',
        ])

    with tmpdir_factory.getbasetemp().join('.gitattributes').open('w+') as f:
        f.writelines([
            '.gitmodules export-ignore'
        ])

    return e


class Record:
    def __init__(self, kind, contents, excluded=False):
        self.kind = kind
        self.contents = contents
        self.excluded = excluded

    def __getitem__(self, item):
        return self.contents[item]

    def __setitem__(self, key, value):
        self.contents[key] = value


FileRecord = partial(Record, 'file', excluded=False)
DirRecord = partial(Record, 'dir', excluded=False)
SubmoduleRecord = partial(Record, 'submodule', excluded=False)


class Repo:
    def __init__(self, path):
        self.path = os.path.abspath(path)

    def init(self):
        os.mkdir(self.path)
        check_call(['git', 'init'], cwd=self.path)

    def add(self, rel_path, record):
        if record.kind == 'file':
            return self.add_file(rel_path, record.contents)
        elif record.kind == 'dir':
            return self.add_dir(rel_path, record.contents)
        elif record.kind == 'submodule':
            return self.add_submodule(rel_path, record.contents)
        else:
            raise ValueError

    def add_file(self, rel_path, contents):
        file_path = path_join(self.path, rel_path)

        with open(file_path, 'w') as f:
            f.write(contents)

        check_call(['git', 'add', as_posix(os.path.normpath(file_path))], cwd=self.path)
        return file_path

    def add_dir(self, rel_path, contents):
        dir_path = path_join(self.path, rel_path)
        makedirs(dir_path)

        for k, v in contents.items():
            self.add(as_posix(os.path.normpath(path_join(rel_path, k))), v)

        check_call(['git', 'add', dir_path], cwd=self.path)
        return dir_path

    def add_submodule(self, rel_path, contents):
        submodule_path = path_join(self.path, rel_path)
        r = Repo(submodule_path)
        r.init()
        r.add_dir('.', contents)
        r.commit('init')
        check_call(['git', 'submodule', 'add', as_posix(os.path.normpath(submodule_path))], cwd=self.path)
        return submodule_path

    def commit(self, message):
        check_call(['git', 'commit', '-m', 'init'], cwd=self.path)

    def archive(self, path):
        a = GitArchiver(main_repo_abspath=self.path)
        a.create(path)


def make_expected_tree(contents):
    """
    Flatten contents dict for comparison.
    """
    e = {}

    for k, v in contents.items():
        if v.kind == 'file' and not v.excluded:
            e[fsdecode(k)] = v.contents
        elif v.kind in ('dir', 'submodule') and not v.excluded:
            for nested_k, nested_v in make_expected_tree(v.contents).items():
                nested_k = fsdecode(as_posix(path_join(k, nested_k)))
                e[nested_k] = nested_v

    return e


def make_actual_tree(tar_file):
    """
    Flatten tar file members for comparison.
    """
    a = {}

    for m in tar_file.getmembers():
        if m.isfile():
            a[fsdecode(m.name)] = tar_file.extractfile(m).read().decode()
        else:
            raise NotImplementedError

    return a


base = {
    'app': DirRecord({
        '__init__.py': FileRecord('#Beautiful is better than ugly.'),
    }),
    'lib': SubmoduleRecord({
        '__init__.py': FileRecord('#Explicit is better than implicit.'),
        'extra': SubmoduleRecord({
            '__init__.py': FileRecord('#Simple is better than complex.'),
        })
    })
}

base_quoted = deepcopy(base)
base_quoted['data'] = DirRecord({
    '\"hello world.dat\"': FileRecord('Special cases aren\'t special enough to break the rules.'),
    '\'hello world.dat\'': FileRecord('Although practicality beats purity.')
})

ignore_in_root = deepcopy(base)
ignore_in_root['.gitattributes'] = FileRecord('tests/__init__.py export-ignore')
ignore_in_root['tests'] = DirRecord({
    '__init__.py': FileRecord('#Complex is better than complicated.', excluded=True)
})

ignore_in_submodule = deepcopy(base)
ignore_in_submodule['lib']['.gitattributes'] = FileRecord('tests/__init__.py export-ignore')
ignore_in_submodule['lib']['tests'] = DirRecord({
    '__init__.py': FileRecord('#Complex is better than complicated.', excluded=True)
})

ignore_in_nested_submodule = deepcopy(base)
ignore_in_nested_submodule['lib']['extra']['.gitattributes'] = FileRecord('tests/__init__.py export-ignore')
ignore_in_nested_submodule['lib']['extra']['tests'] = DirRecord({
    '__init__.py': FileRecord('#Complex is better than complicated.', excluded=True)
})

ignore_in_submodule_from_root = deepcopy(base)
ignore_in_submodule_from_root['.gitattributes'] = FileRecord('lib/tests/__init__.py export-ignore')
ignore_in_submodule_from_root['lib']['tests'] = DirRecord({
    '__init__.py': FileRecord('#Complex is better than complicated.', excluded=True)
})

ignore_in_nested_submodule_from_root = deepcopy(base)
ignore_in_nested_submodule_from_root['.gitattributes'] = FileRecord('lib/extra/tests/__init__.py export-ignore')
ignore_in_nested_submodule_from_root['lib']['extra']['tests'] = DirRecord({
    '__init__.py': FileRecord('#Complex is better than complicated.', excluded=True)
})

ignore_in_nested_submodule_from_submodule = deepcopy(base)
ignore_in_nested_submodule_from_submodule['lib']['.gitattributes'] = FileRecord('extra/tests/__init__.py export-ignore')
ignore_in_nested_submodule_from_submodule['lib']['extra']['tests'] = DirRecord({
    '__init__.py': FileRecord('#Complex is better than complicated.', excluded=True)
})

unset_export_ignore = deepcopy(base)
unset_export_ignore['.gitattributes'] = FileRecord('.* export-ignore\n*.htaccess -export-ignore', excluded=True)
unset_export_ignore['.a'] = FileRecord('Flat is better than nested.', excluded=True)
unset_export_ignore['.b'] = FileRecord('Sparse is better than dense.', excluded=True)
unset_export_ignore['.htaccess'] = FileRecord('Readability counts.')

unicode_base = deepcopy(base)
unicode_base['data'] = DirRecord({
    'مرحبا بالعالم.dat': FileRecord('Special cases aren\'t special enough to break the rules.')
})

unicode_quoted = deepcopy(base)
unicode_quoted['data'] = DirRecord({
    '\"مرحبا بالعالم.dat\"': FileRecord('Special cases aren\'t special enough to break the rules.'),
    '\'привет мир.dat\'': FileRecord('Although practicality beats purity.')
})

nonunicode_base = deepcopy(base)
nonunicode_base['data'] = DirRecord({
    b'test.\xc2': FileRecord('Special cases aren\'t special enough to break the rules.'),
})

nonunicode_quoted = deepcopy(base)
nonunicode_quoted['data'] = DirRecord({
    b'\'test.\xc2\'': FileRecord('Special cases aren\'t special enough to break the rules.'),
    b'\"test.\xc2\"': FileRecord('Special cases aren\'t special enough to break the rules.'),
})

brackets_base = deepcopy(base)
brackets_base['data'] = DirRecord({
    '[.dat': FileRecord('Special cases aren\'t special enough to break the rules.'),
    '(.dat': FileRecord('Although practicality beats purity.'),
    '{.dat': FileRecord('Errors should never pass silently.'),
    '].dat': FileRecord('Unless explicitly silenced.'),
    ').dat': FileRecord('In the face of ambiguity, refuse the temptation to guess.'),
    '}.dat': FileRecord('There should be one-- and preferably only one --obvious way to do it.'),
    '[].dat': FileRecord('Although that way may not be obvious at first unless you\'re Dutch.'),
    '().dat': FileRecord('Now is better than never.'),
    '{}.dat': FileRecord('Although never is often better than *right* now.'),
})

brackets_quoted = deepcopy(base)
brackets_quoted['data'] = DirRecord({
    '\"[.dat\"': FileRecord('Special cases aren\'t special enough to break the rules.'),
    '\'[.dat\'': FileRecord('Special cases aren\'t special enough to break the rules.'),
    '\"(.dat\"': FileRecord('Although practicality beats purity.'),
    '\'(.dat\'': FileRecord('Although practicality beats purity.'),
    '\"{.dat\"': FileRecord('Errors should never pass silently.'),
    '\'{.dat\'': FileRecord('Errors should never pass silently.'),
    '\"].dat\"': FileRecord('Unless explicitly silenced.'),
    '\'].dat\'': FileRecord('Unless explicitly silenced.'),
    '\").dat\"': FileRecord('In the face of ambiguity, refuse the temptation to guess.'),
    '\').dat\'': FileRecord('In the face of ambiguity, refuse the temptation to guess.'),
    '\"}.dat\"': FileRecord('There should be one-- and preferably only one --obvious way to do it.'),
    '\'}.dat\'': FileRecord('There should be one-- and preferably only one --obvious way to do it.'),
    '\"[].dat\"': FileRecord('Although that way may not be obvious at first unless you\'re Dutch.'),
    '\'[].dat\'': FileRecord('Although that way may not be obvious at first unless you\'re Dutch.'),
    '\"().dat\"': FileRecord('Now is better than never.'),
    '\'().dat\'': FileRecord('Now is better than never.'),
    '\"{}.dat\"': FileRecord('Although never is often better than *right* now.'),
    '\'{}.dat\'': FileRecord('Although never is often better than *right* now.'),
})

quote_base = deepcopy(base)
quote_base['data'] = DirRecord({
    '\'.dat': FileRecord('Special cases aren\'t special enough to break the rules.'),
    '\".dat': FileRecord('Although practicality beats purity.'),
})

quote_quoted = deepcopy(base)
quote_quoted['data'] = DirRecord({
    '\"\'.dat\"': FileRecord('Special cases aren\'t special enough to break the rules.'),
    '\'\'.dat\'': FileRecord('Special cases aren\'t special enough to break the rules.'),
    '\"\".dat\"': FileRecord('Although practicality beats purity.'),
    '\'\".dat\'': FileRecord('Although practicality beats purity.'),
})

@pytest.mark.parametrize('contents', [
    pytest.param(base, id='No Ignore'),
    pytest.param(base_quoted, id='No Ignore (Quoted)', marks=pytest.mark.skipif(sys.platform.startswith('win32'), reason="Invalid Windows filename.")),
    pytest.param(ignore_in_root, id='Ignore in Root'),
    pytest.param(ignore_in_submodule, id='Ignore in Submodule'),
    pytest.param(ignore_in_nested_submodule, id='Ignore in Nested Submodule'),
    pytest.param(ignore_in_submodule_from_root, id='Ignore in Submodule from Root'),
    pytest.param(ignore_in_nested_submodule_from_root, id='Ignore in Nested Submodule from Root'),
    pytest.param(ignore_in_nested_submodule_from_submodule, id='Ignore in Nested Submodule from Submodule'),
    pytest.param(unset_export_ignore, id='-export-ignore'),
    pytest.param(unicode_base, id='No Ignore (Unicode)'),
    pytest.param(unicode_quoted, id='No Ignore (Quoted Unicode)', marks=pytest.mark.skipif(sys.platform.startswith('win32'), reason="Invalid Windows filename.")),
    pytest.param(brackets_base, id='Brackets'),
    pytest.param(brackets_quoted, id="Brackets (Quoted)", marks=pytest.mark.skipif(sys.platform.startswith('win32'), reason="Invalid Windows filename.")),
    pytest.param(quote_base, id="Quote", marks=pytest.mark.skipif(sys.platform.startswith('win32'), reason="Invalid Windows filename.")),
    pytest.param(quote_quoted, id="Quote (Quoted)", marks=pytest.mark.skipif(sys.platform.startswith('win32'), reason="Invalid Windows filename.")),
    pytest.param(nonunicode_base, id="No Ignore (Non-Unicode)", marks=pytest.mark.skipif(sys.platform.startswith('darwin'), reason='Invalid APFS filename.')),
    pytest.param(nonunicode_quoted, id="No Ignore (Quoted Non-Unicode)", marks=pytest.mark.skipif(sys.platform.startswith('darwin'), reason='Invalid APFS filename.'))
])
def test_ignore(contents, tmpdir, git_env, monkeypatch):
    """
    Ensure that GitArchiver respects export-ignore.
    """
    for name, value in git_env.items():
        monkeypatch.setenv(name, value)

    repo_path = path_join(tmpdir.strpath, 'repo')
    repo = Repo(repo_path)
    repo.init()
    repo.add_dir('.', contents)
    repo.commit('init')

    repo_tar_path = path_join(tmpdir.strpath, 'repo.tar')
    repo.archive(repo_tar_path)
    repo_tar = TarFile(repo_tar_path, format=PAX_FORMAT)

    expected = make_expected_tree(contents)
    actual = make_actual_tree(repo_tar)

    assert actual == expected


def test_cli(tmpdir, git_env, monkeypatch):
    contents = base

    for name, value in git_env.items():
        monkeypatch.setenv(name, value)

    repo_path = path_join(tmpdir.strpath, 'repo')
    repo = Repo(repo_path)
    repo.init()
    repo.add_dir('.', contents)
    repo.commit('init')

    repo_tar_path = path_join(tmpdir.strpath, 'repo.tar')
    git_archive_all.main(['git_archive_all.py', '--prefix', '', '-C', repo_path, repo_tar_path])
    repo_tar = TarFile(repo_tar_path, format=PAX_FORMAT)

    expected = make_expected_tree(contents)
    actual = make_actual_tree(repo_tar)

    assert actual == expected


def test_pycodestyle():
    style = pycodestyle.StyleGuide(repeat=True, max_line_length=240)
    report = style.check_files(['git_archive_all.py'])
    assert report.total_errors == 0, "Found code style errors (and warnings)."
