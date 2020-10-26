| |pypi| |homebrew|
| |implementations| |versions|
| |travis| |coverage|

.. |pypi| image:: https://img.shields.io/pypi/v/git-archive-all.svg
    :target: https://pypi.python.org/pypi/git-archive-all
    :alt: PyPI
.. |homebrew| image:: https://img.shields.io/homebrew/v/git-archive-all.svg
    :target: https://formulae.brew.sh/formula/git-archive-all
    :alt: Homebrew
.. |versions| image:: https://img.shields.io/pypi/pyversions/git-archive-all.svg
    :target: https://pypi.python.org/pypi/git-archive-all
    :alt: Supported Python versions
.. |implementations| image:: https://img.shields.io/pypi/implementation/git-archive-all.svg
    :target: https://pypi.python.org/pypi/git-archive-all
    :alt: Supported Python implementations
.. |travis| image:: https://travis-ci.org/Kentzo/git-archive-all.svg?branch=master
    :target: https://travis-ci.org/Kentzo/git-archive-all
    :alt: Travis
.. |coverage| image:: https://codecov.io/gh/Kentzo/git-archive-all/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/Kentzo/git-archive-all/branch/master
    :alt: Coverage

Archive a repository with all its submodules.

::

    git-archive-all [-v] [-C BASE_REPO] [--prefix PREFIX] [--no-export-ignore] [--force-submodules] [--include EXTRA1 ...] [--dry-run] [-0 | ... | -9] OUTPUT_FILE

    Options:

      --version             show program's version number and exit

      -h, --help            show this help message and exit

      -v, --verbose         enable verbose mode

      --prefix=PREFIX       prepend PREFIX to each filename in the archive;
                            defaults to OUTPUT_FILE name

      -C BASE_REPO          use BASE_REPO as the main git repository to archive;
                            defaults to the current directory when empty

      --no-export-ignore    ignore the [-]export-ignore attribute in .gitattributes

      --force-submodules    force `git submodule init && git submodule update` at
                            each level before iterating submodules

      --include=EXTRA       additional files to include in the archive

      --dry-run             show files to be archived without actually creating the archive

Questions & Answers
-------------------

| Q: How to exclude files?
| A: Mark paths you want to exclude in the .gitattributes file with the export-ignore attribute. Read more on `git-scm.com <https://git-scm.com/docs/gitattributes#_code_export_ignore_code>`_.

| Q: What about non-unicode filenames?
| A: All filenames that particular version of Python can represent and handle are supported. Extra [en|de]coding is done where appropriate.

Support
-------
If functional you need is missing but you're ready to pay for it, feel free to `contact me <mailto:kulakov.ilya@gmail.com?subject=git-archive-all>`_. If not, create an issue anyway, I'll take a look as soon as I can.
