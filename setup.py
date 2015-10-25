import re
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


# Parse the version from the file.
verstrline = open('git_archive_all.py', "rt").read()
VSRE = r"^__version__ = ['\"]([^'\"]*)['\"]"
mo = re.search(VSRE, verstrline, re.M)
if mo:
    verstr = mo.group(1)
else:
    raise RuntimeError("Unable to find version string in %s." % (SCRIPT,))

setup(
    name='git-archive-all',
    version=verstr,
    description='Archive git repository with its submodules.',
    author='Ilya Kulakov',
    author_email="kulakov.ilya@gmail.com",
    url='https://github.com/Kentzo/git-archive-all',
    py_modules=['git_archive_all'],
    entry_points="""
    [console_scripts]
    git-archive-all=git_archive_all:main
    """,
    license="MIT License",
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Version Control',
        'Topic :: System :: Archiving'
    ]
)
