import argparse
import sys
import logging
import time
import socket
import os
import threading

from utils import packet
from utils import checksum

logging.getLogger().setLevel(logging.DEBUG)

class TCPServer(object):

	def __init__(self, FILE, LISTENING_PORT,
	             ADDR_FOR_ACKS, PORT_FOR_ACKS):

		self.write_file = FILE
		
		# if the file exists, remove the content
		# if the file doesn't exist, create the file
		with open(self.write_file, "wb") as f:
			f.write(b"")
			f.close()

		self.listening_port = LISTENING_PORT

		self.ack_addr = (ADDR_FOR_ACKS, PORT_FOR_ACKS)
		self.ack_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

		self.ack_num = 0 # seq num of next expected byte from client
		self.next_seq_num = 0 # seq num of next packet sent from server

		self.buffer = {} # hold out of order packets 
						 # (keys are sequence numbers and values are packet payloads (bytes))

		self.done = False

	def _send_packet(self, payload, seq_num, ack_num, pattern):
		"""
		Send packet based on input values
		"""
		logging.info("TCPServer::_send_packet")

		# compute checksum and make packet
		checksum_ = checksum.compute_checksum(self.listening_port, self.ack_addr[1], 
			                                  seq_num, ack_num, 
			                                  pattern, payload)
		pkt = packet.make_packet(self.listening_port, self.ack_addr[1], 
			                     seq_num, ack_num, 
			                     pattern, payload, 
			                     checksum_)
		
		# send the packet
		self.ack_socket.sendto(pkt, self.ack_addr)

	def _write_file(self, data):
		"""
		Write data to self.write_file in append mode
		(should exist and initially it should be empty)

		data: bytes
		"""
		logging.info("TCPServer::_write_file")

		with open(self.write_file, "ab") as f:
			f.write(data)
			f.close()


	def _receive(self):
		"""
		Listen on self.listening_port for 
		packets from the client and send ACKS/write to file
		"""
		logging.info("TCPServer::_receive")

		# bind listening port to the server's socket
		self.ack_socket.bind(("", self.listening_port))

		logging.info("TCPServer is ready to receive")

		while True:

			# receive packet
			pkt, _ = self.ack_socket.recvfrom(576 + 20) # max MSS allowed plus
														# 20 bytes of header

			# make sure packet is uncorrupted
			uncorrupted = checksum.receiver_check(pkt)

			if uncorrupted:

				# decode the packet from bytes to dictionary of values
				rtn = packet.decode_packet(pkt)

				# check if the packet is a duplicate one.
				# if so, send an ACK and move on
				if rtn["seq_num"] < self.ack_num:
					# send an ACK
					self._send_packet(None, self.next_seq_num, self.ack_num, 0)
					self.next_seq_num += 1
					continue

				# check if the packet is an out-of-order packet.
				# if it is, check to see if it is a duplicate and if it is,
				# send an ACK and move on. otherwise, buffer it, send an ACK,
				# and move on
				if rtn["seq_num"] > self.ack_num:
					# is this a duplicate?
					if rtn["seq_num"] in self.buffer:
						# send an ACK
						self._send_packet(None, self.next_seq_num, self.ack_num, 0)
						self.next_seq_num += 1
						continue
					# add to buffer
					self.buffer[rtn["seq_num"]] = rtn["payload"]
					# send an ACK
					self._send_packet(None, self.next_seq_num, self.ack_num, 0)
					self.next_seq_num += 1
					continue

				##
				# the packet's seq number is the next expected one
				#

				# if this packet isn't a FIN segment
				if not rtn["is_fin"]:
					# write the payload to self.write_file
					self._write_file(rtn["payload"])

				    # determine if the received packet fills in any gaps
				    # (i.e., is there a contiguous sequence of sequence numbers
				    # in the key set of self.buffer starting from self.ack_num + len(payload))?
					self.ack_num = self.ack_num + len(rtn["payload"])
					while self.ack_num in self.buffer:

				    	# write the data to self.write_file
						self._write_file(self.buffer[self.ack_num])

				    	# increment
						self.ack_num += len(self.buffer[self.ack_num])

				# if the packet is a FIN
				else:
					self.ack_num += 1

				# send an ACK
				self._send_packet(None, self.next_seq_num, self.ack_num, 0)
				self.next_seq_num += 1

				# delete relevant entries from the buffer
				self.buffer = {seq_num:self.buffer[seq_num] for seq_num in self.buffer.keys() if seq_num >= self.ack_num}

				# if the packet is a FIN, break out of the loop
				if rtn["is_fin"]:
					break

		# send a FIN
		self._send_packet(None, self.next_seq_num, self.ack_num, 1)

		logging.info("send a FIN")

		# wait for an ACK from the client
		lock = threading.Lock()

		t1 = threading.Thread(target=TCPServer._wait_fin_ack, args=(self, lock,)) 
		t2 = threading.Thread(target=TCPServer._time_fin_ack, args=(self, lock,))

		t1.start()
		t2.start()

		t1.join()
		t2.join()
		

	def _time_fin_ack(self, lock):
		"""
		Timer for sending FIN 
		"""
		timeout_interval = 2
		timer = time.time() + timeout_interval

		while not self.done:

			if time.time() >= timer:

				lock.acquire()
				
				# retransmit FIN
				self._send_packet(None, self.next_seq_num, self.ack_num, 1)

				lock.release()

				# reset timer
				timer = time.time() + timeout_interval


	def _wait_fin_ack(self, lock):
		"""
		Wait for an ACK after sending a FIN
		"""
		while True:

			# receive packet
			pkt, _ = self.ack_socket.recvfrom(576 + 20) # max MSS allowed plus
														# 20 bytes of header

			# make sure packet is uncorrupted
			uncorrupted = checksum.receiver_check(pkt)

			if uncorrupted:

				# decode the packet from bytes to dictionary of values
				rtn = packet.decode_packet(pkt)

				# if this is the next expected packet and it is an ACK
				if rtn["seq_num"] == self.ack_num and rtn["is_ack"]:
					logging.info("received ACK for FIN")
					break

		lock.acquire()
		self.done = True
		lock.release()



def parse_args():
	"""
	Populates variables at the top of the file
	by parsing CLI input

	Expects `tcpserver file listening_port address_for_acks port_for_acks`
	"""
	if len(sys.argv) != 5:
		print("Please specify all required arguments.")
		return

	FILE, LISTENING_PORT, ADDR_FOR_ACKS, PORT_FOR_ACKS = sys.argv[1:]
	return FILE, int(LISTENING_PORT), ADDR_FOR_ACKS, int(PORT_FOR_ACKS)


if __name__ == '__main__':

	# parse arguments from CLI
	FILE, LISTENING_PORT, ADDR_FOR_ACKS, PORT_FOR_ACKS = parse_args()
	
	# instantiate server
	server = TCPServer(FILE, LISTENING_PORT,
	                   ADDR_FOR_ACKS, PORT_FOR_ACKS)

	# start listening on port and receiving data
	server._receive()
	