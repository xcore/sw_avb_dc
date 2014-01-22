import os

from twisted.internet import reactor

import xmos.test.process as process
import xmos.test.master as master
import xmos.test.base as base
from xmos.test.xmos_logging import log_error, log_warning, log_info, log_debug

all_analyzers = {}

def get_all_analyzers():
  return all_analyzers

def analyzer_port(name):
  return all_analyzers[name]['port']

def siggen_frequency(talker_ep, i):
  """ Extract the frequency for a talker of a given channel offset
  """
  siggen = talker_ep["analyzer"]
  siggen_offset = talker_ep["analyzer_offset"]
  base = siggen["base"]
  index = "%d" % (base + i + siggen_offset)
  return siggen["frequencies"][index]

def start_analyzer(rootDir, master, name, adapter_id, port, analyzer_type, args):
  log_info("Starting %s analyzer %s" % (analyzer_type, name))
  target_name = name + '_target'
  target = process.XrunProcess(target_name, master,
      output_file=os.path.join(args.logdir, target_name + '_console.log'))

  if analyzer_type == 'audio':
    target_bin = os.path.join(rootDir, 'sw_audio_analyzer', 'app_audio_analyzer_avb', 'bin', 'audio_analyzer.xe')
    analyzer_bin = os.path.join(rootDir, 'sw_audio_analyzer', 'host_audio_analyzer', 'audio_analyzer')
  elif analyzer_type == 'qav':
    target_bin = os.path.join(rootDir, 'sw_ethernet_tap', 'app_avb_tester', 'bin', 'app_avb_tester.xe')
    analyzer_bin = os.path.join(rootDir, 'sw_ethernet_tap', 'host_avb_tester', 'avb_tester')
  else:
    test_error("%s: unknown type '%s'" % (name, analyzer_type), critical=True)

  # Windows requires the absolute path of xrun
  exe_name = base.exe_name('xrun')
  xrun = base.file_abspath(exe_name)

  reactor.spawnProcess(target, xrun,
      [xrun, '--adapter-id', adapter_id, '--xscope-port', 'localhost:%d' % port, target_bin],
      env=os.environ, path=args.logdir)

  analyzer = process.Process(name, master,
      output_file=os.path.join(args.logdir, name + '_console.log'))
  reactor.spawnProcess(analyzer, analyzer_bin, [analyzer_bin, '-p', '%d' % port],
      env=os.environ, path=args.logdir)

def start_analyzers(rootDir, args, master, analyzers):
  overrides = {}
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
    start_analyzer(rootDir, master, name, user_config['xrun_adapter_id'],
        analyzer['port'], analyzer['type'], args)

