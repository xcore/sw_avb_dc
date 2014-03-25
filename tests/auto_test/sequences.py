import re
import itertools

import xmos.test.base as base
from xmos.test.base import AllOf, OneOf, NoneOf, Sequence, Expected, getActiveProcesses

import analyzers
import endpoints
import state
import graph

# For checkpoint sequences, keep track of the last value per endpoint
final_port_shaper_states = {}

def get_and_clear_final_port_shaper_states():
  expected = [ a for a in itertools.chain(*final_port_shaper_states.values()) ]
  final_port_shaper_states.clear()
  return expected

def stream_id_from_guid(user, ep, num):
    stream_id = endpoints.get_avb_id(user, ep).replace("fffe","") + "000" + str(num)
    return stream_id.upper()

def expected_seq(name):
    """ Function to convert from a sequence name to the actual sequence
    """
    return eval(name + '_seq')


#
# Controller sequences
#
def controller_enumerate_seq(args, test_step, endpoint_name):
    """ Build an enumerated sequence for an entity by reading from a topology file
    """
    expected_seq = []
    descriptors = endpoints.get(endpoint_name)['descriptors']

    if args.controller_type == 'python':
      # The python controller reads the descriptors each time. The C controller has
      # them cached and so can always return the values.
      visible_endpoints = graph.get_endpoints_connected_to(state.get_current(), args.controller_id)
      if endpoint_name not in visible_endpoints:
        return [Expected(args.controller_id, "No descriptors found", 10, consumeOnMatch=True)]

      for dtor in sorted(descriptors.keys()):
        # Note that the .* is required because the STREAM_INPUT/STREAM_OUTPUT are mapped to the same descriptor
        temp_string = "AVB 1722\.1.*%s" % re.sub('\d*_', '', dtor, 1)
        expected_seq.append(Expected(args.controller_id, temp_string, 10, consumeOnMatch=True))
        for dtor_name in descriptors[str(dtor)].keys():
          temp_string = "object_name\s*=\s*\'%s\'" % dtor_name
          expected_seq.append(Expected(args.controller_id, temp_string, 10, consumeOnMatch=True))
          for element in descriptors[str(dtor)][dtor_name]:
            element_type = element.get('type', 'none')
            if element_type == 'hex':
              temp_string = "%s\s*=\s*0x%x" % (element['item'], element['value'])
            elif element_type == 'state':
              value = eval('state.get_current().get_%s' % element['item'])(endpoint_name)
              temp_string = "%s\s*=\s*%s" % (element['item'], value)
            else:
              temp_string = "%s\s*=\s*%s" % (element['item'], element['value'])
            expected_seq.append(Expected(args.controller_id, temp_string, 10, consumeOnMatch=True))

    else:
      for dtor in sorted(descriptors.keys()):
        temp_string = "descriptor_type: %s" % re.sub('\d*_', '', dtor, 1)
        expected_seq.append(Expected(args.controller_id, temp_string, 10, consumeOnMatch=True))
        for dtor_name in descriptors[str(dtor)].keys():
          temp_string = "object_name\s*=\s*%s" % dtor_name
          expected_seq.append(Expected(args.controller_id, temp_string, 10, consumeOnMatch=True))
          for element in descriptors[str(dtor)][dtor_name]:
            element_type = element.get('type', 'none')
            if element_type == 'flag':
              temp_string = "%s\s*=\s*1" % element['value'].lower()
            elif element_type == 'state':
              value = eval('state.get_current().get_%s' % element['item'])(endpoint_name)
              temp_string = "%s\s*=\s*%s" % (element['item'], value)
            else:
              temp_string = "%s\s*=\s*%s" % (element['item'], element['value'])
            expected_seq.append(Expected(args.controller_id, temp_string, 10, consumeOnMatch=True))

    return [Sequence(expected_seq)]

def controller_success_connect_seq(args, test_step):
  if args.controller_type == 'python':
    return [Expected(args.controller_id, "Success", 10, consumeOnMatch=True)]
  else:
    return [Expected(args.controller_id, "NOTIFICATION.*CONNECT_RX_RESPONSE.*SUCCESS", 10, consumeOnMatch=True)]

def controller_success_set_clock_source_seq(args, test_step):
  if args.controller_type == 'python':
    return [Expected(args.controller_id, "Success", 10, consumeOnMatch=True)]
  else:
    return [Expected(args.controller_id, "NOTIFICATION.*SET_CLOCK_SOURCE.*SUCCESS", 10, consumeOnMatch=True)]

def controller_listener_exclusive_connect_seq(args, test_step):
  if args.controller_type == 'python':
    return [Expected(args.controller_id, "Failed with status LISTENER_EXCLUSIVE", 10, consumeOnMatch=True)]
  else:
    return [Expected(args.controller_id, "NOTIFICATION.*CONNECT_RX_RESPONSE.*LISTENER_EXCLUSIVE", 10, consumeOnMatch=True)]

def controller_listener_talker_timeout_connect_seq(args, test_step):
  if args.controller_type == 'python':
    return [Expected(args.controller_id, "Failed with status LISTENER_TALKER_TIMEOUT", 10, consumeOnMatch=True)]
  else:
    return [Expected(args.controller_id, "NOTIFICATION.*CONNECT_RX_RESPONSE.*LISTENER_TALKER_TIMEOUT", 10, consumeOnMatch=True)]

def controller_timeout_connect_seq(args, test_step):
  return [Expected(args.controller_id, "Timed out", 10, consumeOnMatch=True)]

def controller_success_disconnect_seq(args, test_step):
  if args.controller_type == 'python':
    return [Expected(args.controller_id, "Success", 10, consumeOnMatch=True)]
  else:
    return [Expected(args.controller_id, "NOTIFICATION.*DISCONNECT_RX_RESPONSE.*SUCCESS", 10, consumeOnMatch=True)]

def controller_redundant_disconnect_seq(args, test_step):
  if args.controller_type == 'python':
    return []
  else:
    return [Expected(args.controller_id, "NOTIFICATION.*DISCONNECT_RX_RESPONSE.*NOT_CONNECTED", 10, consumeOnMatch=True)]

def controller_timeout_disconnect_seq(args, test_step):
  return [Expected(args.controller_id, "Timed out", 10, consumeOnMatch=True)]


#
# Talker sequences
#
def talker_new_connect_seq(test_step, user, src, src_stream, dst, dst_stream):
  """ Only on the first time the talker is turned on must the 'ready' be seen.
  """
  stream_id = endpoints.stream_from_guid(endpoints.guid_in_ascii(user, endpoints.get(src)))
  listener_mac = endpoints.mac_in_ascii(user, endpoints.get(dst))
  seq = [Expected(src, "CONNECTING Talker stream #%d \(%s\) -> Listener %s" %
            (src_stream, stream_id, listener_mac), 10)]
  if not state.get_current().get_talker_on_count(src):
    seq += [Expected(src, "Talker stream #%d ready" % src_stream, 10)]
  seq += [Expected(src, "Talker stream #%d on" % src_stream, 10)]

  # If in a sequence of commands then the order cannot be guaranteed - so only
  # expect a Sequence when not checkpointing
  if test_step.checkpoint is None:
    talker_connection = [Sequence(seq)]
  else:
    talker_connection = [AllOf(seq)]
  return talker_connection

def talker_existing_connect_seq(test_step, user, src, src_stream, dst, dst_stream):
  stream_id = endpoints.stream_from_guid(endpoints.guid_in_ascii(user, endpoints.get(src)))
  listener_mac = endpoints.mac_in_ascii(user, endpoints.get(dst))
  talker_connection = [
        Sequence([Expected(src, "CONNECTING Talker stream #%d \(%s\) -> Listener %s" %
                    (src_stream, stream_id, listener_mac), 10)])
    ]
  return talker_connection

def talker_self_connect_seq(test_step, user, src, src_stream, dst, dst_stream):
  """ Even though attempting to connect to self, the talker will become ready. Can
      only guarantee this message will be printed the first time the talker is
      activated.
  """
  if state.get_current().get_talker_on_count(src):
    talker_connection = []
  else:
    talker_connection = [Expected(src, "Talker stream #%d ready" % src_stream, 10)]

  return talker_connection

def talker_all_disconnect_seq(test_step, user, src, src_stream, dst, dst_stream):
  talker_disconnection = [
        Sequence([Expected(src, "DISCONNECTING Talker stream #%d" % src_stream, 10),
                  Expected(src, "Talker stream #%d off" % src_stream, 10)])
    ]
  return talker_disconnection

def talker_existing_disconnect_seq(test_step, user, src, src_stream, dst, dst_stream):
  talker_disconnection = [Expected(src, "DISCONNECTING Talker stream #%d" % src_stream, 10)]

  if test_step.checkpoint is None:
    # Ensure that we don't accidentally trigger the Talker to turn off the stream:
    return [Sequence(talker_disconnection +
              [NoneOf([Expected(src, "Talker stream #%d ready" % src_stream, 10),
                      Expected(src, "Talker stream #%d off" % src_stream, 10)])
           ])]
  else:
    return talker_disconnection

def talker_redundant_connect_seq(test_step, user, src, src_stream, dst, dst_stream):
    if test_step.checkpoint is None:
      return [NoneOf([Expected(src, "Media output \d+ lost lock", 2)])]
    else:
      return []

def talker_redundant_disconnect_seq(test_step, user, src, src_stream, dst, dst_stream):
    return []


#
# Listener sequences
#
def listener_connect_seq(test_step, dst, dst_stream, analyzer_expect):
  ep = endpoints.get(dst)
  listener_connection = [
      Expected(dst, "CONNECTING Listener sink #%d" % dst_stream, 20),
      AllOf([Expected(dst, "%d -> %d" % (n, n), 10) for n in range(ep['in_channels'])]),
      AllOf([Expected(dst, "Media output %d locked" % n, 10) for n in range(ep['in_channels'])])
  ]
  listener_connection += analyzer_expect
  if test_step.checkpoint is None:
    return [Sequence(listener_connection +
              [NoneOf([Expected(dst, "Media output \d+ lost lock", 10)])
           ])]
  else:
    return [Sequence(listener_connection)]

def listener_disconnect_seq(test_step, dst, dst_stream, analyzer_expect):
  listener_disconnection = [
          Expected(dst, "DISCONNECTING Listener sink #%d" % dst_stream, 10)
      ]
  listener_disconnection += analyzer_expect
  return listener_disconnection

def listener_redundant_connect_seq(test_step, dst, dst_stream, analyzer_expect):
    if test_step.checkpoint is None:
      expected = [NoneOf([Expected(dst, "Media output \d+ lost lock", 2)])]
      expected += analyzer_expect
      return expected
    else:
      return analyzer_expect

def listener_redundant_disconnect_seq(test_step, dst, dst_stream, analyzer_expect):
    return analyzer_expect


#
# Stream sequences
#
def stream_forward_enable_seq(test_step, user, forward_ep, talker_ep):
    forward_stream = [
            Expected(forward_ep['name'], "1722 router: Enabled forwarding for stream %s" % stream_id_from_guid(user, talker_ep, 0), 10)
        ]
    return forward_stream

def stream_forward_disable_seq(test_step, user, forward_ep, talker_ep):
    forward_stream = [
            Expected(forward_ep['name'], "1722 router: Disabled forwarding for stream %s" % stream_id_from_guid(user, talker_ep, 0), 10)
        ]
    return forward_stream

def port_shaper_change_seq(test_step, ep, port, action):
    expected = graph.calculate_expected_bandwidth(state.get_next(), ep, port)
    return [ Expected(ep['name'], "%s port %d shaper bandwidth to %s" % (action, port, expected), 10) ]

def port_shaper_no_change_seq(test_step, ep):
  if test_step.checkpoint is None:
    return [NoneOf([Expected(ep['name'], "port \d+ shaper bandwidth", 10)])]
  else:
    return []

def port_shaper_connect_seq(test_step, forward_ep, src, src_stream, dst, dst_stream):
  expect_change = False

  if not state.get_current().connected(src, src_stream, dst, dst_stream) and \
      not state.get_current().listener_active_count(dst, dst_stream):
    forward_port = graph.get_forward_port(state.get_current(), src, dst, forward_ep['name'])

    if forward_port is not None:
      expect_change = graph.port_will_see_bandwidth_change(state.get_current(), src, src_stream,
          forward_ep['name'], forward_port, 'connect')

  if expect_change:
    expected = port_shaper_change_seq(test_step, forward_ep, forward_port, 'Increasing')
  else:
    expected = port_shaper_no_change_seq(test_step, forward_ep)

  # When running a sequences of checkpointed tests don't check shaper bandwidth
  # figures for interim steps. Instead, keep track of the state per end-point so
  # that the final state can be returned at the last checkpoint
  if test_step.checkpoint is not None:
    global final_port_shaper_states
    if not test_step.checkpoint and expected:
      if forward_port is None:
        final_port_shaper_states['%s' % forward_ep['name']] = expected
      else:
        final_port_shaper_states['%s_%s' % (forward_ep['name'], forward_port)] = expected
      expected = []

  return expected

def port_shaper_disconnect_seq(test_step, forward_ep, src, src_stream, dst, dst_stream):
  expect_change = False

  if state.get_current().connected(src, src_stream, dst, dst_stream):
    forward_port = graph.get_forward_port(state.get_current(), src, dst, forward_ep['name'])

    if forward_port is not None:
      expect_change = graph.port_will_see_bandwidth_change(state.get_current(), src, src_stream,
          forward_ep['name'], forward_port, 'disconnect')

  if expect_change:
    expected = port_shaper_change_seq(test_step, forward_ep, forward_port, 'Decreasing')
  else:
    expected = port_shaper_no_change_seq(test_step, forward_ep)

  # When running a sequences of checkpointed tests don't check shaper bandwidth
  # figures for interim steps. Instead, keep track of the state per end-point so
  # that the final state can be returned at the last checkpoint.
  if test_step.checkpoint is not None:
    global final_port_shaper_states
    if not test_step.checkpoint and expected:
      if forward_port is None:
        final_port_shaper_states['%s' % forward_ep['name']] = expected
      else:
        final_port_shaper_states['%s_%s' % (forward_ep['name'], forward_port)] = expected
      expected = []

  return expected

#
# Analyzer sequences
#
def hook_register_error(expected):
  (process_name, patterns) = expected.completionArgs
  process = getActiveProcesses()[process_name]
  for pattern in patterns:
    process.registerErrorPattern(pattern)

def hook_unregister_error(expected):
  (process_name, patterns) = expected.completionArgs
  process = getActiveProcesses()[process_name]
  for pattern in patterns:
    process.unregisterErrorPattern(pattern)

GLITCH_DETECTED_PATTERN = "glitch detected"
LOST_SIGNAL_PATTERN = "Lost signal"

def analyzer_listener_connect_seq(test_step, src, src_stream, dst, dst_stream):
  listener_ep = endpoints.get(dst)
  analyzer = listener_ep['analyzer']
  analyzer_name = analyzer['name']
  analyzer_offset = listener_ep['analyzer_offset'] + analyzer['base']

  # Expect both of the stereo channels to lose signal
  signal_detect = [
    Sequence([Expected(analyzer_name, "Channel %d: Signal detected" % (i + analyzer_offset), 10),
              Expected(analyzer_name, "Channel %d: Frequency %d" % (i + analyzer_offset,
                  analyzers.siggen_frequency(endpoints.get(src), i)),
                timeoutTime=5,
                completionFn=hook_register_error,
                completionArgs=(analyzer_name, [
                  "Channel %d: %s" % (i + analyzer_offset, GLITCH_DETECTED_PATTERN),
                  "Channel %d: %s" % (i + analyzer_offset, LOST_SIGNAL_PATTERN)]))])
      for i in range(0, 2)
  ]
  return signal_detect

def analyzer_listener_redundant_connect_seq(test_step, src, src_stream, dst, dst_stream):
  return []

def analyzer_listener_disconnect_seq(test_step, src, src_stream, dst, dst_stream):
  listener_ep = endpoints.get(dst)
  analyzer = listener_ep['analyzer']
  analyzer_name = analyzer['name']
  analyzer_offset = listener_ep['analyzer_offset'] + analyzer['base']

  # Expect both of the stereo channels to lose signal
  signal_lost = [
    Expected(analyzer_name, "Channel %d: Lost signal" % (i + analyzer_offset),
        timeoutTime=5,
        completionFn=hook_unregister_error,
        completionArgs=(analyzer_name, [
          "Channel %d: %s" % (i + analyzer_offset, GLITCH_DETECTED_PATTERN)]))
      for i in range(0, 2)
  ]

  # Unregister the lost signal error pattern now
  process = getActiveProcesses()[analyzer_name]
  for i in range(0, 2):
    process.unregisterErrorPattern("Channel %d: %s" % (i + analyzer_offset, LOST_SIGNAL_PATTERN))

  return signal_lost

def analyzer_listener_redundant_disconnect_seq(test_step, src, src_stream, dst, dst_stream):
  return []

def analyzer_qav_seq(test_step, src, dst, action, user):
  """ Get the expected sequence for any QAV analyzers active.
  """
  analyzer_expect = []

  for analyzer_name,analyzer in analyzers.get_all().iteritems():
    if analyzer['type'] != 'qav':
      continue

    # If the analyzer is a QAV analyzer then it will detect the stream through
    # the packets being forwarded through it
    if analyzer_name in graph.find_path(state.get_current(), src, dst):
      guid_string = endpoints.guid_in_ascii(user, endpoints.get(src))
      stream_string = endpoints.stream_from_guid(guid_string)
      if action == 'connect':
        action_string = "Adding"
        completionFn = hook_register_error
      else:
        action_string = "Removing"
        completionFn = hook_unregister_error

      analyzer_expect += [Expected(analyzer_name, "%s stream 0x%s" % (action_string, stream_string),
            timeoutTime=10,
            completionFn=completionFn,
            completionArgs=(analyzer_name, ['ERROR']))]

  return analyzer_expect

