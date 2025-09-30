import socket
import threading
import json
import time
import os

HOST = "0.0.0.0"
PORT = 6000
TICK_INTERVAL = 1.0  # seconds between broadcasts
MAP_FILE = "1.map"

lock = threading.Lock()
clients = {}   # name -> {'conn': socket, 'addr': addr}
players = {}   # name -> state dict {x,y,z,h,p,color,hp,ts}

def load_map():
    if not os.path.exists(MAP_FILE):
        default = [
            "############",
            "#..........#",
            "#..~~..##..#",
            "#..~~......#",
            "#......##..#",
            "#..##......#",
            "#..........#",
            "############",
        ]
        with open(MAP_FILE, "w") as f:
            f.write("\n".join(default))
    with open(MAP_FILE, "r") as f:
        return [line.rstrip("\n") for line in f.readlines()]

WORLD_MAP = load_map()

def safe_send(conn, bts):
    try:
        conn.sendall(bts)
        return True
    except Exception:
        return False

def handle_client(conn, addr):
    conn_file = conn.makefile("r")
    name = None
    try:
        # Expect first line to be player name
        raw = conn_file.readline()
        if not raw:
            conn.close(); return
        name = raw.strip()
        if not name:
            conn.close(); return

        with lock:
            clients[name] = {'conn': conn, 'addr': addr}
            players[name] = {'x': 1.0, 'y': 1.0, 'z': 1.5, 'h': 0.0, 'p': 0.0,
                             'color': '#ff0000', 'hp': 100, 'ts': time.time()}

        print(f"[connect] {name} @ {addr}")

        # Send the map once on connect (clients may ignore if they load local map)
        try:
            map_msg = {"type": "map", "payload": {"map": WORLD_MAP}}
            conn.sendall((json.dumps(map_msg) + "\n").encode())
        except Exception:
            pass

        # Read JSON lines from client. Clients will periodically send position snapshots.
        while True:
            line = conn_file.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") == "pos":
                payload = obj.get("payload", {})
                with lock:
                    st = players.get(name, {})
                    try:
                        st['x'] = float(payload.get("x", st.get('x', 1.0)))
                        st['y'] = float(payload.get("y", st.get('y', 1.0)))
                        st['z'] = float(payload.get("z", st.get('z', 1.5)))
                        st['h'] = float(payload.get("h", st.get('h', 0.0)))
                        st['p'] = float(payload.get("p", st.get('p', 0.0)))
                        st['color'] = str(payload.get("color", st.get('color', '#ff0000')))
                        st['hp'] = int(payload.get("hp", st.get('hp', 100)))
                        st['ts'] = time.time()
                        players[name] = st
                    except Exception:
                        pass
            # ignore other message types

    except Exception as e:
        print("client handler exception:", e)
    finally:
        with lock:
            if name:
                print(f"[disconnect] {name}")
                clients.pop(name, None)
                players.pop(name, None)
        try:
            conn.close()
        except:
            pass

def broadcast_loop():
    while True:
        time.sleep(TICK_INTERVAL)
        with lock:
            snapshot = {
                "type": "state",
                "payload": {
                    "players": players,
                    "t": time.time()
                }
            }
            raw = (json.dumps(snapshot) + "\n").encode()
            dead = []
            for name, info in list(clients.items()):
                conn = info['conn']
                ok = safe_send(conn, raw)
                if not ok:
                    dead.append(name)
            for d in dead:
                print(f"[cleanup] removing {d}")
                clients.pop(d, None)
                players.pop(d, None)

def main():
    print("Loading map from", MAP_FILE)
    print("Map size:", len(WORLD_MAP), "rows")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(32)
    print(f"Server listening on {HOST}:{PORT} (LAN)")

    threading.Thread(target=broadcast_loop, daemon=True).start()

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("Server shutting down...")
    finally:
        server.close()

if __name__ == "__main__":
    main()
