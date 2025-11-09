import logging

class Pkt:

    def __init__(self):
        self.seqnum = None
        self.checksum = None
        self.payload = ""

    def get_seqnum(self):
        return self.seqnum

    def set_seqnum(self, n):
        self.seqnum = n

    def get_payload(self):
        return self.payload

    def set_payload(self, p):
        self.payload = p

    def get_checksum(self):
        return self.checksum

    def set_checksum(self, n):
        self.checksum = n

    def calc_checksum(self):
        # TODO
        self.calc = 0
        for char in self.payload:
            self.calc = self.calc + ord(char)

        self.set_checksum(self.calc + self.seqnum)

    def verify_checksum(self):
        # TODO
        self.verify = 0
        for char in self.payload:
            self.verify = self.verify + ord(char)

        self.verify = self.verify + self.seqnum
        return self.verify == self.get_checksum()

class RDTSender:

    def __init__(self, udt, timer):
        self.udt = udt
        self.timer = timer
        # TODO: add any other state variables you need
        self.pkt = Pkt()
        self.msg = None
        self.waiting_for_ack = False
        self.pkt.set_seqnum(0)
        self.current_seqnum = self.pkt.get_seqnum()

    def rdt_send(self, msg):
        """Called from layer 5, it should prepare and send the msg to the other side."""
        # TODO
        if self.waiting_for_ack:
            return False
        else:
            self.waiting_for_ack = True

        self.pkt.set_seqnum(self.current_seqnum)
        self.pkt.set_payload(msg)
        self.pkt.calc_checksum()
        self.msg = msg
        self.udt.send(self.pkt)

        self.timer.start(10.0)
        # return true if you sent the value 
        return True

    def rdt_rcv(self, pkt):
        """Called from layer 3 when a packet arrives from the network."""
        # TODO
        if (pkt.get_payload() == "ACK") and (pkt.get_seqnum() == self.current_seqnum) and pkt.verify_checksum():
            self.current_seqnum = 1 - self.current_seqnum
            self.waiting_for_ack = False
            self.timer.stop()

    def timer_interrupt(self):
        """Called when the timer goes off."""
        # TODO
        self.waiting_for_ack = False
        self.rdt_send(self.msg)

class RDTReceiver:
    def __init__(self, udt, app_layer):
        self.udt = udt
        self.app_layer = app_layer
        # TODO: add any other state variables you need
        self.expected_seqnum = 0
        self.previous_seqnum = None

    def rdt_rcv(self, pkt):
        """Called from layer 3, when a packet arrives from the network."""
        # TODO
        if (pkt.get_seqnum() == self.expected_seqnum) and pkt.verify_checksum():
            self.app_layer.deliver_data(pkt.get_payload())
            self.expected_seqnum = 1 - self.expected_seqnum
            self.previous_seqnum = pkt.get_seqnum()
            
            pkt.set_payload("ACK")
            pkt.calc_checksum()
            self.udt.send(pkt)

        elif (pkt.get_seqnum() == self.previous_seqnum) and pkt.verify_checksum():
            pkt.set_seqnum(self.previous_seqnum)
            pkt.set_payload("ACK")
            pkt.calc_checksum()
            self.udt.send(pkt)

