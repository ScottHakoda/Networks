import socket

# sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# sock.connect(('10.10.0.101',4000))

# dialogue = """
#     She speaks:
#     O, speak again, bright angel! for thou art
#     As glorious to this night, being o'er my head
#     As is a winged messenger of heaven
#     Unto the white-upturned wondering eyes
#     Of mortals that fall back to gaze on him
#     When he bestrides the lazy-pacing clouds
#     And sails upon the bosom of the air.
#     """

# data = sock.recv(1024)
# print("Juliet:")
# print(data.decode("utf-8"), "\n")
# print("Romeo:")
# print(dialogue)
# sock.send(dialogue.encode("utf-8"))

# sock.shutdown(socket.SHUT_RDWR)


def romeo(host, port):
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        sock.sendall(b"Hello World!")
        data  = sock.recv(1024)

    print('Received', repr(data))


import argparse 
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    romeo(args.host, args.port)

if __name__ == "__main__":
    main()  