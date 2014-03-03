import getpass
import json
import os
import random
import re
import sys
import time

from twisted.internet import reactor, defer
from twisted.internet.defer import inlineCallbacks

from path_setup import *

from xmos.test.process import Process
import xmos.test.master
import xmos.test.base as base
import xmos.test.xmos_logging as xmos_logging
import xmos.test.generator as generator
from xmos.test.base import AllOf, OneOf, NoneOf, Sequence, Expected, getActiveProcesses
from xmos.test.xmos_logging import log_error, log_warning, log_info, log_debug

from actions import *
import sequences
import endpoints
import generators
import analyzers
import graph

class ControllerProcess(Process):
  def __init__(self, name, master, controllerType='python', **kwargs):
    Process.__init__(self, name, master, **kwargs)
    self.controllerType = controllerType
    self.discover_active = False
    self.entities = {}

  def outReceived(self, data):
    if self.controllerType == 'python':
      m = re.search("Found \d+ entities", data)
      if m:
        self.entities.clear()
        lines = data.split()
        for line in lines:
          if line.startswith("0x"):
            try:
              self.entities[int(line, 16)] = 1
            except Exception, e:
              pass
    else:
      if not self.discover_active:
        m = re.search("End Station  |  Name                  |  Entity GUID         |  MAC", data)
        if m:
          self.discover_active = True
        self.entities.clear()

      if self.discover_active:
        lines = data.split('\n')
        for line in lines:
          if line.startswith('C - End Station'):
            self.discover_active = False
            break

          if line.startswith('C '):
            try:
              guid = line.split('|')[2].strip()
              self.entities[int(guid, 16)] = 1
            except Exception, e:
              pass

    Process.outReceived(self, data)


# Assign the xrun variable used to start processes
exe_name = base.exe_name('xrun')
xrun = base.file_abspath(exe_name) # Windows requires the absolute path of xrun

def print_comment(test_step):
  comment = getattr(test_step, 'comment', None)
  if comment is not None:
    log_info("\n>> %s\n" % comment)

def configure_analyzers():
  """ Ensure the analyzers have started properly and then configure their channel
      frequencies as specified in the test configuration file
  """
  analyzer_startup = [Expected(a, "connected to .*: %d" % analyzers.get_port(a), 15, critical=True)
                        for a in analyzers.get_all()]
  yield master.expect(AllOf(analyzer_startup))

  for (name,analyzer) in analyzers.get_all().iteritems():
    if analyzer['type'] != 'audio':
      continue

    log_info("Configure %s" % name)

    # Disable all channels
    master.sendLine(name, "d a")
    yield master.expect(Expected(name, "Channel 0: disabled", 15))

    # Set the base channel index
    analyzer_base = analyzer['base']
    master.sendLine(name, "b %d" % analyzer_base)

    # Configure all channels
    for (chan_id,freq) in analyzer['frequencies'].iteritems():
      # Need to convert unicode to string before sending as a command
      chan = int(chan_id)
      master.sendLine(name, "c %d %d" % (chan, freq))

      # The channel ID is offset from the base in the generating message
      yield master.expect(
          Expected(name, "Generating sine table for chan %d" % (chan - analyzer_base), 15))

    master.sendLine(name, "e a")
    channel_enables = [Expected(name, "Channel %d: enabled" % (int(c) - analyzer_base), 15)
                        for c in analyzer['frequencies'].keys()]
    yield master.expect(AllOf(channel_enables))

def configure_generators():
  """ Ensure the generators have started properly
  """
  generator_startup = [Expected(a, "connected to .*: %d" % generators.get_port(a), 15, critical=True)
                        for a in generators.get_all()]
  yield master.expect(AllOf(generator_startup))

  for (name,generator) in generators.get_all().iteritems():
    log_info("Configure %s" % name)

    # Configure a random mix of unicast, multicast and broadcast traffic
    master.sendLine(name, "c u 1 64 1500")
    master.sendLine(name, "c m 1 64 1500")
    master.sendLine(name, "c b 1 64 1500")

    # Apply the specified config
    master.sendLine(name, "e")

    # Apply the specified config
    master.sendLine(name, "p")
    yield master.expect(Expected(name, "Current configuration", 5))

def ptp_startup_two_port(e, grandmaster, user):
  """ Determine the PTP sequence for the node. If it is not the grandmaster
      it should go to slave and lock
  """
  slave_seq = []
  if grandmaster and (endpoints.get_avb_id(user, e) != endpoints.get_avb_id(user, grandmaster)):
    # The length of time to sync will depend on the total number of endpoints
    sync_lock_time = 3 * len(endpoints.get_all())
    slave_seq = [Sequence(
                  [Expected(e['name'], 'PTP Port \d+ Role: Slave', 40),
                   Expected(e['name'], 'PTP sync locked', sync_lock_time)])]

  return Sequence(
            [Expected(e['name'], 'PTP Port 0 Role: Master', 40),
             Expected(e['name'], 'PTP Port 1 Role: Master', 5)] +
            slave_seq)

def ptp_startup_single_port(e, grandmaster, user):
  """ Determine the PTP sequence for the node. If it is not the grandmaster
      it should go to slave and lock
  """
  slave_seq = []
  if grandmaster and (endpoints.get_avb_id(user, e) != endpoints.get_avb_id(user, grandmaster)):
      slave_seq = [Sequence(
                    [Expected(e['name'], 'PTP Role: Slave', 40),
                     Expected(e['name'], 'PTP sync locked', 5)])]

  return Sequence(
             [Expected(e['name'], 'PTP Role: Master', 40)] +
             slave_seq)

def check_endpoint_startup():
  """ Ensure that the endpoints have started correctly. The exact sequence will depend
      on which endpoint is the grandmaster.
  """
  grandmaster = endpoints.determine_grandmaster(args.user)
  log_info("Using grandmaster {gm_id}".format(gm_id=endpoints.get_avb_id(args.user, grandmaster)))

  # Check that all endpoints go to PTP master in 30 seconds and then one of the
  # ports will go Master or Slave and lock
  ptp_startup = [AllOf(
             [ptp_startup_two_port(e, grandmaster, args.user)
               for e in filter(lambda x: x['ports'] == 2, endpoints.get_all().values())] +
             [ptp_startup_single_port(e, grandmaster, args.user)
               for e in filter(lambda x: x['ports'] == 1, endpoints.get_all().values())]
            )]

  maap = [
      AllOf([Expected(e['name'],
            'MAAP reserved Talker stream #%d address: 91:E0:F0:0' % n, 40)
          for n in range(e['talker_streams'])])
      for e in endpoints.get_all().values()
    ]

  yield master.expect(AllOf(ptp_startup + maap))


@inlineCallbacks
def runTest(args):
  """ The test program - needs to yield on each expect and be decorated
    with @inlineCallbacks
  """
  for y in configure_generators():
    yield y

  for y in configure_analyzers():
    yield y

  for y in check_endpoint_startup():
    yield y

  expected = []
  for y in action_discover(args, generator.Command("discover"), expected, []):
    yield y

  check_num = 1
  for test_step in test_steps:
    print_comment(test_step)
    state.move_next_to_current()

    command = test_step.get_command()
    if command is None:
      continue

    action = command.split(' ')
    action_function = eval('action_%s' % action[0])
    expected = []
    for y in action_function(args, test_step, expected, action[1:]):
      yield y
    if expected:
      args.master.addExpected(AllOf(expected))

    if (test_step.checkpoint or test_step.checkpoint is None) and args.master.nextExpected:
      print_title("Check: %d" % check_num)
      check_num += 1

      args.master.startNext()
      yield args.master.expect()

      # Ensure that any remaining output of a previous test step is flushed
      for process in getActiveProcesses():
        master.clearExpectHistory(process)

  # Allow everything time to settle (in case an error is being generated)
  yield base.sleep(5)
  base.testComplete(reactor)

def set_seed(args, test_config):
  """ Set the seed from the config file, unless overridden by the command-line
  """
  seed = 1
  if args.seed is not None:
    seed = args.seed
  elif 'seed' in test_config:
    seed = test_config['seed']

  log_info("Running test with seed {seed}".format(seed=seed))
  random.seed(seed)

def get_eth_id(args):
  """ Get the ethernet interface ID for the current user
  """
  with open('eth.json') as f:
    eth = json.load(f)

  if args.user not in eth:
    log_debug('User %s missing from eth.json' % args.user)
    sys.exit(1)

  return eth[args.user]

def open_json(filename):
  """ Open a json file. Add the '.json' extension if required.
  """
  if not os.path.exists(filename):
    filename += '.json'
  return open(filename)


if __name__ == "__main__":
  parser = base.getParser()
  parser.add_argument('--config', nargs='?', help="name of .json file", required=True)
  parser.add_argument('--user', nargs='?', help="username (selects board setup from json config file)", default=getpass.getuser())
  parser.add_argument('--seed', type=int, nargs='?', help="random seed", default=None)
  parser.add_argument('--test', nargs='?', help="name of .json test configuration file", required=True)
  parser.add_argument('--logdir', nargs='?', help="folder to write all log files to", default="logs")
  parser.add_argument('--types', nargs='*', help="override the types of devices", default="")
  parser.add_argument('--controller-type', choices=['c', 'python'], help="controller type", default='c')
  parser.add_argument('-s', '--stop-on-error', action='store_true', help="set errors to be fatal")
  args = parser.parse_args()

  if args.stop_on_error:
    base.defaultToCriticalFailure = True

  if not os.path.exists(args.logdir):
    os.makedirs(args.logdir)

  xmos_logging.configure_logging(level_file='DEBUG',
      filename=os.path.join(args.logdir, args.logfile),
      summary_filename=args.summaryfile)

  args.eth_id = get_eth_id(args)

  with open_json(args.config) as f:
    config = json.load(f)

  # Read the test file into a standard Python data structure
  with open_json(args.test) as f:
    test_config = json.load(f)

  # Need to set the seed before reading the test_steps as it uses random
  set_seed(args, test_config)

  # Read the test file into class structure
  with open_json(args.test) as f:
    test_steps = json.load(f, object_hook=generator.json_hooks)

  # Create the master to pass to each process
  master = xmos.test.master.Master()
  args.master = master

  # Store the connectivity so that paths between nodes can be determined
  graph.set_connections(config['port_connections'])

  delay = generators.start(rootDir, args, master, config['generators'], 0)
  delay = analyzers.start(rootDir, args, master, config['analyzers'], test_config, delay)
  delay = endpoints.start(rootDir, args, master, config['endpoints'], delay)

  # Create a controller process to send AVB commands to
  controller_id = config['controller']['name']

  # Put the controller ID into the args structure to be used by the action functions
  args.controller_id = controller_id

  if args.controller_type == 'c':
    controller = ControllerProcess(controller_id, master, controllerType=args.controller_type,
        output_file=os.path.join(args.logdir, controller_id + '.log'), send_new_line='\n')

    # Call c-based controller
    controller_bin = os.path.join(rootDir, 'avdecc-lib', 'controller', 'app', 'cmdline', 'avdecccmdline')
    reactor.spawnProcess(controller, controller_bin, [controller_bin, '-t', '-i', args.eth_id], env=os.environ, path=args.logdir)

  else:
    controller = ControllerProcess(controller_id, master, controllerType=args.controller_type,
        output_file=os.path.join(args.logdir, controller_id + '.log'))

    # Call python with unbuffered mode to enable us to see each line as it happens
    controller_dir = os.path.join(rootDir, 'appsval_avb', 'controller', 'avb')
    reactor.spawnProcess(controller, sys.executable, [sys.executable, '-u', 'controller.py', '--batch', '--test-mode', '-i', args.eth_id],
        env=os.environ, path=controller_dir)

  base.testStart(runTest, args)

