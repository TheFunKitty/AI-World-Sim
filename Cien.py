# client_keyboard_rotate.py
# Panda3D client: keyboard-based rotation (arrow keys) + optional mouse-look (toggle M).
# Usage: python client_keyboard_rotate.py
# Requirements: pip install panda3d

import socket, threading, json, time, sys, os, math
from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    CardMaker, Vec3, WindowProperties, TextNode,
    AmbientLight, DirectionalLight, TransparencyAttrib
)

# ===== CONFIG =====
SERVER_HOST_DEFAULT = "127.0.0.1"
SERVER_PORT_DEFAULT = 6000
SEND_INTERVAL = 1.0
MAP_FILE = "1.map"
ROT_SPEED = 90.0     # degrees per second for arrow key rotation
# ===================

net_lock = threading.Lock()
server_players = {}
connected = False

def parse_color_input(s):
    s = s.strip()
    if s.startswith("#") and len(s) in (7,9):
        try:
            r = int(s[1:3],16)/255.0; g = int(s[3:5],16)/255.0; b = int(s[5:7],16)/255.0
            return (r,g,b,1.0), s
        except: pass
    names = {"red":(1,0,0,1),"green":(0,1,0,1),"blue":(0,0,1,1),"white":(1,1,1,1)}
    if s.lower() in names: return names[s.lower()], s.lower()
    parts = s.split()
    try:
        nums = [float(x) for x in parts]
        if len(nums) >= 3:
            if max(nums) > 1.5:
                r,g,b = nums[0]/255.0, nums[1]/255.0, nums[2]/255.0
            else:
                r,g,b = nums[0], nums[1], nums[2]
            return (r,g,b,1.0), f"rgb({r:.2f},{g:.2f},{b:.2f})"
    except: pass
    return (1,0,0,1), "red"

def load_local_map():
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
        with open(MAP_FILE,"w") as f: f.write("\n".join(default))
    with open(MAP_FILE,"r") as f: return [l.rstrip("\n") for l in f.readlines()]

class NetThread(threading.Thread):
    def __init__(self, name, color_string, server_host, server_port):
        super().__init__(daemon=True)
        self.name = name; self.color_string = color_string
        self.server_host = server_host; self.server_port = server_port
        self.sock = None; self.running = True; self.last_send = 0.0
        self.to_send_snapshot = None

    def run(self):
        global connected, server_players
        try:
            self.sock = socket.create_connection((self.server_host, self.server_port), timeout=5.0)
            self.sock.settimeout(0.5)
            self.sock.sendall((self.name + "\n").encode())
            connected = True
            recv_buf = ""
            while self.running:
                try:
                    data = self.sock.recv(4096).decode()
                    if data == "": break
                    recv_buf += data
                    while "\n" in recv_buf:
                        line, recv_buf = recv_buf.split("\n",1)
                        if not line.strip(): continue
                        try: msg = json.loads(line)
                        except: continue
                        if msg.get("type") == "state":
                            payload = msg.get("payload", {})
                            with net_lock:
                                server_players = payload.get("players", {})
                except socket.timeout:
                    pass
                except Exception:
                    break

                now = time.time()
                if now - self.last_send >= SEND_INTERVAL:
                    self.last_send = now
                    s = self.to_send_snapshot
                    if s is None:
                        tosend = {"type":"pos","payload":{"x":0.0,"y":0.0,"z":1.5,"h":0.0,"p":0.0,"color":self.color_string,"hp":100}}
                    else:
                        s2 = dict(s); s2['color'] = self.color_string
                        tosend = {"type":"pos","payload": s2}
                    try:
                        self.sock.sendall((json.dumps(tosend) + "\n").encode())
                    except:
                        break
            try: self.sock.close()
            except: pass
        except Exception as e:
            print("Network thread failed:", e)
        finally:
            connected = False; self.running = False
            with net_lock: server_players = {}

class PandaClient(ShowBase):
    def __init__(self, player_name, color_rgba, color_str, server_host, server_port):
        super().__init__()
        self.player_name = player_name
        self.color_rgba = color_rgba
        self.color_str = color_str
        self.local_map = load_local_map()
        self.net = NetThread(player_name, color_str, server_host, server_port)
        self.net.start()

        # Window - DO NOT hide or lock mouse by default
        self.disableMouse()
        props = WindowProperties(); props.setCursorHidden(False); self.win.requestProperties(props)
        wp = self.win.getProperties()
        self.win_center_x = max(1, wp.getXSize()//2); self.win_center_y = max(1, wp.getYSize()//2)

        # Default: keyboard rotation (mouse_look False). Toggle with 'm'
        self.mouse_look = False
        self.accept("m", self.toggle_mouse_look)

        # lighting
        al = AmbientLight("al"); al.setColor((0.6,0.6,0.6,1)); self.render.setLight(self.render.attachNewNode(al))
        dl = DirectionalLight("dl"); dl.setColor((0.8,0.8,0.7,1)); dn = self.render.attachNewNode(dl); dn.setHpr(45,-45,0); self.render.setLight(dn)

        # camera
        self.camera.setPos(2, -4, 1.5); self.camera.setHpr(0,0,0)
        self.cam_speed = 3.5; self.mouse_sensitivity = 0.12

        # movement keys
        self.key_map = {"w":False,"s":False,"a":False,"d":False}
        self.accept("w", self.set_key, ["w", True]); self.accept("w-up", self.set_key, ["w", False])
        self.accept("s", self.set_key, ["s", True]); self.accept("s-up", self.set_key, ["s", False])
        self.accept("a", self.set_key, ["a", True]); self.accept("a-up", self.set_key, ["a", False])
        self.accept("d", self.set_key, ["d", True]); self.accept("d-up", self.set_key, ["d", False])

        # arrow rotation keys
        self.rot_map = {"left":False,"right":False,"up":False,"down":False}
        self.accept("arrow_left", self.set_rot, ["left", True]); self.accept("arrow_left-up", self.set_rot, ["left", False])
        self.accept("arrow_right", self.set_rot, ["right", True]); self.accept("arrow_right-up", self.set_rot, ["right", False])
        self.accept("arrow_up", self.set_rot, ["up", True]); self.accept("arrow_up-up", self.set_rot, ["up", False])
        self.accept("arrow_down", self.set_rot, ["down", True]); self.accept("arrow_down-up", self.set_rot, ["down", False])

        self.accept("escape", self.cleanup_and_exit)

        # HUD
        HUD_Y = 0.92
        self.hud_title = OnscreenText(text=f"Player: {self.player_name}", pos=(-1.25, HUD_Y), scale=0.05, fg=(1,1,1,1), align=TextNode.ALeft)
        self.hud_hp = OnscreenText(text="HP: 100", pos=(-1.25, HUD_Y-0.05), scale=0.05, fg=(1,1,1,1), align=TextNode.ALeft)
        self.hud_instr = OnscreenText(text="WASD: move   Arrows: rotate   M: toggle mouse-look   ESC: quit", pos=(-1.25, HUD_Y-0.10), scale=0.045, fg=(1,1,1,1), align=TextNode.ALeft)

        # map + remote players
        self.tile_nodes = []; self.tile_size = 1.0; self.render_map_tiles()
        self.remote_nodes = {}

        self.taskMgr.add(self.update, "update")

    def toggle_mouse_look(self):
        self.mouse_look = not self.mouse_look
        props = WindowProperties()
        props.setCursorHidden(self.mouse_look)
        self.win.requestProperties(props)
        # if enabling mouse look, center pointer
        if self.mouse_look:
            self.win.movePointer(0, self.win_center_x, self.win_center_y)
        print("Mouse-look:", self.mouse_look)

    def set_key(self, k, v): self.key_map[k] = v
    def set_rot(self, k, v): self.rot_map[k] = v

    def cleanup_and_exit(self):
        props = WindowProperties(); props.setCursorHidden(False); self.win.requestProperties(props)
        if self.net: self.net.running = False
        sys.exit(0)

    def render_map_tiles(self):
        rows = len(self.local_map); cols = max(len(r) for r in self.local_map) if rows>0 else 0
        origin_x = -(cols/2) * self.tile_size; origin_y = -(rows/2) * self.tile_size
        for y, row in enumerate(self.local_map):
            for x, ch in enumerate(row):
                cm = CardMaker(f"tile_{x}_{y}"); cm.setFrame(0, self.tile_size, 0, self.tile_size)
                node = self.render.attachNewNode(cm.generate())
                px = origin_x + x * self.tile_size; py = origin_y + y * self.tile_size
                node.setPos(px, py, 0); node.setP(-90)
                if ch == "#": node.setColor(0.2,0.2,0.2,1)
                elif ch == "~": node.setColor(0.2,0.4,0.8,1)
                else: node.setColor(0.6,0.8,0.6,1)
                node.setTransparency(TransparencyAttrib.MAlpha); self.tile_nodes.append(node)

    def make_remote_node(self, name, color=(1,0,0,1)):
        cm = CardMaker(f"box_{name}"); size = 0.6
        node = self.render.attachNewNode(name + "_node"); faces = []
        for i in range(6):
            face = node.attachNewNode(cm.generate()); face.setScale(size, size, 1); faces.append(face)
        faces[0].setPos(0,0,0); faces[0].setP(0)
        faces[1].setPos(0,0,0); faces[1].setP(0); faces[1].setH(180)
        faces[2].setPos(-size/2,0,0); faces[2].setH(-90)
        faces[3].setPos(size/2,0,0); faces[3].setH(90)
        faces[4].setPos(0,0,size/2); faces[4].setP(-90)
        faces[5].setPos(0,0,-size/2); faces[5].setP(90)
        for f in faces: f.setColor(color)
        return node

    def update(self, task):
        dt = globalClock.getDt()

        # Rotation: arrow keys
        yaw = 0.0; pitch = 0.0
        if self.rot_map["left"]: yaw += ROT_SPEED * dt
        if self.rot_map["right"]: yaw -= ROT_SPEED * dt
        if self.rot_map["up"]: pitch += ROT_SPEED * dt
        if self.rot_map["down"]: pitch -= ROT_SPEED * dt
        # apply rotation (clamp pitch)
        new_h = self.camera.getH() + yaw
        new_p = max(-89, min(89, self.camera.getP() + pitch))
        self.camera.setHpr(new_h, new_p, 0)

        # If mouse-look is on, process mouse deltas instead
        if self.mouse_look:
            pointer = self.win.getPointer(0)
            dx = pointer.getX() - self.win_center_x
            dy = pointer.getY() - self.win_center_y
            h = self.camera.getH() - dx * self.mouse_sensitivity
            p = self.camera.getP() - dy * self.mouse_sensitivity
            p = max(-89, min(89, p))
            self.camera.setHpr(h, p, 0)
            self.win.movePointer(0, self.win_center_x, self.win_center_y)

        # Movement WASD (camera-relative)
        dir = Vec3(0,0,0)
        if self.key_map["w"]: dir.y += 1
        if self.key_map["s"]: dir.y -= 1
        if self.key_map["a"]: dir.x -= 1
        if self.key_map["d"]: dir.x += 1
        if dir.length() > 0: dir.normalize()
        forward = self.render.getRelativeVector(self.camera, Vec3(0,1,0)); right = self.render.getRelativeVector(self.camera, Vec3(1,0,0))
        forward.setZ(0); right.setZ(0)
        if forward.length() > 0: forward.normalize()
        if right.length() > 0: right.normalize()
        move_vec = forward * dir.y + right * dir.x
        self.camera.setPos(self.camera.getPos() + move_vec * (self.cam_speed * dt))

        # HUD and network snapshot
        with net_lock:
            sp = dict(server_players)
        if self.player_name in sp:
            self.hud_hp.setText(f"HP: {sp[self.player_name].get('hp',100)}")
        if self.net and self.net.running:
            px,py,pz = self.camera.getPos()
            self.net.to_send_snapshot = {"x": px, "y": py, "z": pz, "h": self.camera.getH(), "p": self.camera.getP(), "hp": int(sp.get(self.player_name, {}).get("hp",100))}

        # update remote players
        for name, st in sp.items():
            if name == self.player_name: continue
            node = self.remote_nodes.get(name)
            color_hex = st.get("color", "#ff0000")
            try:
                if color_hex.startswith("#") and len(color_hex) >= 7:
                    r = int(color_hex[1:3],16)/255.0; g = int(color_hex[3:5],16)/255.0; b = int(color_hex[5:7],16)/255.0
                    rgba = (r,g,b,1.0)
                else:
                    rgba = (1,0,0,1)
            except:
                rgba = (1,0,0,1)
            if node is None:
                node = self.make_remote_node(name, color=rgba); self.remote_nodes[name] = node
            node.setPos(st.get("x",0.0), st.get("y",0.0), st.get("z",1.0))
            node.setH(st.get("h", 0.0))

        return task.cont

# ===== main =====
if __name__ == "__main__":
    print("=== Panda3D LAN Client (keyboard rotate) ===")
    server_ip = input(f"Server IP (default {SERVER_HOST_DEFAULT}): ").strip() or SERVER_HOST_DEFAULT
    try:
        server_port = int(input(f"Server port (default {SERVER_PORT_DEFAULT}): ").strip() or SERVER_PORT_DEFAULT)
    except:
        server_port = SERVER_PORT_DEFAULT
    name = input("Player name: ").strip()
    if not name:
        print("Name required."); sys.exit(1)
    color_in = input("Choose body color (name, #RRGGBB, or 'r g b'): ").strip() or "red"
    color_rgba, color_str = parse_color_input(color_in)

    app = PandaClient(name, color_rgba, color_str, server_ip, server_port)
    app.run()
