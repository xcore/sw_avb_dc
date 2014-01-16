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
from sequences import get_avb_id
import state
from endpoints import start_endpoints, get_all_endpoints, get_path_endpoints, entity_by_name
from analyzers import start_analyzers, get_all_analyzers, analyzer_port

controller_id = 'c1'

# Assign the xrun variable used to start processes
exe_name = base.exe_name('xrun')
xrun = base.file_abspath(exe_name) # Windows requires the absolute path of xrun

def find_path(graph, start, end, path=[]):
  path = path + [start]
  if start == end:
    return path
  if not graph.has_key(start):
    return None
  for node in graph[start]:
    if node not in path:
      newpath = find_path(graph, node, end, path)
      if newpath: return newpath
  return None

def node_will_see_stream_enable(src, src_stream, dst, dst_stream, node, nodes):
  if (state.connected(src, src_stream, dst, dst_stream) or
      state.listener_active_count(dst, dst_stream)):
    # Connection will have no effect
    return False

  # Look for all nodes past this one in the path. If one of them is connected to
  # this stream then this node won't see enable, otherwise it should expect to
  found = False
  for n in nodes:
    if found:
      if state.connected(src, src_stream, n):
        return False

    elif n == node:
      found = True

  return True

def node_will_see_stream_disable(src, src_stream, dst, dst_stream, node, nodes):
  if not state.connected(src, src_stream, dst, dst_stream):
    # Disconnection will have no effect
    return False

  # Look for all nodes past this one in the path. If one of them is connected to
  # this stream then this node won't see disable, otherwise it should expect to
  found = False
  for n in nodes:
    if found:
      if state.connected(src, src_stream, n):
        return False

    elif n == node:
      found = True

  return True

def print_title(title):
    log_info("\n%s\n%s\n" % (title, '=' * len(title)))

def guid_in_ascii(ep):
  return get_avb_id(args.user, ep).encode('ascii', 'ignore')

def check_set_clock_masters():
  for loop in state.get_loops():
    loop_master = loop[0]
    for ep_name in loop:
      if state.is_clock_source_master(ep_name):
        loop_master = ep
        break

    if not state.is_clock_source_master(loop_master):
      ep = entity_by_name(loop_master)
      master.sendLine(controller_id, "set_clock_source_master 0x%s" % (guid_in_ascii(ep)))
      state.set_clock_source_master(ep['name'])

      controller_expect = [Expected(controller_id, "Success", 5)]
      ep_expect = [Expected(loop_master, "Setting clock source: LOCAL_CLOCK", 5)]
      yield master.expect(AllOf(controller_expect + ep_expect))

def check_clear_clock_masters():
  for name,ep in get_all_endpoints().iteritems():
    if state.is_clock_source_master(name) and not state.is_in_loop(ep['name']):
      master.sendLine(controller_id, "set_clock_source_slave 0x%s" % (guid_in_ascii(ep)))
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
        guid_in_ascii(talker_ep), src_stream, guid_in_ascii(listener_ep), dst_stream))

def controller_disconnect(controller_id, src, src_stream, dst, dst_stream):
  talker_ep = entity_by_name(src)
  listener_ep = entity_by_name(dst)
  state.disconnect(src, src_stream, dst, dst_stream)
  master.sendLine(controller_id, "disconnect 0x%s %d 0x%s %d" % (
        guid_in_ascii(talker_ep), src_stream, guid_in_ascii(listener_ep), dst_stream))

def controller_enumerate(controller_id, avb_ep):
  entity_id = entity_by_name(avb_ep)
  master.sendLine(controller_id, "enumerate 0x%s" % (guid_in_ascii(entity_id)))

def get_expected(src, src_stream, dst, dst_stream, command):
  state.dump_state()
  talker_state = state.get_talker_state(src, src_stream, dst, dst_stream, command)
  talker_expect = sequences.expected_seq(talker_state)(entity_by_name(src), src_stream)

  listener_state = state.get_listener_state(src, src_stream, dst, dst_stream, command)
  listener_expect = sequences.expected_seq(listener_state)(entity_by_name(dst), dst_stream)
  analyzer_state = "analyzer_" + listener_state
  analyzer_expect = sequences.expected_seq(analyzer_state)(entity_by_name(src), src_stream,
      entity_by_name(dst), dst_stream)

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
  nodes = get_path_endpoints(find_path(connections, src, dst))
  for node in get_dual_port_nodes(nodes):
    if node_will_see_stream_enable(src, src_stream, dst, dst_stream, node, nodes):
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
  nodes = get_path_endpoints(find_path(connections, src, dst))
  for node in get_dual_port_nodes(nodes):
    if node_will_see_stream_disable(src, src_stream, dst, dst_stream, node, nodes):
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

  controller_disconnect(controller_id, src, dst_stream, dst, dst_stream)

  yield master.expect(AllOf(talker_expect + listener_expect +
        controller_expect + analyzer_expected + forward_disable + not_forward_disable))

def action_continue(params_list):
  """ Do nothing
  """
  yield master.expect(None)

def chk(master, endpoints):
  return master.expect(Expected(controller_id, "Found %d entities" % len(endpoints), 15))

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
      slave_seq = [Sequence(
                    [Expected(e['name'], 'PTP Port \d+ Role: Slave', 40),
                     Expected(e['name'], 'PTP sync locked', 5)])]

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

@inlineCallbacks
def runTest(args):
  """ The test program - needs to yield on each expect and be decorated
    with @inlineCallbacks
  """
  analyzer_startup =  [Expected(a, "connected to .*: %d" % analyzer_port(a), 15)
                        for a in get_all_analyzers()]
  yield master.expect(AllOf(analyzer_startup))

  for (name,analyzer) in get_all_analyzers().iteritems():
    log_info("Configure %s" % name)

    # Disable all channels
    master.sendLine(name, "d a")
    yield master.expect(Expected(name, "Channel 0: disabled", 15))

    # Set the base channel index
    analyzer_base = analyzer['base']
    master.sendLine(name, "b %d" % analyzer_base)

    # Configure all channels
    for (chan_id, freq) in analyzer['frequencies'].iteritems():
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

  time.sleep(5)
  master.clearExpectHistory(controller_id)
  master.sendLine(controller_id, "discover")
  yield chk(master, get_all_endpoints().values())

  if not getEntities():
    base.testError("no entities found", True)

  for (test_num, ts) in enumerate(test_steps):
    # Ensure that the remaining output of a previous test step is flushed
    for process in getActiveProcesses():
      master.clearExpectHistory(process)

    print_title("Test %d - %s" % (test_num+1, ts))
    action = ts.split(' ')
    action_function = eval('action_%s' % action[0])
    for y in action_function(action[1:]):
      yield y

    for y in check_clear_clock_masters():
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

if __name__ == "__main__":
  parser = base.getParser()
  parser.add_argument('--config', dest='config', nargs='?', help="name of .json file", required=True)
  parser.add_argument('--user', dest='user', nargs='?', help="username (selects board setup from json config file)", default=getpass.getuser())
  parser.add_argument('--seed', dest='seed', type=int, nargs='?', help="random seed", default=1)
  parser.add_argument('--workdir', dest='workdir', nargs='?', help="working directory", default='./')
  parser.add_argument('--test_file', dest='test_file', nargs='?', help="name of .json test configuration file", required=True)
  args = parser.parse_args()

  xmos_logging.configure_logging(level_file='DEBUG', filename=args.logfile)

  eth_id = get_eth_id(args)

  with open(args.config) as f:
    topology = json.load(f)
    endpoints = topology['endpoints']
    analyzers = topology['analyzers']
    connections = topology['port_connections']

  if not os.path.exists(args.test_file):
    args.test_file += '.json'

  with open(args.test_file) as f:
    test_steps = json.load(f, object_hook=generator.json_hooks)

  # Create the master to pass to each process
  master = master.Master()

  log_info("Running test with seed {seed}".format(seed=args.seed))
  random.seed(args.seed)

  start_analyzers(rootDir, args, master, analyzers)
  start_endpoints(rootDir, args, endpoints, master, analyzers)

  # Create a controller process to send AVB commands to
  controller_dir = os.path.join(rootDir, 'appsval_avb', 'controller', 'avb')
  controller = ControllerProcess('c1', master, output_file="cl.log")

  # Call python with unbuffered mode to enable us to see each line as it happens
  reactor.spawnProcess(controller, sys.executable, [sys.executable, '-u', 'controller.py', '--batch', '-i', eth_id],
      env=os.environ, path=controller_dir)

  base.testStart(runTest, args)

