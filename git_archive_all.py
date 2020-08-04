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
from os import environ, extsep, path, readlink
from subprocess import CalledProcessError, Popen, PIPE
import sys
import re

__version__ = "1.22.0"


try:
    # Python 3.2+
    from os import fsdecode
except ImportError:
    def fsdecode(filename):
        if not isinstance(filename, unicode):
            return filename.decode(sys.getfilesystemencoding(), 'strict')
        else:
            return filename

try:
    # Python 3.2+
    from os import fsencode
except ImportError:
    def fsencode(filename):
        if not isinstance(filename, bytes):
            return filename.encode(sys.getfilesystemencoding(), 'strict')
        else:
            return filename


def git_fsdecode(filename):
    """
    Decode filename from git output into str.
    """
    if sys.platform.startswith('win32'):
        return filename.decode('utf-8')
    else:
        return fsdecode(filename)


def git_fsencode(filename):
    """
    Encode filename from str into git input.
    """
    if sys.platform.startswith('win32'):
        return filename.encode('utf-8')
    else:
        return fsencode(filename)


try:
    # Python 3.6+
    from os import fspath as _fspath

    def fspath(filename, decoder=fsdecode, encoder=fsencode):
        """
        Convert filename into bytes or str, depending on what's the best type
        to represent paths for current Python and platform.
        """
        # Python 3.6+: str can represent any path (PEP 383)
        #   str is not required on Windows (PEP 529)
        # Decoding is still applied for consistency and to follow PEP 519 recommendation.
        return decoder(_fspath(filename))
except ImportError:
    def fspath(filename, decoder=fsdecode, encoder=fsencode):
        # Python 3.4 and 3.5: str can represent any path (PEP 383),
        #   but str is required on Windows (no PEP 529)
        #
        # Python 2.6 and 2.7: str cannot represent any path (no PEP 383),
        #   str is required on Windows (no PEP 529)
        #   bytes is required on POSIX (no PEP 383)
        if sys.version_info > (3,):
            import pathlib
            if isinstance(filename, pathlib.PurePath):
                return str(filename)
            else:
                return decoder(filename)
        elif sys.platform.startswith('win32'):
            return decoder(filename)
        else:
            return encoder(filename)


def git_fspath(filename):
    """
    fspath representation of git output.
    """
    return fspath(filename, git_fsdecode, git_fsencode)


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

    def __init__(self, prefix='', exclude=True, force_sub=False, extra=None, main_repo_abspath=None, git_version=None):
        """
        @param prefix: Prefix used to prepend all paths in the resulting archive.
            Extra file paths are only prefixed if they are not relative.
            E.g. if prefix is 'foo' and extra is ['bar', '/baz'] the resulting archive will look like this:
            /
              baz
              foo/
                bar

        @param exclude: Determines whether archiver should follow rules specified in .gitattributes files.

        @param force_sub: Determines whether submodules are initialized and updated before archiving.

        @param extra: List of extra paths to include in the resulting archive.

        @param main_repo_abspath: Absolute path to the main repository (or one of subdirectories).
            If given path is path to a subdirectory (but not a submodule directory!) it will be replaced
            with abspath to top-level directory of the repository.
            If None, current cwd is used.

        @param git_version: Version of Git that determines whether various workarounds are on.
            If None, tries to resolve via Git's CLI.
        """
        self._check_attr_gens = {}
        self._ignored_paths_cache = {}

        if git_version is None:
            git_version = self.get_git_version()

        if git_version is not None and git_version < (1, 6, 1):
            raise ValueError("git of version 1.6.1 and higher is required")

        self.git_version = git_version

        if main_repo_abspath is None:
            main_repo_abspath = path.abspath('')
        elif not path.isabs(main_repo_abspath):
            raise ValueError("main_repo_abspath must be an absolute path")

        self.main_repo_abspath = self.resolve_git_main_repo_abspath(main_repo_abspath)

        self.prefix = fspath(prefix)
        self.exclude = exclude
        self.extra = [fspath(e) for e in extra] if extra is not None else []
        self.force_sub = force_sub

    def create(self, output_path, dry_run=False, output_format=None, compresslevel=None):
        """
        Create the archive at output_file_path.

        Type of the archive is determined either by extension of output_file_path or by output_format.
        Supported formats are: gz, zip, bz2, xz, tar, tgz, txz

        @param output_path: Output file path.

        @param dry_run: Determines whether create should do nothing but print what it would archive.

        @param output_format: Determines format of the output archive. If None, format is determined from extension
            of output_file_path.

        @param compresslevel: Optional compression level. Interpretation depends on the output format.
        """
        output_path = fspath(output_path)

        if output_format is None:
            file_name, file_ext = path.splitext(output_path)
            output_format = file_ext[len(extsep):].lower()
            self.LOG.debug("Output format is not explicitly set, determined format is {0}.".format(output_format))

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
                self.LOG.debug(fspath("{0} => {1}").format(file_path, arcname))
                add_file(file_path, arcname)
        else:
            archive = None

            def archiver(file_path, arcname):
                self.LOG.info(fspath("{0} => {1}").format(file_path, arcname))

        self.archive_all_files(archiver)

        if archive is not None:
            archive.close()

    def is_file_excluded(self, repo_abspath, repo_file_path):
        """
        Checks whether file at a given path is excluded.

        @param repo_abspath: Absolute path to the git repository.

        @param repo_file_path: Path to a file relative to repo_abspath.

        @return: True if file should be excluded. Otherwise False.
        """
        if not self.exclude:
            return False

        cache = self._ignored_paths_cache.setdefault(repo_abspath, {})

        if repo_file_path not in cache:
            next(self._check_attr_gens[repo_abspath])
            attrs = self._check_attr_gens[repo_abspath].send(repo_file_path)
            export_ignore_attr = attrs['export-ignore']

            if export_ignore_attr == b'set':
                cache[repo_file_path] = True
            elif export_ignore_attr == b'unset':
                cache[repo_file_path] = False
            else:
                repo_file_dir_path = path.dirname(repo_file_path)

                if repo_file_dir_path:
                    cache[repo_file_path] = self.is_file_excluded(repo_abspath, repo_file_dir_path)
                else:
                    cache[repo_file_path] = False

        return cache[repo_file_path]

    def archive_all_files(self, archiver):
        """
        Archive all files using archiver.

        @param archiver: Callable that accepts 2 arguments:
            abspath to file on the system and relative path within archive.
        """
        for file_path in self.extra:
            archiver(path.abspath(file_path), path.join(self.prefix, file_path))

        for file_path in self.walk_git_files():
            archiver(path.join(self.main_repo_abspath, file_path), path.join(self.prefix, file_path))

    def walk_git_files(self, repo_path=fspath('')):
        """
        An iterator method that yields a file path relative to main_repo_abspath
        for each file that should be included in the archive.
        Skips those that match the exclusion patterns found in
        any discovered .gitattributes files along the way.

        Recurs into submodules as well.

        @param repo_path: Path to the git submodule repository relative to main_repo_abspath.

        @return: Generator to traverse files under git control relative to main_repo_abspath.
        """
        repo_abspath = path.join(self.main_repo_abspath, fspath(repo_path))
        assert repo_abspath not in self._check_attr_gens
        self._check_attr_gens[repo_abspath] = self.check_git_attr(repo_abspath, ['export-ignore'])

        try:
            repo_file_paths = self.list_repo_files(repo_abspath)

            for repo_file_path in repo_file_paths:
                repo_file_abspath = path.join(repo_abspath, repo_file_path)  # absolute file path
                main_repo_file_path = path.join(repo_path, repo_file_path)  # relative to main_repo_abspath

                if not path.islink(repo_file_abspath) and path.isdir(repo_file_abspath):
                    continue

                if self.is_file_excluded(repo_abspath, repo_file_path):
                    continue

                yield main_repo_file_path

            if self.force_sub:
                self.run_git_shell('git submodule init', repo_abspath)
                self.run_git_shell('git submodule update', repo_abspath)

            try:
                repo_gitmodules_abspath = path.join(repo_abspath, fspath(".gitmodules"))

                with open(repo_gitmodules_abspath) as f:
                    lines = f.readlines()

                for l in lines:
                    m = re.match("^\\s*path\\s*=\\s*(.*)\\s*$", l)

                    if m:
                        repo_submodule_path = fspath(m.group(1))  # relative to repo_path
                        main_repo_submodule_path = path.join(repo_path, repo_submodule_path)  # relative to main_repo_abspath

                        if self.is_file_excluded(repo_abspath, repo_submodule_path):
                            continue

                        for main_repo_submodule_file_path in self.walk_git_files(main_repo_submodule_path):
                            repo_submodule_file_path = path.relpath(main_repo_submodule_file_path, repo_path)  # relative to repo_path
                            if self.is_file_excluded(repo_abspath, repo_submodule_file_path):
                                continue

                            yield main_repo_submodule_file_path
            except IOError:
                pass
        finally:
            self._check_attr_gens[repo_abspath].close()
            del self._check_attr_gens[repo_abspath]

    def check_git_attr(self, repo_abspath, attrs):
        """
        Generator that returns git attributes for received paths relative to repo_abspath.

        >>> archiver = GitArchiver(...)
        >>> g = archiver.check_git_attr('repo_path', ['export-ignore'])
        >>> next(g)
        >>> attrs = g.send('relative_path')
        >>> print(attrs['export-ignore'])

        @param repo_abspath: Absolute path to a git repository.

        @param attrs: Attributes to check
        """
        def make_process():
            env = dict(environ, GIT_FLUSH='1')
            cmd = 'git check-attr --stdin -z {0}'.format(' '.join(attrs))
            return Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, cwd=repo_abspath, env=env)

        def read_attrs(process, repo_file_path):
            process.stdin.write(repo_file_path + b'\0')
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
                        yield path, attr, info

                        path, attr, info = b'', b'', b''
                elif nuls_count % 3 == 0:
                    path += b
                elif nuls_count % 3 == 1:
                    attr += b
                elif nuls_count % 3 == 2:
                    info += b

        def read_attrs_old(process, repo_file_path):
            """
            Compatibility with versions 1.8.5 and below that do not recognize -z for output.
            """
            process.stdin.write(repo_file_path + b'\0')
            process.stdin.flush()

            # For every attribute check-attr will output: <path>: <attribute>: <info>\n
            # where <path> is c-quoted

            path, attr, info = b'', b'', b''
            lines_count = 0
            lines_expected = len(attrs)

            while lines_count != lines_expected:
                line = process.stdout.readline()

                info_start = line.rfind(b': ')
                if info_start == -1:
                    raise RuntimeError("unexpected output of check-attr: {0}".format(line))

                attr_start = line.rfind(b': ', 0, info_start)
                if attr_start == -1:
                    raise RuntimeError("unexpected output of check-attr: {0}".format(line))

                path = line[:attr_start]
                attr = line[attr_start + 2:info_start]  # trim leading ": "
                info = line[info_start + 2:len(line) - 1]  # trim leading ": " and trailing \n
                yield path, attr, info

                lines_count += 1

        if not attrs:
            return

        process = make_process()

        if self.git_version is None or self.git_version > (1, 8, 5):
            reader = read_attrs
        else:
            reader = read_attrs_old

        try:
            while True:
                repo_file_path = yield
                repo_file_path = git_fsencode(fspath(repo_file_path))
                repo_file_attrs = {}

                for path, attr, value in reader(process, repo_file_path):
                    attr = attr.decode('utf-8')
                    repo_file_attrs[attr] = value

                yield repo_file_attrs
        finally:
            process.stdin.close()
            process.wait()

    def resolve_git_main_repo_abspath(self, abspath):
        """
        Return absolute path to the repo for a given path.
        """
        try:
            main_repo_abspath = self.run_git_shell('git rev-parse --show-toplevel', cwd=abspath).rstrip()
            return path.abspath(git_fspath(main_repo_abspath))
        except CalledProcessError as e:
            raise ValueError("{0} is not part of a git repository ({1})".format(abspath, e.returncode))

    @classmethod
    def run_git_shell(cls, cmd, cwd=None):
        """
        Run git shell command, read output and decode it into a unicode string.

        @param cmd: Command to be executed.

        @param cwd: Working directory.

        @return: Output of the command.

        @raise CalledProcessError:  Raises exception if return code of the command is non-zero.
        """
        p = Popen(cmd, shell=True, stdout=PIPE, cwd=cwd)
        output, _ = p.communicate()

        if p.returncode:
            if sys.version_info > (2, 6):
                raise CalledProcessError(returncode=p.returncode, cmd=cmd, output=output)
            else:
                raise CalledProcessError(returncode=p.returncode, cmd=cmd)

        return output

    @classmethod
    def get_git_version(cls):
        """
        Return version of git current shell points to.

        If version cannot be parsed None is returned.
        """
        try:
            output = cls.run_git_shell('git version')
        except CalledProcessError:
            cls.LOG.warning("Unable to get Git version.")
            return None

        try:
            version = output.split()[2]
        except IndexError:
            cls.LOG.warning("Unable to parse Git version \"%s\".", output)
            return None

        try:
            return tuple(int(v) if v.isdigit() else 0 for v in version.split(b'.'))
        except ValueError:
            cls.LOG.warning("Unable to parse Git version \"%s\".", version)
            return None

    @classmethod
    def list_repo_files(cls, repo_abspath):
        repo_file_paths = cls.run_git_shell(
            'git ls-files -z --cached --full-name --no-empty-directory',
            cwd=repo_abspath
        )
        repo_file_paths = repo_file_paths.split(b'\0')[:-1]

        if sys.platform.startswith('win32'):
            repo_file_paths = (git_fspath(p.replace(b'/', b'\\')) for p in repo_file_paths)
        else:
            repo_file_paths = map(git_fspath, repo_file_paths)

        return repo_file_paths


def main(argv=None):
    if argv is None:
        argv = sys.argv

    from optparse import OptionParser, SUPPRESS_HELP

    parser = OptionParser(
        usage="usage: %prog [-v] [-C BASE_REPO] [--prefix PREFIX] [--no-export-ignore]"
              " [--force-submodules] [--include EXTRA1 ...] [--dry-run] [-0 | ... | -9] OUTPUT_FILE",
        version="%prog {0}".format(__version__)
    )

    parser.add_option('--prefix',
                      type='string',
                      dest='prefix',
                      default=None,
                      help="""prepend PREFIX to each filename in the archive;
                      defaults to OUTPUT_FILE name""")

    parser.add_option('-C',
                      type='string',
                      dest='base_repo',
                      default=None,
                      help="""use BASE_REPO as the main git repository to archive;
                      defaults to the current directory when empty""")

    parser.add_option('-v', '--verbose',
                      action='store_true',
                      dest='verbose',
                      help='enable verbose mode')

    parser.add_option('--no-export-ignore', '--no-exclude',
                      action='store_false',
                      dest='exclude',
                      default=True,
                      help="ignore the [-]export-ignore attribute in .gitattributes")

    parser.add_option('--force-submodules',
                      action='store_true',
                      dest='force_sub',
                      help='force `git submodule init && git submodule update` at each level before iterating submodules')

    parser.add_option('--include', '--extra',
                      action='append',
                      dest='extra',
                      default=[],
                      help="additional files to include in the archive")

    parser.add_option('--dry-run',
                      action='store_true',
                      dest='dry_run',
                      help="show files to be archived without actually creating the archive")

    for i in range(10):
        parser.add_option('-{0}'.format(i),
                          action='store_const',
                          const=i,
                          dest='compresslevel',
                          help=SUPPRESS_HELP)

    options, args = parser.parse_args(argv[1:])

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
        archiver = GitArchiver(options.prefix,
                               options.exclude,
                               options.force_sub,
                               options.extra,
                               path.abspath(options.base_repo) if options.base_repo is not None else None
                               )
        archiver.create(output_file_path, options.dry_run, compresslevel=options.compresslevel)
    except Exception as e:
        parser.exit(2, "{0}\n".format(e))

    return 0


if __name__ == '__main__':
    sys.exit(main())
