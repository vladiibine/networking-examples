import socket
from server import Reactor, create_async_server_socket, readline


async def nonblocking_caser(s: socket.socket):
    cmd_quit = 'quit'
    cmd_upper = 'upper'
    cmd_title = 'title'
    cmd_lower = 'lower'
    cmd_help = 'help'

    mode = cmd_upper
    print(f"Received connection from {Reactor.get_instance().get_address_of(s)}")

    try:
        s.sendall(b"<Welcome to the echo-server! Starting in upper case mode>\r\n")
        s.sendall(b"<To see the available commands, type \"help\" and press return>\r\n")
        while True:
            line = await readline(s)

            if line == cmd_quit:
                s.sendall(b"bye!\r\n")
                return

            if line == cmd_help:
                s.sendall(b"Available commands: \r\n"
                          b"help - shows the available commands\r\n"
                          b"quit - quits the session\r\n"
                          b"upper - sets the echoing mode to UPPER case\r\n"
                          b"lower - sets the echoing mode to lower case\r\n"
                          b"title - sets the echoing mode to Title case\r\n"
                          )
                continue

            if mode is not cmd_title and line == cmd_title:
                s.sendall(b"<switching to Title case mode>\r\n")
                mode = cmd_title
                continue

            if mode is not cmd_upper and line == cmd_upper:
                s.sendall(b"<switching to UPPER case mode>\r\n")
                mode = cmd_upper
                continue

            if mode is not cmd_lower and line == cmd_lower:
                s.sendall(b"<Switching to lower case mode>\r\n")
                mode = cmd_lower
                continue

            if mode is cmd_upper:
                s.sendall(b"UPPER-cased: %a \r\n" % line.upper())
            elif mode is cmd_title:
                s.sendall(b"Title-cased: %a \r\n" % line.title())
            elif mode is cmd_lower:
                s.sendall(b"lower-cased: %a \r\n" % line.lower())

            print(f"From {Reactor.get_instance().get_address_of(s)} got {line}")
    finally:
        print(f"{Reactor.get_instance().get_address_of(s)} quit")


if __name__ == '__main__':
    reactor = Reactor.get_instance()

    server_socket = create_async_server_socket('localhost', 1848)
    reactor.add_server_socket_and_callback(server_socket, nonblocking_caser)

    reactor.start_reactor()
