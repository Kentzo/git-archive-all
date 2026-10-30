from copy import deepcopy
import errno
from functools import partial
import os
from pathlib import Path, PurePosixPath
from subprocess import check_call
import sys
from tarfile import TarFile
from zipfile import ZipFile

try:
    import lzma
except ImportError:
    lzma = None

try:
    from compression import zstd
except ImportError:
    zstd = None

import pycodestyle
import pytest

import git_archive_all
from git_archive_all import GitArchiver, fspath


@pytest.fixture
def git_env(tmp_path_factory, monkeypatch):
    """
    Configure ENV of git for tests:

    1. Both system and user configs are ignored
    2. Custom git user
    3. .gitmodules file is ignored by default
    """
    home_path = tmp_path_factory.getbasetemp()
    e = {
        'GIT_CONFIG_NOSYSTEM': 'true',
        'HOME': fspath(home_path)
    }

    with (home_path / '.gitconfig').open('wb+') as f:
        f.writelines([
            b'[core]\n',
            f"attributesfile = {(home_path / '.gitattributes').as_posix()}\n".encode(),
            b'[user]\n',
            b'name = git-archive-all\n',
            b'email = git-archive-all@example.com\n',
        ])

    # .gitmodules's content is dynamic and is maintained by git.
    # It's therefore ignored solely to simplify tests.
    #
    # If test is run with the --no-exclude CLI option (or its exclude=False API equivalent)
    # then the file itself is included while its content is discarded for the same reason.
    with (home_path / '.gitattributes').open('wb+') as f:
        f.writelines([
            b'.gitmodules export-ignore\n'
        ])

    for name, value in e.items():
        monkeypatch.setenv(name, value)


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
        self.path = Path(path).resolve()
        self.contents = None

    @classmethod
    def create(cls, path, contents):
        r = cls(path)
        r.init()
        r.add_dir('.', contents)
        r.commit('init')
        r.contents = contents
        return r

    def init(self):
        self.path.mkdir()
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
        file_path = self.path / rel_path

        with file_path.open('wb') as f:
            f.write(contents)

        check_call(['git', 'add', file_path], cwd=self.path)
        return file_path

    def add_dir(self, rel_path, contents):
        dir_path = self.path / rel_path
        dir_path.mkdir(parents=True, exist_ok=True)

        for k, v in contents.items():
            self.add(dir_path / fspath(k), v)

        check_call(['git', 'add', dir_path], cwd=self.path)
        return dir_path

    def add_submodule(self, rel_path, contents):
        submodule_path = self.path / rel_path
        Repo.create(submodule_path, contents)
        check_call(['git', 'submodule', 'add', submodule_path], cwd=self.path)
        return submodule_path

    def commit(self, message):
        check_call(['git', 'commit', '-m', message], cwd=self.path)

    def assert_archive(self, path, exclude=True):
        """
        Archive the repo into tar at path and assert that it matches contents committed by create.
        """
        a = GitArchiver(exclude=exclude, main_repo_abspath=self.path)
        a.create(path)

        with TarFile(path, encoding='utf-8') as tar_file:
            actual = make_actual_tree(tar_file)

        assert actual == make_expected_tree(self.contents, exclude)


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
                nested_k = (PurePosixPath(fspath(k)) / fspath(nested_k)).as_posix()
                e[nested_k] = nested_v

    return e


def make_actual_tree(tar_file):
    a = {}

    for m in tar_file.getmembers():
        if m.isfile():
            name = m.name

            # See the comment in git_env.
            if not name.endswith('.gitmodules'):
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

single_quote_submodule = deepcopy(base)
single_quote_submodule['\'lib\''] = SubmoduleRecord({
    '__init__.py': FileRecord(b'#If the implementation is hard to explain, it\'s a bad idea.'),
})

double_quote_submodule = deepcopy(base)
double_quote_submodule['\"lib\"'] = SubmoduleRecord({
    '__init__.py': FileRecord(b'#If the implementation is easy to explain, it may be a good idea.'),
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

git_in_cwd = deepcopy(base)
git_in_cwd['git.exe'] = FileRecord(b'')
git_in_cwd['git.bat'] = FileRecord(b'@echo shadowed\r\n')
git_in_cwd['lib']['git.exe'] = FileRecord(b'')
git_in_cwd['lib']['git.bat'] = FileRecord(b'@echo shadowed\r\n')


@pytest.fixture
def contents():
    """
    Return contents of the repo fixture.

    Override with @pytest.mark.parametrize('contents', [...]).
    """
    return base


@pytest.fixture
def repo(contents, tmp_path, git_env):
    """
    Return Repo with contents committed.
    """
    return Repo.create(tmp_path / 'repo', contents)


skipif_file_darwin = pytest.mark.skipif(sys.platform == 'darwin', reason='Invalid macOS filename.')
skipif_file_win32 = pytest.mark.skipif(sys.platform == 'win32', reason="Invalid Windows filename.")

git_version = GitArchiver.get_git_version()
skipif_git_config_count = pytest.mark.skipif(git_version is None or git_version < (2, 31), reason="GIT_CONFIG_COUNT requires git 2.31+")


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
    pytest.param(single_quote_submodule, id='Submodule (Single Quote)'),
    pytest.param(double_quote_submodule, id='Submodule (Double Quote)', marks=skipif_file_win32),
    pytest.param(ignore_dir, id='Ignore Directory')
])
@pytest.mark.parametrize('exclude', [
    pytest.param(True, id='With export-ignore'),
    pytest.param(False, id='Without export-ignore'),
])
def test_ignore(exclude, tmp_path, repo):
    """
    Ensure that GitArchiver respects export-ignore.
    """
    repo_tar_path = tmp_path / 'repo.tar'
    repo.assert_archive(repo_tar_path, exclude=exclude)


def test_cli(tmp_path, repo):
    repo_tar_path = fspath(tmp_path / 'repo.tar')
    git_archive_all.main(['git_archive_all.py', '--prefix', '', '-C', fspath(repo.path), repo_tar_path])

    with TarFile(repo_tar_path, encoding='utf-8') as repo_tar:
        assert make_actual_tree(repo_tar) == make_expected_tree(repo.contents)


@pytest.mark.parametrize('contents', [
    pytest.param(unicode_base, id='Unicode'),
])
@pytest.mark.parametrize('option', [
    '-v',
    '--dry-run'
])
def test_cli_log(option, tmp_path, repo, capfd):
    """
    Ensure that CLI logs non-ASCII paths.
    """
    repo_tar_path = fspath(tmp_path / 'repo.tar')
    capfd.readouterr()
    git_archive_all.main(['git_archive_all.py', option, '--prefix', '', '-C', fspath(repo.path), repo_tar_path])
    out, _ = capfd.readouterr()

    assert f" => {os.path.join('data', 'مرحبا بالعالم.dat')}\n" in out


@pytest.mark.parametrize('env_vars', [
    pytest.param({'GIT_DIR': '.git'}, id='GIT_DIR'),
    pytest.param({'GIT_DIR': '.git', 'GIT_WORK_TREE': '.'}, id='GIT_DIR and GIT_WORK_TREE'),
    pytest.param({'GIT_INDEX_FILE': '.git/index'}, id='GIT_INDEX_FILE'),
])
def test_submodule_local_env(env_vars, tmp_path, repo, monkeypatch):
    """
    Ensure that repository-local variables of the main repository (e.g. set by git for hooks)
    do not leak into submodules.
    """
    # git-archive-all must clear these variables before running git in submodules.
    # Otherwise `git ls-files` in a submodule reads the main repository's index and
    # returns its paths, which, joined with the submodule's path, do not exist.

    for name, value in env_vars.items():
        # Absolute, otherwise each git command would resolve against its own cwd.
        monkeypatch.setenv(name, fspath(repo.path / value))

    repo_tar_path = tmp_path / 'repo.tar'
    repo.assert_archive(repo_tar_path)


@pytest.mark.parametrize('env_var', [
    pytest.param('GIT_CONFIG_PARAMETERS', id='GIT_CONFIG_PARAMETERS'),
    pytest.param('GIT_CONFIG_COUNT', id='GIT_CONFIG_COUNT', marks=skipif_git_config_count),
])
def test_submodule_config_env(env_var, tmp_path, repo, monkeypatch):
    """
    Ensure that config passed via `git -c` applies to submodules, same as in git.
    """
    if env_var == 'GIT_CONFIG_PARAMETERS':
        config_env = {'GIT_CONFIG_PARAMETERS': "'safe.directory=*'"}
    else:
        config_env = {
            'GIT_CONFIG_COUNT': '1',
            'GIT_CONFIG_KEY_0': 'safe.directory',
            'GIT_CONFIG_VALUE_0': '*',
        }

    for name, value in config_env.items():
        monkeypatch.setenv(name, value)

    # Every repository is now considered to be of dubious ownership unless safe.directory reaches it.
    monkeypatch.setenv('GIT_TEST_ASSUME_DIFFERENT_OWNER', '1')

    repo_tar_path = tmp_path / 'repo.tar'
    repo.assert_archive(repo_tar_path)


def test_archiver_error(repo):
    """
    Ensure that git processes are closed when archiver raises.
    """
    class ArchiverError(Exception):
        pass

    def archiver(file_path, arcname):
        if Path(arcname) == Path('lib', 'extra', '__init__.py'):
            raise ArchiverError()

    a = GitArchiver(prefix='', main_repo_abspath=repo.path)

    with pytest.raises(ArchiverError):
        a.archive_all_files(archiver)

    assert len(a._check_attr_gens) == 0


@pytest.mark.parametrize('output_format', [
    'tar',
    'tgz',
    'zip'
])
def test_cli_error_cleanup(output_format, tmp_path, repo):
    """
    Ensure that incomplete archive is removed on error.
    """
    missing_path = fspath(tmp_path / 'missing')
    repo_archive_path = fspath(tmp_path / f'repo.{output_format}')

    with pytest.raises(SystemExit):
        git_archive_all.main(['git_archive_all.py', '--include', missing_path, '-C', fspath(repo.path), repo_archive_path])

    assert not os.path.exists(repo_archive_path)


@pytest.mark.parametrize('fail_close, fail_remove', [
    (False, True),
    (True, False),
    (True, True)
])
def test_error_cleanup_error(fail_close, fail_remove, tmp_path, repo, monkeypatch):
    """
    Ensure that errors during cleanup do not hide the original exception.
    """
    missing_path = tmp_path / 'missing'
    repo_tar_path = tmp_path / 'repo.tar'
    real_close = TarFile.close
    real_remove = git_archive_all.remove

    def close(self):
        real_close(self)

        if fail_close:
            raise OSError(errno.EIO, '')

    def remove(p):
        if fail_remove:
            raise OSError(errno.EACCES, '')

        real_remove(p)

    monkeypatch.setattr(TarFile, 'close', close)
    monkeypatch.setattr(git_archive_all, 'remove', remove)
    a = GitArchiver(extra=[missing_path], main_repo_abspath=repo.path)

    with pytest.raises(OSError) as e:
        a.create(repo_tar_path)

    expected = []
    if fail_remove:
        expected += [errno.EACCES]
    if fail_close:
        expected += [errno.EIO]
    expected += [errno.ENOENT]

    actual = []
    context = e.value

    while context is not None:
        actual.append(context.errno)
        context = context.__context__

    assert actual == expected

    assert os.path.exists(repo_tar_path) == fail_remove


@pytest.mark.parametrize('version', [
    b'git version 2.21.0.0.1',
    b'git version 2.21.0.windows.1'
])
def test_git_version_parse(version, mocker):
    mocker.patch.object(GitArchiver, 'run_git_shell', return_value=version)
    assert GitArchiver.get_git_version() == (2, 21, 0, 0, 1)


@pytest.mark.parametrize('output, unparsed', [
    pytest.param(b'git version', 'git version', id='No version'),
    pytest.param(b'git version 2.\xc2\xb2', '2.\u00b2', id='Non-ASCII digit'),
])
def test_git_version_parse_error(output, unparsed, mocker, caplog):
    """
    Ensure that unparsable version is logged as text.
    """
    mocker.patch.object(GitArchiver, 'run_git_shell', return_value=output)
    assert GitArchiver.get_git_version() is None
    assert caplog.messages == [f'Unable to parse Git version "{unparsed}".']


@pytest.mark.skipif(sys.platform != 'win32', reason="Windows only.")
@pytest.mark.parametrize('contents', [
    pytest.param(git_in_cwd, id='git in cwd')
])
def test_git_in_cwd(tmp_path, repo, monkeypatch):
    """
    Ensure that git committed into the repository does not shadow git in PATH.
    """
    # Both the current directory of the process and the working directory of commands are searched by cmd.exe.
    monkeypatch.chdir(repo.path)

    repo_tar_path = tmp_path / 'repo.tar'
    repo.assert_archive(repo_tar_path)


@pytest.mark.skipif(sys.platform != 'win32', reason="Windows only.")
@pytest.mark.parametrize('output_format', [
    'tar',
    'zip'
])
def test_backslash_separator(output_format, tmp_path, repo, monkeypatch):
    """
    Ensure that backslash-separated paths are accepted on Windows and archived with forward slashes.
    """
    extra_path = tmp_path / 'extra' / 'file.dat'
    extra_path.parent.mkdir()
    extra_path.write_bytes(b'Namespaces are one honking great idea -- let\'s do more of those!')
    monkeypatch.chdir(tmp_path)

    a = GitArchiver(prefix='archive\\root\\', extra=['extra\\file.dat'], main_repo_abspath=fspath(repo.path))

    expected = make_expected_tree(repo.contents)
    assert sorted(a.walk_git_files()) == sorted(k.replace('/', '\\') for k in expected)

    repo_archive_path = tmp_path / f'repo.{output_format}'
    a.create(repo_archive_path)

    expected = {f'archive/root/{k}': v for k, v in expected.items()}
    expected['archive/root/extra/file.dat'] = extra_path.read_bytes()

    if output_format == 'zip':
        with ZipFile(repo_archive_path) as zip_file:
            actual = {i.filename: zip_file.read(i) for i in zip_file.infolist()}
    else:
        with TarFile(repo_archive_path, encoding='utf-8') as tar_file:
            actual = make_actual_tree(tar_file)

    assert actual == expected


def test_pycodestyle():
    style = pycodestyle.StyleGuide(repeat=True, max_line_length=240)
    report = style.check_files(['git_archive_all.py'])
    assert report.total_errors == 0, "Found code style errors (and warnings)."


@pytest.mark.parametrize('output_format', [
    'tgz',
    'tbz2',
    pytest.param('txz', marks=pytest.mark.skipif(lzma is None, reason="Requires lzma.")),
    pytest.param('tzst', marks=pytest.mark.skipif(zstd is None, reason="Requires zstd.")),
])
@pytest.mark.parametrize('compresslevel', ['-1', '-9'])
def test_cli_compresslevel(output_format, compresslevel, tmpdir, git_env, monkeypatch):
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

    repo_archive_path = os_path_join(tmpdir.strpath, 'repo.' + output_format)
    git_archive_all.main(['git_archive_all.py', '--prefix', '', '-C', repo_path, compresslevel, repo_archive_path])

    with TarFile.open(repo_archive_path, format=PAX_FORMAT, encoding='utf-8') as repo_tar:
        expected = make_expected_tree(contents)
        actual = make_actual_tree(repo_tar)

    assert actual == expected


def test_cli_compresslevel_tar(tmpdir, git_env, monkeypatch):
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

    with pytest.raises(SystemExit) as e:
        git_archive_all.main(['git_archive_all.py', '--prefix', '', '-C', repo_path, '-9', repo_tar_path])

    assert e.value.code == 2
