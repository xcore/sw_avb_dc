#!/usr/bin/python

import os
import re
import subprocess
import sys
import time

import datetime
import dateutil.relativedelta

def attr_to_string(obj, attr_name):
  if hasattr(obj, attr_name) and getattr(obj, attr_name) > 0:
    return "%d %s " % (getattr(obj, attr_name), attr_name)
  else:
    return ""

def print_run_time(start, end):
  dt1 = datetime.datetime.fromtimestamp(start)
  dt2 = datetime.datetime.fromtimestamp(end)
  rd = dateutil.relativedelta.relativedelta (dt2, dt1)

  print "%s%s%s%s%s%s" % (
    attr_to_string(rd, 'years'),
    attr_to_string(rd, 'months'),
    attr_to_string(rd, 'days'),
    attr_to_string(rd, 'hours'),
    attr_to_string(rd, 'minutes'),
    attr_to_string(rd, 'seconds'))

test_folders = {
  'basics' : [1],
  'regressions' : [1],
  'random_1' : range(1,3),
  'random_2' : range(1,3),
  'random_3' : range(1,3),
}

def run_test(folder, test, seed):
  test_name = test[:-len('.json')]
  print "---- Running %s : %s - seed %s ----" % (folder, test_name, seed)

  # This was done using subprocess.call, but that fails to work with the
  # tests using the Twisted framework
  logdir = os.path.join(folder, test_name, 'seed_%d' % seed)
  if not os.path.exists(logdir):
    os.makedirs(logdir)

  t_start = time.time()
  os.system("python test.py --config four.json --logdir %s --summaryfile %s/summary.log --test %s  > %s/test.output 2>&1" %
      (logdir, logdir, os.path.join(folder, test), logdir))
  t_end = time.time()

  errors = 0
  for file_name in os.listdir(logdir):
    with open(os.path.join(logdir, file_name)) as f:
      for line in f.readlines():
        if re.match("^ERROR", line):
          errors += 1

  print_run_time(t_start, t_end)
  if errors == 0:
      print "PASSED"
  else:
      print "ERROR: found %d errors" % errors

  # Give the xrun processes time to die off
  time.sleep(5)

def run_folder(folder):
  seeds = test_folders.get(folder, [1])
  for seed in seeds:
    tests = [x for x in os.listdir(folder) if re.match('.*\.json$', x)]
    tests.sort()

    top_dir = os.getcwd()

    for test in tests:
      run_test(folder, test, seed)

def run_all():
  for folder in sorted(test_folders):
    run_folder(os.path.join('configs', folder))

if len(sys.argv) == 1:
  run_all()
else:
  for arg in sys.argv[1:]:
    if os.path.isdir(os.path.join('configs', arg)):
      run_folder(os.path.join('configs', arg))
    elif os.path.exists(arg + '.json'):
      run_test(os.path.dirname(arg), os.path.basename(arg) + '.json', 1)
    elif os.path.isdir(arg):
      run_folder(arg)
    elif arg.endswith('.json'):
      run_test(os.path.dirname(arg), os.path.basename(arg), 1)
    else:
      print "ERROR: Can't find test '%s'" % arg

