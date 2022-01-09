import argparse
import sys
import logging
import time
import socket
import threading
import os

from utils import packet
from utils import checksum


logging.getLogger().setLevel(logging.DEBUG)


class TCPSender(object):

	def __init__(self, INPUT_FILE, ADDR_OF_UDPL, 
		         PORT_NUMBER_OF_UDPL,
		         WINDOWSIZE, ACK_PORT_NUMBER):

		self.src_port = 12000

		# input file (type: str)
		self.file = INPUT_FILE
		
		# socket for sending packets
		self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		# (address of udpl, port number of udpl)
		self.send_addr = (ADDR_OF_UDPL, PORT_NUMBER_OF_UDPL)
		
		self.MSS = 576 # bytes

		self.windowsize = WINDOWSIZE # in bytes

		self.ack_port = ACK_PORT_NUMBER

		self.NextSeqNum = 0
		self.SendBase = 0 # byte number of oldest unacknowledge byte
		self.ack_num = 0 # next expected seq number from receiver

		self._init_send_buffer()

		self.timeout = 1 # in seconds
		self.timer = None # time of timeout
		self.rtm_seq_num = None #seq num of retransmitted pkt
		self.rtm_count = 0 # number of retransmitted pkts with seq
						   # num of self.rtm_seq_num


		self.RTT_timer = None
		self.RTT_seq_num = None
		self.estimated_rtt = 0
		self.alpha = 0.125
		self.devrtt = 0
		self.beta = 0.25

		self.done = False

	def _update_rtt_fields(self, sample_rtt):
		"""
		Update self.estimated_rtt, self.timeout,
		and self.devrtt

		sample_rtt: measurement in seconds
		"""
		self.estimated_rtt = ((1 - self.alpha) * self.estimated_rtt) + (self.alpha * sample_rtt)
		self.devrtt = (1 - self.beta) * self.devrtt + (self.beta * abs(sample_rtt - self.estimated_rtt))
		self.timeout = self.estimated_rtt + (4 * self.devrtt)

	def _timeout(self):
		"""
		Returns whether a timout has occurred (definition slightly relaxed 
		to account for delays from lock acquisition between threads)
		"""
		lst = [self.ack_dict[seq_num] for seq_num in self.ack_dict.keys() if seq_num < self.NextSeqNum]
		currently_timing = False in lst
		
		return self.timer is not None and time.time() >= self.timer and currently_timing

	def _send_data_pkt(self, payload, seq_num, ack_num, pattern):
		"""
		Send packet based on input values
		"""
		logging.info("TCPSender::_send_data_pkt")

		# compute checksum and make packet
		checksum_ = checksum.compute_checksum(self.src_port, self.send_addr[1], 
			                                  seq_num, ack_num, 
			                                  pattern, payload)
		pkt = packet.make_packet(self.src_port, self.send_addr[1], 
			                     seq_num, ack_num, 
			                     pattern, payload, 
			                     checksum_)
		
		# send the packet
		self.send_socket.sendto(pkt, self.send_addr)

	def _listen(self, lock):
		"""
		Listens on `self.ack_port` for ACKs from receiver
		ACKs are assumed to arrive without 
		delay or loss, but can be corrupted.
		
		"""
		logging.info("TCPSender::_listen")

		# create a listening socket
		ack_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		ack_socket.bind(("", self.ack_port))

		logging.info("sender is ready to receive ACKs")

		while not self.done:

			pkt, _ = ack_socket.recvfrom(self.MSS + 20) # max size of payload and
														# 20 bytes of header
			
			# check if ACK is corrupted
			uncorrupted = checksum.receiver_check(pkt)
			
			if uncorrupted:

				rtn = packet.decode_packet(pkt)
				if rtn["is_ack"]: # should always be
					y = rtn["ack_num"]

					lock.acquire()

					# if this is the next expected packet, increment
					if rtn["seq_num"] == self.ack_num:
						self.ack_num += 1

					logging.info("received ACK %s", y)

					if y > self.SendBase:

						# iterate through self.ack_dict
						# and for each key (sequence #) that is less than y,
						# set the value in self.ack_dict to True
						# (might be redundant, but that's okay!)
						for seq_num in self.ack_dict:
							if seq_num < y:
								self.ack_dict[seq_num] = True

						# if we are currently timing the RTT for a packet and
						# y is greater than self.RTT_seq_num
						# then we update the RTT values because this is an ACK
						# for that packet
						if self.RTT_seq_num != None and y > self.RTT_seq_num:
							self._update_rtt_fields(time.time() - self.RTT_timer)
							self.RTT_timer = None
							self.RTT_seq_num = None

						# if this ACK is for a retransmitted packet
						# set self.rtm_seq_num back to None
						if self.rtm_seq_num != None and y > self.rtm_seq_num:
							self.rtm_seq_num = None
							self.rtm_count = 0

						# update SendBase
						self.SendBase = y
						
						# if there are currently any un-ACKed packets
						lst = [self.ack_dict[seq_num] for seq_num in self.ack_dict.keys() if seq_num < self.NextSeqNum]
						if False in lst:
							# restart timer
							self.timer = self.timeout + time.time()
						
						# if all packets in send buffer were sent and we have received
						# ACKs for all of them, self.done should be set to true
						if False not in self.ack_dict.values():
							self.done = True

					lock.release()

		# wait for server to send a FIN
		cond = lambda: True
		_time = None
		while cond():
			
			pkt, _ = ack_socket.recvfrom(self.MSS + 20) # max size of payload and
														# 20 bytes of header
			
			# check if ACK is corrupted
			uncorrupted = checksum.receiver_check(pkt)
			
			if uncorrupted:

				rtn = packet.decode_packet(pkt)
				
				# if this is the next expected packet from the server
				# and the packet is a FIN
				if rtn["is_fin"] and rtn["seq_num"] == self.ack_num:

					logging.info("received FIN")

					# send an ACK
					self._send_data_pkt(None, self.NextSeqNum, self.ack_num + 1, 0)

					if _time == None:
						_time = time.time() + 120 # enter waiting period of 2 minutes
						cond = lambda: time.time() >= _time



	def _check_timer(self, lock):
		"""
		Check for timeouts
		"""
		logging.info("TCPSender::_check_timer")

		while not self.done:

			if self._timeout():

				lock.acquire()
				
				# self.done could have been changed while
				# waiting for another thread to release the lock
				if self.done:
					break

				# accounts for delayed execution from threading
				# (e.g., actual timeout occurs while a received ACK is processed)
				if not self._timeout():
					continue
				
				logging.info("timeout for packet %s", self.SendBase)
				
				# retransmit unACKed segment with 
				# smallest sequence number (self.SendBase)

				# if we aren't retransmitting the FIN
				if not self._received_file():
					self._send_data_pkt(self.send_buffer[self.seq_num_idx[self.SendBase]], 
						                self.SendBase, self.ack_num, 3)
				# if we are retransmitting the FIN
				else:
					self._send_data_pkt(self.send_buffer[self.seq_num_idx[self.SendBase]], 
						                self.SendBase, self.ack_num, 1)

				# exclude retransmitted packets from
				# RTT estimate
				if self.RTT_seq_num != None and self.RTT_seq_num == self.SendBase:
					self.RTT_seq_num = None
					self.RTT_timer = None
				
				##
				# on timeout, we double the timeout interval
				#

				# if the current timeout interval was not
				# obtained from doubling on timeout for the same packet
				if self.rtm_seq_num == None:
					self.rtm_seq_num = self.SendBase
					self.rtm_count = 1
				# otherwise, we increment the retransmission count
				else:
					self.rtm_count += 1
				self.timer = (self.timeout * self.rtm_count * 2) + time.time()

				lock.release()

	def _received_file(self):
		"""
		Returns True if the receiver has received the file
		"""
		
		# get the sequence number of the FIN chunk
		seq_fin_ = max(self.seq_num_idx.keys())
		
		return self.SendBase == seq_fin_


	def _send_file(self, lock):
		"""
		Send packets as `window` 
		gets shifted

		"""

		logging.info("TCPSender::_send_file")

		# keep looping until we have sent all file chunks
		# in the send buffer
		
		seq_fin_ = max(self.seq_num_idx.keys())
		
		while self.NextSeqNum != seq_fin_:

			unACKed_bytes = self.NextSeqNum - self.SendBase

			while unACKed_bytes < self.windowsize and self.NextSeqNum != seq_fin_:

				# get idx of pkt with sequence number self.NextSeqNum
				# in self.send_buffer
				idx = self.seq_num_idx[self.NextSeqNum]
				chunk = self.send_buffer[idx]

				# if the total number of unACKed bytes will 
				# exceed the windowsize after sending the packet,
				# stop
				if len(chunk) + unACKed_bytes > self.windowsize:
					break

				lock.acquire()
				
				# send next packet with sequence number of self.NextSeqNum
				self._send_data_pkt(chunk, self.NextSeqNum, self.ack_num, 3)

				# if the timer isn't currently running, start the timer
				if self.timer == None:
					self.timer = time.time() + self.timeout

				# if we're not currently measuring SampleRTT
				# start the timer
				if self.RTT_seq_num == None:
					self.RTT_seq_num = self.NextSeqNum
					self.RTT_timer = time.time()

				# update by adding size of pkt in bytes to NextSeqNum
				self.NextSeqNum += len(chunk)

				lock.release()

				unACKed_bytes += len(chunk)

		# now, self.NextSeqNum is seq_fin_
		#
		# we loop until we are sure that the receiver
		# has received the file
		# 
		# when this happens, we can send a FIN
		while True:

			if self._received_file():

				lock.acquire()

				logging.info("sending FIN")

				# send FIN
				self._send_data_pkt(self.send_buffer[-1], self.NextSeqNum,
				                    self.ack_num, 1)

				# if the timer isn't currently running, start the timer
				if self.timer == None:
					self.timer = time.time() + self.timeout

				self.NextSeqNum += 1

				lock.release()

				# exit
				break


	def _init_send_buffer(self):
		"""
		Initialize self.send_buffer and self.ack_dict

			self.send_buffer is a list of chunks (each of size MSS bytes)
			self.ack_dict is a dictionary mapping the indices of 
							self.send_buffer to booleans indicating whether 
							the corresponding chunks have been ACK-ed or not
		"""
		logging.info("TCPSender::_init_send_buffer")

		# read input file (in binary mode) in 
		# chunks of size self.MSS bytes
		self.send_buffer = []
		with open(self.file, "rb") as reader:
			chunk = reader.read(self.MSS)
			while chunk:
				self.send_buffer.append(chunk)
				chunk = reader.read(self.MSS)

		logging.info("send_buffer: %s", self.send_buffer)

		# map sequence number to corresponding 
		# idx in self.send_buffer
		self.seq_num_idx = {idx*self.MSS:idx for idx in range(0, len(self.send_buffer))}

		# map sequence number to booleans
		self.ack_dict = {num:False for num in self.seq_num_idx.keys()}

		# add FIN chunk (payload is None)
		self.send_buffer.append(None)
		# the last chunk may contains less than self.MSS bytes,
		# so to determine the sequence number of the FIN segment,
		# add the size of the last chunk to the largest sequence number
		size_of_last = len(self.send_buffer[-2])
		fin_seq_num = size_of_last + max(self.seq_num_idx.keys())
		self.seq_num_idx[fin_seq_num] = len(self.send_buffer) - 1
		self.ack_dict[fin_seq_num] = False

		logging.info("seq_num_idx: %s", self.seq_num_idx)
		logging.info("ack_dict: %s", self.ack_dict)



def parse_args():
	"""
	Populates variables at the top of the file
	by parsing CLI input

	Expects `tcpclient file address_of_udpl port_number_of_udpl windowsize ack_port_number`
	"""
	logging.info("tcpclient.parse_args")

	if len(sys.argv) != 6:
		logging.error("Please specify all required arguments.")
		return

	INPUT_FILE, ADDR_OF_UDPL, PORT_NUMBER_OF_UDPL, WINDOWSIZE, ACK_PORT_NUMBER = sys.argv[1:]
	return INPUT_FILE, ADDR_OF_UDPL, int(PORT_NUMBER_OF_UDPL), int(WINDOWSIZE), int(ACK_PORT_NUMBER)


if __name__ == '__main__':

	# parse arguments from CLI
	INPUT_FILE, ADDR_OF_UDPL, PORT_NUMBER_OF_UDPL, WINDOWSIZE, ACK_PORT_NUMBER = parse_args()

	logging.info("CLI args: %s %s %s %s %s", 
		         INPUT_FILE, ADDR_OF_UDPL, 
		         PORT_NUMBER_OF_UDPL,
		         WINDOWSIZE, ACK_PORT_NUMBER)

	# initialize a `TCPSender` instance
	sender = TCPSender(INPUT_FILE, ADDR_OF_UDPL, 
		               PORT_NUMBER_OF_UDPL,
		               WINDOWSIZE, ACK_PORT_NUMBER)


	lock = threading.Lock()

	t1 = threading.Thread(target=TCPSender._listen, args=(sender, lock,)) 
	t2 = threading.Thread(target=TCPSender._send_file, args=(sender, lock,))
	t3 = threading.Thread(target=TCPSender._check_timer, args=(sender, lock,))

	t1.start()
	t2.start()
	t3.start()

	t1.join()
	t2.join()
	t3.join()

