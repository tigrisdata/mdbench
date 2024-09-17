#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#
# Copyright (C) 2013-2022 Deutsches Elektronen-Synchroton,
# Member of the Helmholtz Association, (DESY), HAMBURG, GERMANY
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.
#

'''
Simple filesystem metadata operations benchmark

Usage: mdbench [options] <PATH>

  where options are:
    -f, --files <N>      : number of generated files per directory
    -d, --dirs  <N>      : number of generated directories to generate
    -s, --size  <N>      : size of generated files in B/K/M/G
    -n, --no-clean       : do not delete created files and directories
    --no-container       : do not create the 'mdbench.<name>.<pid>' directory
    -e, --extended-checks: runs extended tests as chmod and mv
    -c, --csv-file       : export csv file with the results
    -r, --random-data    : fill files with random data
    -h, --help           : help message

  and PATH points to the directory where tests should run. Current directory
  is used if not specified.

If number of generated directories is 0 then files are created within
the container directory ("mdbench.<name>.<pid>") or in PATH if
--no-container is specified.

The file size can be specified in human friendly format, e.g.: 1K, 256M. 4G.
'''

from __future__ import division
import sys
import os
import socket
import getopt
import string
from datetime import datetime
import math
import random

DIR = 'dir.'
FILE = 'file.'

gen_dir = lambda base, gen : '%s/%s%d' % (base, DIR, gen)
gen_file = lambda base, gen : '%s/%s%d' % (base, FILE, gen)

B = 1
K = 1024
M = K*K
G = K*M

DATA_SIZES = {'b':B, 'k': K, 'm': M, 'g': G}


class MovingAvg:
	"""
	Calculate moving average.
	"""

	def __init__(self):
		self._avg = 0.0
		self._count = 0
		self._sigma = 0.0
		self._total = 0

	def avg(self):
		"""
		Return the current value of average.
		"""
		return self._avg

	def std(self):
		"""
		Returns the the current value of standard deviation.
		"""
		return math.sqrt(self._sigma - self._avg**2)

	def update(self, v):
		"""
		Update average with new value.
		"""
		self._avg = (self._avg * self._count + v) / (self._count + 1)
		self._sigma = (self._sigma * self._count + v**2) / (self._count + 1)
		self._count += 1
		self._total += v

	def sum(self):
		"""
		Return the sum of all values.
		"""
		return self._total

	def count(self):
		"""
		Return the total number up updates.
		"""
		return self._count


dir_creates = MovingAvg()
file_creates = MovingAvg()
file_stats = MovingAvg()
dir_stats = MovingAvg()
chmod_stats = MovingAvg()
mv_stats = MovingAvg()
dir_removes = MovingAvg()
file_removes = MovingAvg()

def get_size(s):

	last_symbol = s[-1:].lower()
	if last_symbol in string.digits:
		return int(s)

	if last_symbol not in DATA_SIZES:
		raise Exception('Invalid format: %s' % s)

	return int(s[:-1])*DATA_SIZES[last_symbol]

def make_dirs(root, count):
	for i in range(count):
		mkdir( gen_dir(root, i) )

	fsync(root, dir_creates)

def make_files(root, dir_count, file_count, size = 0, random_data = False):

	for j in range(file_count):
		if dir_count > 0:
			for i in range(dir_count):
				mkfile(gen_file( gen_dir(root, i), j ), size, 1024, random_data = random_data)
		else:
			mkfile(gen_file(root, j), size, 1024, random_data = random_data)

	fsync(root, file_creates)

def del_files(root, dir_count, file_count):
	for j in range(file_count):
		if dir_count > 0:
			for i in range(dir_count):
				rmfile(gen_file( gen_dir(root, i), j ))
		else:
			rmfile(gen_file(root, j))

	fsync(root, file_removes)

def del_dirs(root, count):
	for i in range(count):
		rmdir( gen_dir(root, i) )

	fsync(root, dir_removes)

def stat_dirs(root, count):
	for i in range(count):
		statdir( gen_dir(root, i) )

	fsync(root, dir_stats)

def stat_files(root, dir_count, file_count):
	for j in range(file_count):
		if dir_count > 0:
			for i in range(dir_count):
				statfile(gen_file( gen_dir(root, i), j ))
		else:
			statfile(gen_file(root, j))

	fsync(root, file_stats)

def chmod_files(root, dir_count, file_count):
	for j in range(file_count):
		if dir_count > 0:
			for i in range(dir_count):
				chmodfile(gen_file( gen_dir(root, i), j ))
		else:
			chmodfile(gen_file(root, j))

	fsync(root, chmod_stats)

def mv_files(root, dir_count, file_count):
	for j in range(file_count):
		if dir_count > 0:
			for i in range(dir_count):
				mvfile(gen_file( gen_dir(root, i), j ))
		else:
			mvfile(gen_file(root, j))

	fsync(root, mv_stats)


def rmfile(f):
	start = datetime.now()
	os.remove(f)
	end = datetime.now()
	file_removes.update(total_millis(end - start))

def rmdir(d):
	start = datetime.now()
	os.rmdir(d)
	end = datetime.now()
	dir_removes.update(total_millis(end - start))

def mkdir(d):
	start = datetime.now()
	os.mkdir(d)
	end = datetime.now()
	dir_creates.update(total_millis(end - start))

def chmodfile(f):
	start = datetime.now()
	os.chmod(f, 777)
	end = datetime.now()
	chmod_stats.update(total_millis(end - start))

def mvfile(f):
	start = datetime.now()
	os.rename(f, "%s_moved" % f)
	end = datetime.now()
	os.rename("%s_moved" % f, f)
	mv_stats.update(total_millis(end - start))

def statfile(f):
	start = datetime.now()
	os.stat(f)
	end = datetime.now()
	file_stats.update(total_millis(end - start))

def statdir(f):
	start = datetime.now()
	os.stat(f)
	end = datetime.now()
	dir_stats.update(total_millis(end - start))

def mkfile(fname, size, chunk = 65536, sync = False, random_data = False) :

	off = 0
	remaining = size

	start = datetime.now()
	with open(fname, "wb") as f:

		while remaining > 0:
			wsize = min(chunk, remaining)
			data = random.randbytes(wsize) if random_data else bytearray(wsize)
			f.write(data)
			off += wsize
			remaining -= wsize

		if sync:
			f.flush()
			os.fsync(f.fileno())

	end = datetime.now()
	file_creates.update(total_millis(end - start))

# issues a directory fsync after every test to flush changes to object storage
def fsync(root, stat):
	start = datetime.now()
	os.fsync(os.open(root, os.O_RDONLY))
	end = datetime.now()
	stat.update(total_millis(end - start))

def total_micros(td):
	return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6)

def total_millis(td):
	return total_micros(td)/1000

def report(title, counter, csvFile = None):
	print('{:16}: {:6.2f}ms ±{:=6.2f}ms, {:6.2f} op/s' \
		.format(title, counter.avg(), counter.std(), counter.count()/counter.sum()*10**3))
	if csvFile is not None:
		with open(csvFile, "a") as f:
			txt = '%s,%.2f,%.2f,%.2f\n' % (title, counter.avg(), counter.std(), counter.count()/counter.sum()*10**3)
			f.write(txt)
DIR_COUNT = 1000
FILE_COUNT = 10
FILE_SIZE = 0

def usage():
	print(__doc__)
	sys.exit(1)

def main():

	dir_count = DIR_COUNT
	file_count = FILE_COUNT
	file_size = FILE_SIZE
	cleanup = True
	createContainer = True
	extendedChecks = False
	csvFile = None
	random_data = False

	try:
		options, remainder = getopt.gnu_getopt(sys.argv[1:], 'f:d:s:c:nher', \
					 ['files=','dirs=','size=','no-clean','no-container','extended-checks','csv-file=', "random-date",'help'])
	except getopt.GetoptError as err:
		print(str(err))
		usage()

	for opt, arg in options:
		if opt in ('-f', '--files'):
			file_count = int(arg)
		elif opt in ('-d', '--dirs'):
			dir_count = int(arg)
		elif opt in ('-s', '--size'):
			file_size = get_size(arg)
		elif opt in ('-n', '--no-clean'):
			cleanup = False
		elif opt == '--no-container':
			createContainer = False
		elif opt in ('-e', '--extended-checks'):
			extendedChecks = True
		elif opt in ('-c', '--csv-file'):
			csvFile = arg
		elif opt in ('-r', '--random-data'):
			random_data = True
		elif opt in ('-h', '--help'):
			usage()

	if len(remainder) != 1 :
		usage()

	path = remainder[0]

	root = '%s/mdbench.%s.%d' % (path, socket.gethostname(), os.getpid()) if createContainer else path

	if createContainer:
		os.mkdir(root)
	if csvFile:
		# Create empty file
		with open(csvFile, 'w') as f:
			f.write("title,average,std,IOPS\n")


	t0 = datetime.now()
	print('{:16}: {}'.format( "Starting at: ", t0))
	print()

	make_dirs(root, dir_count)
	report("dir creates", dir_creates, csvFile)
	make_files(root, dir_count, file_count , file_size, random_data)
	report("file creates", file_creates, csvFile)
	stat_files(root, dir_count, file_count)
	report("file stats", file_stats, csvFile)
	if extendedChecks:
		chmod_files(root, dir_count, file_count)
		report("chmod stats", chmod_stats, csvFile)
		mv_files(root, dir_count, file_count)
		report("mv stats", mv_stats, csvFile)

	stat_dirs(root, dir_count)
	report("dir stats", dir_stats, csvFile)

	if cleanup:
		del_files(root, dir_count, file_count )
		report("file removes", file_removes, csvFile)
		del_dirs(root, dir_count )
		report("dir removes", dir_removes, csvFile)
		if createContainer:
			os.rmdir(root)

	t1 = datetime.now()
	td = t1 - t0
	print()
	print('{:16}: {}, runtime: {}'.format( "Finished at: ", t1, td))

if __name__ == '__main__':
	main()
