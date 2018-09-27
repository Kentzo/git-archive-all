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
from os import extsep, path, readlink
from subprocess import CalledProcessError, Popen, PIPE
import sys
import re

__version__ = "1.18.3"


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

    def __init__(self, prefix='', exclude=True, force_sub=False, extra=None, main_repo_abspath=None):
        """
        @param prefix: Prefix used to prepend all paths in the resulting archive.
            Extra file paths are only prefixed if they are not relative.
            E.g. if prefix is 'foo' and extra is ['bar', '/baz'] the resulting archive will look like this:
            /
              baz
              foo/
                bar
        @type prefix: str

        @param exclude: Determines whether archiver should follow rules specified in .gitattributes files.
        @type exclude: bool

        @param force_sub: Determines whether submodules are initialized and updated before archiving.
        @type force_sub: bool

        @param extra: List of extra paths to include in the resulting archive.
        @type extra: list

        @param main_repo_abspath: Absolute path to the main repository (or one of subdirectories).
            If given path is path to a subdirectory (but not a submodule directory!) it will be replaced
            with abspath to top-level directory of the repository.
            If None, current cwd is used.
        @type main_repo_abspath: str
        """
        if extra is None:
            extra = []

        if main_repo_abspath is None:
            main_repo_abspath = path.abspath('')
        elif not path.isabs(main_repo_abspath):
            raise ValueError("main_repo_abspath must be an absolute path")

        try:
            main_repo_abspath = path.abspath(self.run_git_shell('git rev-parse --show-toplevel', main_repo_abspath).rstrip())
        except CalledProcessError:
            raise ValueError("{0} is not part of a git repository".format(main_repo_abspath))

        self.prefix = prefix
        self.exclude = exclude
        self.extra = extra
        self.force_sub = force_sub
        self.main_repo_abspath = main_repo_abspath

    def create(self, output_path, dry_run=False, output_format=None):
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
            self.LOG.debug("Output format is not explicitly set, determined format is {0}.".format(output_format))

        if not dry_run:
            if output_format in self.ZIPFILE_FORMATS:
                from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

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
                archive = tarfile.open(path.abspath(output_path), mode)

                def add_file(file_path, arcname):
                    archive.add(file_path, arcname)
            else:
                raise ValueError("unknown format: {0}".format(output_format))

            def archiver(file_path, arcname):
                self.LOG.debug("{0} => {1}".format(file_path, arcname))
                add_file(file_path, arcname)
        else:
            archive = None

            def archiver(file_path, arcname):
                self.LOG.info("{0} => {1}".format(file_path, arcname))

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
        out = self.run_git_shell(
            'git check-attr -z export-ignore -- %s' % quote(repo_file_path),
            cwd=repo_abspath
        ).split('\0')

        try:
            return out[2] == 'set'
        except IndexError:
            return False

    def archive_all_files(self, archiver):
        """
        Archive all files using archiver.

        @param archiver: Callable that accepts 2 arguments:
            abspath to file on the system and relative path within archive.
        @type archiver: Callable
        """
        for file_path in self.extra:
            archiver(path.abspath(file_path), path.join(self.prefix, file_path))

        for file_path in self.walk_git_files():
            archiver(path.join(self.main_repo_abspath, file_path), path.join(self.prefix, file_path))

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
        repo_file_paths = self.run_git_shell(
            'git ls-files -z --cached --full-name --no-empty-directory',
            repo_abspath
        ).split('\0')[:-1]

        for repo_file_path in repo_file_paths:
            repo_file_abspath = path.join(repo_abspath, repo_file_path)  # absolute file path
            main_repo_file_path = path.join(repo_path, repo_file_path)  # file path relative to the main repo

            # Only list symlinks and files.
            if not path.islink(repo_file_abspath) and path.isdir(repo_file_abspath):
                continue

            if self.is_file_excluded(repo_abspath, repo_file_path):
                continue

            yield main_repo_file_path

        if self.force_sub:
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
                    main_repo_submodule_path = path.join(repo_path, repo_submodule_path)  # relative to main_repo_abspath

                    if self.is_file_excluded(repo_abspath, repo_submodule_path):
                        continue

                    for main_repo_submodule_file_path in self.walk_git_files(main_repo_submodule_path):
                        repo_submodule_file_path = main_repo_submodule_file_path.replace(repo_path, "", 1).strip("/")
                        if self.is_file_excluded(repo_abspath, repo_submodule_file_path):
                            continue

                        yield main_repo_submodule_file_path
        except IOError:
            pass

    @staticmethod
    def run_git_shell(cmd, cwd=None):
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
        output = output.decode('unicode_escape').encode('raw_unicode_escape').decode('utf-8')

        if p.returncode:
            if sys.version_info > (2, 6):
                raise CalledProcessError(returncode=p.returncode, cmd=cmd, output=output)
            else:
                raise CalledProcessError(returncode=p.returncode, cmd=cmd)

        return output


def main():
    from optparse import OptionParser

    parser = OptionParser(
        usage="usage: %prog [-v] [--prefix PREFIX] [--no-exclude] [--force-submodules]"
              " [--extra EXTRA1 [EXTRA2]] [--dry-run] OUTPUT_FILE",
        version="%prog {0}".format(__version__)
    )

    parser.add_option('--prefix',
                      type='string',
                      dest='prefix',
                      default=None,
                      help="""prepend PREFIX to each filename in the archive.
                          OUTPUT_FILE name is used by default to avoid tarbomb.
                          You can set it to '' in order to explicitly request tarbomb""")

    parser.add_option('-v', '--verbose',
                      action='store_true',
                      dest='verbose',
                      help='enable verbose mode')

    parser.add_option('--no-exclude',
                      action='store_false',
                      dest='exclude',
                      default=True,
                      help="don't read .gitattributes files for patterns containing export-ignore attrib")

    parser.add_option('--force-submodules',
                      action='store_true',
                      dest='force_sub',
                      help='force a git submodule init && git submodule update at each level before iterating submodules')

    parser.add_option('--extra',
                      action='append',
                      dest='extra',
                      default=[],
                      help="any additional files to include in the archive")

    parser.add_option('--dry-run',
                      action='store_true',
                      dest='dry_run',
                      help="don't actually archive anything, just show what would be done")

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
        archiver = GitArchiver(options.prefix,
                               options.exclude,
                               options.force_sub,
                               options.extra)
        archiver.create(output_file_path, options.dry_run)
    except Exception as e:
        parser.exit(2, "{0}\n".format(e))

    sys.exit(0)


if __name__ == '__main__':
    main()
