import zmq


class SocketServer:
    def __init__(self):
        self.ctx = zmq.Context()
        self.socket = self.ctx.socket(zmq.REP)
        self.socket.bind("tcp://*:5555")

    def send_message(self, message):
        self.socket.recv_string()
        print("Enviando mensaje")
        self.socket.send_string(f"{message}")
