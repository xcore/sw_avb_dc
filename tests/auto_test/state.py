import xmos.test.base as base
import xmos.test.xmos_logging as xmos_logging
from xmos.test.xmos_logging import log_error, log_warning, log_info, log_debug

''' Track the current connections in the topology.
     - active_connections contains the list of connections (src:src_stream->dst:dst_stream)
     - active_talkers     contains the active talkers (src:src_stream) and the count of how may times they are used
     - active_listeners   contains the active listeners (dst:dst_stream). They can only accept one connection.
'''
active_connections = {}
active_talkers = {}
active_listeners = {}
talker_on_count = {}
clock_source_master = {}

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


def dump_state():
  log_debug("Current state:")
  for t,n in active_talkers.iteritems():
    log_debug("Talker %s : %d" % (t, n))
  for l,n in active_listeners.iteritems():
    log_debug("Listeners %s : %d" % (l, n))
  for c,n in active_connections.iteritems():
    log_debug("Connection %s : %d" % (c, n))
  for c,n in talker_on_count.iteritems():
    log_debug("Talker on count %s : %d" % (c, n))
  for c,n in clock_source_master.iteritems():
    if n:
      log_debug("Clock source master %s" % c)

def connect(src, src_stream, dst, dst_stream):
  """ A connection will occur if the connection doesn't already exist
      and the listener is not in use.
  """
  if (connected(src, src_stream, dst, dst_stream) or
      listener_active_count(dst, dst_stream)):
    return

  talker = Talker(src, src_stream)
  listener = Listener(dst, dst_stream)
  connection = Connection(talker, listener)

  talker_on_count[src] = talker_on_count.get(src, 0) + 1
  active_talkers[talker] = active_talkers.get(talker, 0) + 1
  active_listeners[listener] = 1 # Listeners can only accept one connection
  active_connections[connection] = active_connections.get(connection, 0) + 1

def disconnect(src, src_stream, dst, dst_stream):
  if not connected(src, src_stream, dst, dst_stream):
    return

  talker = Talker(src, src_stream)
  listener = Listener(dst, dst_stream)
  connection = Connection(talker, listener)

  assert active_talkers.get(talker, 0)
  active_talkers[talker] -= 1

  assert active_listeners.get(listener, 0)
  active_listeners[listener] -= 1

  assert active_connections.get(connection, 0)
  active_connections[connection] -= 1

def connected(src, src_stream, dst, dst_stream=None):
  """ Check whether a src stream is connected to a dest node. Can specify the
      dest stream if desired.
  """
  talker = Talker(src, src_stream)
  listener = Listener(dst, dst_stream)
  connected = False
  if dst_stream:
    connection = Connection(talker, listener)
    if active_connections.get(connection, 0):
        connected = True

  else:
    for c,n in active_connections.iteritems():
      if not n:
        continue

      if c.talker == talker and c.listener.dst == dst:
        connected = True

  log_debug("connected {src} {src_stream} {dst} {dst_stream} ? {answer}".format(
        src=src, src_stream=src_stream, dst=dst, dst_stream=dst_stream,
        answer=connected))
  return connected

def talker_active_count(src, src_stream):
  talker = Talker(src, src_stream)
  return active_talkers.get(talker, 0)

def get_talker_on_count(src):
  return talker_on_count.get(src, 0)

def listener_active_count(dst, dst_stream):
  listener = Listener(dst, dst_stream)
  return active_listeners.get(listener, 0)

def get_talker_state(src, src_stream, dst, dst_stream, action):
  if action == 'connect':
    if connected(src, src_stream, dst, dst_stream):
      state = 'redundant'
    else:
      if listener_active_count(dst, dst_stream):
        state = 'redundant'
      elif talker_active_count(src, src_stream):
        state = 'talker_existing'
      else:
        state = 'talker_new'
  elif action == 'disconnect':
    if not connected(src, src_stream, dst, dst_stream):
      state = 'redundant'
    else:
      if talker_active_count(src, src_stream) == 1:
        state = 'talker_all'
      else:
        state = 'talker_existing'

  log_debug("get_talker_state for %s %d %s %d: %s" % (src, src_stream, dst, dst_stream, state))
  return (state + '_' + action)

def get_listener_state(src, src_stream, dst, dst_stream, action):
  if action == 'connect':
    if listener_active_count(dst, dst_stream):
      state = 'redundant'
    else:
      state = 'listener'
  elif action == 'disconnect':
    if connected(src, src_stream, dst, dst_stream):
      state = 'listener'
    else:
      state = 'redundant'
  else:
    testError("Unknown action '%s'" % action, True)

  log_debug("get_listener_state for %s %d: %s" % (dst, dst_stream, state))
  return (state + '_' + action)

def get_controller_state(src, src_stream, dst, dst_stream, action):
  if action == 'connect':
    if connected(src, src_stream, dst, dst_stream):
      state = 'success'
    elif listener_active_count(dst, dst_stream):
      state = 'listener_exclusive'
    else:
      state = 'success'
  elif action == 'disconnect':
    if not connected(src, src_stream, dst, dst_stream):
      state = 'redundant'
    else:
      state = 'success'

  log_debug("get_controller_state for %s %d %s %d: %s" % (src, src_stream, dst, dst_stream, state))
  return ('controller_' + state + '_' + action)

def get_loops_for_node(node, path_so_far, loops):
  """ Recursive function that looks through connections to search for loops.
      Any loop that is found is added to the loops list.
  """
  for c,n in active_connections.iteritems():
    if not n or (node != c.talker.src):
      continue

    dest = c.listener.dst
    if dest in path_so_far:
      # Only add this as a loop if the destination is the same as the start node.
      # Otherwise this is a path that has joined a loop.
      if dest == path_so_far[0]:
        loops += [path_so_far + [dest]]

    else:
      get_loops_for_node(dest, path_so_far + [dest], loops)

def get_loops():
  """ Find all the loops in the current set of connections.
  """
  loops = []

  for t,n in active_talkers.iteritems():
    # If the endpoint is not active or already in a loop then ignore it
    if not n or any(t.src in loop for loop in loops):
      continue

    get_loops_for_node(t.src, [t.src], loops)

  log_debug("get_loops got %s" % loops)
  return loops

def is_in_loop(node):
  loops = get_loops()
  for loop in loops:
    if node in loop:
      return True
  return False

def is_clock_source_master(node):
  return clock_source_master.get(node, 0)

def set_clock_source_master(node):
  clock_source_master[node] = 1

def set_clock_source_slave(node):
  clock_source_master[node] = 0


if __name__ == "__main__":
  # A basic test for the loop detection logic
  xmos_logging.configure_logging(level_console='INFO')
  print get_loops()
  connect("dc0", 0, "dc1", 0)
  print get_loops()
  connect("dc1", 0, "dc0", 0)
  print get_loops()
  disconnect("dc1", 0, "dc0", 0)
  print get_loops()
  connect("dc1", 0, "sp0", 0)
  print get_loops()
  connect("sp0", 0, "dc0", 0)
  print get_loops()
