import zmq


class SocketServer:
    def __init__(self):
        self.ctx = zmq.Context()
        self.socket = self.ctx.socket(zmq.REP)
        self.socket.bind("tcp://*:5555")

    def send_message(self, message):
        msg = self.socket.recv_string()
        print("sending message")
        self.socket.send_string(f"{message}")
