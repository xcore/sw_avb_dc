import os

from twisted.internet import reactor, defer

import xmos.test.process as process
import xmos.test.master as master
import xmos.test.base as base
from xmos.test.xmos_logging import log_error, log_warning, log_info, log_debug

all_generators = {}

def get_all():
  return all_generators

def get(name):
  return all_generators.get(name, None)

def get_port(name):
  return all_generators[name]['port']

def start_generator(combined_args):
  (name, adapter_id, target_bin, generator_bin, target_process, generator_process, port, args) = combined_args

  # Windows requires the absolute path of xrun
  exe_name = base.exe_name('xrun')
  xrun = base.file_abspath(exe_name)

  log_info("Starting generator %s" % name)

  reactor.spawnProcess(target_process, xrun,
      [xrun, '--adapter-id', adapter_id, '--xscope-port', 'localhost:%d' % port, target_bin],
      env=os.environ, path=args.logdir)

  reactor.spawnProcess(generator_process, generator_bin, [generator_bin, '-p', '%d' % port],
      env=os.environ, path=args.logdir)

def start_generator_with_delay(rootDir, master, delay, name, adapter_id, generator, args):
  # Need to ensure that the endpoint and process are created and registered before the
  # master task is started
  generator_process = process.Process(name, master, output_file=os.path.join(args.logdir, name + '_console.log'))

  target_name = name + '_target'
  target_process = process.XrunProcess(target_name, master,
      output_file=os.path.join(args.logdir, target_name + '_console.log'))

  target_bin = os.path.join(rootDir, 'sw_ethernet_traffic_gen', 'app_traffic_gen', 'bin', 'app_traffic_gen.xe')
  generator_bin = os.path.join(rootDir, 'sw_ethernet_traffic_gen', 'host_traffic_gen', 'traffic_gen_controller')

  log_info("Starting generator %s in %.3f" % (name, delay))
  d = defer.Deferred()
  reactor.callLater(delay, d.callback, (name, adapter_id, target_bin, generator_bin,
       target_process, generator_process, generator['port'], args))
  d.addCallback(start_generator)

def start(rootDir, args, master, generators, initial_delay):
  overrides = {}
  delay = initial_delay

  for generator in generators:
    name = generator['name']
    all_generators[name] = generator
    if args.user not in generator['users']:
      teset_error("User '%s' not found in config file '%s' for generator '%s'" %
          (args.user, args.config, name), critical=True)

    user_config = generator['users'][args.user]
    start_generator_with_delay(rootDir, master, delay, name, user_config['xrun_adapter_id'], generator, args)

    delay += 2.0

  # Return the delay used so that the next set of processes can be started after these ones
  # to minimize chances of interference
  return delay

