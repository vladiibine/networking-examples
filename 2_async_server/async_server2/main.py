import dataclasses
import socket
from typing import Callable

from server import Reactor, create_async_server_socket, readline


@dataclasses.dataclass
class Command:
    name: str
    func: Callable[[bytes], bytes]

    def case_self(self):
        return self.func(self.name.encode())

    def switching_to_msg(self):
        return b"<Switching to %a cased mode>\r\n" % self.case_self()

    def echo_msg(self, msg: bytes):
        return b"%a-cased: %a\r\n" % (self.case_self(), msg)


async def nonblocking_caser(s: socket.socket):
    cmd_quit = 'quit'
    cmd_upper = 'upper'
    cmd_title = 'title'
    cmd_lower = 'lower'
    cmd_help = 'help'

    possible_modes = {
        cmd_upper: Command(cmd_upper, bytes.upper,),
        cmd_title: Command(cmd_title, bytes.title,),
        cmd_lower: Command(cmd_lower, bytes.lower,),
    }

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
            elif line in possible_modes:
                for mode_candidate in possible_modes:
                    if mode is not mode_candidate and line == mode_candidate:
                        s.sendall(possible_modes[mode].switching_to_msg())
                        mode = mode_candidate
            else:
                s.sendall(possible_modes[mode].echo_msg(line.encode('utf-8')))

            print(f"From {Reactor.get_instance().get_address_of(s)} got {line}")
    finally:
        print(f"{Reactor.get_instance().get_address_of(s)} quit")


if __name__ == '__main__':
    reactor = Reactor.get_instance()

    server_socket = create_async_server_socket('localhost', 1848)
    reactor.add_server_socket_and_callback(server_socket, nonblocking_caser)

    reactor.start_reactor()
