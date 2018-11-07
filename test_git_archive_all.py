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

from git_archive_all import GitArchiver


def makedirs(p):
    try:
        os.makedirs(p)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


@pytest.fixture
def git_env(tmpdir_factory):
    """
    Return ENV git configured for tests:

    1. Both system and user configs are ignored
    2. Custom git user
    3. .gitmodules file is ignored by default
    """
    e = deepcopy(os.environ)
    e['GIT_CONFIG_NOSYSTEM'] = 'true'
    e['HOME'] = str(tmpdir_factory.getbasetemp())

    with tmpdir_factory.getbasetemp().join('.gitconfig').open('w+') as f:
        f.writelines([
            '[core]\n',
            'attributesfile = {0}/.gitattributes\n'.format(tmpdir_factory.getbasetemp()),
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
    def __init__(self, path, git_env):
        self.path = os.path.abspath(path)
        self.git_env = git_env

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
        file_path = os.path.join(self.path, rel_path)

        with open(file_path, 'w') as f:
            f.write(contents)

        check_call(['git', 'add', file_path], cwd=self.path, env=self.git_env)
        return file_path

    def add_dir(self, rel_path, contents):
        dir_path = os.path.join(self.path, rel_path)
        makedirs(dir_path)

        for k, v in contents.items():
            self.add(os.path.join(dir_path, k), v)

        check_call(['git', 'add', dir_path], cwd=self.path, env=self.git_env)
        return dir_path

    def add_submodule(self, rel_path, contents):
        submodule_path = os.path.join(self.path, rel_path)
        r = Repo(submodule_path, self.git_env)
        r.init()
        r.add_dir('.', contents)
        r.commit('init')
        check_call(['git', 'submodule', 'add', submodule_path], cwd=self.path, env=self.git_env)
        return submodule_path

    def commit(self, message):
        check_call(['git', 'commit', '-m', 'init'], cwd=self.path, env=self.git_env)

    def archive(self, path, include=None, exclude=None):
        a = GitArchiver(main_repo_abspath=self.path, include=include, exclude=exclude)
        a.create(path)


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
    pytest.param(base_quoted, id='No Ignore (Quoted)'),
    pytest.param(ignore_in_root, id='Ignore in Root'),
    pytest.param(ignore_in_submodule, id='Ignore in Submodule'),
    pytest.param(ignore_in_nested_submodule, id='Ignore in Nested Submodule'),
    pytest.param(ignore_in_submodule_from_root, id='Ignore in Submodule from Root'),
    pytest.param(ignore_in_nested_submodule_from_root, id='Ignore in Nested Submodule from Root'),
    pytest.param(ignore_in_nested_submodule_from_submodule, id='Ignore in Nested Submodule from Submodule'),
    pytest.param(unset_export_ignore, id='-export-ignore'),
    pytest.param(unicode_base, id='No Ignore (Unicode)'),
    pytest.param(unicode_quoted, id='No Ignore (Quoted Unicode)'),
    pytest.param(brackets_base, id='Brackets'),
    pytest.param(brackets_quoted, id="Brackets (Quoted)"),
    pytest.param(quote_base, id="Quote"),
    pytest.param(quote_quoted, id="Quote (Quoted)")
])
def test_export_ignore(contents, tmpdir, git_env):
    """
    Ensure that GitArchiver respects export-ignore.
    """
    repo_path = os.path.join(str(tmpdir), 'repo')
    repo = Repo(repo_path, git_env)
    repo.init()
    repo.add_dir('.', contents)
    repo.commit('init')

    repo_tar_path = os.path.join(str(tmpdir), 'repo.tar')
    repo.archive(repo_tar_path)
    repo_tar = TarFile(repo_tar_path, format=PAX_FORMAT, encoding='utf-8')

    def make_expected(contents):
        e = {}

        for k, v in contents.items():
            if v.kind == 'file' and not v.excluded:
                e[k] = v.contents
            elif v.kind in ('dir', 'submodule') and not v.excluded:
                for nested_k, nested_v in make_expected(v.contents).items():
                    e[os.path.join(k, nested_k)] = nested_v

        return e

    def make_actual(tar_file):
        a = {}

        for m in tar_file.getmembers():
            if m.isfile():
                name = m.name

                if sys.version_info < (3,):
                    name = m.name.decode('utf-8')

                a[name] = tar_file.extractfile(m).read().decode()
            else:
                raise NotImplementedError

        return a

    expected = make_expected(contents)
    actual = make_actual(repo_tar)

    assert actual == expected


@pytest.mark.parametrize('name', [
    pytest.param('repo ', id='Trailing space'),
])
def test_repo_dirs_with_trailing_whitespaces(name, tmpdir, git_env):
    repo_path = os.path.join(str(tmpdir), name)
    repo = Repo(repo_path, git_env)
    repo.init()
    repo.add_dir('.', base)
    repo.commit('init')

    repo_tar_path = os.path.join(str(tmpdir), 'repo.tar')
    repo.archive(repo_tar_path)


def test_explicitly_included_file(tmpdir, git_env):
    repo_path = os.path.join(str(tmpdir), 'repo')
    repo = Repo(repo_path, git_env)
    repo.init()
    repo.add_dir('.', base)
    repo.commit('init')

    file_path = os.path.join(repo_path, 'include')
    with open(file_path, 'w') as f:
        f.write('Hello')

    repo_tar_path = os.path.join(str(tmpdir), 'repo.tar')
    repo.archive(repo_tar_path, include=['include'])
    repo_tar = TarFile(repo_tar_path, format=PAX_FORMAT, encoding='utf-8')

    repo_tar.getmember('include')


def test_explicitly_included_dir(tmpdir, git_env):
    repo_path = os.path.join(str(tmpdir), 'repo')
    repo = Repo(repo_path, git_env)
    repo.init()
    repo.add_dir('.', base)
    repo.commit('init')

    dir_path = os.path.join(repo_path, 'include_dir')
    makedirs(dir_path)
    file_path = os.path.join(dir_path, 'include_file')
    with open(file_path, 'w') as f:
        f.write('Hello')

    repo_tar_path = os.path.join(str(tmpdir), 'repo.tar')
    repo.archive(repo_tar_path, include=['include_dir'])
    repo_tar = TarFile(repo_tar_path, format=PAX_FORMAT, encoding='utf-8')

    repo_tar.getmember('include_dir/include_file')


def test_explicitly_excluded_file(tmpdir, git_env):
    repo_path = os.path.join(str(tmpdir), 'repo')
    repo = Repo(repo_path, git_env)
    repo.init()
    repo.add_dir('.', base)
    repo.commit('init')

    repo_tar_path = os.path.join(str(tmpdir), 'repo.tar')
    repo.archive(repo_tar_path, exclude=['app/__init__.py'])
    repo_tar = TarFile(repo_tar_path, format=PAX_FORMAT, encoding='utf-8')

    repo_tar.getmember('lib/__init__.py')

    with pytest.raises(KeyError):
        repo_tar.getmember('app/__init__.py')


def test_explicitly_excluded_dir(tmpdir, git_env):
    repo_path = os.path.join(str(tmpdir), 'repo')
    repo = Repo(repo_path, git_env)
    repo.init()
    repo.add_dir('.', base)
    repo.commit('init')

    repo_tar_path = os.path.join(str(tmpdir), 'repo.tar')
    repo.archive(repo_tar_path, exclude=['lib'])
    repo_tar = TarFile(repo_tar_path, format=PAX_FORMAT, encoding='utf-8')

    repo_tar.getmember('app/__init__.py')

    with pytest.raises(KeyError):
        repo_tar.getmember('lib/__init__.py')

    with pytest.raises(KeyError):
        repo_tar.getmember('lib/extra/__init__.py')


def test_pycodestyle():
    style = pycodestyle.StyleGuide(repeat=True, max_line_length=240)
    report = style.check_files(['git_archive_all.py'])
    assert report.total_errors == 0, "Found code style errors (and warnings)."
