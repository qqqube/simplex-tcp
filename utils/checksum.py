"""
Checksum Methods
"""

from packet import *

def convert_to_binary_str(integer, length):
    """
    Convert integer to binary string and pad
    with leading zeros to acheive input length (in bits)
    """
    bit_str = bin(integer)[2:]
    while len(bit_str) < length:
        bit_str = "0" + bit_str
    return bit_str


def sum_bits(x, y, z):
    """
    Given three bit strings, return the sum and the carry_bit
    
    so i think we can turn them into integers and then convert back?
    
    so if they are all 0 then obviously 0
    if the sum comes out to 1 then exactly one is 1 and the rest are 0
    
    if 2 are 1 and exactly 1 is 0, then the sum comes out to 2 so the sum should be "0" and the carry shoudl be "1"
    
    if all are 1 then the sum is 3 and the sum should be "1" and the carry should be "1"
    
    """
    int_x = int(x)
    int_y = int(y)
    int_z = int(z)
    
    int_sum = int_x + int_y + int_z
    
    if int_sum == 0:
        return "0", "0"
    if int_sum == 1:
        return "0", "1"
    if int_sum == 2:
        return "1", "0"
    return "1", "1"


def sum_bit_str(x, y):
    """
    Given two 16-bit binary strings, compute the sum
    with any overflow encountered being wrapped around
    """
    # turn x and y into lists
    
    # iterate from the back and start adding
    
    _sum = []
    x = [x[i] for i in range(16)]
    y = [y[i] for i in range(16)]
    
    carry_bit = "0"
    
    for idx in reversed(range(16)):
        
        x_bit = x[idx]
        y_bit = y[idx]
        
        carry_bit, sum_bit = sum_bits(x_bit, y_bit, carry_bit)
        _sum = [sum_bit] + _sum
    
    # convert _sum list to string
    rtn = ""
    for bit in _sum:
        rtn += bit
    
    # if carry_bit is 1, add it to rtn
    if carry_bit == "1":
        return sum_bit_str(rtn, "0000000000000001")
    
    return rtn


def ones_complement(_sum):
    """
    Given a 16-bit binary string, return the ones complement
    """
    flip = {"0":"1", "1":"0"}
    rtn = ""
    for bit in _sum:
        rtn += flip[bit]
    return rtn


def compute_checksum(src_port, dest_port, seq_num,
                     ack_num, pattern, payload):
    """
    Compute checksum of packet (represented as string of bits)
    """
    
    #############################
    # First process the header
    ########################## 
    
    # `pkt` will be a list of binary strings (each of length 16 bits)
    pkt = [convert_to_binary_str(src_port, 16),
           convert_to_binary_str(dest_port, 16)]
    
    seq_num = convert_to_binary_str(seq_num, 32)
    ack_num = convert_to_binary_str(ack_num, 32)
    
    # break sequence and ack numbers into 16 bit sequences
    pkt.append(seq_num[0:16])
    pkt.append(seq_num[16:])
    pkt.append(ack_num[0:16])
    pkt.append(ack_num[16:])
    
    pkt.append(patterns[pattern])
    
    # the receive window and the 16 bit section after the
    # checksum in the header are set to all zeros, so 
    # we don't need to explicitly include them in the checksum
    
    ########################################################
    # Next, we break the payload into 16-bit sequences, which is passed in as bytes
    #######################################################
    
    if payload:
        
        # list of bytes in integer format
        byte_ints = [x for x in payload]
        
        # loop through each pair of integers/bytes,
        # concatenate bit string representations,
        # and add to `pkt` list
        for idx in range(0, len(byte_ints), 2):

            # if we have an odd number of bytes,
            # prepend zeros to the last chunk
            # until it is 16 bits
            if idx + 1 >= len(byte_ints):
                x = byte_ints[idx]
                x_bin = convert_to_binary_str(x, 8)
                y_bin = convert_to_binary_str(0, 8)
                pkt.append(y_bin + x_bin)
            
                
            else:
                x = byte_ints[idx]
                y = byte_ints[idx + 1]
                
                x_bin = convert_to_binary_str(x, 8)
                y_bin = convert_to_binary_str(y, 8)
                
                pkt.append(x_bin + y_bin)
        
    #####################################################################
    # Now, we sum over all 16-bit sequences and return the ones complement
    #######################################################################
    
    _sum = pkt[0]
    for idx in range(1, len(pkt)):
        _sum = sum_bit_str(_sum, pkt[idx])

    return ones_complement(_sum)


def receiver_check(pkt):
    """
    Return if a packet has been corrupted or not (True/False)
    
    pkt: received packet in bytes
    """
    # get list of bytes in integer representation
    pkt_int = [x for x in pkt]
    
    # iterate through each pair of ints,
    # create a 16-bit binary sequence,
    # and sum
    
    # make the first sequence
    _sum = convert_to_binary_str(pkt_int[0], 8)
    _sum = _sum + convert_to_binary_str(pkt_int[1], 8)
    
    for idx in range(2, len(pkt_int), 2):
        
        # if we have an odd number of bytes
        # pad the front of sequence with zero
        
        if idx + 1 >= len(pkt_int):
            
            x_int = pkt_int[idx]
            x_seq = convert_to_binary_str(x_int, 8)
            y_seq = convert_to_binary_str(0, 8)
            
            _sum = sum_bit_str(_sum, y_seq + x_seq)
            
        else:
            
            x_int = pkt_int[idx]
            y_int = pkt_int[idx + 1]
            x_seq = convert_to_binary_str(x_int, 8)
            y_seq = convert_to_binary_str(y_int, 8)
            
            _sum = sum_bit_str(_sum, x_seq + y_seq)
    
    return "0" not in _sum






