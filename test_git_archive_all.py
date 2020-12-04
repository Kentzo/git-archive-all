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
import warnings

import pycodestyle
import pytest

import git_archive_all
from git_archive_all import GitArchiver, fspath


def makedirs(p):
    try:
        os.makedirs(p)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def as_posix(p):
    if sys.platform.startswith('win32'):
        return p.replace(b'\\', b'/') if isinstance(p, bytes) else p.replace('\\', '/')
    else:
        return p


def os_path_join(*args):
    """
    Ensure that all path components are uniformly encoded.
    """
    return os.path.join(*(fspath(p) for p in args))


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
        'HOME': tmpdir_factory.getbasetemp().strpath
    }

    with tmpdir_factory.getbasetemp().join('.gitconfig').open('wb+') as f:
        f.writelines([
            b'[core]\n',
            'attributesfile = {0}\n'.format(as_posix(tmpdir_factory.getbasetemp().join('.gitattributes').strpath)).encode(),
            b'[user]\n',
            b'name = git-archive-all\n',
            b'email = git-archive-all@example.com\n',
        ])

    # .gitmodules's content is dynamic and is maintained by git.
    # It's therefore ignored solely to simplify tests.
    #
    # If test is run with the --no-exclude CLI option (or its exclude=False API equivalent)
    # then the file itself is included while its content is discarded for the same reason.
    with tmpdir_factory.getbasetemp().join('.gitattributes').open('wb+') as f:
        f.writelines([
            b'.gitmodules export-ignore\n'
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
        self.path = os.path.abspath(fspath(path))

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
        file_path = os_path_join(self.path, rel_path)

        with open(file_path, 'wb') as f:
            f.write(contents)

        check_call(['git', 'add', as_posix(os.path.normpath(file_path))], cwd=self.path)
        return file_path

    def add_dir(self, rel_path, contents):
        dir_path = os_path_join(self.path, rel_path)
        makedirs(dir_path)

        for k, v in contents.items():
            self.add(as_posix(os.path.normpath(os_path_join(dir_path, k))), v)

        check_call(['git', 'add', dir_path], cwd=self.path)
        return dir_path

    def add_submodule(self, rel_path, contents):
        submodule_path = os_path_join(self.path, rel_path)
        r = Repo(submodule_path)
        r.init()
        r.add_dir('.', contents)
        r.commit('init')
        check_call(['git', 'submodule', 'add', as_posix(os.path.normpath(submodule_path))], cwd=self.path)
        return submodule_path

    def commit(self, message):
        check_call(['git', 'commit', '-m', 'init'], cwd=self.path)

    def archive(self, path, exclude=True):
        a = GitArchiver(exclude=exclude, main_repo_abspath=self.path)
        a.create(path)


def make_expected_tree(contents, exclude=True):
    e = {}

    for k, v in contents.items():
        if v.kind == 'file' and not (exclude and v.excluded):
            e[k] = v.contents
        elif v.kind in ('dir', 'submodule') and not (exclude and v.excluded):
            # See the comment in git_env.
            if v.kind == 'submodule' and not exclude:
                e['.gitmodules'] = None

            for nested_k, nested_v in make_expected_tree(v.contents, exclude).items():
                nested_k = as_posix(os_path_join(k, nested_k))
                e[nested_k] = nested_v

    return e


def make_actual_tree(tar_file):
    a = {}

    for m in tar_file.getmembers():
        if m.isfile():
            name = fspath(m.name)

            # See the comment in git_env.
            if not name.endswith(fspath('.gitmodules')):
                a[name] = tar_file.extractfile(m).read()
            else:
                a[name] = None
        else:
            raise NotImplementedError

    return a


base = {
    'app': DirRecord({
        '__init__.py': FileRecord(b'#Beautiful is better than ugly.'),
    }),
    'lib': SubmoduleRecord({
        '__init__.py': FileRecord(b'#Explicit is better than implicit.'),
        'extra': SubmoduleRecord({
            '__init__.py': FileRecord(b'#Simple is better than complex.'),
        })
    })
}

base_quoted = deepcopy(base)
base_quoted['data'] = DirRecord({
    '\"hello world.dat\"': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
    '\'hello world.dat\'': FileRecord(b'Although practicality beats purity.')
})

ignore_in_root = deepcopy(base)
ignore_in_root['.gitattributes'] = FileRecord(b'tests/__init__.py export-ignore')
ignore_in_root['tests'] = DirRecord({
    '__init__.py': FileRecord(b'#Complex is better than complicated.', excluded=True)
})

ignore_in_submodule = deepcopy(base)
ignore_in_submodule['lib']['.gitattributes'] = FileRecord(b'tests/__init__.py export-ignore')
ignore_in_submodule['lib']['tests'] = DirRecord({
    '__init__.py': FileRecord(b'#Complex is better than complicated.', excluded=True)
})

ignore_in_nested_submodule = deepcopy(base)
ignore_in_nested_submodule['lib']['extra']['.gitattributes'] = FileRecord(b'tests/__init__.py export-ignore')
ignore_in_nested_submodule['lib']['extra']['tests'] = DirRecord({
    '__init__.py': FileRecord(b'#Complex is better than complicated.', excluded=True)
})

ignore_in_submodule_from_root = deepcopy(base)
ignore_in_submodule_from_root['.gitattributes'] = FileRecord(b'lib/tests/__init__.py export-ignore')
ignore_in_submodule_from_root['lib']['tests'] = DirRecord({
    '__init__.py': FileRecord(b'#Complex is better than complicated.', excluded=True)
})

ignore_in_nested_submodule_from_root = deepcopy(base)
ignore_in_nested_submodule_from_root['.gitattributes'] = FileRecord(b'lib/extra/tests/__init__.py export-ignore')
ignore_in_nested_submodule_from_root['lib']['extra']['tests'] = DirRecord({
    '__init__.py': FileRecord(b'#Complex is better than complicated.', excluded=True)
})

ignore_in_nested_submodule_from_submodule = deepcopy(base)
ignore_in_nested_submodule_from_submodule['lib']['.gitattributes'] = FileRecord(b'extra/tests/__init__.py export-ignore')
ignore_in_nested_submodule_from_submodule['lib']['extra']['tests'] = DirRecord({
    '__init__.py': FileRecord(b'#Complex is better than complicated.', excluded=True)
})

unset_export_ignore = deepcopy(base)
unset_export_ignore['.gitattributes'] = FileRecord(b'.* export-ignore\n*.htaccess -export-ignore', excluded=True)
unset_export_ignore['.a'] = FileRecord(b'Flat is better than nested.', excluded=True)
unset_export_ignore['.b'] = FileRecord(b'Sparse is better than dense.', excluded=True)
unset_export_ignore['.htaccess'] = FileRecord(b'Readability counts.')

unicode_base = deepcopy(base)
unicode_base['data'] = DirRecord({
    'مرحبا بالعالم.dat': FileRecord(b'Special cases aren\'t special enough to break the rules.')
})

unicode_quoted = deepcopy(base)
unicode_quoted['data'] = DirRecord({
    '\"مرحبا بالعالم.dat\"': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
    '\'привет мир.dat\'': FileRecord(b'Although practicality beats purity.')
})

brackets_base = deepcopy(base)
brackets_base['data'] = DirRecord({
    '[.dat': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
    '(.dat': FileRecord(b'Although practicality beats purity.'),
    '{.dat': FileRecord(b'Errors should never pass silently.'),
    '].dat': FileRecord(b'Unless explicitly silenced.'),
    ').dat': FileRecord(b'In the face of ambiguity, refuse the temptation to guess.'),
    '}.dat': FileRecord(b'There should be one-- and preferably only one --obvious way to do it.'),
    '[].dat': FileRecord(b'Although that way may not be obvious at first unless you\'re Dutch.'),
    '().dat': FileRecord(b'Now is better than never.'),
    '{}.dat': FileRecord(b'Although never is often better than *right* now.'),
})

brackets_quoted = deepcopy(base)
brackets_quoted['data'] = DirRecord({
    '\"[.dat\"': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
    '\'[.dat\'': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
    '\"(.dat\"': FileRecord(b'Although practicality beats purity.'),
    '\'(.dat\'': FileRecord(b'Although practicality beats purity.'),
    '\"{.dat\"': FileRecord(b'Errors should never pass silently.'),
    '\'{.dat\'': FileRecord(b'Errors should never pass silently.'),
    '\"].dat\"': FileRecord(b'Unless explicitly silenced.'),
    '\'].dat\'': FileRecord(b'Unless explicitly silenced.'),
    '\").dat\"': FileRecord(b'In the face of ambiguity, refuse the temptation to guess.'),
    '\').dat\'': FileRecord(b'In the face of ambiguity, refuse the temptation to guess.'),
    '\"}.dat\"': FileRecord(b'There should be one-- and preferably only one --obvious way to do it.'),
    '\'}.dat\'': FileRecord(b'There should be one-- and preferably only one --obvious way to do it.'),
    '\"[].dat\"': FileRecord(b'Although that way may not be obvious at first unless you\'re Dutch.'),
    '\'[].dat\'': FileRecord(b'Although that way may not be obvious at first unless you\'re Dutch.'),
    '\"().dat\"': FileRecord(b'Now is better than never.'),
    '\'().dat\'': FileRecord(b'Now is better than never.'),
    '\"{}.dat\"': FileRecord(b'Although never is often better than *right* now.'),
    '\'{}.dat\'': FileRecord(b'Although never is often better than *right* now.'),
})

quote_base = deepcopy(base)
quote_base['data'] = DirRecord({
    '\'.dat': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
    '\".dat': FileRecord(b'Although practicality beats purity.'),
})

quote_quoted = deepcopy(base)
quote_quoted['data'] = DirRecord({
    '\"\'.dat\"': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
    '\'\'.dat\'': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
    '\"\".dat\"': FileRecord(b'Although practicality beats purity.'),
    '\'\".dat\'': FileRecord(b'Although practicality beats purity.'),
})

nonunicode_base = deepcopy(base)
nonunicode_base['data'] = DirRecord({
    b'test.\xc2': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
})

nonunicode_quoted = deepcopy(base)
nonunicode_quoted['data'] = DirRecord({
    b'\'test.\xc2\'': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
    b'\"test.\xc2\"': FileRecord(b'Although practicality beats purity.'),
})

backslash_base = deepcopy(base)
backslash_base['data'] = DirRecord({
    '\\.dat': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
})

backslash_quoted = deepcopy(base)
backslash_quoted['data'] = DirRecord({
    '\'\\.dat\'': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
    '\"\\.dat\"': FileRecord(b'Although practicality beats purity.')
})

non_unicode_backslash_base = deepcopy(base)
non_unicode_backslash_base['data'] = DirRecord({
    b'\\\xc2.dat': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
})

non_unicode_backslash_quoted = deepcopy(base)
non_unicode_backslash_quoted['data'] = DirRecord({
    b'\'\\\xc2.dat\'': FileRecord(b'Special cases aren\'t special enough to break the rules.'),
    b'\"\\\xc2.dat\"': FileRecord(b'Although practicality beats purity.')
})

ignore_dir = {
    '.gitattributes': FileRecord(b'.gitattributes export-ignore\n**/src export-ignore\ndata/src/__main__.py -export-ignore', excluded=True),
    '__init__.py': FileRecord(b'#Beautiful is better than ugly.'),
    'data': DirRecord({
        'src': DirRecord({
            '__init__.py': FileRecord(b'#Explicit is better than implicit.', excluded=True),
            '__main__.py': FileRecord(b'#Simple is better than complex.')
        })
    })
}

skipif_file_darwin = pytest.mark.skipif(sys.platform.startswith('darwin'), reason='Invalid macOS filename.')
skipif_file_win32 = pytest.mark.skipif(sys.platform.startswith('win32'), reason="Invalid Windows filename.")


@pytest.mark.parametrize('contents', [
    pytest.param(base, id='No Ignore'),
    pytest.param(base_quoted, id='No Ignore (Quoted)', marks=skipif_file_win32),
    pytest.param(ignore_in_root, id='Ignore in Root'),
    pytest.param(ignore_in_submodule, id='Ignore in Submodule'),
    pytest.param(ignore_in_nested_submodule, id='Ignore in Nested Submodule'),
    pytest.param(ignore_in_submodule_from_root, id='Ignore in Submodule from Root'),
    pytest.param(ignore_in_nested_submodule_from_root, id='Ignore in Nested Submodule from Root'),
    pytest.param(ignore_in_nested_submodule_from_submodule, id='Ignore in Nested Submodule from Submodule'),
    pytest.param(unset_export_ignore, id='-export-ignore'),
    pytest.param(unicode_base, id='Unicode'),
    pytest.param(unicode_quoted, id='Unicode (Quoted)', marks=skipif_file_win32),
    pytest.param(brackets_base, id='Brackets'),
    pytest.param(brackets_quoted, id="Brackets (Quoted)", marks=skipif_file_win32),
    pytest.param(quote_base, id="Quote", marks=skipif_file_win32),
    pytest.param(quote_quoted, id="Quote (Quoted)", marks=skipif_file_win32),
    pytest.param(nonunicode_base, id="Non-Unicode", marks=[skipif_file_win32, skipif_file_darwin]),
    pytest.param(nonunicode_quoted, id="Non-Unicode (Quoted)", marks=[skipif_file_win32, skipif_file_darwin]),
    pytest.param(backslash_base, id='Backslash', marks=skipif_file_win32),
    pytest.param(backslash_quoted, id='Backslash (Quoted)', marks=skipif_file_win32),
    pytest.param(non_unicode_backslash_base, id='Non-Unicode Backslash', marks=[skipif_file_win32, skipif_file_darwin]),
    pytest.param(non_unicode_backslash_quoted, id='Non-Unicode Backslash (Quoted)', marks=[skipif_file_win32, skipif_file_darwin]),
    pytest.param(ignore_dir, id='Ignore Directory')
])
@pytest.mark.parametrize('exclude', [
    pytest.param(True, id='With export-ignore'),
    pytest.param(False, id='Without export-ignore'),
])
def test_ignore(contents, exclude, tmpdir, git_env, monkeypatch):
    """
    Ensure that GitArchiver respects export-ignore.
    """
    # On Python 2.7 contained code raises pytest.PytestWarning warning for no good reason.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        for name, value in git_env.items():
            monkeypatch.setenv(name, value)

    repo_path = os_path_join(tmpdir.strpath, 'repo')
    repo = Repo(repo_path)
    repo.init()
    repo.add_dir('.', contents)
    repo.commit('init')

    repo_tar_path = os_path_join(tmpdir.strpath, 'repo.tar')
    repo.archive(repo_tar_path, exclude=exclude)
    repo_tar = TarFile(repo_tar_path, format=PAX_FORMAT, encoding='utf-8')

    expected = make_expected_tree(contents, exclude)
    actual = make_actual_tree(repo_tar)

    assert actual == expected


def test_cli(tmpdir, git_env, monkeypatch):
    contents = base

    # On Python 2.7 contained code raises pytest.PytestWarning warning for no good reason.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        for name, value in git_env.items():
            monkeypatch.setenv(name, value)

    repo_path = os_path_join(tmpdir.strpath, 'repo')
    repo = Repo(repo_path)
    repo.init()
    repo.add_dir('.', contents)
    repo.commit('init')

    repo_tar_path = os_path_join(tmpdir.strpath, 'repo.tar')
    git_archive_all.main(['git_archive_all.py', '--prefix', '', '-C', repo_path, repo_tar_path])
    repo_tar = TarFile(repo_tar_path, format=PAX_FORMAT, encoding='utf-8')

    expected = make_expected_tree(contents)
    actual = make_actual_tree(repo_tar)

    assert actual == expected


@pytest.mark.parametrize('version', [
    b'git version 2.21.0.0.1',
    b'git version 2.21.0.windows.1'
])
def test_git_version_parse(version, mocker):
    mocker.patch.object(GitArchiver, 'run_git_shell', return_value=version)
    assert GitArchiver.get_git_version() == (2, 21, 0, 0, 1)


def test_pycodestyle():
    style = pycodestyle.StyleGuide(repeat=True, max_line_length=240)
    report = style.check_files(['git_archive_all.py'])
    assert report.total_errors == 0, "Found code style errors (and warnings)."
