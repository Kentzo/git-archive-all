import re
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

SCRIPT="git-archive-all"

# Parse the version from the file.
verstrline = open(SCRIPT, "rt").read()
VSRE = r"^__version__ = ['\"]([^'\"]*)['\"]"
mo = re.search(VSRE, verstrline, re.M)
if mo:
    verstr = mo.group(1)
else:
    raise RuntimeError("Unable to find version string in %s." % (SCRIPT,))

setup(
    name=SCRIPT,
    version=verstr,
    description='Like git-archive, but archives a git superproject and its submodules',
    author='Ilya Kulakov',
    url='https://github.com/Kentzo/git-archive-all',
    scripts = [SCRIPT],
)
