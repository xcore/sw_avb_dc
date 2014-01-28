import copy

import xmos.test.base as base
import xmos.test.xmos_logging as xmos_logging
from xmos.test.xmos_logging import log_error, log_warning, log_info, log_debug

import endpoints
import state_rendering as rendering
import graph

class Connection(object):
  def __init__(self, talker, listener):
    self.talker = talker
    self.listener = listener

  def __eq__(self, another):
    return (hasattr(another, 'talker') and
            hasattr(another, 'listener') and
            self.talker == another.talker and
            self.listener == another.listener)

  def __hash__(self):
    return hash(self.__str__())

  def __repr__(self):
    return "Connection(%r, %r)" % (self.talker, self.listener)

  def __str__(self):
    return str(self.talker) + "->" + str(self.listener)


class Talker(object):
  def __init__(self, src, src_stream):
    self.src = src
    self.src_stream = src_stream

  def __eq__(self, another):
    return (hasattr(another, 'src') and
            hasattr(another, 'src_stream') and
            self.src == another.src and
            self.src_stream == another.src_stream)

  def __hash__(self):
    return hash(self.__str__())

  def __repr__(self):
    return "Talker(%r, %r)" % (self.src, self.src_stream)

  def __str__(self):
    return self.src + ":" + str(self.src_stream)


class Listener(object):
  def __init__(self, dst, dst_stream):
    self.dst = dst
    self.dst_stream = dst_stream

  def __eq__(self, another):
    return (hasattr(another, 'dst') and
            hasattr(another, 'dst_stream') and
            self.dst == another.dst and
            self.dst_stream == another.dst_stream)

  def __hash__(self):
    return hash(self.__str__())

  def __repr__(self):
    return "Listener(%r, %r)" % (self.dst, self.dst_stream)

  def __str__(self):
    return self.dst + ":" + str(self.dst_stream)


class State(object):
  def __init__(self):
    """ Track the current connections in the topology.
         - active_connections contains the list of connections (src:src_stream->dst:dst_stream)
         - active_talkers     contains the active talkers (src:src_stream) and the count of how may times they are used
         - active_listeners   contains the active listeners (dst:dst_stream). They can only accept one connection.
    """
    self.active_connections = {}
    self.active_talkers = {}
    self.active_listeners = {}
    self.talker_on_count = {}
    self.clock_source_master = {}
    self.open_relays = {}

  def dump(self):
    log_debug("State:")
    for t,n in self.active_talkers.iteritems():
      log_debug("Talker %s : %d" % (t, n))
    for l,n in self.active_listeners.iteritems():
      log_debug("Listeners %s : %d" % (l, n))
    for c,n in self.active_connections.iteritems():
      log_debug("Connection %s : %d" % (c, n))
    for c,n in self.talker_on_count.iteritems():
      log_debug("Talker on count %s : %d" % (c, n))
    for c,n in self.clock_source_master.iteritems():
      if n:
        log_debug("Clock source master %s" % c)

    rendering.draw_state(self, sorted(endpoints.get_all().keys()))

  def connect(self, src, src_stream, dst, dst_stream):
    """ A connection will occur if the connection doesn't already exist
        and the listener is not in use. There must also be a valid path
        between the two endpoints.
    """
    if (self.connected(src, src_stream, dst, dst_stream) or
        self.listener_active_count(dst, dst_stream)):
      return

    path = graph.find_path(self, src, dst)
    if not path:
      return

    talker = Talker(src, src_stream)
    listener = Listener(dst, dst_stream)
    connection = Connection(talker, listener)

    self.talker_on_count[src] = self.talker_on_count.get(src, 0) + 1
    self.active_talkers[talker] = self.active_talkers.get(talker, 0) + 1
    self.active_listeners[listener] = 1 # Listeners can only accept one connection
    self.active_connections[connection] = self.active_connections.get(connection, 0) + 1

  def disconnect(self, src, src_stream, dst, dst_stream):
    if not self.connected(src, src_stream, dst, dst_stream):
      return

    talker = Talker(src, src_stream)
    listener = Listener(dst, dst_stream)
    connection = Connection(talker, listener)

    assert self.active_talkers.get(talker, 0)
    self.active_talkers[talker] -= 1

    assert self.active_listeners.get(listener, 0)
    self.active_listeners[listener] -= 1

    assert self.active_connections.get(connection, 0)
    self.active_connections[connection] -= 1

  def connected(self, src, src_stream, dst, dst_stream=None):
    """ Check whether a src stream is connected to a dest node. Can specify the
        dest stream if desired.
    """
    talker = Talker(src, src_stream)
    listener = Listener(dst, dst_stream)
    connected = False
    if dst_stream:
      connection = Connection(talker, listener)
      if self.active_connections.get(connection, 0):
          connected = True

    else:
      for c,n in self.active_connections.iteritems():
        if not n:
          continue

        if c.talker == talker and c.listener.dst == dst:
          connected = True

    # Note that the format of each operand is %s because that copes with a None
    log_debug("connected %s %s %s %s ? %s" % (src, src_stream, dst, dst_stream, connected))
    return connected

  def talker_active_count(self, src, src_stream):
    talker = Talker(src, src_stream)
    return self.active_talkers.get(talker, 0)

  def get_talker_on_count(self, src):
    return self.talker_on_count.get(src, 0)

  def listener_active_count(self, dst, dst_stream):
    listener = Listener(dst, dst_stream)
    return self.active_listeners.get(listener, 0)

  def get_talker_state(self, src, src_stream, dst, dst_stream, action):
    if graph.find_path(self, src, dst) is None:
      state = 'talker_redundant'

    elif action == 'connect':
      if self.connected(src, src_stream, dst, dst_stream):
        state = 'talker_redundant'
      else:
        if self.listener_active_count(dst, dst_stream):
          state = 'talker_redundant'
        elif self.talker_active_count(src, src_stream):
          state = 'talker_existing'
        else:
          state = 'talker_new'

    elif action == 'disconnect':
      if not self.connected(src, src_stream, dst, dst_stream):
        state = 'talker_redundant'
      else:
        if self.talker_active_count(src, src_stream) == 1:
          state = 'talker_all'
        else:
          state = 'talker_existing'

    else:
      base.testError("Unknown action '%s'" % action, critical=True)

    log_debug("get_talker_state for %s %d %s %d: %s" % (src, src_stream, dst, dst_stream, state))
    return (state + '_' + action)

  def get_listener_state(self, src, src_stream, dst, dst_stream, action):
    if graph.find_path(self, src, dst) is None:
      state = 'listener_redundant'

    elif action == 'connect':
      if self.listener_active_count(dst, dst_stream):
        state = 'listener_redundant'
      else:
        state = 'listener'

    elif action == 'disconnect':
      if self.connected(src, src_stream, dst, dst_stream):
        state = 'listener'
      else:
        state = 'listener_redundant'

    else:
      base.testError("Unknown action '%s'" % action, critical=True)

    log_debug("get_listener_state for %s %d: %s" % (dst, dst_stream, state))
    return (state + '_' + action)

  def get_controller_state(self, controller_id, src, src_stream, dst, dst_stream, action):
    controllable_endpoints = graph.get_endpoints_connected_to(self, controller_id)
    if src not in controllable_endpoints or dst not in controllable_endpoints:
      state = 'timeout'

    elif action == 'connect':
      if self.connected(src, src_stream, dst, dst_stream):
        state = 'success'
      elif self.listener_active_count(dst, dst_stream):
        state = 'listener_exclusive'
      else:
        state = 'success'

    elif action == 'disconnect':
      if not self.connected(src, src_stream, dst, dst_stream):
        state = 'redundant'
      else:
        state = 'success'

    else:
      base.testError("Unknown action '%s'" % action, critical=True)

    log_debug("get_controller_state for %s %d %s %d: %s" % (src, src_stream, dst, dst_stream, state))
    return ('controller_' + state + '_' + action)

  def is_clock_source_master(self, node):
    return self.clock_source_master.get(node, 0)

  def set_clock_source_master(self, node):
    self.clock_source_master[node] = 1

  def set_clock_source_slave(self, node):
    self.clock_source_master[node] = 0

  def set_relay_open(self, node):
    self.open_relays[node] = 1

  def set_relay_closed(self, node):
    self.open_relays[node] = 0

  def is_relay_open(self, node):
    return self.open_relays.get(node, 0)

# Global state variables (not to be accessed directly)
_current = State()
_next = State()


# Access functions
def get_current():
  return _current

def get_next():
  return _next

def move_next_to_current():
  global _next
  global _current
  _current = _next
  _next = copy.deepcopy(_current)

