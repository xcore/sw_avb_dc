import random
import re

import xmos.test.base as base
import xmos.test.xmos_logging as xmos_logging
from xmos.test.base import AllOf, OneOf, NoneOf, Sequence, Expected, getActiveProcesses
from xmos.test.xmos_logging import log_error, log_warning, log_info, log_debug

import analyzers
import endpoints
import generators
import graph
import sequences
import state

def print_title(title):
  log_info("\n%s\n%s\n" % (title, '=' * len(title)))

def choose_from(group, params, index):
  if index < len(params):
    choice = group.get(params[index])
    if choice is not None:
      return choice['name']

  choice = random.choice(group.get_all().keys())
  return choice

def choose_generator(params, index):
  return choose_from(generators, params, index)

def choose_generator_rate(params, index):
  try:
    return int(params[index])
  except:
    # Have a 25% chance of disabling the generator (returning 0)
    mode = random.random()
    if mode > 0.25:
      return int(random.random() * 100)
    else:
      return 0

def choose_analyzer(params, index):
  return choose_from(analyzers, params, index)

def choose_src(params, index):
  return choose_from(endpoints, params, index)

def choose_src_stream(params, index):
  try:
    return int(params[index])
  except:
    return 0

def choose_dst(params, index):
  return choose_from(endpoints, params, index)

def choose_dst_stream(params, index):
  return choose_src_stream(params, index)

def select_endpoint(args, endpoint_name):
  entity = 0
  configuration = 0
  args.master.sendLine(args.controller_id, "select 0x%s %d %d" % (
        endpoints.guid_in_ascii(args.user, endpoint_name), entity, configuration))

def check_set_clock_masters(args, test_step, expected):
  for loop in graph.get_loops(state.get_next()):
    loop_master = loop[0]
    for ep_name in loop:
      # Look at the next state in case the node has just been set clock master
      if state.get_next().is_clock_source_master(ep_name):
        loop_master = ep_name
        break

    if not state.get_next().is_clock_source_master(loop_master):
      ep = endpoints.get(loop_master)
      print_title("Command: set_clock_source_master %s" % loop_master)
      if args.controller_type == 'python':
        args.master.sendLine(args.controller_id, "set_clock_source_master 0x%s" % (
              endpoints.guid_in_ascii(args.user, ep)))
      else:
        select_endpoint(args, ep)
        args.master.sendLine(args.controller_id, "set clock_source 0 0 1")

      state.get_next().set_clock_source_master(ep['name'])

      if test_step.do_checks:
        controller_expect = sequences.expected_seq('controller_success_set_clock_source')(args, test_step)
        ep_expect = [Expected(loop_master, "Setting clock source: LOCAL_CLOCK", 5)]
        if controller_expect or ep_expect:
          expected += [AllOf(controller_expect + ep_expect)]

def check_clear_clock_masters(args, test_step, expected):
  for name,ep in endpoints.get_all().iteritems():
    if state.get_current().is_clock_source_master(name) and not graph.is_in_loop(state.get_current(), ep['name']):
      print_title("Command: set_clock_source_slave %s" % name)
      if args.controller_type == 'python':
        args.master.sendLine(args.controller_id, "set_clock_source_slave 0x%s" % (
              endpoints.guid_in_ascii(args.user, ep)))
      else:
        select_endpoint(args, ep)
        args.master.sendLine(args.controller_id, "set clock_source 0 0 0")

      state.get_next().set_clock_source_slave(ep['name'])

      if test_step.do_checks:
        controller_expect = sequences.expected_seq('controller_success_set_clock_source')(args, test_step)
        ep_expect = [Expected(ep['name'], "Setting clock source: INPUT_STREAM_DERIVED", 5)]
        if controller_expect or ep_expect:
          expected += [AllOf(controller_expect + ep_expect)]

def controller_connect(args, test_step, expected, src, src_stream, dst, dst_stream):
  talker_ep = endpoints.get(src)
  listener_ep = endpoints.get(dst)

  state.get_next().connect(src, src_stream, dst, dst_stream)
  check_set_clock_masters(args, test_step, expected)

  print_title("Command: connect %s %d %s %d" % (src, src_stream, dst, dst_stream))
  args.master.sendLine(args.controller_id, "connect 0x%s %d 0x%s %d" % (
        endpoints.guid_in_ascii(args.user, talker_ep), src_stream,
        endpoints.guid_in_ascii(args.user, listener_ep), dst_stream))

def controller_disconnect(args, test_step, expected, src, src_stream, dst, dst_stream):
  talker_ep = endpoints.get(src)
  listener_ep = endpoints.get(dst)

  state.get_next().disconnect(src, src_stream, dst, dst_stream)
  check_clear_clock_masters(args, test_step, expected)

  print_title("Command: disconnect %s %d %s %d" % (src, src_stream, dst, dst_stream))
  args.master.sendLine(args.controller_id, "disconnect 0x%s %d 0x%s %d" % (
        endpoints.guid_in_ascii(args.user, talker_ep), src_stream,
        endpoints.guid_in_ascii(args.user, listener_ep), dst_stream))

def controller_enumerate(args, avb_ep):
  entity_id = endpoints.get(avb_ep)
  print_title("Command: enumerate %s" % avb_ep)
  if args.controller_type == 'python':
    args.master.sendLine(args.controller_id, "enumerate 0x%s" % (
          endpoints.guid_in_ascii(args.user, entity_id)))
  else:
    select_endpoint(args, entity_id)

    descriptors = endpoints.get(avb_ep)['descriptors']
    for dtor in sorted(descriptors.keys()):
      index = 0
      command = "view descriptor %s %d" % (re.sub('\d*_', '', dtor, 1), index)
      args.master.sendLine(args.controller_id, command.encode('ascii', 'ignore'))

def get_expected(args, test_step, src, src_stream, dst, dst_stream, command):
  state.get_current().dump()
  talker_state = state.get_current().get_talker_state(src, src_stream, dst, dst_stream, command)
  talker_expect = sequences.expected_seq(talker_state)(test_step, args.user, src, src_stream, dst, dst_stream)

  listener_state = state.get_current().get_listener_state(src, src_stream, dst, dst_stream, command)
  analyzer_state = "analyzer_" + listener_state
  analyzer_expect = sequences.expected_seq(analyzer_state)(test_step, src, src_stream, dst, dst_stream)
  analyzer_expect += sequences.analyzer_qav_seq(test_step, src, dst, command, args.user)

  if analyzer_expect:
    analyzer_expect = [AllOf(analyzer_expect)]
  listener_expect = sequences.expected_seq(listener_state)(test_step, dst, dst_stream, analyzer_expect)

  controller_state = state.get_current().get_controller_state(args.controller_id,
      src, src_stream, dst, dst_stream, command)
  controller_expect = sequences.expected_seq(controller_state)(args, test_step)
  return (talker_expect, listener_expect, controller_expect)

def get_dual_port_nodes(nodes):
  return [node for node in nodes if endpoints.get(node)['ports'] == 2]

def action_discover(args, test_step, expected, params_list):
  if args.controller_type == 'c':
    yield base.sleep(10)

    print_title("Command: list")
    args.master.sendLine(args.controller_id, "list")

    yield base.sleep(2)

  else:
    args.master.clearExpectHistory(args.controller_id)
    print_title("Command: discover")
    args.master.sendLine(args.controller_id, "discover")

    if test_step.do_checks:
      expected += [Expected(args.controller_id, "Found \d+ entities", 15)]

  yield args.master.expect(None)

def action_enumerate(args, test_step, expected, params_list):
  endpoint_name = choose_src(params_list, 0)

  controller_expect = sequences.controller_enumerate_seq(args, test_step, endpoint_name)
  controller_enumerate(args, endpoint_name)

  if test_step.do_checks:
    expected += controller_expect

  yield args.master.expect(None)

def action_connect(args, test_step, expected, params_list):
  src = choose_src(params_list, 0)
  src_stream = choose_src_stream(params_list, 1)
  dst = choose_dst(params_list, 2)
  dst_stream = choose_dst_stream(params_list, 3)

  controller_connect(args, test_step, expected, src, src_stream, dst, dst_stream)

  (talker_expect, listener_expect, controller_expect) = get_expected(
      args, test_step, src, src_stream, dst, dst_stream, 'connect')

  # Find the path between the src and dst and check whether there are any nodes between them
  forward_enable = []
  nodes = endpoints.get_path_endpoints(graph.find_path(state.get_current(), src, dst))
  for node in get_dual_port_nodes(nodes):
    if graph.node_will_see_stream_enable(state.get_current(), src, src_stream, dst, dst_stream, node):
      forward_enable += sequences.expected_seq('stream_forward_enable')(test_step, args.user,
        endpoints.get(node), endpoints.get(src))
      forward_enable += sequences.expected_seq('port_shaper_connect')(test_step, endpoints.get(node),
          src, src_stream, dst, dst_stream)

  # If there are any nodes in the chain then they must be seen to start forwarding before
  # the listener can be expected to see the stream
  if forward_enable and listener_expect:
    listener_expect = [Sequence([AllOf(forward_enable)] + listener_expect)]
  elif forward_enable:
      listener_expect = forward_enable
  elif listener_expect:
    listener_expect = listener_expect
  else:
    listener_expect = []

  # Expect not to see any enables from other nodes
  not_forward_enable = []
  temp_nodes = set(endpoints.get_all().keys()) - set(nodes)
  for node in get_dual_port_nodes(temp_nodes):
    not_forward_enable += sequences.expected_seq('stream_forward_enable')(test_step, args.user,
      endpoints.get(node), endpoints.get(src))

  if not_forward_enable:
    if test_step.checkpoint is None:
      not_forward_enable = [NoneOf(not_forward_enable)]
    else:
      not_forward_enable = []

  for node in get_dual_port_nodes(temp_nodes):
    not_forward_enable += sequences.expected_seq('port_shaper_connect')(test_step, endpoints.get(node),
          src, src_stream, dst, dst_stream)

  if test_step.do_checks and (talker_expect or listener_expect or controller_expect or not_forward_enable):
    expected += [AllOf(talker_expect + listener_expect + controller_expect + not_forward_enable)]

  yield args.master.expect(None)

def action_disconnect(args, test_step, expected, params_list):
  src = choose_src(params_list, 0)
  src_stream = choose_src_stream(params_list, 1)
  dst = choose_dst(params_list, 2)
  dst_stream = choose_dst_stream(params_list, 3)

  controller_disconnect(args, test_step, expected, src, dst_stream, dst, dst_stream)

  (talker_expect, listener_expect, controller_expect) = get_expected(
      args, test_step, src, src_stream, dst, dst_stream, 'disconnect')

  # Find the path between the src and dst and check whether there are any nodes between them
  forward_disable = []
  nodes = endpoints.get_path_endpoints(graph.find_path(state.get_current(), src, dst))
  for node in get_dual_port_nodes(nodes):
    if graph.node_will_see_stream_disable(state.get_current(), src, src_stream, dst, dst_stream, node):
      forward_disable += sequences.expected_seq('stream_forward_disable')(test_step, args.user,
        endpoints.get(node), endpoints.get(src))
      forward_disable += sequences.expected_seq('port_shaper_disconnect')(test_step, endpoints.get(node),
          src, src_stream, dst, dst_stream)

  # If there are any nodes in the chain then the forward disabling is expected before the
  # audio will be seen to be lost
  if forward_disable and listener_expect:
    listener_expect = [Sequence([AllOf(forward_disable)] + listener_expect)]
  elif forward_disable:
    listener_expect = forward_disable
  elif listener_expect:
    listener_expect = listener_expect
  else:
    listener_expect = []

  # Expect not to see any disables from other nodes
  not_forward_disable = []
  temp_nodes = set(endpoints.get_all().keys()) - set(nodes)
  for node in get_dual_port_nodes(temp_nodes):
    not_forward_disable += sequences.expected_seq('stream_forward_disable')(test_step, args.user,
        endpoints.get(node), endpoints.get(src))

  if not_forward_disable:
    if test_step.checkpoint is None:
      not_forward_disable = [NoneOf(not_forward_disable)]
    else:
      not_forward_disable = []

  for node in get_dual_port_nodes(temp_nodes):
    not_forward_disable += sequences.expected_seq('port_shaper_disconnect')(test_step, endpoints.get(node),
          src, src_stream, dst, dst_stream)

  if test_step.do_checks and (talker_expect or listener_expect or controller_expect or not_forward_disable):
    expected += [AllOf(talker_expect + listener_expect + controller_expect + not_forward_disable)]

  yield args.master.expect(None)

def action_ping(args, test_step, expected, params_list):
  """ Ping a node with and check that it responds accordingly. This is used to test
      connectivity.
  """
  ep_name = choose_src(params_list, 0)
  ep = endpoints.get(ep_name)

  node_expect = [Expected(ep_name, "IDENTIFY Ping", 5)]
  controller_expect = [Expected(args.controller_id, "Success", 5)]

  print_title("Command: identify %s on" % ep_name)
  args.master.sendLine(args.controller_id, "identify 0x%s on" % endpoints.guid_in_ascii(args.user, ep))
  print_title("Command: identify %s off" % ep_name)
  args.master.sendLine(args.controller_id, "identify 0x%s off" % endpoints.guid_in_ascii(args.user, ep))

  if test_step.do_checks and (node_expect or controller_expect):
    expected += [AllOf(node_expect + controller_expect)]

  yield args.master.expect(None)

def action_link_downup(args, test_step, expected, params_list):
  """ Expect all connections which bridge the relay to be lost and restored if there
      is a quick link down/up event. The first argument is the analyzer controlling
      the relay. The second is the time to sleep before restoring the link.
  """
  analyzer_name = choose_analyzer(params_list, 0)
  sleep_time = int(params_list[1])

  lost = []
  # Expect all the connections which cross the relay to be lost
  for c,n in state.get_current().active_connections.iteritems():
    if n and analyzer_name in graph.find_path(state.get_current(), c.talker.src, c.listener.dst):
      lost += sequences.analyzer_listener_disconnect_seq(test_step,
                      c.talker.src, c.talker.src_stream,
                      c.listener.dst, c.listener.dst_stream)

  # Send the command to open the relay '(r)elay (o)pen'
  args.master.sendLine(analyzer_name, "r o")
  state.get_next().set_relay_open(analyzer_name)

  if test_step.do_checks and lost:
    expected += [AllOf(lost)]

  # Perform a sleep as defined by the second argument
  yield base.sleep(sleep_time)

  found = []
  # Expect all the connections which cross the relay to be restored
  state.get_next().set_relay_closed(analyzer_name)
  for c,n in state.get_current().active_connections.iteritems():
    if n and analyzer_name in graph.find_path(state.get_current(), c.talker.src, c.listener.dst):
      found += sequences.analyzer_listener_connect_seq(test_step,
                      c.talker.src, c.talker.src_stream,
                      c.listener.dst, c.listener.dst_stream)

  # Send the command to close the relay '(r)elay (c)lose'
  args.master.sendLine(analyzer_name, "r c")

  if test_step.do_checks and found:
    expected += [AllOf(found)]

  yield args.master.expect(None)

def action_link_up(args, test_step, expected, params_list):
  analyzer_name = choose_analyzer(params_list, 0)

  # Send the command to close the relay '(r)elay (c)lose'
  args.master.sendLine(analyzer_name, "r c")
  state.get_next().set_relay_closed(analyzer_name)

  # Always allow time for the relay to actually be opened
  yield base.sleep(0.1)

def action_link_down(args, test_step, expected, params_list):
  analyzer_name = choose_analyzer(params_list, 0)

  checks = []
  affected_talkers = set()
  # Expect all the connections which cross the relay to be lost
  for c,n in state.get_current().active_connections.iteritems():
    if not n:
      continue

    path = graph.find_path(state.get_current(), c.talker.src, c.listener.dst)
    if path and analyzer_name in path:
      affected_talkers |= set([c.talker])
      checks += [Expected(c.listener.dst, "ADP: Removing entity who timed out -> GUID", 30)]
      checks += sequences.analyzer_listener_disconnect_seq(test_step,
                      c.talker.src, c.talker.src_stream,
                      c.listener.dst, c.listener.dst_stream)
      state.get_next().disconnect(c.talker.src, c.talker.src_stream, c.listener.dst, c.listener.dst_stream)

  for talker in affected_talkers:
    if not state.get_next().talker_active_count(talker.src, talker.src_stream):
      checks += [Expected(talker.src, "Talker stream #%d off" % talker.src_stream, 30)]

  # Send the command to close the relay '(r)elay (c)lose'
  args.master.sendLine(analyzer_name, "r o")
  state.get_next().set_relay_open(analyzer_name)

  if test_step.do_checks and checks:
    expected += [AllOf(checks)]
    yield args.master.expect(None)
  else:
    # At least allow time for the relay to actually be closed
    yield base.sleep(0.1)

def action_check_connections(args, test_step, expected, params_list):
  """ Check that the current state the controller reads from the endpoints matches
      the state the test framework expects.
  """
  checks = []

  # Expect all connections to be restored
  for c,n in state.get_current().active_connections.iteritems():
    if n:
      checks += [Expected(args.controller_id, "0x%s\[%d\] -> 0x%s\[%d\]" % (
                      endpoints.guid_in_ascii(args.user, endpoints.get(c.talker.src)),
                      c.talker.src_stream,
                      endpoints.guid_in_ascii(args.user, endpoints.get(c.listener.dst)),
                      c.listener.dst_stream), 10)]

  print_title("Command: show_connections")
  args.master.sendLine(args.controller_id, "show connections")

  if test_step.do_checks:
    if checks:
      expected += [AllOf(checks)]
    elif test_step.checkpoint is None:
      expected += [NoneOf([Expected(args.controller_id, "->", 5)])]

  yield args.master.expect(None)

def action_sleep(args, test_step, expected, params_list):
  """ Do nothing for the defined time.
  """
  yield base.sleep(int(params_list[0]))

def action_continue(args, test_step, expected, params_list):
  """ Do nothing.
  """
  yield args.master.expect(None)

def action_generator(args, test_step, expected, params_list):
  generator_name = choose_generator(params_list, 0)
  data_rate = choose_generator_rate(params_list, 1)

  if not data_rate:
    # Set generator to silent mode
    args.master.sendLine(generator_name, "m s")
  else:
    # Set a new data rate
    args.master.sendLine(generator_name, "r %d" % data_rate)

    # Apply the changed data rate
    args.master.sendLine(generator_name, "e")

    # Enable the generator
    args.master.sendLine(generator_name, "m d")

  yield args.master.expect(None)
