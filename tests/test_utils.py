"""
Test packet.py and checksum.py
"""

import packet
import checksum
import logging

import os
import sys

logging.getLogger().setLevel(logging.DEBUG)


def test_with_payload():
	"""
	Test `compute_checksum`, `make_packet`, 
	and `receiver_check` with payloads
	"""

	src_port = 3
	dest_port = 3
	seq_num = 1
	ack_num = 1
	pattern = 0
	payload = b'Hi!'

	checksum_ = checksum.compute_checksum(src_port, dest_port, seq_num, ack_num, pattern, payload)
	assert checksum_ == '0110011101011101'

	pkt = packet.make_packet(src_port, dest_port, seq_num, ack_num, pattern, payload, checksum_)
	assert checksum.receiver_check(pkt)

	# now try larger payload
	payload = b'hash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swanhash_swan'

	checksum_ = checksum.compute_checksum(src_port, dest_port, seq_num, ack_num, pattern, payload)
	
	pkt = packet.make_packet(src_port, dest_port, seq_num, ack_num, pattern, payload, checksum_)
	assert checksum.receiver_check(pkt)

	# even larger payload
	payload += b'swn_hsh_swn_hsh_swn_hsh_swn_hsh_swn_hsh_swn_hsh_swn_hsh_swn_hsh_swn_hsh_swn_hsh_swn_hsh_swn_hsh_swn_hsh_swn_hsh_swn_hsh_swn_hsh_rin'

	checksum_ = checksum.compute_checksum(src_port, dest_port, seq_num, ack_num, pattern, payload)
	
	pkt = packet.make_packet(src_port, dest_port, seq_num, ack_num, pattern, payload, checksum_)
	assert checksum.receiver_check(pkt)

	logging.info("_test_with_payload: PASSED")


def test_without_payload():
	"""
	Test `compute_checksum`, `make_packet`, 
	and `receiver_check` without payload
	"""
	src_port = 3
	dest_port = 3
	seq_num = 1
	ack_num = 1
	pattern = 0
	payload = None

	checksum_ = checksum.compute_checksum(src_port, dest_port, seq_num, ack_num, pattern, payload)
	assert checksum_ == '1010111111100111'

	pkt = packet.make_packet(src_port, dest_port, seq_num, ack_num, pattern, payload, checksum_)
	assert checksum.receiver_check(pkt)

	pattern = 3
	checksum_ = checksum.compute_checksum(src_port, dest_port, seq_num, ack_num, pattern, payload)
	pkt = packet.make_packet(src_port, dest_port, seq_num, ack_num, pattern, payload, checksum_)
	assert checksum.receiver_check(pkt)

	logging.info("_test_without_payload: PASSED")

def test_decode_packet():
	"""
	Test `decode_packet`
	"""
	src_port = 80
	dest_port = 60
	seq_num = 1
	ack_num = 12
	pattern = 3
	payload = b"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

	checksum_ = checksum.compute_checksum(src_port, dest_port, seq_num, ack_num, pattern, payload)
	pkt = packet.make_packet(src_port, dest_port, seq_num, ack_num, pattern, payload, checksum_)
	assert checksum.receiver_check(pkt)
	rtn = packet.decode_packet(pkt)
	assert rtn["payload"] == payload
	assert rtn["seq_num"] == seq_num
	assert rtn["ack_num"] == ack_num
	assert rtn["is_ack"] == False
	assert rtn["is_fin"] == False

	logging.info("_test_decode_packet: PASSED")

if __name__ == "__main__":

	tests_dir = os.path.dirname(os.path.realpath(__file__))
	head, tail = os.path.split(tests_dir)
	print(head)

