import pygbag.aio as asyncio

import sys
import aio
import time
import socket
import select
import json
import base64


import io, socket


# TODO: use websockets module when on desktop to connect to service directly.

# for now the goal is to connect directly without more dependency to
# a mini irc included with pygbag python module that will capture all traffic
# for local testing purpose.


async def aio_sock_open(sock, host, port):
    print(f"20:aio_sock_open({host=},{port=}) {aio.cross.simulator=}")
    if aio.cross.simulator:
        host, trail = host.strip(":/").split("/", 1)
        port = int(trail.rsplit("/", 1)[-1])
        print(f"21:aio_sock_open({host=},{port=})")


    while True:
        try:
            sock.connect(
                (
                    host,
                    port,
                )
            )
        except BlockingIOError:
            await aio.sleep(0)
        except OSError as e:
            # 30 emsdk, 106 linux means connected.
            if e.errno in (30, 106):
                return sock
            sys.print_exception(e)


class aio_sock:
    def __init__(self, url, mode, tmout):
        host, port = url.rsplit(":", 1)
        self.port = int(port)
        # we don't want simulator to fool us
        if __WASM__ and __import__("platform").is_browser:
            if not url.startswith("://"):
                pdb(f"switching to {self.port}+20000 as websocket")
                self.port += 20000
            else:
                _, host = host.split("://", 1)

        self.host = host

        self.socket = socket.socket()
        # self.sock.setblocking(0)

    # overload socket directly ?

    def fileno(self):
        return self.sock.fileno()

    def send(self, *argv, **kw):
        self.sock.send(*argv, **kw)

    def recv(self, *argv):
        return self.sock.recv(*argv)

    # ============== specific ===========================

    async def __aenter__(self):
        # use async
        print("64: aio_sock_open", self.host, self.port)
        await aio_sock_open(self.socket, self.host, self.port)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        aio.protect.append(self)
        aio.defer(self.socket.close, (), {})
        del self.port, self.host, self.socket

    def read(self, size=-1):
        return self.recv(0)

    def write(self, data):
        if isinstance(data, str):
            return self.socket.send(data.encode())
        return self.socket.send(data)

    def print(self, *argv, **kw):
        kw["file"] = io.StringIO(newline="\r\n")
        print(*argv, **kw)
        self.write(kw["file"].getvalue())

    def __enter__(url, mode, tmout):
        # use softrt (wapy)
        return aio.await_for(self.__aenter__())

    def __exit__(self, exc_type, exc, tb):
        # self.socket.close()
        pass


# TODO: get host url and lobby name from a json config on CDN
# to allow redirect to new server without breaking existing games.

# from enum import auto ?


class Node:
    CONNECTED = "a"
    RX = "b"
    PING = "c"
    PONG = "d"
    RAW = "e"
    LOBBY = "f"
    HELLO = "g"
    OFFER = "h"
    USERS = "i"
    SPURIOUS = "j"

    GLOBAL = "k"
    USERLIST = "l"
    JOINED = "m"
    TOPIC = "o"
    LOBBY_GAME = "p"
    GAME = "q"
    SYNC = "r"
    CMD = "cmd"
    PID = "pid"
    B64JSON = "j64"

    host = "://pmp-p.ddns.net/wss/6667:443"
    lobby = "#pygbag"
    lobby_channel = f"{lobby}-0"
    lobby_topic = "Welcome to Pygbag lobby [hosted by pmp-p]"

    events = []

    # initial process is pygbag lobby chat.
    gid = 0
    groupname = "Lobby"

    pstree = {}

    def __init__(self, gid=0, groupname="", host="", offline=False):
        self.aiosock = None

        self.gid = gid or self.gid
        self.groupname = groupname or self.groupname

        self.users = {}

        self.rxq = []
        self.txq = []
        self.offline = offline
        self.alarm_set = 0

        # last joined channel
        self.joined = ""

        # topics bookeeping
        self.channel = self.lobby_channel
        self.topics = {}

        if not offline:
            aio.create_task(self.connect(host or self.host))

        # if there's no chanserv, then first arrived will have to do it
        self.topic_todo = []

        # game host is root
        self.uid = 0

        # no game running on start
        self.pid = 0

        # default is take over channel (operator)
        self.fork = -1

    async def connect(self, host):
        self.peek = []
        async with aio_sock(host, "a+", 5) as sock:
            self.host = host
            self.events.append(self.CONNECTED)
            self.aiosock = sock
            self.alarm()

            while not aio.exit:
                rr, rw, re = select.select([sock.socket], [], [], 0)
                if rr or rw or re:
                    while not aio.exit and self.aiosock:
                        try:
                            # emscripten does not honor PEEK
                            # peek = sock.socket.recv(1, socket.MSG_PEEK |socket.MSG_DONTWAIT)
                            one = sock.socket.recv(1, socket.MSG_DONTWAIT)
                            if one:
                                self.peek.append(one)
                                # full line let's send that to event processing
                                if one == b"\n":
                                    self.rxq.append(b"".join(self.peek))
                                    self.peek.clear()
                                    self.events.append(self.RX)
                                    break
                            else:
                                # lost con.
                                print("HANGUP", self.peek)
                                self.aiosock = None
                                print("TODO: ask for reconnect")
                                return
                        except BlockingIOError as e:
                            if e.errno == 6:
                                await aio.sleep(0)
                else:
                    await aio.sleep(0)
            sock.print("DISCONNECT")

    def publish(self):
        self.lobby_cmd(
            self.gid,
            self.pid,
            self.OFFER,
            self.groupname,
            hint=f" {self.lobby}-{self.gid} : Game offer {self.groupname=} started with {self.pid=}",
        )

    # default for data is speak into lobby with gameid>0
    def tx(self, obj, mem=False, shm=False):
        ser = json.dumps(obj)

        if self.fork < 0:
            self.fork = 0
            self.wire(f"JOIN #pygbag-{self.gid}")
            self.topic_todo.append([f"#pygbag-{self.gid}", self.groupname.replace(" ", "_")])

        # autopublish is broken
        #            self.publish()

        if mem:
            self.pstree[self.pid]["mem"].append(ser)
        if shm:
            self.pstree[self.pid]["shm"].append(ser)

        self.out(self.B64JSON + ":" + base64.b64encode(ser.encode("ascii")).decode("utf-8"), gid=self.gid)

    def pscheck(self, pid, nick):
        self.pstree.setdefault(int(pid), {"nick": nick, "mem": [], "shm": [], "rev": 0, "forks": []})

    def privmsg(self, cpid, data):
        nick = self.pstree[cpid]["nick"]
        self.wire(f"PRIVMSG {nick} :{data}")

    def lobby_cmd(self, *cmd, hint=""):
        data = ":".join(map(str, cmd))

        if hint:
            self.out(f"{data}§{hint}")
        else:
            self.out(data)

    # default for text is speak into lobby (gameid == 0)

    def out(self, *blocks, gid=-1):
        if gid < 0:
            gid = 0
        if gid:
            self.wire(f"PRIVMSG {self.lobby}-{gid} :{self.fork}:{self.pid}:{' '.join(map(str, blocks))}")
        else:
            self.wire(f"PRIVMSG {self.lobby_channel} :{' '.join(map(str, blocks))}")

    # TODO: handle hangup/reconnect nicely (no flood)
    def wire(self, rawcmd):
        if self.offline:
            print("WIRE:", rawcmd)
        else:
            self.txq.append(rawcmd)
            if self.aiosock and self.aiosock.socket:
                while len(self.txq):
                    self.aiosock.print(self.txq.pop(0))

    def quit(self, msg="DISCONNECT"):
        self.out(msg)
        self.aiosock.socket.close()
        self.aiosock = None

    def check_topic(self):
        if self.joined != self.lobby_channel:
            return False

        if not self.topics[self.lobby_channel]:
            todo = [self.lobby_channel, self.lobby_topic.replace(" ", "_")]
            self.topic_todo.append(todo)

    # motd join userlist ping pong

    def process_server(self, cmd, line):
        self.discarded = False

        if cmd.find(f" 331 ") > 0:
            if line == "No topic is set":
                self.topics[self.joined] = ""
                self.check_topic()
                return self.discard()

            print("267: topic noise", line)
            return self.discard()

        if cmd.find(f" 332 ") > 0:
            self.proto = "topic"
            self.joined = cmd.strip().rsplit(" ", 1)[-1]
            self.topics[self.joined] = line.strip()
            self.check_topic()
            self.channel = self.joined
            yield self.TOPIC
            return self.discard()

        # TODO clear userlist on JOIN
        if cmd.find(" 353 ") > 0:
            self.proto = "users"
            self.data = line.split(" ")
            for u in self.data:
                if not u in self.users:
                    self.users.setdefault(u, {})

            yield self.USERS
            return self.discard()

        if cmd.find(" 366 ") > 0:
            self.check_topic()
            todel = []
            for idx, todo in enumerate(self.topic_todo):
                if self.joined == todo[0]:
                    if not self.topics[self.joined]:
                        send = f"TOPIC {todo[0]} {todo[1]}"
                        print("sent topic:", send)
                        self.wire(send)
                    todel.append(idx)
            while len(todel):
                self.topic_todo.pop(todel.pop())

            yield self.USERLIST
            return self.discard()

        if cmd.find(" JOIN #") > 0:
            self.proto = "join"
            self.joined = cmd.split(" JOIN ")[-1]
            self.data = self.joined

            yield self.JOINED
            return self.discard()

        if cmd.find(" TOPIC ") > 0:
            _, self.channel = cmd.strip().split(" TOPIC ", 1)
            self.topics[self.channel] = line.strip()
            yield self.TOPIC
            return self.discard()

        if cmd.find(" PONG ") > 0:
            self.proto, self.data = cmd.strip().split(" PONG ", 1)
            yield self.PONG
            return self.discard()

        for srv in "001 002 003 004 251 375 372 376".split(" "):
            if cmd.find(f" {srv} ") > 0:
                self.proto = cmd
                self.data = line.strip()
                yield self.GLOBAL
                return self.discard()

        if cmd.find("PING ") >= 0:
            print("348: PING ?")
            self.proto, self.data = cmd.strip().split(":", 1)
            self.wire(line.replace("PING ", "PONG ", 1))
            yield self.PING
            return self.discard()

    # handle Lobby commands : game offer, lobby chat

    def process_lobby(self, cmd, line):
        self.discarded = False

        maybe_hint = line.rsplit("§", 1)

        if len(maybe_hint) > 1:
            self.hint = maybe_hint[-1]
            print("HINT", maybe_hint[-1])
            line = maybe_hint[0]
        else:
            self.hint = ""

        room = f" {self.lobby_channel} "
        if cmd.endswith(room):
            try:
                nick = cmd.split("!", 1)[0]
                gid, pid, proto, info = line.split(":", 3)
                node.pstree.setdefault(int(pid), {"nick": nick, "mem": [], "shm": [], "rev": 0})

                # that's our game
                if gid == str(self.gid):
                    self.proto = [proto, int(pid), nick, info]
                    self.data = line
                    yield self.LOBBY_GAME
                    return self.discard()

                # or still see others
                yield self.LOBBY
            except:
                self.proto = cmd
                self.data = line
                yield self.SPURIOUS

            return self.discard()

    # handle game fork / game logic
    def process_game(self, cmd, line):
        self.discarded = False
        privmsg = f" {self.nick} "

        # TODO route msg or game
        if cmd.endswith(privmsg):
            if line.startswith(f"{node.B64JSON}:"):
                try:
                    _, data = line.split(":", 1)
                    data = base64.b64decode(data.encode())
                    self.data = json.loads(data.decode())
                    yield self.GAME
                    return self.discard()

                except Exception as e:
                    sys.print_exception(e)
            print("PRIV ?:", cmd, line)
            return self.discard()

        room = f" {self.lobby}-{self.gid} "

        self.proto = cmd
        self.data = line
        if cmd.endswith(room):
            game = f"{self.fork or self.pid}:"

            if self.fork:
                self.proto = "fork"
                if line.startswith("0:"):
                    _, pid, msgtype, data = line.split(":", 3)

                    # ND rpid could be different from payload pid in case of message relaying
                    # on a mesh.
                    # rpid = int(pid)
                    try:
                        if msgtype == node.B64JSON:
                            data = base64.b64decode(data.encode())
                            self.data = json.loads(data.decode())
                            yield self.SYNC
                            return self.discard()

                    except Exception as e:
                        sys.print_exception(e)

            else:
                self.proto = "main"

            # print(f"i am {self.nick}({self.proto}) filtering on {game=} {line=}")

            if line.startswith(game):
                _, pid, msgtype, data = line.split(":", 3)

                # ND rpid could be different from payload pid in case of message relaying
                # on a mesh.
                # rpid = int(pid)
                try:
                    if msgtype == node.B64JSON:
                        data = base64.b64decode(data.encode())
                        self.data = json.loads(data.decode())
                        yield self.GAME
                        return self.discard()

                except Exception as e:
                    sys.print_exception(e)

            # uncompatible fork and not PR.
            else:
                self.proto = "noise"

        yield self.SPURIOUS
        return self.discard()

    # push a pull, as a response to a clone demand
    def checkout_for(self, n_data):
        cpid = int(n_data[node.PID])
        self.pscheck(cpid, n_data["nick"])

        current = self.pstree[cpid].get("rev", 0)

        # register new fork
        if not current:
            self.pstree[self.pid]["forks"].append(cpid)

        # TODO send expected rev number before flooding + global checksum
        # TODO use a task to avoid flood
        # TODO sign packets
        for idx, ser in enumerate(self.pstree[self.pid]["shm"], current):
            self.privmsg(cpid, self.B64JSON + ":" + base64.b64encode(ser.encode("ascii")).decode("utf-8"))
            node.pstree[cpid]["rev"] = idx

    # TODO invalidate fork try on timeout
    def clone(self, ppid):
        self.fork = int(ppid)
        self.tx({node.CMD: "clone", node.PID: self.pid, "main": self.fork, "nick": self.nick})

    def discard(self):
        self.discarded = True

    def alarm(self):
        t = time.time()

        if t >= self.alarm_set:
            self.alarm_set = t + 30
            return self.alarm_set
        return 0

    def get_events(self):
        alarm = self.alarm()

        if alarm:
            self.wire(f"PING :{alarm}")

        while len(self.events):
            ev = self.events.pop(0)

            if ev == self.RX:
                while len(self.rxq):
                    srvdata = self.rxq.pop(0).decode("utf-8").strip().split(":", 2)
                    noise = srvdata.pop(0)
                    if noise:
                        print(f"364: server {noise=} on rxq, remaining {srvdata=}")

                    if len(srvdata) < 2:
                        srvdata.append("")

                    yield from self.process_server(*srvdata)

                    if not self.discarded:
                        yield from self.process_lobby(*srvdata)

                    if not self.discarded:
                        yield from self.process_game(*srvdata)

                    if not self.discarded:
                        self.data = ":".join(srvdata)
                        yield self.RAW
                continue

            if ev == self.CONNECTED:
                # attribute a pseudo random pid to network agent, use that for uid nickname
                # not foolproof should use a service for that
                stime = str(time.time())[-5:].replace(".", "")
                self.pid = int(stime)
                self.nick = "u_" + str(self.pid)
                self.pscheck(self.pid, self.nick)

                # TODO: maybe do not list as channels members people who don't want to chat
                # that still allow to send game start info to lobby when no channel mode enforced

                d = {"nick": self.nick, "channel": self.lobby_channel}

                self.aiosock.print(
                    """CAP LS\r\nNICK {nick}\r\nUSER {nick} {nick} localhost :wsocket\r\nJOIN {channel}""".format(**d)
                )
                self.lobby_cmd(self.gid, self.pid, self.HELLO, self.nick, hint=f"Hi from {self.nick}")
            else:
                print(f"402:? {ev=} {self.rxq=}")

            yield ev





if __name__ == "__main__":
    from pygbag_net_minimal import main
    asyncio.run(main())
