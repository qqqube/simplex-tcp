"""
File for creating/processing packets
"""



##########################################
# 16-bit section before the receive window
# in the header can only take on 4
# different values since the header length
# is always 20 bytes and we're ignoring
# many values
##########################################

ACK_only_bits = "0101000000010000"
FIN_only_bits = "0101000000000001"
ACK_FIN_bits = "0101000000010001"
data_bits = "0101000000000000"
    
patterns = {0:ACK_only_bits, 1:FIN_only_bits,
            2:ACK_FIN_bits, 3:data_bits}


def _sq16_to_bytes(sequence):
	"""
	Convert bit sequence (16 bits) to bytes

	sequence: 16-bit string
	"""
	head_bits = sequence[0:8]
	tail_bits = sequence[8:]

	head_byte = int(head_bits, 2).to_bytes(1, "big")
	tail_byte = int(tail_bits, 2).to_bytes(1, "big")

	return head_byte + tail_byte


def make_packet(src_port, dest_port, seq_num,
                ack_num, pattern, payload, 
                checksum):
    """
    Returns a packet in bytes
    
    src_port: integer
    dest_port: integer
    seq_num: integer
    ack_num: integer
    pattern: {0, 1, 2, 3}
    payload: bytes or None
    checksum: 16-bit string
    """
    src_port = src_port.to_bytes(2, "big")
    dest_port = dest_port.to_bytes(2, "big")

    seq_num = seq_num.to_bytes(4, "big")
    ack_num = ack_num.to_bytes(4, "big")

    section = _sq16_to_bytes(patterns[pattern])

    receive_window = (0).to_bytes(2, "big")

    checksum = _sq16_to_bytes(checksum)

    last_section = (0).to_bytes(2, "big")
    
    if payload is None:
        return src_port + dest_port + seq_num + ack_num + section + receive_window + checksum + last_section
    return src_port + dest_port + seq_num + ack_num + section + receive_window + checksum + last_section + payload


def decode_packet(pkt):
    """
    Return dictionary of extracted values:
    {   seq_num:<int>, 
        is_ack:<True/False>, 
        ack_num:<int>,
        is_fin:<True/False>,
        payload:<bytes>
    }
    
    pkt: received packet in bytes
    """
    rtn = {}
    
    # headers are always 20 bytes,
    # so if the packet is only 20 bytes
    # then there is no payload
    if len(pkt) == 20:
        rtn["payload"] = None
    else:
        rtn["payload"] = bytes(pkt[20:])
    
    rtn["seq_num"] = int.from_bytes(bytes(pkt[4:8]), "big")
    rtn["ack_num"] = int.from_bytes(bytes(pkt[8:12]), "big")
    
    # the 13th byte can either be
    # 0001 0000,
    # 0000 0001,
    # 0001 0001,
    # or 0000 0000
    ack_fin_byte = pkt[13]
    rtn["is_ack"] = ack_fin_byte in [16, 17]
    rtn["is_fin"] = ack_fin_byte in [1, 17]
    
    return rtn
