import os

from twisted.internet import reactor, defer

import xmos.test.process as process
import xmos.test.master as master
import xmos.test.base as base
from xmos.test.xmos_logging import log_error, log_warning, log_info, log_debug

all_analyzers = {}

def get_all():
  return all_analyzers

def get(name):
  return all_analyzers.get(name, None)

def get_port(name):
  return all_analyzers[name]['port']

def siggen_frequency(talker_ep, i):
  """ Extract the frequency for a talker of a given channel offset
  """
  siggen = talker_ep["analyzer"]
  siggen_offset = talker_ep["analyzer_offset"]
  base = siggen["base"]
  index = "%d" % (base + i + siggen_offset)
  return siggen["frequencies"][index]

def startAnalyzer(combined_args):
  (name, adapter_id, target_bin, analyzer_bin, target_process, analyzer_process, port, args) = combined_args

  # Windows requires the absolute path of xrun
  exe_name = base.exe_name('xrun')
  xrun = base.file_abspath(exe_name)

  log_info("Starting analyzer %s" % name)

  reactor.spawnProcess(target_process, xrun,
      [xrun, '--adapter-id', adapter_id, '--xscope-port', 'localhost:%d' % port, target_bin],
      env=os.environ, path=args.logdir)

  reactor.spawnProcess(analyzer_process, analyzer_bin, [analyzer_bin, '-p', '%d' % port],
      env=os.environ, path=args.logdir)

def startAnalyzerWithDelay(rootDir, master, delay, name, adapter_id, analyzer, args):
  # Need to ensure that the endpoint and process are created and registered before the
  # master task is started
  analyzer_process = process.Process(name, master,
      output_file=os.path.join(args.logdir, name + '_console.log'))

  target_name = name + '_target'
  target_process = process.XrunProcess(target_name, master,
      output_file=os.path.join(args.logdir, target_name + '_console.log'))

  ep_bin = os.path.join(rootDir, 'sw_avb_dc', 'app_daisy_chain', 'bin', 'app_daisy_chain.xe')
  if analyzer['type'] == 'audio':
    target_bin = os.path.join(rootDir, 'sw_audio_analyzer', 'app_audio_analyzer_avb', 'bin', 'audio_analyzer.xe')
    analyzer_bin = os.path.join(rootDir, 'sw_audio_analyzer', 'host_audio_analyzer', 'audio_analyzer')
  elif analyzer['type'] == 'qav':
    target_bin = os.path.join(rootDir, 'sw_ethernet_tap', 'app_avb_tester', 'bin', 'app_avb_tester.xe')
    analyzer_bin = os.path.join(rootDir, 'sw_ethernet_tap', 'host_avb_tester', 'avb_tester')
  else:
    test_error("%s: unknown type '%s'" % (name, analyzer['type']), critical=True)

  log_info("Starting %s analyzer %s in %.3f" % (analyzer['type'], name, delay))
  d = defer.Deferred()
  reactor.callLater(delay, d.callback, (name, adapter_id, target_bin, analyzer_bin,
       target_process, analyzer_process, analyzer['port'], args))
  d.addCallback(startAnalyzer)

def start(rootDir, args, master, analyzers, test_config, initial_delay):
  overrides = {}
  delay = initial_delay

  # Read any test file specified types
  for name,new_type in test_config.get('types', {}).iteritems():
    overrides[name] = new_type

  # Read any command-line specified types
  for override in args.types:
    if '=' not in override:
      test_error("Type override should be of the form '<name>=<type>', found '%s'" % override,
          critical=True)
    name,new_type = override.split('=')
    overrides[name] = new_type

  for analyzer in analyzers:
    name = analyzer['name']
    all_analyzers[name] = analyzer
    if args.user not in analyzer['users']:
      teset_error("User '%s' not found in config file '%s' for analyzer '%s'" %
          (args.user, args.config, name), critical=True)

    if name in overrides:
      analyzer['type'] = overrides[name]

    user_config = analyzer['users'][args.user]
    startAnalyzerWithDelay(rootDir, master, delay, name, user_config['xrun_adapter_id'], analyzer, args)

    delay += 1.0

  # Return the delay used so that the next set of processes can be started after these ones
  # to minimize chances of interference
  return delay

