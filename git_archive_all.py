#! /usr/bin/env python
# coding=utf-8

# The MIT License (MIT)
#
# Copyright (c) 2010 Ilya Kulakov
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from __future__ import print_function
from __future__ import unicode_literals

import logging
from os import extsep, path, readlink, walk
from subprocess import CalledProcessError, Popen, PIPE
import sys
import re

__version__ = "1.19.1"


try:
    # Python 3.3+
    from shlex import quote
except ImportError:
    _find_unsafe = re.compile(r'[^a-zA-Z0-9_@%+=:,./-]').search

    def quote(s):
        """Return a shell-escaped version of the string *s*."""
        if not s:
            return "''"

        if _find_unsafe(s) is None:
            return s

        return "'" + s.replace("'", "'\"'\"'") + "'"


class GitArchiver(object):
    """
    GitArchiver

    Scan a git repository and export all tracked files, and submodules.
    Checks for .gitattributes files in each directory and uses 'export-ignore'
    pattern entries for ignore files in the archive.

    >>> archiver = GitArchiver(main_repo_abspath='my/repo/path')
    >>> archiver.create('output.zip')
    """
    TARFILE_FORMATS = {
        'tar': 'w',
        'tbz2': 'w:bz2',
        'tgz': 'w:gz',
        'txz': 'w:xz',
        'bz2': 'w:bz2',
        'gz': 'w:gz',
        'xz': 'w:xz'
    }
    ZIPFILE_FORMATS = ('zip',)

    LOG = logging.getLogger('GitArchiver')

    def __init__(
            self,
            prefix='',
            _exclude=None,  # use ignore_gitattributes instead
            force_submodules=None,
            include=None,
            main_repo_abspath=None,
            exclude=None,
            ignore_gitattributes=None,
            ignore_uninitialized_submodules=None,
            **kwargs):
        """
        @param prefix: Prefix used to prepend all paths in the resulting archive.
            Extra file paths are only prefixed if they are not relative.
            E.g. if prefix is 'foo' and extra is ['bar', '/baz'] the resulting archive will look like this:
            /
              baz
              foo/
                bar
        @type prefix: str

        @param force_submodules: Whether submodules are initialized and updated before archiving.
            Defaults to False
        @type force_submodules: bool

        @param include: List of extra paths to include in the resulting archive.
            Relative paths are resolved against main_repo_abspath.
        @type include: [str] or None

        @param main_repo_abspath: Absolute path to the main repository (or one of subdirectories).
            If given path is a path to a subdirectory (but not a submodule directory!) it will be replaced
            with abspath to a top-level directory of the repository.
            Defaults to the current working directory.
        @type main_repo_abspath: str or None

        @param exclude: List of extra paths to exclude from the resulting archive.
            Relative paths are resolved against main_repo_abspath.
        @type exclude: [str] or None

        @param ignore_gitattributes: Whether archiver should follow rules specified in .gitattributes files.
            Defaults to False.
        @type ignore_gitattributes: bool

        @param ignore_uninitialized_submodules: Whether archiver should ignore uninitialized submodules.
            Defaults to False.
        @type ignore_uninitialized_submodules: bool
        """
        if force_submodules is None:
            force_submodules = None

        if ignore_uninitialized_submodules is None:
            ignore_uninitialized_submodules = False

        if include is None:
            include = []

        if exclude is None:
            exclude = []

        # Backward compatibility with 1.19-
        if isinstance(exclude, bool):
            self.LOG.warning("The exclude keyword argument is now reserved for files exclusion."
                             " Use ignore_gitattributes instead.")
            ignore_gitattributes = exclude
            exclude = None

        if _exclude is not None:
            self.LOG.warning("The exclude positional argument is deprecated,"
                             " use the ignore_gitattributes keyword argument instead.")

            if ignore_gitattributes is None:
                ignore_gitattributes = _exclude
            else:
                raise TypeError("cannot set ignore_gitattributes keyword argument"
                                " and _exclude positional argument at the same time")

        if 'extra' in kwargs and kwargs['extra']:
            self.LOG.warning("The extra keyword argument is deprecated,"
                             " use the include keyword argument instead.")
            include.extend(kwargs['extra'])

        if 'force_sub' in kwargs:
            self.LOG.warning("The force_sub keyword argument is deprecated,"
                             " use the force_submodules keyword argument instead.")
            force_submodules = kwargs['force_sub']

        if main_repo_abspath is None:
            main_repo_abspath = path.abspath('')
        elif not path.isabs(main_repo_abspath):
            raise ValueError("main_repo_abspath must be an absolute path")

        def abspath(p):
            return path.normpath(path.join(main_repo_abspath, p))

        exclude = [abspath(p) for p in exclude]
        self.excluded_dirs = [p + path.sep for p in exclude if path.isdir(p)]
        self.excluded_files = [p for p in exclude if path.isfile(p)]

        self.included_dirs = []
        self.included_files = []
        for file_path in include:
            file_abspath = abspath(file_path)

            if path.isdir(file_abspath):
                self.included_dirs.append(file_abspath)
            elif path.isfile(file_abspath):
                self.included_files.append(file_abspath)

        try:
            self.main_repo_abspath = path.abspath(self.run_git_shell('git rev-parse --show-toplevel', main_repo_abspath)[:-1])
        except CalledProcessError:
            raise ValueError("{0} is not part of a git repository".format(main_repo_abspath))

        self.prefix = prefix
        self.force_submodules = force_submodules

        self.ignore_gitattributes = ignore_gitattributes
        self.ignore_uninitialized_submodules = ignore_uninitialized_submodules

        self._check_attr_gens = {}

    def create(self, output_path, dry_run=False, output_format=None, compresslevel=None):
        """
        Create the archive at output_file_path.

        Type of the archive is determined either by extension of output_file_path or by output_format.
        Supported formats are: gz, zip, bz2, xz, tar, tgz, txz

        @param output_path: Output file path.
        @type output_path: str

        @param dry_run: Determines whether create should do nothing but print what it would archive.
        @type dry_run: bool

        @param output_format: Determines format of the output archive. If None, format is determined from extension
            of output_file_path.
        @type output_format: str
        """
        if output_format is None:
            file_name, file_ext = path.splitext(output_path)
            output_format = file_ext[len(extsep):].lower()
            self.LOG.debug("Output format is not explicitly set, determined format is %s.", output_format)

        if not dry_run:
            if output_format in self.ZIPFILE_FORMATS:
                from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

                if compresslevel is not None:
                    if sys.version_info > (3, 7):
                        archive = ZipFile(path.abspath(output_path), 'w', compresslevel=compresslevel)
                    else:
                        raise ValueError("Compression level for zip archives requires Python 3.7+")
                else:
                    archive = ZipFile(path.abspath(output_path), 'w')

                def add_file(file_path, arcname):
                    if not path.islink(file_path):
                        archive.write(file_path, arcname, ZIP_DEFLATED)
                    else:
                        i = ZipInfo(arcname)
                        i.create_system = 3
                        i.external_attr = 0xA1ED0000
                        archive.writestr(i, readlink(file_path))
            elif output_format in self.TARFILE_FORMATS:
                import tarfile

                mode = self.TARFILE_FORMATS[output_format]

                if compresslevel is not None:
                    try:
                        archive = tarfile.open(path.abspath(output_path), mode, compresslevel=compresslevel)
                    except TypeError:
                        raise ValueError("{0} cannot be compressed".format(output_format))
                else:
                    archive = tarfile.open(path.abspath(output_path), mode)

                def add_file(file_path, arcname):
                    archive.add(file_path, arcname)
            else:
                raise ValueError("unknown format: {0}".format(output_format))

            def archiver(file_path, arcname):
                self.LOG.debug("%s => %s", file_path, arcname)
                add_file(file_path, arcname)
        else:
            archive = None

            def archiver(file_path, arcname):
                self.LOG.info("%s => %s", file_path, arcname)

        self.archive_all_files(archiver)

        if archive is not None:
            archive.close()

    def is_file_excluded(self, repo_abspath, repo_file_path):
        """
        Checks whether file at a given path is excluded.

        @param repo_abspath: Absolute path to the git repository.
        @type repo_abspath: str

        @param repo_file_path: Path to a file relative to repo_abspath.
        @type repo_file_path: str

        @return: True if file should be excluded. Otherwise False.
        @rtype: bool
        """
        repo_file_abspath = path.join(repo_abspath, repo_file_path)

        if self.excluded_files or self.excluded_dirs:
            if repo_file_abspath in self.excluded_files or repo_file_abspath in self.excluded_dirs:
                self.LOG.debug("%s is excluded explicitly.", repo_file_abspath)
                return True
            elif self.excluded_dirs:
                for d in self.excluded_dirs:
                    if repo_file_abspath.startswith(d):
                        self.LOG.debug("%s is inside explicitly excluded directory %s.", repo_file_abspath, d)
                        return True

        if not self.ignore_gitattributes:
            next(self._check_attr_gens[repo_abspath])
            attrs = self._check_attr_gens[repo_abspath].send(repo_file_path)

            if attrs['export-ignore'] == 'set':
                self.LOG.debug("%s is excluded via .gitattributes", repo_file_abspath)
                return True

        return False

    def archive_all_files(self, archiver):
        """
        Archive all files using archiver.

        @param archiver: Callable that accepts 2 arguments:
            abspath to a file in the file system and relative path within archive.
        @type archiver: Callable
        """
        def arcpath(p):
            if p.startswith(self.main_repo_abspath + path.sep):
                return path.join(self.prefix, path.relpath(p, self.main_repo_abspath))
            else:
                return path.join(self.prefix, p)

        for file_abspath in self.included_files:
            self.LOG.debug("%s is included explicitly.", file_abspath)
            archiver(file_abspath, arcpath(file_abspath))

        for dir_abspath in self.included_dirs:
            for subdir_abspath, _, filenames in walk(dir_abspath):
                for file_path in filenames:
                    file_abspath = path.join(subdir_abspath, file_path)
                    self.LOG.debug("%s is inside explicitly included directory %s.", file_abspath, dir_abspath)
                    archiver(file_abspath, arcpath(file_abspath))

        for main_repo_file_path in self.walk_git_files():
            archiver(path.join(self.main_repo_abspath, main_repo_file_path), path.join(self.prefix, main_repo_file_path))

    def walk_git_files(self, repo_path=''):
        """
        An iterator method that yields a file path relative to main_repo_abspath
        for each file that should be included in the archive.
        Skips those that match the exclusion patterns found in
        any discovered .gitattributes files along the way.

        Recurs into submodules as well.

        @param repo_path: Path to the git submodule repository relative to main_repo_abspath.
        @type repo_path: str

        @return: Iterator to traverse files under git control relative to main_repo_abspath.
        @rtype: Iterable
        """
        repo_abspath = path.join(self.main_repo_abspath, repo_path)

        if not self.ignore_gitattributes:
            assert repo_abspath not in self._check_attr_gens
            self._check_attr_gens[repo_abspath] = self.check_attr(repo_abspath, ['export-ignore'])

        try:
            repo_file_paths = self.run_git_shell(
                'git ls-files -z --cached --full-name --no-empty-directory',
                repo_abspath
            ).split('\0')[:-1]

            for repo_file_path in repo_file_paths:
                repo_file_abspath = path.join(repo_abspath, repo_file_path)  # absolute file path
                main_repo_file_path = path.join(repo_path, repo_file_path)  # relative to main_repo_abspath

                # Only list symlinks and files.
                if not path.islink(repo_file_abspath) and path.isdir(repo_file_abspath):
                    continue

                if self.is_file_excluded(repo_abspath, repo_file_path):
                    continue

                yield main_repo_file_path

            if self.force_submodules:
                self.run_git_shell('git submodule init', repo_abspath)
                self.run_git_shell('git submodule update', repo_abspath)

            try:
                repo_gitmodules_abspath = path.join(repo_abspath, ".gitmodules")

                with open(repo_gitmodules_abspath) as f:
                    lines = f.readlines()

                for l in lines:
                    m = re.match("^\\s*path\\s*=\\s*(.*)\\s*$", l)

                    if m:
                        repo_submodule_path = m.group(1)  # relative to repo_path

                        if self.is_file_excluded(repo_abspath, repo_submodule_path):
                            continue

                        main_repo_submodule_path = path.join(repo_path, repo_submodule_path)  # relative to main_repo_abspath
                        main_repo_submodule_abspath = path.join(self.main_repo_abspath, main_repo_submodule_path)

                        if not path.exists(main_repo_submodule_abspath) and self.ignore_uninitialized_submodules:
                            self.LOG.debug("The %s submodule does not exist, but uninitialized submodules are ignored.",
                                           main_repo_submodule_abspath)
                            continue

                        for main_repo_submodule_file_path in self.walk_git_files(main_repo_submodule_path):
                            repo_submodule_file_path = main_repo_submodule_file_path.replace(repo_path, "", 1).strip("/")  # relative to repo_path
                            if self.is_file_excluded(repo_abspath, repo_submodule_file_path):
                                continue

                            yield main_repo_submodule_file_path
            except IOError:
                pass
        finally:
            self._check_attr_gens[repo_abspath].close()
            del self._check_attr_gens[repo_abspath]

    @classmethod
    def decode_git_output(cls, output):
        """
        Decode Git's binary output handeling the way it escapes unicode characters.

        @type output: bytes

        @rtype: str
        """
        return output.decode('unicode_escape').encode('raw_unicode_escape').decode('utf-8')

    @classmethod
    def run_git_shell(cls, cmd, cwd=None):
        """
        Runs git shell command, reads output and decodes it into unicode string.

        @param cmd: Command to be executed.
        @type cmd: str

        @type cwd: str
        @param cwd: Working directory.

        @rtype: str
        @return: Output of the command.

        @raise CalledProcessError:  Raises exception if return code of the command is non-zero.
        """
        p = Popen(cmd, shell=True, stdout=PIPE, cwd=cwd)
        output, _ = p.communicate()
        output = cls.decode_git_output(output)

        if p.returncode:
            if sys.version_info > (2, 6):
                raise CalledProcessError(returncode=p.returncode, cmd=cmd, output=output)
            else:
                raise CalledProcessError(returncode=p.returncode, cmd=cmd)

        return output

    @classmethod
    def check_attr(cls, repo_abspath, attrs):
        """
        Generator that returns attributes for given paths relative to repo_abspath.

        >>> g = GitArchiver.check_attr('repo_path', ['export-ignore'])
        >>> next(g)
        >>> attrs = g.send('relative_path')
        >>> print(attrs['export-ignore'])

        @param repo_abspath: Absolute path to a git repository.
        @type repo_abspath: str

        @param attrs: Attributes to check.
        @type attrs: [str]

        @rtype: generator
        """
        def make_process():
            cmd = 'GIT_FLUSH=1 git check-attr --stdin -z {0}'.format(' '.join(attrs))
            return Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, cwd=repo_abspath)

        def read_attrs(process, repo_file_path):
            process.stdin.write(repo_file_path.encode('utf-8') + b'\0')
            process.stdin.flush()

            # For every attribute check-attr will output: <path> NUL <attribute> NUL <info> NUL
            path, attr, info = b'', b'', b''
            nuls_count = 0
            nuls_expected = 3 * len(attrs)

            while nuls_count != nuls_expected:
                b = process.stdout.read(1)

                if b == b'' and process.poll() is not None:
                    raise RuntimeError("check-attr exited prematurely")
                elif b == b'\0':
                    nuls_count += 1

                    if nuls_count % 3 == 0:
                        yield map(cls.decode_git_output, (path, attr, info))
                        path, attr, info = b'', b'', b''
                elif nuls_count % 3 == 0:
                    path += b
                elif nuls_count % 3 == 1:
                    attr += b
                elif nuls_count % 3 == 2:
                    info += b

        if not attrs:
            return

        process = make_process()

        try:
            while True:
                repo_file_path = yield
                repo_file_attrs = {}

                for path, attr, value in read_attrs(process, repo_file_path):
                    assert path == repo_file_path
                    assert attr in attrs
                    repo_file_attrs[attr] = value

                yield repo_file_attrs
        finally:
            process.stdin.close()
            process.wait()


def main():
    from optparse import OptionParser, SUPPRESS_HELP

    parser = OptionParser(
        usage="usage: %prog [-v] [--dry-run] [--prefix PREFIX] [--ignore-gitattributes] [--ignore-uninitialized-submodules] [--force-submodules]"
              " [--include FILE1 [--include FILE2 ...]] [--exclude FILE1 [--exclude FILE2 ...]] [-0 | ... | -9] OUTPUT_FILE",
        version="%prog {0}".format(__version__)
    )

    parser.add_option('-v', '--verbose',
                      action='store_true',
                      dest='verbose',
                      help='enable verbose mode')

    parser.add_option('--dry-run',
                      action='store_true',
                      dest='dry_run',
                      help="don't actually archive anything, just show what would be done")

    parser.add_option('--prefix',
                      type='string',
                      dest='prefix',
                      default=None,
                      help="""prepend PREFIX to each filename in the archive.
                          OUTPUT_FILE name is used by default to avoid tarbomb.
                          You can set it to '' in order to explicitly request tarbomb""")

    parser.add_option('--ignore-gitattributes',
                      action='store_true',
                      dest='ignore_gitattributes',
                      default=False,
                      help="ignore the export-ignore attribute in .gitattributes")

    parser.add_option('--ignore-uninitialized-submodules',
                      action='store_true',
                      dest='ignore_uninitialized_submodules',
                      default=False,
                      help="ignore uninitialized submodules instead of failing with error")

    parser.add_option('--force-submodules',
                      action='store_true',
                      dest='force_submodules',
                      help="""force a git submodule init && git submodule update at
                           each level before iterating submodules""")

    parser.add_option('--include',
                      action='append',
                      dest='include',
                      default=[],
                      help="any additional files to include in the archive")

    parser.add_option('--exclude',
                      action='append',
                      dest='exclude',
                      default=[],
                      help="any additional files to exclude from the archive")

    parser.add_option('--no-exclude',
                      action='store_true',
                      dest='ignore_gitattributes',
                      help=SUPPRESS_HELP)

    parser.add_option('--extra',
                      action='append',
                      dest='include',
                      default=[],
                      help=SUPPRESS_HELP)

    for i in range(10):
        parser.add_option('-{0}'.format(i),
                          action='store_const',
                          const=i,
                          dest='compresslevel',
                          help=SUPPRESS_HELP)

    options, args = parser.parse_args()

    if len(args) != 1:
        parser.error("You must specify exactly one output file")

    output_file_path = args[0]

    if path.isdir(output_file_path):
        parser.error("You cannot use directory as output")

    # avoid tarbomb
    if options.prefix is not None:
        options.prefix = path.join(options.prefix, '')
    else:
        output_name = path.basename(output_file_path)
        output_name = re.sub(
            '(\\.zip|\\.tar|\\.tbz2|\\.tgz|\\.txz|\\.bz2|\\.gz|\\.xz|\\.tar\\.bz2|\\.tar\\.gz|\\.tar\\.xz)$',
            '',
            output_name
        ) or "Archive"
        options.prefix = path.join(output_name, '')

    try:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(message)s'))
        GitArchiver.LOG.addHandler(handler)
        GitArchiver.LOG.setLevel(logging.DEBUG if options.verbose else logging.INFO)
        archiver = GitArchiver(prefix=options.prefix,
                               ignore_gitattributes=options.ignore_gitattributes,
                               ignore_uninitialized_submodules=options.ignore_uninitialized_submodules,
                               force_submodules=options.force_submodules,
                               include=options.include,
                               exclude=options.exclude)
        archiver.create(output_file_path, options.dry_run, compresslevel=options.compresslevel)
    except Exception as e:
        parser.exit(2, "{0}\n".format(e))

    sys.exit(0)


if __name__ == '__main__':
    main()
