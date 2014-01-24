import endpoints

PACKETS_PER_SECOND = 8000

def data_bytes_per_packet(talker):
  """ Returns how many bytes per packet there will be.
  """
  talker_ep = endpoints.get(talker.src)
  samples_per_packet = (talker_ep['sample_rate'] + (PACKETS_PER_SECOND-1)) / PACKETS_PER_SECOND
  num_channels = talker_ep['out_channels']
  return samples_per_packet * 4 * num_channels

def calculate_stream_bandwidth(talker, extra_byte):
  """ Determine how many bits per second a given stream will require. This includes
      the inter-frame gap and the preamble, all the headers, data and crc
  """
  ifg_bytes = 12
  preamble_bytes = 8
  ether_hdr_bytes = 14
  vlan_tag_bytes = 4
  crc_bytes = 4
  frame_bytes = ifg_bytes + preamble_bytes + ether_hdr_bytes + vlan_tag_bytes + crc_bytes

  avb_1722_and_sip_hdr_bytes = 32
  data_bytes = data_bytes_per_packet(talker)
  frame_bytes += avb_1722_and_sip_hdr_bytes + data_bytes

  if extra_byte:
    frame_bytes += 1

  return frame_bytes * 8 * PACKETS_PER_SECOND

