# simplex-tcp

simplex-tcp implements TCP over UDP and provides interfaces for both the client and the server. It supports a one-time data exchange   and connection termination at the client (excludes initial handshaking). The client should send data to a link emulator that could possibly corrupt, lose, or delay packets, and the server should directly send ACKs back to the client. 


### Getting Started
---
To run the programs, add the `dist` directory to your machine's `$PATH` variable. 
```
export PATH=$PATH:<your path to dist>
```
If for some reason the executables don't work on your machine, they can be regenerated with `pyinstaller`.
```
pyinstaller -F simplex_client.py
pyinstaller -F simplex_server.py
```

### CLI Entrypoints
---
The client has the following interface:

```
simplex_client file linkAddr linkPort windowSize portForAcks
```
The `windowsize` should be at least the hardcoded MSS, which is 576 bytes. 

The server has the following interface:
```
simplex_server file listenPort ackAddr ackPort
```

### How it works
---
The CLI entry point for the TCP client first instantiates an abstract client instance used to maintain state throughout the connection and creates three threads, each corresponding to three processes: one for listening on a port and receiving ACKs, a second for periodically sending packets from the send buffer (detects when the window has shifted and sends accordingly), and a third for retransmitting when timeouts occur. A lock is passed around between the three threads since each thread modifies the same client state instance (i.e., a thread acquires a lock whenever the state is changed in any way). When a packet is sent, if the timer isn’t currently running, it is started. When a timeout occurs, the unACKed packet with the smallest sequence number is retransmitted and the timer is restarted. When an ACK is received, if its ACK number is larger than the smallest sequence number out of all of the sequence numbers belonging to unACKed packets, if there are currently any not-yet-acknowledged packets, and if the received ACK is uncorrupted, the timer is restarted.
When the abstract client instance is instantiated, it reads in the file, breaks it up into chunks of bytes (each has 576 bytes, except for possibly the last one), and places each chunk in a send buffer. When a packet is sent, its round trip time may be measured and used to update the estimated RTT given by the formula: 

`EstimatedRTT <- 0.875 * EstimatedRTT + 0.125 * SampleRTT`

That is, the estimated RTT is an exponential weighted moving average of the sample RTTs (these specific coefficients were recommended in RFC 6298). RTT’s for retransmitted packets aren’t measured and only one packet is measured at a time. The client also maintains an estimate of how much a sampled RTT typically deviates from the estimated RTT (denoted DevRTT) which is given by the formula:

`DevRTT <- 0.75 * DevRTT + 0.25 * |SampleRTT - EstimatedRTT|`

The initial timeout for the retransmission timer is 1 second. On timeout, the timeout interval is doubled; otherwise, the timeout interval is given by EstimatedRTT + 4 * DevRTT. 
Once the client receives all ACKs for the packets containing the file, the client will send a FIN to the server. Once the client receives an ACK in response to the FIN, it will wait for the server to send a FIN and respond with an ACK. Then, the client enters a waiting period of 2 minutes in case it needs to retransmit the ACK. The client’s connection is closed after this interval.
The CLI entry point for the TCP server first instantiates an abstract server instance used to maintain state throughout the connection, creates a file with the passed in filename if it doesn’t exist, and overwrites the contents of the file with the passed in filename if it does exist. A listening UDP socket is created and bound to the passed in listening port. A logical loop is then entered which receives an incoming packet and checks if it is corrupted by computing the sum over all 16-bit words. If the packet is uncorrupted, packet processing begins; if the packet is a duplicate, an ACK is sent; if the packet has a sequence number that is larger than the expected sequence number, it is buffered since this is more efficient (in terms of network bandwidth) than discarding them; finally, if the packet is in-order, the payload is written to the file and an ACK is sent (if the packet fills in any gaps, the relevant buffered packets get processed in the same way). If a FIN is received from the client, an ACK is sent. Then, a FIN is sent to the client and the server starts waiting for an ACK from the client. To implement this waiting period, two threads were created, one that corresponds to a procedure that checks the timer and retransmits the FIN when the timer expires and another that corresponds to a procedure that listens on the listening port and validates received packets (checks if they are uncorrupted and if they have the correct sequence numbers). The timeout interval is 2 seconds. A lock is passed around between the two threads since each thread modifies the same server state instance (i.e., a thread acquires a lock whenever the state is changed in any way). If the server doesn’t receive an ACK from the client before the client closes the connection, the server will continue running and sending FIN packets.

### Running Simple Unit Tests
---
There are simple unit tests in the `tests` directory. To run them, configure your `PYTHONPATH` variable to include your path to the `utils` directory. Then, run `pytest` on the command line from the root directory.