import socket, threading, json, os, requests
from direct.showbase.ShowBase import ShowBase
from panda3d.core import CardMaker, Vec3

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

# --- client config ---
client_config = {
    "server": {"ip": "127.0.0.1", "port": 6000},
    "client": {"username": "Player1", "color": [0, 0, 1, 1], "map": "1.map"}
}
with open("client_config.json", "w") as f:
    json.dump(client_config, f, indent=2)

server_ip = client_config["server"]["ip"]
server_port = client_config["server"]["port"]

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((server_ip, server_port))


class MyGame(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        self.disableMouse()

        # Player cube
        cm = CardMaker("player")
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)
        self.player = render.attachNewNode(cm.generate())
        self.player.setColor(*client_config["client"]["color"])
        self.player.setScale(1, 1, 2)
        self.player.setPos(0, 0, 1)

        # Gun
        gun_cm = CardMaker("gun")
        gun_cm.setFrame(-0.2, 0.2, -0.2, 0.2)
        gun = self.player.attachNewNode(gun_cm.generate())
        gun.setColor(0.2, 0.2, 0.2, 1)
        gun.setScale(0.3, 0.5, 0.3)
        gun.setPos(0.6, 0, 0.5)

        # Map
        map_file = ensure_map(client_config["client"]["map"])
        self.load_map(map_file)

        self.other_players = {}

        self.accept("arrow_up", self.move, [Vec3(0, 1, 0)])
        self.accept("arrow_down", self.move, [Vec3(0, -1, 0)])
        self.accept("arrow_left", self.move, [Vec3(-1, 0, 0)])
        self.accept("arrow_right", self.move, [Vec3(1, 0, 0)])

        self.taskMgr.doMethodLater(1, self.update_network, "update_network")
        threading.Thread(target=self.listen_server, daemon=True).start()

    def load_map(self, map_file):
        with open(map_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                obj, x, y, z, sx, sy, sz = line.split()
                cm = CardMaker(obj)
                cm.setFrame(-0.5, 0.5, -0.5, 0.5)
                cube = render.attachNewNode(cm.generate())
                cube.setScale(float(sx), float(sy), float(sz))
                cube.setPos(float(x), float(y), float(z))

    def move(self, vec):
        self.player.setPos(self.player.getPos() + vec)

    def update_network(self, task):
        pos = self.player.getPos()
        msg = {"type": "update", "pos": [pos.x, pos.y, pos.z]}
        client_socket.sendall((json.dumps(msg) + "\n").encode())
        return task.again

    def listen_server(self):
        buf = ""
        while True:
            try:
                data = client_socket.recv(1024)
                if not data:
                    break
                buf += data.decode()
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    if not line.strip():
                        continue
                    msg = json.loads(line)
                    if msg["type"] == "update":
                        for pid, pdata in msg["players"].items():
                            if pid == str(id(client_socket)):
                                continue
                            if pid not in self.other_players:
                                cm = CardMaker("npc")
                                cm.setFrame(-0.5, 0.5, -0.5, 0.5)
                                other = render.attachNewNode(cm.generate())
                                other.setColor(*pdata["color"])
                                other.setScale(1, 1, 2)
                                self.other_players[pid] = other
                            self.other_players[pid].setPos(*pdata["pos"])
            except:
                break


if __name__ == "__main__":
    game = MyGame()
    game.run()
