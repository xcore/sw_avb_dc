import sys
import random
import time
import json
import getpass
import os

from twisted.internet import reactor, defer
from twisted.internet.defer import inlineCallbacks

def get_parent(full_path):
  (parent, file) = os.path.split(full_path)
  return parent

# Configure the path so that the test framework will be found
rootDir = get_parent(get_parent(get_parent(get_parent(os.path.realpath(__file__)))))
sys.path.append(os.path.join(rootDir,'test_framework'))

from xmos.test.process import getEntities, ControllerProcess
import xmos.test.master as master
import xmos.test.base as base
import xmos.test.xmos_logging as xmos_logging
import xmos.test.generator as generator
from xmos.test.base import AllOf, OneOf, NoneOf, Sequence, Expected, getActiveProcesses
from xmos.test.xmos_logging import log_error, log_warning, log_info, log_debug

import sequences
import state
from endpoints import start_endpoints, get_all_endpoints, get_path_endpoints, entity_by_name
from endpoints import guid_in_ascii, get_avb_id
from analyzers import start_analyzers, get_all_analyzers, analyzer_port

controller_id = 'c1'

# Assign the xrun variable used to start processes
exe_name = base.exe_name('xrun')
xrun = base.file_abspath(exe_name) # Windows requires the absolute path of xrun

def print_title(title):
    log_info("\n%s\n%s\n" % (title, '=' * len(title)))

def check_set_clock_masters():
  for loop in state.get_loops():
    loop_master = loop[0]
    for ep_name in loop:
      if state.is_clock_source_master(ep_name):
        loop_master = ep_name
        break

    if not state.is_clock_source_master(loop_master):
      ep = entity_by_name(loop_master)
      master.sendLine(controller_id, "set_clock_source_master 0x%s" % (
            guid_in_ascii(args.user, ep)))
      state.set_clock_source_master(ep['name'])

      controller_expect = [Expected(controller_id, "Success", 5)]
      ep_expect = [Expected(loop_master, "Setting clock source: LOCAL_CLOCK", 5)]
      yield master.expect(AllOf(controller_expect + ep_expect))

def check_clear_clock_masters():
  for name,ep in get_all_endpoints().iteritems():
    if state.is_clock_source_master(name) and not state.is_in_loop(ep['name']):
      master.sendLine(controller_id, "set_clock_source_slave 0x%s" % (
            guid_in_ascii(args.user, ep)))
      state.set_clock_source_slave(ep['name'])

      controller_expect = [Expected(controller_id, "Success", 5)]
      ep_expect = [Expected(ep['name'], "Setting clock source: INPUT_STREAM_DERIVED", 5)]
      yield master.expect(AllOf(controller_expect + ep_expect))

def controller_connect(controller_id, src, src_stream, dst, dst_stream):
  talker_ep = entity_by_name(src)
  listener_ep = entity_by_name(dst)

  state.connect(src, src_stream, dst, dst_stream)
  for y in check_set_clock_masters():
    yield y

  master.sendLine(controller_id, "connect 0x%s %d 0x%s %d" % (
        guid_in_ascii(args.user, talker_ep), src_stream,
        guid_in_ascii(args.user, listener_ep), dst_stream))

def controller_disconnect(controller_id, src, src_stream, dst, dst_stream):
  talker_ep = entity_by_name(src)
  listener_ep = entity_by_name(dst)

  state.disconnect(src, src_stream, dst, dst_stream)
  for y in check_clear_clock_masters():
    yield y

  master.sendLine(controller_id, "disconnect 0x%s %d 0x%s %d" % (
        guid_in_ascii(args.user, talker_ep), src_stream,
        guid_in_ascii(args.user, listener_ep), dst_stream))

def controller_enumerate(controller_id, avb_ep):
  entity_id = entity_by_name(avb_ep)
  master.sendLine(controller_id, "enumerate 0x%s" % (guid_in_ascii(args.user, entity_id)))

def get_expected(src, src_stream, dst, dst_stream, command):
  state.dump_state()
  talker_state = state.get_talker_state(src, src_stream, dst, dst_stream, command)
  talker_expect = sequences.expected_seq(talker_state)(entity_by_name(src), src_stream)

  listener_state = state.get_listener_state(src, src_stream, dst, dst_stream, command)
  listener_expect = sequences.expected_seq(listener_state)(entity_by_name(dst), dst_stream)
  analyzer_state = "analyzer_" + listener_state
  analyzer_expect = sequences.expected_seq(analyzer_state)(entity_by_name(src), src_stream,
      entity_by_name(dst), dst_stream)

  analyzer_expect += sequences.analyzer_qav_seq(src, dst, command, connections, args.user)

  controller_state = state.get_controller_state(src, src_stream, dst, dst_stream, command)
  controller_expect = sequences.expected_seq(controller_state)(controller_id)
  return (talker_expect, listener_expect, controller_expect, analyzer_expect)

def get_dual_port_nodes(nodes):
  return [node for node in nodes if entity_by_name(node)['ports'] == 2]

def action_enumerate(params_list):
  entity_id = params_list[0]

  descriptors = entity_by_name(entity_id)['descriptors']
  controller_expect = sequences.controller_enumerate_seq(controller_id, descriptors)
  controller_enumerate(controller_id, entity_id)

  yield master.expect(controller_expect)

def action_connect(params_list):
  src = params_list[0]
  src_stream = int(params_list[1])
  dst = params_list[2]
  dst_stream = int(params_list[3])

  (talker_expect, listener_expect,
   controller_expect, analyzer_expected) = get_expected(src, src_stream, dst, dst_stream, 'connect')

  # Find the path between the src and dst and check whether there are any nodes between them
  forward_enable = []
  nodes = get_path_endpoints(state.find_path(connections, src, dst))
  for node in get_dual_port_nodes(nodes):
    if state.node_will_see_stream_enable(src, src_stream, dst, dst_stream, node, connections):
      forward_enable += sequences.expected_seq('stream_forward_enable')(args.user,
        entity_by_name(node), entity_by_name(src))

  # Expect not to see any enables from other nodes
  not_forward_enable = []
  temp_nodes = set(get_all_endpoints().keys()) - set(nodes)
  for node in get_dual_port_nodes(temp_nodes):
    not_forward_enable += sequences.expected_seq('stream_forward_enable')(args.user,
      entity_by_name(node), entity_by_name(src))

  if not_forward_enable:
    not_forward_enable = [NoneOf(not_forward_enable)]

  for y in controller_connect(controller_id, src, src_stream, dst, dst_stream):
    yield y

  yield master.expect(AllOf(talker_expect + listener_expect +
        controller_expect + analyzer_expected + forward_enable + not_forward_enable))

def action_disconnect(params_list):
  src = params_list[0]
  src_stream = int(params_list[1])
  dst = params_list[2]
  dst_stream = int(params_list[3])

  (talker_expect, listener_expect,
   controller_expect, analyzer_expected) = get_expected(src, src_stream, dst, dst_stream, 'disconnect')

  # Find the path between the src and dst and check whether there are any nodes between them
  forward_disable = []
  nodes = get_path_endpoints(state.find_path(connections, src, dst))
  for node in get_dual_port_nodes(nodes):
    if state.node_will_see_stream_disable(src, src_stream, dst, dst_stream, node, connections):
      forward_disable += sequences.expected_seq('stream_forward_disable')(args.user,
        entity_by_name(node), entity_by_name(src))

  # Expect not to see any disables from other nodes
  not_forward_disable = []
  temp_nodes = set(get_all_endpoints().keys()) - set(nodes)
  for node in get_dual_port_nodes(temp_nodes):
    not_forward_disable += sequences.expected_seq('stream_forward_disable')(args.user,
      entity_by_name(node), entity_by_name(src))

  if not_forward_disable:
    not_forward_disable = [NoneOf(not_forward_disable)]

  for y in controller_disconnect(controller_id, src, dst_stream, dst, dst_stream):
    yield y

  yield master.expect(AllOf(talker_expect + listener_expect +
        controller_expect + analyzer_expected + forward_disable + not_forward_disable))

def action_ping(params_list):
  """ Ping a node with and check that it responds accordingly. This is used to test
      connectivity.
  """
  node_name = params_list[0]
  ep = entity_by_name(node_name)

  node_expect = [Expected(ep['name'], "IDENTIFY Ping", 5)]
  controller_expect = [Expected(controller_id, "Success", 5)]

  master.sendLine(controller_id, "identify 0x%s on" % guid_in_ascii(args.user, ep))
  master.sendLine(controller_id, "identify 0x%s off" % guid_in_ascii(args.user, ep))

  yield master.expect(AllOf(node_expect + controller_expect))

def action_link_downup(params_list):
  """ Expect all connections which bridge the relay to be lost and restored if there
      is a quick link down/up event. The first argument is the analyzer controlling
      the relay. The second is the time to sleep before restoring the link.
  """
  analyzer_name = params_list[0]
  sleep_time = int(params_list[1])
  expected = []

  # Expect all the connections which cross the relay to be lost
  for c,n in state.active_connections.iteritems():
    if n and analyzer_name in state.find_path(connections, c.talker.src, c.listener.dst):
      expected += sequences.analyzer_listener_disconnect_seq(
                      entity_by_name(c.talker.src), c.talker.src_stream,
                      entity_by_name(c.listener.dst), c.listener.dst_stream)

  # Send the command to open the relay '(r)elay (o)pen'
  master.sendLine(analyzer_name, "r o")

  if expected:
    yield master.expect(AllOf(expected))
  else:
    yield master.expect(None)

  # Perform a sleep as defined by the second argument
  yield base.sleep(sleep_time)

  expected = []

  # Expect all the connections which cross the relay to be restored
  for c,n in state.active_connections.iteritems():
    if n and analyzer_name in state.find_path(connections, c.talker.src, c.listener.dst):
      expected += sequences.analyzer_listener_connect_seq(
                      entity_by_name(c.talker.src), c.talker.src_stream,
                      entity_by_name(c.listener.dst), c.listener.dst_stream)

  # Send the command to close the relay '(r)elay (c)lose'
  master.sendLine(analyzer_name, "r c")

  if expected:
    yield master.expect(AllOf(expected))
  else:
    yield master.expect(None)

def action_link_up(params_list):
  analyzer_name = params_list[0]
  # Send the command to close the relay '(r)elay (c)lose'
  master.sendLine(analyzer_name, "r c")
  # Don't expect anything to happen just from closing the relay
  yield master.expect(None)


def action_check_connections(params_list):
  """ Check that the current state the controller reads from the endpoints matches
      the state the test framework expects.
  """
  expected = []

  # Expect all connections to be restored
  for c,n in state.active_connections.iteritems():
    if n:
      expected += [Expected(controller_id, "0x%s\[%d\] -> 0x%s\[%d\]" % (
                      guid_in_ascii(args.user, entity_by_name(c.talker.src)), c.talker.src_stream,
                      guid_in_ascii(args.user, entity_by_name(c.listener.dst)), c.listener.dst_stream), 10)]

  master.sendLine(controller_id, "show connections")

  if expected:
    yield master.expect(AllOf(expected))
  else:
    yield master.expect(NoneOf([Expected(controller_id, "->", 5)]))

def action_sleep(params_list):
  """ Do nothing for the defined time.
  """
  yield base.sleep(int(params_list[0]))
  yield master.expect(None)

def action_continue(params_list):
  """ Do nothing.
  """
  yield master.expect(None)

def chk(master, endpoints):
  return master.expect(Expected(controller_id, "Found %d entities" % len(endpoints), 15))

def configure_analyzers():
  """ Ensure the analyzers have started properly and then configure their channel
      frequencies as specified in the test configuration file
  """
  analyzer_startup =  [Expected(a, "connected to .*: %d" % analyzer_port(a), 15)
                        for a in get_all_analyzers()]
  yield master.expect(AllOf(analyzer_startup))

  for (name,analyzer) in get_all_analyzers().iteritems():
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

def determine_grandmaster(user):
  """ From the endpoints described determine which will be the grandmaster.
      It is the node with the lowest MAC address unless there is a switch
      which has a different priority.
  """
  grandmaster = None
  for name,ep in get_all_endpoints().iteritems():
    if not grandmaster:
      grandmaster = ep
    else:
      e_id = get_avb_id(user, ep)
      if e_id < get_avb_id(user, grandmaster):
        grandmaster = ep
  return grandmaster

def ptp_startup_two_port(e, grandmaster, user):
  """ Determine the PTP sequence for the node. If it is not the grandmaster
      it should go to slave and lock
  """
  slave_seq = []
  if grandmaster and (get_avb_id(user, e) != get_avb_id(user, grandmaster)):
    # The length of time to sync will depend on the total number of endpoints
    sync_lock_time = 3 * len(get_all_endpoints())
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
  if grandmaster and (get_avb_id(user, e) != get_avb_id(user, grandmaster)):
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
  grandmaster = determine_grandmaster(args.user)
  log_info("Using grandmaster {gm_id}".format(gm_id=get_avb_id(args.user, grandmaster)))

  # Check that all endpoints go to PTP master in 30 seconds and then one of the
  # ports will go Master or Slave and lock
  ptp_startup = [AllOf(
             [ptp_startup_two_port(e, grandmaster, args.user)
               for e in filter(lambda x: x['ports'] == 2, get_all_endpoints().values())] +
             [ptp_startup_single_port(e, grandmaster, args.user)
               for e in filter(lambda x: x['ports'] == 1, get_all_endpoints().values())]
            )]

  maap = [
      AllOf([Expected(e['name'],
            'MAAP reserved Talker stream #%d address: 91:E0:F0:0' % n, 40)
          for n in range(e['talker_streams'])])
      for e in get_all_endpoints().values()
    ]

  yield master.expect(AllOf(ptp_startup + maap))


@inlineCallbacks
def runTest(args):
  """ The test program - needs to yield on each expect and be decorated
    with @inlineCallbacks
  """
  for y in configure_analyzers():
    yield y

  for y in check_endpoint_startup():
    yield y

  master.clearExpectHistory(controller_id)
  master.sendLine(controller_id, "discover")
  yield chk(master, get_all_endpoints().values())

  if not getEntities():
    base.testError("no entities found", critical=True)

  for (test_num, ts) in enumerate(test_steps):
    # Ensure that any remaining output of a previous test step is flushed
    for process in getActiveProcesses():
      master.clearExpectHistory(process)

    print_title("Test %d - %s" % (test_num+1, ts))
    action = ts.split(' ')
    action_function = eval('action_%s' % action[0])
    for y in action_function(action[1:]):
      yield y


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
  parser.add_argument('--config', dest='config', nargs='?', help="name of .json file", required=True)
  parser.add_argument('--user', dest='user', nargs='?', help="username (selects board setup from json config file)", default=getpass.getuser())
  parser.add_argument('--seed', dest='seed', type=int, nargs='?', help="random seed", default=None)
  parser.add_argument('--test', dest='test', nargs='?', help="name of .json test configuration file", required=True)
  parser.add_argument('--logdir', dest='logdir', nargs='?', help="folder to write all log files to", default="logs")
  parser.add_argument('--types', dest='types', nargs='*', help="override the types of devices", default="")
  args = parser.parse_args()

  if not os.path.exists(args.logdir):
    os.makedirs(args.logdir)

  xmos_logging.configure_logging(level_file='DEBUG',
      filename=os.path.join(args.logdir, args.logfile),
      summary_filename=args.summaryfile)

  eth_id = get_eth_id(args)

  with open_json(args.config) as f:
    topology = json.load(f)

  # Read the test file into a standard Python data structure
  with open_json(args.test) as f:
    test_config = json.load(f)

  # Need to set the seed before reading the test_steps as it uses random
  set_seed(args, test_config)

  # Read the test file into class structure
  with open_json(args.test) as f:
    test_steps = json.load(f, object_hook=generator.json_hooks)

  # Create the master to pass to each process
  master = master.Master()

  endpoints = topology['endpoints']
  analyzers = topology['analyzers']
  connections = topology['port_connections']

  start_analyzers(rootDir, args, master, analyzers)
  start_endpoints(rootDir, args, endpoints, master, analyzers)

  # Create a controller process to send AVB commands to
  controller_dir = os.path.join(rootDir, 'appsval_avb', 'controller', 'avb')
  controller = ControllerProcess('c1', master, output_file="cl.log")

  # Call python with unbuffered mode to enable us to see each line as it happens
  reactor.spawnProcess(controller, sys.executable, [sys.executable, '-u', 'controller.py', '--batch', '--test-mode', '-i', eth_id],
      env=os.environ, path=controller_dir)

  base.testStart(runTest, args)

