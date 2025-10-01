import socket, threading, json, yaml, time, os, requests

HOST = "0.0.0.0"
PORT = 6000

players = {}  # conn -> player dict
clients = []

# --- Map manager integrated ---
def ensure_map(map_name, maps_folder="maps"):
    os.makedirs(maps_folder, exist_ok=True)
    map_path = os.path.join(maps_folder, map_name)

    if not os.path.exists(map_path):
        print(f"Map {map_name} not found locally.")
        url = input(f"Enter download link for {map_name} (or 'pass' to skip): ")
        if url.strip().lower() != "pass":
            r = requests.get(url)
            if r.status_code == 200:
                with open(map_path, "wb") as f:
                    f.write(r.content)
                print(f"Downloaded {map_name} to {map_path}")
            else:
                raise RuntimeError(f"Failed to download {map_name}: {r.status_code}")
        else:
            print(f"Skipping download of {map_name}.")
    return map_path

MAP_NAME = "1.map"
map_path = ensure_map(MAP_NAME)

# --- write YAML config ---
server_config = {
    "server": {"ip": HOST, "port": PORT},
    "gameplay": {"max_hp": 100, "damage": 20, "respawn_time": 5},
    "map": MAP_NAME
}
with open("server_config.yaml", "w") as f:
    yaml.dump(server_config, f)


def handle_client(conn, addr):
    print(f"Client {addr} connected")
    clients.append(conn)
    players[conn] = {"pos": [0, 0, 0], "color": [1, 1, 1, 1], "hp": 100, "alive": True}

    try:
        buf = ""
        while True:
            data = conn.recv(1024)
            if not data:
                break
            buf += data.decode()
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                if not line.strip():
                    continue
                msg = json.loads(line)
                if msg["type"] == "update":
                    players[conn]["pos"] = msg["pos"]
                elif msg["type"] == "shoot":
                    target_id = msg.get("target")
                    dmg = server_config["gameplay"]["damage"]
                    for c, pdata in players.items():
                        if id(c) == target_id and pdata["alive"]:
                            pdata["hp"] -= dmg
                            if pdata["hp"] <= 0:
                                pdata["hp"] = 0
                                pdata["alive"] = False
    finally:
        print(f"Client {addr} disconnected")
        if conn in clients:
            clients.remove(conn)
        if conn in players:
            players.pop(conn, None)
        conn.close()


def players_state():
    return {
        str(id(c)): {
            "pos": pdata["pos"],
            "color": pdata["color"],
            "hp": pdata["hp"],
            "alive": pdata["alive"]
        }
        for c, pdata in players.items()
    }


def broadcast_loop():
    while True:
        if clients:
            msg = {"type": "update", "players": players_state()}
            packet = (json.dumps(msg) + "\n").encode()
            for c in list(clients):
                try:
                    c.sendall(packet)
                except:
                    pass
        time.sleep(1)


def main():
    threading.Thread(target=broadcast_loop, daemon=True).start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"Server running on {HOST}:{PORT} with map {MAP_NAME}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
