import xmos.test.base as base

''' Track the current connections in the topology.
     - active_connections contains the list of connections (src:src_stream->dst:dst_stream)
     - active_talkers     contains the active talkers (src:src_stream) and the count of how may times they are used
     - active_listeners   contains the active listeners (dst:dst_stream). They can only accept one connection.
'''
active_connections = {}
active_talkers = {}
active_listeners = {}

def get_src_key(src, src_stream):
    return src + ':' + str(src_stream)

def get_dst_key(dst, dst_stream):
    return dst + ':' + str(dst_stream)

def get_con_key(src, src_stream, dst, dst_stream):
    return get_src_key(src, src_stream) + get_dst_key(dst, dst_stream)

def connect(src, src_stream, dst, dst_stream):
    src_key = get_src_key(src, src_stream)
    dst_key = get_dst_key(dst, dst_stream)
    con_key = get_con_key(src, src_stream, dst, dst_stream)

    talkers = active_talkers.get(src_key, 0)
    connections = active_connections.get(con_key, 0)

    # The talker count should only be incremented if this is a new connection
    if not active_connections.get(con_key, 0):
        active_talkers[src_key] = talkers + 1

    active_connections[con_key] = connections + 1

    # Listeners can only accept one connection
    active_listeners[dst_key] = 1

def disconnect(src, src_stream, dst, dst_stream):
    src_key = get_src_key(src, src_stream)
    dst_key = get_dst_key(dst, dst_stream)
    con_key = get_con_key(src, src_stream, dst, dst_stream)
    if active_talkers.get(src_key, 0):
        active_talkers[src_key] -= 1
    if active_listeners.get(dst_key,0):
        active_listeners[dst_key] -= 1
    if active_connections.get(con_key,0):
        active_connections[con_key] -= 1

def connected(src, src_stream, dst, dst_stream):
    con_key = get_con_key(src, src_stream, dst, dst_stream)
    if active_connections.get(con_key, 0):
        return True
    return False

def talker_active_count(src, src_stream):
    src_key = get_src_key(src, src_stream)
    return active_talkers.get(src_key, 0)

def listener_active_count(dst, dst_stream):
    dst_key = get_src_key(dst, dst_stream)
    return active_listeners.get(dst_key, 0)

def get_talker_state(src, src_stream, dst, dst_stream, action):
    if action == 'connect':
        if connected(src, src_stream, dst, dst_stream):
            state = 'redundant'
        else:
            if talker_active_count(src, src_stream):
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

    if base.test_config.verbose:
        print "get_talker_state for %s %d %s %d: %s" % (src, src_stream, dst, dst_stream, state)
    return (state + '_' + action)

def get_listener_state(dst, dst_stream, action):
    if action == 'connect':
        state = 'listener'
    elif action == 'disconnect':
        if listener_active_count(dst, dst_stream):
            state = 'listener'
        else:
            state = 'redundant'
    else:
      testError("Unknown action '%s'" % action, True)

    if base.test_config.verbose:
        print "get_listener_state for %s %d: %s" % (dst, dst_stream, state)
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

    if base.test_config.verbose:
        print "get_controller_state for %s %d %s %d: %s" % (src, src_stream, dst, dst_stream, state)
    return ('controller_' + state + '_' + action)

