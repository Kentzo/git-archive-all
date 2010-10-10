#! /usr/bin/python

from os import path, chdir
from subprocess import Popen, PIPE
from optparse import OptionParser
from sys import argv, stdout

git_repositary_path = path.abspath('')
git_repositary_name = path.basename(git_repositary_path)

parser = OptionParser(usage="usage: %prog --output OUTPUT_FILE [--format FORMAT] [-v] [--prefix PREFIX]", version="%prog 1.0")
parser.add_option('--format', type='choice', dest='format', choices=['zip','tar'], default='tar', help="format of the resulting archive: tar or zip. The default output format is %default")
parser.add_option('--prefix', type='string', dest='prefix', default='', help="prepend PREFIX to each filename in the archive")
parser.add_option('-o', '--output', type='string', dest='output_file', default='', help='output file')
parser.add_option('-v', '--verbose', action='store_true', dest='verbose', help='enabel verbose mode')

(options, args) = parser.parse_args()

if options.output_file == '':
   parser.error('You must specify output file')
elif path.isdir(options.output_file):
   parser.error('You cannot use directory as output')

#print options.output_file

def git_files(baselevel=''):
   for filepath in Popen('git ls-files --cached --full-name --no-empty-directory', shell=True, stdout=PIPE).stdout.read().splitlines():
       if not filepath.startswith('.git') and not path.isdir(filepath):
          # baselevel is needed to tell the arhiver where it have to extract file
          yield filepath, path.join(baselevel, filepath)
   # get paths for every submodule
   for submodule in Popen("git submodule --quiet foreach --recursive 'pwd'", shell=True, stdout=PIPE).stdout.read().splitlines():
       chdir(submodule)
       # in order to get output path we need to exclude repository path from the submodule path
       submodule = submodule[len(git_repositary_path)+1:]
       # recursion allows us to process repositories with more than one level of submodules
       for git_file in git_files(submodule):
           yield git_file

if options.format == 'zip':
    from zipfile import ZipFile, ZIP_DEFLATED
    output_archive = ZipFile(path.abspath(options.output_file), 'w')
    for name, arcname in git_files():
       if options.verbose: print 'Compressing ' + arcname + '...'
       output_archive.write(name, options.prefix + arcname, ZIP_DEFLATED)
elif options.format == 'tar':
    from tarfile import TarFile
    output_archive = TarFile(path.abspath(options.output_file), 'w')
    for name, arcname in git_files():
       if options.verbose: print 'Compressing ' + arcname + '...'
       output_archive.add(name, options.prefix + arcname)
