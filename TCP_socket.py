from TCP_socket_p2 import TCP_Connection

#export PATH="$PATH:/koko/system/anaconda3/bin"
#source activate python310

class TCP_Connection_Final(TCP_Connection):
    """docstring for TCP_Connection_Final"""
    def __init__(self, self_address, dst_address, self_seq_num, dst_seq_num, log_file=None):
        super().__init__(self_address, dst_address, self_seq_num, dst_seq_num, log_file)
  
    def measure_RTT(self):
        #helper method for when the first RTT measurement is made (2.2)
        
        self.SRTT = self.RTT_Sequence_num
        self.RTTVAR = self.RTT_Sequence_num / 2

        self.compute_RTO(self)

    def subsequent_RTT(self):
        #helper method for when subsequent RTT measurement R' is made (2.3)
        alpha = 1/8
        beta = 1/4

        self.RTTVAR = (1 - beta) * self.RTTVAR + beta * abs(self.SRTT - self.RTT_Sequence_num)
        self.SRTT = (1 - alpha) * self.SRTT + alpha * self.RTT_Sequence_num

        self.compute_RTO(self)

    def compute_RTO(self):
        #helper function to compute RTO
        #G and K values as specified in RFC
        G = 0.1
        K = 4
        #RTO computation formula RFC 6298 section 2.3
        clock_granularity = self.SRTT + max(G, K * self.RTTVAR)
        #(2.4) Whenever RTO is computed, if it is less than 1 second, then the RTO SHOULD be rounded up to 1 second.
        if(clock_granularity < 1):
            clock_granularity = 1
        self.RTO_timer.set_length(clock_granularity)

    def is_acceptable(self, packet):#NEED TO IMPLEMENT
        #sequence numbers allowed for new reception
        SEG_SEQ = packet.SEQ
        SEG_LEN = len(packet.data)
        if(SEG_LEN == 0 and self.RCV.WND == 0):
            return SEG_SEQ == self.RCV.NXT
        elif(SEG_LEN == 0 and self.RCV.WND > 0):
            return self.RCV.NXT <= SEG_SEQ < self.RCV.NXT + self.RCV.WND
        elif(SEG_LEN > 0 and self.RCV.WND == 0):
            #not acceptable case
            return False
        else:
            if(self.RCV.NXT <= SEG_SEQ < self.RCV.NXT + self.RCV.WND or
                  self.RCV.NXT <= SEG_SEQ + SEG_LEN - 1 < self.RCV.NXT + self.RCV.WND):
                return True
            
        return False

#HELPER FUNCTIONS ^^^^^ HELPER FUNCTIONS

    def handle_timeout(self): #NEED TO IMPLEMENT
        #put code to handle RTO timeout here
        #send a single packet containing the oldest unacknowledged data
        #increase the RTO timer 
        
        # (5.4) Retransmit the earliest segment that has not been acknowledged by the TCP receiver.
        #not correct implementation need logic to read first packet
        to_send = bytearray()
        #loop should run from beginning to end to see if our data contains a PSH flag
        for byte in self.send_buff[:self.SND.MSS]:
            to_send.append(byte)
    
        # in this case the data that is sent is the first byte from the buffer
        self._packetize_and_send(self.SND.UNA, False, to_send)
        
        # (5.5) The host MUST set RTO <- RTO * 2 ("back off the timer").  The  maximum value discussed in (2.5)
        # (5.6) Start the retransmission timer, such that it expires after RTO seconds (for the value of RTO after the doubling operation outlined in 5.5).
        timer_multiple = 2 * self.RTO_timer.timer_length
        self.RTO_timer.set_and_start(timer_multiple)
            
    def handle_window_timeout(self): #NEED TO IMPLEMENT
        #put code to handle window timeout here
        #in other words, if we haven't sent any data in while (which causes this time to go off),
        #send an empty packet
        self._packetize_and_send(self.last_packet) #send packet containing most recent data
        #include some piece of code to reset timer by a factor of 2
                
    def receive_packets(self, packets): #NEED TO IMPLEMENT
        #insert code to deal with a list of incoming packets here
        #NOTE: this code can send one packet, but should never send more than one packet
        #iterate through packets
         
        for packet in packets:
            #process packets
            #check if there is any space in the receive buffer
            if(self.RCV.WND == 0):
                continue
            
            # #check acceptability
            # if(not self.is_acceptable(packet)):
            # #if not acceptable --> send acknowledgement set snd.ack to be true and continue lines 128-129
            #     packet.flags.ACK = True
            #     packet.SEQ = self.SND.NXT
            #     continue
            
            start_seq = packet.SEQ - self.receive_buffer_start_seq
            end_seq = start_seq + len(packet.data)
            ack_flag = False
            #read data into receive buffer
            for byte in packet.data:
                #need to write push flag logic
                #if we have hit the last byte of data in the packet
                if(start_seq == (end_seq-1) and packet.flags.PSH == True):
                    datum = bytes([byte] + list(b'PSH'))
                    self.receive_buffer[end_seq-1] = datum
                    #decrement window as you read into buffer
                    self.RCV.WND -= 1
                    #increment RCV.NXT as you read into buffer
                    self.RCV.NXT += 1
                    ack_flag = True
                else: #read into buffer normally
                    self.receive_buffer[start_seq] = byte
                    #decrement window as you read into buffer
                    self.RCV.WND -= 1
                    #increment RCV.NXT as you read into buffer
                    self.RCV.NXT += 1
                    #increment to place correctly into receive buffer
                    start_seq += 1
                    
            #send ACK
            if(packet.flags.ACK and ack_flag and packet.data != b''):
                self._packetize_and_send(self.SND.NXT)
                #stop timer when data received
                self.RTO_timer.stop_timer()

            #ESTABLISHED STATE 
            #check if SND.UNA needs to be updated if so update send buffer
            if(self.SND.UNA < packet.ACK and packet.ACK <= self.SND.NXT):
                #difference between old snd.una and new
                self.send_buff = self.send_buff[packet.ACK - self.SND.UNA:]
                self.SND.UNA = packet.ACK
            #update send window accordingly           
            elif(self.SND.UNA <= packet.ACK and packet.ACK <= self.SND.NXT):
                self.RCV.WND = packet.WND - len(packet.data)
        return

    def send_data(self, window_timeout = False, RTO_timeout = False):
        
        #put code to send a single packet of data here
        #note that this code does not always need to send data, only if TCP policy thinks it makes sense
        #if there is any data to send, i.e. we have data we have not sent and we are allowed to send by our
        #congestion and flow control windows, then send one packet of that data

        #implementation: 
        #compute in flight data
        in_flightData = self.SND.NXT - self.SND.UNA
        #largest packet size is min of maximum segment size, flow con. window,
        largest_packet_size = min(self.SND.MSS, self.SND.WND-in_flightData)
        
        #if no data send no packet or send window is 0
        if(largest_packet_size <= 0 or len(self.send_buff) == 0):
            return
        
        #calulates correct number of bytes to process for packet
        if(largest_packet_size < len(self.send_buff)):
            process_bytes = largest_packet_size
        else:
            process_bytes = len(self.send_buff)

        #deal with PSH flag
        to_send = bytearray()
        push_flag = False
        #loop should run from beginning to end to see if our data contains a PSH flag
        for byte in self.send_buff[in_flightData:process_bytes+in_flightData]:
            if (not isinstance(byte, int) and byte.endswith(b'PSH')):
                push_flag = True
                byte = byte[0]
            to_send.append(byte)
            self.SND.WND -= 1
        
        #dont send any empty packets
        if(to_send != b''):
            self.last_packet = [self.SND.NXT, push_flag, to_send]
            #acutally send data
            self._packetize_and_send(self.SND.NXT, push_flag, to_send)
            #start timer when we send a packet
            self.RTO_timer.set_and_start(1)
            # increment sequence number to read any remaining data
            self.SND.NXT += process_bytes
        