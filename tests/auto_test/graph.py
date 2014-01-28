import xmos.test.base as base
import xmos.test.xmos_logging as xmos_logging
from xmos.test.xmos_logging import log_error, log_warning, log_info, log_debug

import endpoints
import avb_1722

""" The physical connections as defined in the test configuration file. These
    are used to determine the paths between two endpoints.
"""
physical_connections = {}

def set_connections(connections):
  global physical_connections
  physical_connections = connections

def _find_path(state, start, end, path=[]):
  """ Recursive function to build up the path between the specified start and end point
  """
  path = path + [start]
  if start == end:
    return path

  if not physical_connections.has_key(start):
    return None

  if state.is_relay_open(start):
    return None

  for node in physical_connections[start]:
    if node not in path:
      newpath = _find_path(state, node, end, path)
      if newpath:
        return newpath
  return None

def find_path(state, start, end, path=[]):
  """ A front-end for debug purposes
  """
  path = _find_path(state, start, end)
  log_debug("find_path %s -> %s : %s" % (start, end, path))
  return path

def _get_loops(state, node, path_so_far, loops):
  """ Recursive function that looks through connections to search for loops.
      Any loop that is found is added to the loops list.
  """
  for c,n in state.active_connections.iteritems():
    if not n or (node != c.talker.src):
      continue

    dest = c.listener.dst
    if dest in path_so_far:
      # Only add this as a loop if the destination is the same as the start node.
      # Otherwise this is a path that has joined a loop.
      if dest == path_so_far[0]:
        loops += [path_so_far + [dest]]

    else:
      _get_loops(state, dest, path_so_far + [dest], loops)

def get_loops(state):
  """ Find all the loops in the current set of connections.
  """
  loops = []

  for t,n in state.active_talkers.iteritems():
    # If the endpoint is not active or already in a loop then ignore it
    if not n or any(t.src in loop for loop in loops):
      continue

    _get_loops(state, t.src, [t.src], loops)

  log_debug("get_loops got %s" % loops)
  return loops

def is_in_loop(state, node):
  in_loop = False
  loops = get_loops(state)
  for loop in loops:
    if node in loop:
      in_loop = True
      break

  log_debug("is_in_loop %s = %d" % (node, in_loop))
  return in_loop

def get_forward_port(state, src, dst, node):
  """ Find the port name that is used to forward out of a node on a path from
      src -> dst. This is done by finding the node in the path. Its forwarding
      port name is the next node in the path. The port ID is the last character
      of that name.
  """
  port = None
  try:
    path = find_path(state, src, dst)
    index = path.index(node)
    port_name = path[index + 1]
    port = int(port_name[-1])
  except:
    pass

  log_debug("get_forward_port %s in %s -> %s: %s" % (node, src, dst, port))
  return port

def port_is_egress_in_path(state, connection, ep_name, port):
  """ Determine whether a port is an egress port in a given path
  """
  path = find_path(state, connection.talker.src, connection.listener.dst)
  # As long as the endpoint is in the path before the end
  if path and ep_name in path and ep_name != connection.listener.dst:
    # Determine wether this port is the egress port for the path found
    # that means the node after the endpoint. 
    index = path.index(ep_name)

    # The port ID is the last character of the port name
    egress_port = int(path[index + 1][-1])
    if port == egress_port:
      return True

  return False

def calculate_expected_bandwidth(state, ep, port):
  ep_name = ep['name']
  bandwidth = 0
  for c,n in state.active_connections.iteritems():
    if not n:
      continue

    if port_is_egress_in_path(state, c, ep_name, port):
      # A bridge must reserve an extra byte per packet
      is_bridge = ep_name != c.talker.src
      bandwidth += avb_1722.calculate_stream_bandwidth(c.talker, is_bridge)

  return bandwidth

def port_will_see_bandwidth_change(state, src, src_stream, ep_name, port, command):
  num_active_streams = 0
  
  # Look at all connections of this src stream
  for c,n in state.active_connections.iteritems():
    if not n or c.talker.src != src or c.talker.src_stream != src_stream:
      continue

    if port_is_egress_in_path(state, c, ep_name, port):
      num_active_streams += 1

  log_debug("port_will_see_bandwidth_change found %d active streams for %s:%s" % (
        num_active_streams, ep_name, port))

  if command == 'connect':
    # On connect the bandwidth should only change if this stream is not currently
    # forwarded through this port
    return num_active_streams == 0
  else:
    # On disconnect the bandwidth should only change if there is 1 active
    # stream as this will be removed
    return num_active_streams == 1

def node_will_see_stream_enable(state, src, src_stream, dst, dst_stream, node):
  """ Determine whether a given node will see the stream between src/dst as a new
      stream. Returns True if it will be a new stream, False if it is an existing
      stream.
  """
  log_debug("node_will_see_stream_enable %s ?" % node)
  if (state.connected(src, src_stream, dst, dst_stream) or
      state.listener_active_count(dst, dst_stream)):
    # Connection will have no effect
    log_debug("No, connection will not happen")
    return False

  # Look at all connections of this src stream
  for c,n in state.active_connections.iteritems():
    if not n or c.talker.src != src or c.talker.src_stream != src_stream:
      continue

    nodes = find_path(state, src, c.listener.dst)
    log_debug("What about path %s?" % nodes)
      
    # Look for all nodes past this one in the path. If one of them is connected to
    # this stream then this node won't see enable, otherwise it should expect to
    past_node = False
    for n in nodes:
      if past_node:
        if state.connected(src, src_stream, n):
          log_debug("No forwarding, node %s is connected beyond %s?" % (n, node))
          return False

      elif n == node:
        past_node = True

  return True

def node_will_see_stream_disable(state, src, src_stream, dst, dst_stream, node):
  """ Determine whether a given node will see being disabled if it is turned off.
  """
  log_debug("node_will_see_stream_disable %s ?" % node)
  if not state.connected(src, src_stream, dst, dst_stream):
    # Disconnection will have no effect
    log_debug("No, stream not connected")
    return False

  # Look at all connections of this src stream
  for c,n in state.active_connections.iteritems():
    if not n:
      continue

    if c.talker.src != src or c.talker.src_stream != src_stream:
      continue

    nodes = find_path(state, src, c.listener.dst)
    log_debug("What about path %s?" % nodes)
      
    # Look for all nodes past this one in the path. If one of them is connected to
    # this stream then this node won't see disable, otherwise it should expect to
    past_node = False
    for n in nodes:
      if n == dst:
        # Ignore the current connection
        continue

      if past_node:
        if state.connected(src, src_stream, n):
          log_debug("No forwarding, node %s is connected beyond %s?" % (n, node))
          return False

      elif n == node:
        past_node = True

  return True

def get_endpoints_connected_to(state, node):
  connected = set()
  for endpoint in endpoints.get_all():
    if find_path(state, node, endpoint):
      connected |= set([endpoint])
  log_debug("get_endpoints_connected_to %s: %s" % (node, connected))
  return connected

