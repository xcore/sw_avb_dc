import sys
import random
import time
import getpass
import json
import os

from twisted.internet import reactor, defer
from twisted.internet.defer import inlineCallbacks

import xmos.test.process as process
import xmos.test.master as master
import xmos.test.base as base
import xmos.test.generator as generator
from xmos.test.base import AllOf, OneOf, NoneOf, Sequence, Expected

import sequences
import state

all_ep_names = set()
endpoints = []
controller_id = 'c1'

def handle_config_error(file, user):
  print "Device configuration is not available in '%s' file for the user '%s' " % (file, user)
  exit(1)

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

def print_title(title):
    print "\n%s\n%s\n" % (title, '=' * len(title))

def get_parent(full_path):
  (parent, file) = os.path.split(full_path)
  return parent

def guid_in_ascii(ep):
  return sequences.get_avb_id(args.user, ep).encode('ascii', 'ignore')

def entity_by_name(name):
  matches = [e for e in endpoints if e["name"] == name]
  if matches:
    return matches[0]
  else:
    return None

def controller_connect(controller_id, src, src_stream, dst, dst_stream):
  talker_ep = entity_by_name(src)
  listener_ep = entity_by_name(dst)
  master.sendLine(controller_id, "connect 0x%s %d 0x%s %d" % (
        guid_in_ascii(talker_ep), src_stream, guid_in_ascii(listener_ep), dst_stream))
  state.connect(src, src_stream, dst, dst_stream)

def controller_disconnect(controller_id, src, src_stream, dst, dst_stream):
  talker_ep = entity_by_name(src)
  listener_ep = entity_by_name(dst)
  master.sendLine(controller_id, "disconnect 0x%s %d 0x%s %d" % (
        guid_in_ascii(talker_ep), src_stream, guid_in_ascii(listener_ep), dst_stream))
  state.disconnect(src, src_stream, dst, dst_stream)

def controller_enumerate(controller_id, avb_ep):
  entity_id = entity_by_name(avb_ep)
  master.sendLine(controller_id, "enumerate 0x%s" % (guid_in_ascii(entity_id)))

def get_expected(src, src_stream, dst, dst_stream, command):
  talker_state = state.get_talker_state(src, src_stream, dst, dst_stream, command)
  talker_expect = sequences.expected_seq(talker_state)(entity_by_name(src), src_stream)
  listener_state = state.get_listener_state(dst, dst_stream, command)
  listener_expect = sequences.expected_seq(listener_state)(entity_by_name(dst), dst_stream)
  controller_state = state.get_controller_state(src, src_stream, dst, dst_stream, command)
  controller_expect = sequences.expected_seq(controller_state)(controller_id)
  return (talker_expect, listener_expect, controller_expect)

def get_dual_port_nodes(nodes):
  return [node for node in nodes if entity_by_name(node)["ports"] == 2]

def action_enumerate(params_list):
  entity_id = params_list[0]
  
  descriptors = entity_by_name(entity_id)["descriptors"]
  controller_expect = sequences.controller_enumerate_seq(controller_id, descriptors)
  controller_enumerate(controller_id, entity_id)
    
  return master.expect(controller_expect)

def action_connect(params_list):
  src = params_list[0]
  src_stream = int(params_list[1])
  dst = params_list[2]
  dst_stream = int(params_list[3])

  (talker_expect, listener_expect, controller_expect) = get_expected(src, src_stream, dst, dst_stream, 'connect')
  controller_connect(controller_id, src, src_stream, dst, dst_stream)

  # Find the path between the src and dst and check whether there are any nodes between them
  forward_enable = []
  nodes = get_path_endpoints(find_path(connections, src, dst))
  for node in get_dual_port_nodes(nodes):
    forward_enable += sequences.expected_seq('stream_forward_enable')(args.user,
      entity_by_name(node), entity_by_name(src))

  # Expect not to see any enables from other nodes
  not_forward_enable = []
  temp_nodes = set(all_ep_names) - set(nodes)
  for node in get_dual_port_nodes(temp_nodes):
    not_forward_enable += sequences.expected_seq('stream_forward_enable')(args.user,
      entity_by_name(node), entity_by_name(src))

  if not_forward_enable:
    not_forward_enable = [NoneOf(not_forward_enable)]
    
  return master.expect(AllOf(talker_expect + listener_expect + controller_expect + forward_enable + not_forward_enable))

def action_disconnect(params_list):
  src = params_list[0]
  src_stream = int(params_list[1])
  dst = params_list[2]
  dst_stream = int(params_list[3])

  (talker_expect, listener_expect, controller_expect) = get_expected(src, src_stream, dst, dst_stream, 'disconnect')
  controller_disconnect(controller_id, src, dst_stream, dst, dst_stream)

  # Find the path between the src and dst and check whether there are any nodes between them
  forward_disable = []
  nodes = get_path_endpoints(find_path(connections, src, dst))
  for node in get_dual_port_nodes(nodes):
    forward_disable += sequences.expected_seq('stream_forward_disable')(args.user,
      entity_by_name(node), entity_by_name(src))

  # Expect not to see any disables from other nodes
  not_forward_disable = []
  temp_nodes = set(all_ep_names) - set(nodes)
  for node in get_dual_port_nodes(temp_nodes):
    not_forward_disable += sequences.expected_seq('stream_forward_disable')(args.user,
      entity_by_name(node), entity_by_name(src))

  if not_forward_disable:
    not_forward_disable = [NoneOf(not_forward_disable)]

  return master.expect(AllOf(talker_expect + listener_expect + controller_expect + forward_disable + not_forward_disable))

def action_continue(params_list):
  ''' Do nothing 
  '''
  return master.expect(None)
  
def chk(master, endpoints):
  return master.expect(Expected(controller_id, "Found %d entities" % len(endpoints), 15))


@inlineCallbacks
def runTest(args):
  """ The test program - needs to yield on each expect and be decorated
    with @inlineCallbacks
  """

  # Check that all endpoints go to PTP master in 30 seconds
  ptp_startup1 = [AllOf(
             [Sequence(
               [Expected(e["name"], "PTP Port 0 Role: Master", 40),
               Expected(e["name"], "PTP Port 1 Role: Master", 5)])
               for e in filter(lambda x: x["ports"] == 2, endpoints)] +
             [Sequence(
               [Expected(e["name"], "PTP Role: Master", 40)])
               for e in filter(lambda x: x["ports"] == 1, endpoints)]
             )]

  ptp_startup2 = [OneOf(
             [Sequence(
               [Expected(e["name"], "PTP Port \d+ Role: Slave", 40),
               Expected(e["name"], "PTP sync locked", 5)])
               for e in filter(lambda x: x["ports"] == 2, endpoints)] +
             [Sequence(
               [Expected(e["name"], "PTP Port \d+ Role: Master", 40),
               Expected(e["name"], "PTP sync locked", 5)])
               for e in filter(lambda x: x["ports"] == 2, endpoints)] +
             [Sequence(
               [Expected(e["name"], "PTP Role: Slave", 40),
               Expected(e["name"], "PTP sync locked", 5)])
               for e in filter(lambda x: x["ports"] == 1, endpoints)] +
             [Sequence(
               [Expected(e["name"], "PTP Role: Master", 40),
               Expected(e["name"], "PTP sync locked", 5)])
               for e in filter(lambda x: x["ports"] == 1, endpoints)] )
          ]
  maap = [
      AllOf([Expected(e["name"], "MAAP reserved Talker stream #%d address: 91:E0:F0:0" % n, 40) for n in range(e["talker_streams"])])
      for e in endpoints
    ]

  yield master.expect(AllOf(ptp_startup1 + ptp_startup2 + maap))

  time.sleep(5)
  master.clearExpectHistory(controller_id)
  master.sendLine(controller_id, "discover")
  yield chk(master, endpoints)

  if not process.getEntities():
    testError("no entities found", True)

  for (test_num, ts) in enumerate(test_steps):
    print_title("Test %d - %s" % (test_num+1, ts))
    action = ts.split(' ')
    action_function = eval('action_%s' % action[0])
    yield action_function(action[1:])

  base.testComplete(reactor)

def startXrun(combined_args):
  (name, process, adapter_id, bin, args) = combined_args

  exe_name = base.exe_name('xrun')
  xrun = base.file_abspath(exe_name) # Windows requires the absolute path of xrun
  print "Starting %s (%s)" % (name, ' '.join(['--adapter-id', adapter_id, '--xscope', bin]))
  reactor.spawnProcess(process, xrun, [xrun, '--adapter-id', adapter_id, '--xscope', bin],
      env=os.environ, path=args.workdir)

def startXrunWithDelay(delay, name, adapter_id, bin, args):
  # Need to ensure that the endpoint and process are created and registered before the
  # master task is started
  ep = process.XrunProcess(name, master, verbose=True, output_file=name + '_console.log')

  print "Starting %s in %.3f" % (name, delay)
  d = defer.Deferred()
  reactor.callLater(delay, d.callback, (name, ep, adapter_id, bin, args))
  d.addCallback(startXrun)


if __name__ == "__main__":
  parser = base.getParser()
  parser.add_argument('--config', dest='config', nargs='?', help="name of .json file", required=True)
  parser.add_argument('--user', dest='user', nargs='?', help="username (selects board setup from json config file)", default=getpass.getuser())
  parser.add_argument('--seed', dest='seed', type=int, nargs='?', help="random seed", default=1)
  parser.add_argument('--workdir', dest='workdir', nargs='?', help="working directory", default='./')
  parser.add_argument('--test_file', dest='test_file', nargs='?', help="name of .json test configuration file", required=True)
  args = parser.parse_args()

  with open('eth.json') as f:
    eth = json.load(f)

  with open(args.config + '.json') as f:
    topology = json.load(f)
    endpoints = topology['endpoints']
    connections = topology['connections']

  with open(args.test_file + '.json') as f:
    test_steps = json.load(f, object_hook=generator.json_hooks)

  # Create the master to pass to each process
  master = master.Master()

  print "Running test with seed {seed}".format(seed=args.seed)
  random.seed(args.seed)
  delay = random.uniform(0, 10)

  for ep in endpoints:
    all_ep_names.add(ep['name'])

    if args.user not in ep['users']:
      handle_config_error((args.config + '.json'), args.user)

    user_config = ep['users'][args.user]
    startXrunWithDelay(delay, ep['name'], user_config['xrun_adapter_id'], user_config['binary'], args)
    delay += random.uniform(0, 10)

  # Create a controller process to send AVB commands to
  controller = process.ControllerProcess('c1', master, verbose=args.verbose, output_file="cl.log")

  sandbox = get_parent(get_parent(get_parent(get_parent(os.path.realpath(__file__)))))
  scriptdir = os.path.join(sandbox, 'appsval_avb', 'controller', 'avb')

  try:
    eth_id = eth[args.user]
  except:
    handle_config_error('eth.json', args.user)

  # Call python with unbuffered mode to enable us to see each line as it happens
  reactor.spawnProcess(controller, sys.executable, [sys.executable, '-u', 'controller.py', '--batch', '-i', eth_id],
      env=os.environ, path=scriptdir)

  base.testStart(runTest, args)

