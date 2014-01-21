import sys
import random
import time
import os

from twisted.internet import reactor, defer

import xmos.test.process as process
import xmos.test.master as master
import xmos.test.base as base
from xmos.test.xmos_logging import log_error, log_warning, log_info, log_debug

from analyzers import get_all_analyzers

all_endpoints = {}

def get_all_endpoints():
  return all_endpoints

def get_path_endpoints(path):
  ''' Given a path, find any endpoints between the start and end endpoints.
  '''

  # There should always be more than 2 elements on the path since there are the node + the ports.
  assert len(path) > 2

  nodes = []
  for node in path[1:-1]:
    if entity_by_name(node):
      nodes.append(node)
  return nodes

def entity_by_name(name):
  return all_endpoints.get(name, None)

def startXrun(combined_args):
  (name, process, adapter_id, bin, args) = combined_args

  # Windows requires the absolute path of xrun
  exe_name = base.exe_name('xrun')
  xrun = base.file_abspath(exe_name)

  log_info("Starting %s (%s)" % (name, ' '.join(['--adapter-id', adapter_id, '--xscope', bin])))
  reactor.spawnProcess(process, xrun, [xrun, '--adapter-id', adapter_id, '--xscope', bin],
      env=os.environ, path=args.logdir)

def startXrunWithDelay(rootDir, master, delay, name, adapter_id, args):
  # Need to ensure that the endpoint and process are created and registered before the
  # master task is started
  ep = process.XrunProcess(name, master,
      output_file=os.path.join(args.logdir, name + '_console.log'))
  ep_bin = os.path.join(rootDir, 'sw_avb_dc', 'app_daisy_chain', 'bin', 'app_daisy_chain.xe')

  log_info("Starting %s in %.3f" % (name, delay))
  d = defer.Deferred()
  reactor.callLater(delay, d.callback, (name, ep, adapter_id, ep_bin, args))
  d.addCallback(startXrun)

def start_endpoints(rootDir, args, endpoints, master, analyzers):
  delay = random.uniform(0, 10)
  for ep in endpoints:
    name = ep['name']
    all_endpoints[name] = ep

    if args.user not in ep['users']:
      log_error("User '%s' not found in config file '%s' for endpoint '%s'" %
          (args.user, args.config, name))
      sys.exit(1)

    user_config = ep['users'][args.user]
    startXrunWithDelay(rootDir, master, delay, ep['name'], user_config['xrun_adapter_id'], args)
    delay += random.uniform(0, 10)

  # Connect up the analyzers to then endpoints
  for ep in endpoints:
    analyzer_name = ep['analyzer']
    if analyzer_name not in get_all_analyzers():
      log_error("Invalid analyzer '%s' for endpoint '%s'" % (analyzer_name, ep['name']))
    ep['analyzer'] = get_all_analyzers()[analyzer_name]

