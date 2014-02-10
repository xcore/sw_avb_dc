#!/usr/bin/python

import datetime
import dateutil.relativedelta
import os
import psutil
import re
import shutil
import subprocess
import sys
import time

test_folders = {
  os.path.join('configs', 'basics') : [1],
  os.path.join('configs', 'regressions') : [1],
  os.path.join('configs', 'random_1') : range(1,4),
  os.path.join('configs', 'random_2') : range(1,4),
  os.path.join('configs', 'random_3') : range(1,4),
  os.path.join('configs', 'random_4') : range(1,4),
}

def attr_to_string(obj, attr_name):
  if hasattr(obj, attr_name) and getattr(obj, attr_name) > 0:
    return "%d %s " % (getattr(obj, attr_name), attr_name)
  else:
    return ""

def print_run_time(start, end):
  """ Print the run time in an easily human-readable form. This means only non-zero units
      are shown.
  """
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

def kill_all(process_name):
  found = False
  for proc in psutil.process_iter():
    if proc.name == process_name and proc.pid not in active_pids:
      found = True
      print "Killing %s" % process_name
      proc.kill()
  return found

def run_test(folder, test, seed):
  while True:
    test_name = test[:-len('.json')]
    run = 1
    while True:
      logdir = os.path.join(folder, test_name, 'seed_%d' % seed, 'run_%d' % run)
      if not os.path.exists(logdir):
        break
      run += 1

    print "---- Running %s - seed %s run %d ----" % (os.path.join(folder, test_name), seed, run)
    os.makedirs(logdir)

    t_start = time.time()
    # This was done using subprocess.call, but that fails to work with the
    # tests using the Twisted framework
    os.system("python test.py --config four.json --logdir %s --summaryfile %s/summary.log --test %s  > %s/test.output 2>&1" %
        (logdir, logdir, os.path.join(folder, test), logdir))
    t_end = time.time()

    errors = 0
    needs_rerun = False
    with open(os.path.join(logdir, 'summary.log')) as f:
      for line in f.readlines():
        if re.match('^ERROR', line):
          errors += 1
        if re.match('^ERROR:.*xrun: The selected adapter is not connected', line):
          print "XTAG gone AWOL, giving up"
          sys.exit(1)
        if re.match('^ERROR:.*xrun:', line):
          needs_rerun = True

    print_run_time(t_start, t_end)
    if errors == 0:
        print "PASSED"
    else:
        print "ERROR: found %d errors" % errors

    # Give the xrun processes time to die off
    time.sleep(5)

    # Kill off any remaining processes if they exist
    found = True
    while found:
      found = kill_all('xgdb')
      if found:
        time.sleep(2)

    if needs_rerun:
      print "Found xrun error, re-running test"
    else:
      break

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
    run_folder(folder)

def get_current_pids(process_name):
  pids = set()
  for proc in psutil.process_iter():
    if proc.name == process_name:
      pids |= set([proc.pid])
  return pids

if __name__ == "__main__":
  active_pids = get_current_pids('xgdb')

  if len(sys.argv) == 1:
    run_all()
  else:
    for arg in sys.argv[1:]:
      if arg == '--clean':
        print "Cleaning out old runs"
        for f in os.listdir('configs'):
          folder = os.path.join('configs', f)
          if not os.path.isdir(folder):
            continue
          for g in os.listdir(folder):
            subfolder = os.path.join(folder, g)
            if os.path.isdir(subfolder):
              print "Removing %s" % subfolder
              shutil.rmtree(subfolder)

      elif os.path.isdir(os.path.join('configs', arg)):
        run_folder(os.path.join('configs', arg))
      elif os.path.exists(arg + '.json'):
        run_test(os.path.dirname(arg), os.path.basename(arg) + '.json', 1)
      elif os.path.isdir(arg):
        run_folder(arg)
      elif arg.endswith('.json'):
        run_test(os.path.dirname(arg), os.path.basename(arg), 1)
      else:
        print "ERROR: Can't find test '%s'" % arg

