import aio

from pygbag_net import Node

async def main():
    global node

    node = Node()

    while not aio.exit:
        for ev in node.get_events():
            try:
                if ev == node.SYNC:
                    cmd = node.data[node.CMD]
                    print("SYNC:", node.proto, node.data, cmd)

                elif ev == node.GAME:
                    cmd = node.data[node.CMD]
                    print("GAME:", node.proto, node.data, cmd)

                    if cmd == "clone":
                        # send all history to child
                        node.checkout_for(node.data)

                    elif cmd == "ingame":
                        print("TODO: join game")
                    else:
                        print("602 ?", cmd,  node.data)

                elif ev == node.CONNECTED:
                    print(f"CONNECTED as {node.nick}")

                elif ev == node.JOINED:
                    print("Entered channel", node.joined)
                    if node.joined == node.lobby_channel:
                        node.tx({node.CMD: "ingame", node.PID: node.pid})

                elif ev == node.TOPIC:
                    print(f'[{node.channel}] TOPIC "{node.topics[node.channel]}"')

                elif ev in [node.LOBBY, node.LOBBY_GAME]:
                    cmd, pid, nick, info = node.proto

                    if cmd == node.HELLO:
                        print("Lobby/Game:", "Welcome", nick)
                        # publish if main
                        if not node.fork:
                            node.publish()

                    elif (ev == node.LOBBY_GAME) and (cmd == node.OFFER):
                        if node.fork:
                            print("cannot fork, already a clone/fork pid=", node.fork)
                        elif len(node.pstree[node.pid]["forks"]):
                            print("cannot fork, i'm main for", node.pstree[node.pid]["forks"])
                        else:
                            print("forking to game offer", node.hint)
                            node.clone(pid)

                    else:
                        print(f"\nLOBBY/GAME: {node.fork=} {node.proto=} {node.data=} {node.hint=}")

                elif ev in [node.USERS]:
                    ...

                elif ev in [node.GLOBAL]:
                    print("GLOBAL:", node.data)

                elif ev in [node.SPURIOUS]:
                    print(f"\nRAW: {node.proto=} {node.data=}")

                elif ev in [node.USERLIST]:
                    print(node.proto, node.users)

                elif ev == node.RAW:
                    print("RAW:", node.data)

                elif ev == node.PING:
                    # print("ping", node.data)
                    ...
                elif ev == node.PONG:
                    # print("pong", node.data)
                    ...

                # promisc mode dumps everything.
                elif ev == node.RX:
                    ...

                else:
                    print(f"52:{ev=} {node.rxq=}")
            except Exception as e:
                print(f"52:{ev=} {node.rxq=} {node.proto=} {node.data=}")
                sys.print_exception(e)

        await aio.sleep(0)

