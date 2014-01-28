#!/usr/bin/python

import os
import subprocess
import re
import time

test_folders = {
  'basics' : [1],
  'regressions' : [1],
#  'random_1' : range(1,3),
#  'random_2' : range(1,3),
}

for folder in sorted(test_folders):
  seeds = test_folders[folder]
  for seed in seeds:
    tests = [x for x in os.listdir(os.path.join('configs', folder)) if re.match('.*\.json$', x)]
    tests.sort()

    top_dir = os.getcwd()

    for test in tests:
      test_name = test[:-len('.json')]
      print "---- Running %s/%s/%s ----" % (folder, test_name, seed)

      # This was done using subprocess.call, but that fails to work with the
      # tests using the Twisted framework
      logdir = os.path.join('configs', folder, test_name, 'seed_%d' % seed)
      if not os.path.exists(logdir):
        os.makedirs(logdir)
      os.system("python test.py --config four.json --logdir %s --summaryfile %s/summary.log --test %s  > %s/test.output 2>&1" %
          (logdir, logdir, os.path.join('configs', folder, test), logdir))

      errors = 0
      for file_name in os.listdir(logdir):
        with open(os.path.join(logdir, file_name)) as f:
          for line in f.readlines():
            if re.match("^ERROR", line):
              errors += 1

      if errors == 0:
          print "PASSED"
      else:
          print "ERROR: found %d errors" % errors

      # Give the xrun processes time to die off
      time.sleep(5)

