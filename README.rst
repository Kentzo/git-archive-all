Archive repository with all its submodules.

::

    git-archive-all [-v] [--prefix PREFIX] [--no-exclude] [--force-submodules] [--extra] [--dry-run] OUTPUT_FILE

    Options:

      --version             Show program's version number and exit.

      -h, --help            Show this help message and exit.

      -v, --verbose         Enable verbose mode.

      --prefix=PREFIX       Prepend PREFIX to each filename in the archive. OUTPUT_FILE name is used by default to avoid tarbomb. You can set it to '' in order to explicitly request tarbomb.

      --no-exclude          Don't read .gitattributes files for patterns containing export-ignore attributes.

      --force-submodules    Force a `git submodule init && git submodule update` at each level before iterating submodules

      --extra               Include extra files to the resulting archive.

      --dry-run             Don't actually archive anything, just show what would be done.

Support
-------
If functional you need is missing but you're ready to pay for it, feel free to `contact me <mailto:kulakov.ilya@gmail.com?subject=git-archive-all>`_. If not, create an issue anyway, I'll take a look as soon as I can.
