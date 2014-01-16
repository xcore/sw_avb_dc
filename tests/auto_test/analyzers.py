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

def start_analyzer(rootDir, master, name, adapter_id, port):
  log_info("Starting %s" % name)
  target_name = name + '_target'
  target = process.XrunProcess(target_name, master, output_file=target_name + '_console.log')
  target_bin = os.path.join(rootDir, 'sw_audio_analyzer', 'app_audio_analyzer_avb', 'bin', 'audio_analyzer.xe')

  # Windows requires the absolute path of xrun
  exe_name = base.exe_name('xrun')
  xrun = base.file_abspath(exe_name)

  reactor.spawnProcess(target, xrun,
      [xrun, '--adapter-id', adapter_id, '--xscope-port', 'localhost:%d' % port, target_bin],
      env=os.environ)

  analyzer = process.Process(name, master, output_file=name + '_console.log')
  analyzer_bin = os.path.join(rootDir, 'sw_audio_analyzer', 'host_audio_analyzer', 'audio_analyzer')
  reactor.spawnProcess(analyzer, analyzer_bin, [analyzer_bin, '-p', '%d' % port], env=os.environ)

def start_analyzers(rootDir, args, master, analyzers):
  for analyzer in analyzers:
    name = analyzer['name']
    all_analyzers[name] = analyzer
    if args.user not in analyzer['users']:
      log_error("User '%s' not found in config file '%s' for analyzer '%s'" %
          (args.user, args.config, name))
      sys.exit(1)

    user_config = analyzer['users'][args.user]
    start_analyzer(rootDir, master, name, user_config['xrun_adapter_id'], analyzer['port'])

