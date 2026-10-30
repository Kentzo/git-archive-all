"""
Usage: python release-notes.py TAG OUTPUT

Fails if TAG doesn't match __version__ or CHANGES.rst has no changes for it.
"""
import re
import sys
from pathlib import Path

import pypandoc


def main(tag, output):
    script = Path('git_archive_all.py').read_text(encoding='utf-8')
    match = re.search(r"^__version__ = (['\"])(.+?)\1", script, re.M)
    if not match:
        sys.exit("::error::No __version__ in git_archive_all.py")

    version = match.group(2)
    if tag != version:
        sys.exit(f"::error::Requested version ({tag}) doesn't match __version__ ({version})")

    changes = Path('CHANGES.rst').read_text(encoding='utf-8')
    # -> ['CHANGES', ver1, body1, ver2, body2, ...]
    parts = re.split(r"^(\S+) \(\d{4}-\d{2}-\d{2}\)\n-+\n", changes, flags=re.M)
    # -> {ver1: body1, ver2: body2, ...}
    sections = dict(zip(parts[1::2], parts[2::2]))
    rst = sections.get(version, '').strip()
    if not rst:
        sys.exit(f"::error::No changes for {version} in CHANGES.rst")

    md = pypandoc.convert_text(rst, 'gfm', format='rst', extra_args=['--wrap=none'])
    md = re.sub(r'\\#(?=\d)', '#', md).strip()  # let GitHub autolink issue references
    Path(output).write_text(md, encoding='utf-8')


if __name__ == '__main__':
    main(*sys.argv[1:])
