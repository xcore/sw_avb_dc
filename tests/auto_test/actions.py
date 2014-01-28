from xmos.test.process import getEntities, ControllerProcess
import xmos.test.base as base
import xmos.test.xmos_logging as xmos_logging
from xmos.test.base import AllOf, OneOf, NoneOf, Sequence, Expected, getActiveProcesses
from xmos.test.xmos_logging import log_error, log_warning, log_info, log_debug

import sequences
import state
import endpoints
import analyzers
import graph

def check_set_clock_masters(args, test_step, expected):
  for loop in graph.get_loops(state.get_current()):
    loop_master = loop[0]
    for ep_name in loop:
      if state.get_current().is_clock_source_master(ep_name):
        loop_master = ep_name
        break

    if not state.get_current().is_clock_source_master(loop_master):
      ep = endpoints.get(loop_master)
      args.master.sendLine(args.controller_id, "set_clock_source_master 0x%s" % (
            endpoints.guid_in_ascii(args.user, ep)))
      state.get_next().set_clock_source_master(ep['name'])

      if do_checks:
        controller_expect = [Expected(args.controller_id, "Success", 5)]
        ep_expect = [Expected(loop_master, "Setting clock source: LOCAL_CLOCK", 5)]
        yield args.master.expect(AllOf(controller_expect + ep_expect))

def check_clear_clock_masters(args, do_checks):
  for name,ep in endpoints.get_all().iteritems():
    if state.get_current().is_clock_source_master(name) and not graph.is_in_loop(state.get_current(), ep['name']):
      args.master.sendLine(args.controller_id, "set_clock_source_slave 0x%s" % (
            endpoints.guid_in_ascii(args.user, ep)))
      state.get_next().set_clock_source_slave(ep['name'])

      if do_checks:
        controller_expect = [Expected(args.controller_id, "Success", 5)]
        ep_expect = [Expected(ep['name'], "Setting clock source: INPUT_STREAM_DERIVED", 5)]
        yield args.master.expect(AllOf(controller_expect + ep_expect))

def controller_connect(args, do_checks, src, src_stream, dst, dst_stream):
  talker_ep = endpoints.get(src)
  listener_ep = endpoints.get(dst)

  state.get_next().connect(src, src_stream, dst, dst_stream)
  check_set_clock_masters(args, test_step, expected)

  args.master.sendLine(args.controller_id, "connect 0x%s %d 0x%s %d" % (
        endpoints.guid_in_ascii(args.user, talker_ep), src_stream,
        endpoints.guid_in_ascii(args.user, listener_ep), dst_stream))

def controller_disconnect(args, do_checks, src, src_stream, dst, dst_stream):
  talker_ep = endpoints.get(src)
  listener_ep = endpoints.get(dst)

  state.get_next().disconnect(src, src_stream, dst, dst_stream)
  check_clear_clock_masters(args, test_step, expected)

  args.master.sendLine(args.controller_id, "disconnect 0x%s %d 0x%s %d" % (
        endpoints.guid_in_ascii(args.user, talker_ep), src_stream,
        endpoints.guid_in_ascii(args.user, listener_ep), dst_stream))

def controller_enumerate(args, avb_ep):
  entity_id = endpoints.get(avb_ep)
  args.master.sendLine(args.controller_id, "enumerate 0x%s" % (
        endpoints.guid_in_ascii(args.user, entity_id)))

def get_expected(args, src, src_stream, dst, dst_stream, command):
  state.get_current().dump()
  talker_state = state.get_current().get_talker_state(src, src_stream, dst, dst_stream, command)
  talker_expect = sequences.expected_seq(talker_state)(test_step, args.user, src, src_stream, dst, dst_stream)

  listener_expect = sequences.expected_seq(listener_state)(endpoints.get(dst), dst_stream)
  listener_state = state.get_current().get_listener_state(src, src_stream, dst, dst_stream, command)
  analyzer_state = "analyzer_" + listener_state
  analyzer_expect = sequences.expected_seq(analyzer_state)(endpoints.get(src), src_stream,
      endpoints.get(dst), dst_stream)

  analyzer_expect += sequences.analyzer_qav_seq(src, dst, command, args.user)

  controller_state = state.get_current().get_controller_state(args.controller_id,
      src, src_stream, dst, dst_stream, command)
  controller_expect = sequences.expected_seq(controller_state)(args.controller_id)
  return (talker_expect, listener_expect, controller_expect, analyzer_expect)

def get_dual_port_nodes(nodes):
  return [node for node in nodes if endpoints.get(node)['ports'] == 2]

def action_discover(args, do_checks, params_list):
  args.master.clearExpectHistory(args.controller_id)
  args.master.sendLine(args.controller_id, "discover")
  visible_endpoints = graph.get_endpoints_connected_to(args.controller_id)

  if do_checks:
    yield args.master.expect(Expected(args.controller_id, "Found %d entities" % len(visible_endpoints), 15))

def action_enumerate(args, do_checks, params_list):
  endpoint_name = params_list[0]

  controller_expect = sequences.controller_enumerate_seq(args.controller_id, endpoint_name)
  controller_enumerate(args, endpoint_name)

  if do_checks:
    yield args.master.expect(controller_expect)

def action_connect(args, do_checks, params_list):
  src = params_list[0]
  src_stream = int(params_list[1])
  dst = params_list[2]
  dst_stream = int(params_list[3])

  (talker_expect, listener_expect, controller_expect, analyzer_expected) = get_expected(
      args, src, src_stream, dst, dst_stream, 'connect')

  # Find the path between the src and dst and check whether there are any nodes between them
  forward_enable = []
  nodes = endpoints.get_path_endpoints(graph.find_path(src, dst))
  for node in get_dual_port_nodes(nodes):
    if graph.node_will_see_stream_enable(src, src_stream, dst, dst_stream, node):
      forward_enable += sequences.expected_seq('stream_forward_enable')(args.user,
        endpoints.get(node), endpoints.get(src))
      forward_enable += sequences.expected_seq('port_shaper_connect')(endpoints.get(node),
          src, src_stream, dst, dst_stream)

  # If there are any nodes in the chain then they must be seen to start forwarding before
  # the listener can be expected to see the stream
  if forward_enable:
    listener_expect = [Sequence([AllOf(forward_enable), AllOf(listener_expect + analyzer_expected)])]
  elif listener_expect or analyzer_expected:
    listener_expect = [AllOf(listener_expect + analyzer_expected)]

  # Expect not to see any enables from other nodes
  not_forward_enable = []
  temp_nodes = set(endpoints.get_all().keys()) - set(nodes)
  for node in get_dual_port_nodes(temp_nodes):
    not_forward_enable += sequences.expected_seq('stream_forward_enable')(args.user,
      endpoints.get(node), endpoints.get(src))

  if not_forward_enable:
    not_forward_enable = [NoneOf(not_forward_enable)]

  for node in get_dual_port_nodes(temp_nodes):
    not_forward_enable += sequences.expected_seq('port_shaper_connect')(endpoints.get(node),
          src, src_stream, dst, dst_stream)

  for y in controller_connect(args, do_checks, src, src_stream, dst, dst_stream):
    yield y

  if do_checks:
    yield args.master.expect(AllOf(talker_expect + listener_expect +
          controller_expect + not_forward_enable))

def action_disconnect(args, do_checks, params_list):
  src = params_list[0]
  src_stream = int(params_list[1])
  dst = params_list[2]
  dst_stream = int(params_list[3])

  (talker_expect, listener_expect, controller_expect, analyzer_expected) = get_expected(
      args, src, src_stream, dst, dst_stream, 'disconnect')

  # Find the path between the src and dst and check whether there are any nodes between them
  forward_disable = []
  nodes = endpoints.get_path_endpoints(graph.find_path(src, dst))
  for node in get_dual_port_nodes(nodes):
    if graph.node_will_see_stream_disable(src, src_stream, dst, dst_stream, node):
      forward_disable += sequences.expected_seq('stream_forward_disable')(args.user,
        endpoints.get(node), endpoints.get(src))
      forward_disable += sequences.expected_seq('port_shaper_disconnect')(endpoints.get(node),
          src, src_stream, dst, dst_stream)

  # If there are any nodes in the chain then the forward disabling is expected before the
  # audio will be seen to be lost
  if forward_disable:
    listener_expect = [Sequence([AllOf(forward_disable), AllOf(listener_expect + analyzer_expected)])]
  elif listener_expect or analyzer_expected:
    listener_expect = [AllOf(listener_expect + analyzer_expected)]

  # Expect not to see any disables from other nodes
  not_forward_disable = []
  temp_nodes = set(endpoints.get_all().keys()) - set(nodes)
  for node in get_dual_port_nodes(temp_nodes):
    not_forward_disable += sequences.expected_seq('stream_forward_disable')(args.user,
      endpoints.get(node), endpoints.get(src))

  if not_forward_disable:
    not_forward_disable = [NoneOf(not_forward_disable)]

  for node in get_dual_port_nodes(temp_nodes):
    not_forward_disable += sequences.expected_seq('port_shaper_disconnect')(endpoints.get(node),
          src, src_stream, dst, dst_stream)

  for y in controller_disconnect(args, do_checks, src, dst_stream, dst, dst_stream):
    yield y

  if do_checks:
    yield args.master.expect(AllOf(talker_expect + listener_expect +
          controller_expect + not_forward_disable))

def action_ping(args, do_checks, params_list):
  """ Ping a node with and check that it responds accordingly. This is used to test
      connectivity.
  """
  node_name = params_list[0]
  ep = endpoints.get(node_name)

  node_expect = [Expected(ep['name'], "IDENTIFY Ping", 5)]
  controller_expect = [Expected(args.controller_id, "Success", 5)]

  args.master.sendLine(args.controller_id, "identify 0x%s on" % endpoints.guid_in_ascii(args.user, ep))
  args.master.sendLine(args.controller_id, "identify 0x%s off" % endpoints.guid_in_ascii(args.user, ep))

  if do_checks:
    yield args.master.expect(AllOf(node_expect + controller_expect))

def action_link_downup(args, do_checks, params_list):
  """ Expect all connections which bridge the relay to be lost and restored if there
      is a quick link down/up event. The first argument is the analyzer controlling
      the relay. The second is the time to sleep before restoring the link.
  """
  analyzer_name = params_list[0]
  sleep_time = int(params_list[1])
  expected = []

  # Expect all the connections which cross the relay to be lost
    if n and analyzer_name in graph.find_path(c.talker.src, c.listener.dst):
      expected += sequences.analyzer_listener_disconnect_seq(
  for c,n in state.get_current().active_connections.iteritems():
                      endpoints.get(c.talker.src), c.talker.src_stream,
                      endpoints.get(c.listener.dst), c.listener.dst_stream)

  # Send the command to open the relay '(r)elay (o)pen'
  args.master.sendLine(analyzer_name, "r o")
  state.get_next().set_relay_open(analyzer_name)

  if do_checks and expected:
    yield args.master.expect(AllOf(expected))

  # Perform a sleep as defined by the second argument
  yield base.sleep(sleep_time)

  expected = []

  # Expect all the connections which cross the relay to be restored
  state.get_next().set_relay_closed(analyzer_name)
  for c,n in state.get_current().active_connections.iteritems():
    if n and analyzer_name in graph.find_path(state.get_current(), c.talker.src, c.listener.dst):
      found += sequences.analyzer_listener_connect_seq(test_step,
                      endpoints.get(c.talker.src), c.talker.src_stream,
                      endpoints.get(c.listener.dst), c.listener.dst_stream)

  # Send the command to close the relay '(r)elay (c)lose'
  args.master.sendLine(analyzer_name, "r c")

  if do_checks and expected:
    yield args.master.expect(AllOf(expected))

def action_link_up(args, do_checks, params_list):
  analyzer_name = params_list[0]

  # Send the command to close the relay '(r)elay (c)lose'
  args.master.sendLine(analyzer_name, "r c")
  state.get_next().set_relay_closed(analyzer_name)

  # Always allow time for the relay to actually be opened
  yield base.sleep(0.1)

def action_link_down(args, do_checks, params_list):
  analyzer_name = params_list[0]

  expected = []
  affected_talkers = set()
  # Expect all the connections which cross the relay to be lost
  for c,n in state.get_current().active_connections.iteritems():
    if not n:
      continue

    path = graph.find_path(c.talker.src, c.listener.dst)
    if path and analyzer_name in path:
      affected_talkers |= set([c.talker])
      expected += [Expected(c.listener.dst, "ADP: Removing entity who timed out -> GUID", 30)]
      expected += sequences.analyzer_listener_disconnect_seq(
                      endpoints.get(c.talker.src), c.talker.src_stream,
                      endpoints.get(c.listener.dst), c.listener.dst_stream)
      state.get_next().disconnect(c.talker.src, c.talker.src_stream, c.listener.dst, c.listener.dst_stream)

  for talker in affected_talkers:
      expected += [Expected(talker.src, "Talker stream #%d off" % talker.src_stream, 30)]
    if not state.get_next().talker_active_count(talker.src, talker.src_stream):

  # Send the command to close the relay '(r)elay (c)lose'
  args.master.sendLine(analyzer_name, "r o")
  state.get_next().set_relay_open(analyzer_name)

  if do_checks and expected:
    yield args.master.expect(AllOf(expected))
  else:
    # At least allow time for the relay to actually be closed
    yield base.sleep(0.1)

def action_check_connections(args, do_checks, params_list):
  """ Check that the current state the controller reads from the endpoints matches
      the state the test framework expects.
  """
  expected = []

  # Expect all connections to be restored
  for c,n in state.get_current().active_connections.iteritems():
    if n:
      expected += [Expected(args.controller_id, "0x%s\[%d\] -> 0x%s\[%d\]" % (
                      endpoints.guid_in_ascii(args.user, endpoints.get(c.talker.src)),
                      c.talker.src_stream,
                      endpoints.guid_in_ascii(args.user, endpoints.get(c.listener.dst)),
                      c.listener.dst_stream), 10)]

  args.master.sendLine(args.controller_id, "show connections")

  if do_checks:
    if expected:
      yield args.master.expect(AllOf(expected))
    else:
      yield args.master.expect(NoneOf([Expected(args.controller_id, "->", 5)]))

def action_sleep(args, do_checks, params_list):
  """ Do nothing for the defined time.
  """
  yield base.sleep(int(params_list[0]))

def action_continue(args, do_checks, params_list):
  """ Do nothing.
  """
  yield args.master.expect(None)

