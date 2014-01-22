import re

import xmos.test.base as base
from xmos.test.base import AllOf, OneOf, NoneOf, Sequence, Expected, getActiveProcesses
import analyzers
import endpoints
import state

def stream_id_from_guid(user, ep, num):
    stream_id = endpoints.get_avb_id(user, ep).replace("fffe","") + "000" + str(num)
    return stream_id.upper()

def expected_seq(name):
    ''' Function to convert from a sequence name to the actual sequence
    '''
    return eval(name + '_seq')

def controller_enumerate_seq(controller_id, descriptors):
    ''' Build an enumerated sequence for an entity by reading from a topology file
    '''

    time_out = 10
    expected_seq = []

    for dtor in sorted(descriptors.keys()):
        temp_string = "AVB 1722.1 {0} ".format(re.sub('\d*_', '', dtor, 1))
        expected_seq.append(Expected(controller_id, temp_string, time_out))
        for dtor_name in descriptors[str(dtor)].keys():
            temp_string = "object_name\s*=\s*\'{0}\'".format(dtor_name)
            expected_seq.append(Expected(controller_id, temp_string, time_out))
            for element in descriptors[str(dtor)][dtor_name]:
                temp_string = "{0}\s*=\s*{1}".format(element['item'], element['value'])
                expected_seq.append(Expected(controller_id, temp_string, time_out))

    return (Sequence(expected_seq))

def controller_success_connect_seq(controller_id):
    return [Expected(controller_id, "Success", 10)]

def controller_listener_exclusive_connect_seq(controller_id):
    return [Expected(controller_id, "Failed with status LISTENER_EXCLUSIVE", 10)]

def controller_success_disconnect_seq(controller_id):
    return [Expected(controller_id, "Success", 10)]

def controller_redundant_disconnect_seq(controller_id):
    return []

def talker_new_connect_seq(ep, stream_num):
  """ Only on the first time the talker is turned on must the 'ready' be seen.
  """
  seq = [Expected(ep['name'], "CONNECTING Talker stream #%d" % stream_num, 10)]
  if not state.get_talker_on_count(ep['name']):
    seq += [Expected(ep['name'], "Talker stream #%d ready" % stream_num, 10)]
  seq += [Expected(ep['name'], "Talker stream #%d on" % stream_num, 10)]

  talker_connection = [Sequence(seq)]
  return talker_connection

def talker_existing_connect_seq(ep, stream_num):
    talker_connection = [
            Sequence([Expected(ep['name'], "CONNECTING Talker stream #%d" % stream_num, 10)])
        ]
    return talker_connection

def talker_all_disconnect_seq(ep, stream_num):
    talker_disconnection = [
            Sequence([Expected(ep['name'], "DISCONNECTING Talker stream #%d" % stream_num, 10),
                      Expected(ep['name'], "Talker stream #%d off" % stream_num, 10)])
        ]
    return talker_disconnection

def talker_existing_disconnect_seq(ep, stream_num):
    talker_disconnection = [
            Sequence([Expected(ep['name'], "DISCONNECTING Talker stream #%d" % stream_num, 10),
                    # Ensure that we don't accidentally trigger the Talker to turn off the stream:
                      NoneOf([Expected(ep['name'], "Talker stream #%d ready" % stream_num, 10),
                              Expected(ep['name'], "Talker stream #%d off" % stream_num, 10)])
                    ])
        ]
    return talker_disconnection

def listener_connect_seq(ep, stream_num):
    listener_connection = [
            Sequence([Expected(ep['name'], "CONNECTING Listener sink #%d" % stream_num, 30),
                      AllOf([Expected(ep['name'], "%d -> %d" % (n, n), 10) for n in range(ep['in_channels'])]),
                      AllOf([Expected(ep['name'], "Media output %d locked" % n, 10) for n in range(ep['in_channels'])]),
                      NoneOf([Expected(ep['name'], "Media output \d+ lost lock", 10)])])
        ]
    return listener_connection

def listener_disconnect_seq(ep, stream_num):
    listener_disconnection = [
            Expected(ep['name'], "DISCONNECTING Listener sink #%d" % stream_num, 10)
        ]
    return listener_disconnection

def redundant_connect_seq(ep, stream_num):
    ''' This sequence may be due to redundant connect from a random test sequence.
        Just ensuring that lock is not lost.
    '''
    empty_seq = [
            NoneOf([Expected(ep['name'], "Media output \d+ lost lock", 2)])
        ]
    return empty_seq

def redundant_disconnect_seq(ep, stream_num):
    ''' This sequence may be due to redundant disconnect from a random test sequence.
        Nothing to test.
    '''
    return []

def stream_forward_enable_seq(user, forward_ep, talker_ep):
    forward_stream = [
            Expected(forward_ep['name'], "1722 router: Enabled forwarding for stream %s" % stream_id_from_guid(user, talker_ep, 0), 10)
        ]
    return forward_stream

def stream_forward_disable_seq(user, forward_ep, talker_ep):
    forward_stream = [
            Expected(forward_ep['name'], "1722 router: Disabled forwarding for stream %s" % stream_id_from_guid(user, talker_ep, 0), 10)
        ]
    return forward_stream

def hook_register_error(args):
  (process_name, patterns) = args
  process = getActiveProcesses()[process_name]
  for pattern in patterns:
    process.registerErrorPattern(pattern)

def hook_unregister_error(args):
  (process_name, patterns) = args
  process = getActiveProcesses()[process_name]
  for pattern in patterns:
    process.unregisterErrorPattern(pattern)

GLITCH_DETECTED_PATTERN = "glitch detected"
LOST_SIGNAL_PATTERN = "Lost signal"

def analyzer_listener_connect_seq(talker_ep, talker_stream_num, listener_ep, listener_stream_num):
  analyzer = listener_ep['analyzer']
  analyzer_name = analyzer['name']
  analyzer_offset = listener_ep['analyzer_offset'] + analyzer['base']

  # Expect both of the stereo channels to lose signal
  signal_detect = [
    Sequence([Expected(analyzer_name, "Channel %d: Signal detected" % (i + analyzer_offset), 10),
              Expected(analyzer_name, "Channel %d: Frequency %d" % (i + analyzer_offset,
                  analyzers.siggen_frequency(talker_ep, i)),
                timeout_time=5,
                completionFn=hook_register_error,
                completionArgs=(analyzer_name, [
                  "Channel %d: %s" % (i + analyzer_offset, GLITCH_DETECTED_PATTERN),
                  "Channel %d: %s" % (i + analyzer_offset, LOST_SIGNAL_PATTERN)]))])
      for i in range(0, 2)
  ]
  return signal_detect

def analyzer_redundant_connect_seq(talker_ep, talker_stream_num, listener_ep, listener_stream_num):
  return []

def analyzer_qav_seq(src, dst, command, connections, user):
  """ Get the expected sequence for any QAV analyzers active.
  """
  analyzer_expect = []

  for analyzer_name,analyzer in analyzers.get_all_analyzers().iteritems():
    if analyzer['type'] != 'qav':
      continue

    # If the analyzer is a QAV analyzer then it will detect the stream through
    # the packets being forwarded through it
    if analyzer_name in state.find_path(connections, src, dst):
      guid_string = endpoints.guid_in_ascii(user, endpoints.entity_by_name(src))
      stream_string = endpoints.stream_from_guid(guid_string)
      if command == 'connect':
        action_string = "Adding"
        completionFn = hook_register_error
      else:
        action_string = "Removing"
        completionFn = hook_unregister_error

      analyzer_expect += [Expected(analyzer_name, "%s stream 0x%s" % (action_string, stream_string),
            timeout_time=10,
            completionFn=completionFn,
            completionArgs=(analyzer_name, ['ERROR']))]

  return analyzer_expect

def analyzer_listener_disconnect_seq(talker_ep, talker_stream_num, listener_ep, listener_stream_num):
  analyzer = listener_ep['analyzer']
  analyzer_name = analyzer['name']
  analyzer_offset = listener_ep['analyzer_offset'] + analyzer['base']

  # Expect both of the stereo channels to lose signal
  signal_lost = [
    Expected(analyzer_name, "Channel %d: Lost signal" % (i + analyzer_offset),
        timeout_time=5,
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

def analyzer_redundant_disconnect_seq(talker_ep, talker_stream_num, listener_ep, listener_stream_num):
  return []
