import gi, os, json, hashlib, threading, socket, time, subprocess, shutil, tarfile, zipfile
from pathlib import Path

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango

USER_FILE = "users.json"
UDP_PORT = 50000
UDP_TIMEOUT = 2.0

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def load_json(file):
    if Path(file).exists():
        try:
            return json.loads(Path(file).read_text())
        except Exception:
            return {}
    return {}

def save_json(file, data):
    Path(file).write_text(json.dumps(data, indent=2))

def start_udp_listener(on_message):
    def listener():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", UDP_PORT))
        except Exception:
            return
        sock.settimeout(1.0)
        while True:
            try:
                data, addr = sock.recvfrom(65536)
            except socket.timeout:
                continue
            except Exception:
                break
            try:
                msg = json.loads(data.decode('utf-8', errors='ignore'))
                on_message(msg, addr)
            except Exception:
                continue
    t = threading.Thread(target=listener, daemon=True)
    t.start()
    return t

def udp_broadcast(msg: dict):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.sendto(json.dumps(msg).encode('utf-8'), ('<broadcast>', UDP_PORT))
    finally:
        sock.close()

class BlueShell(Gtk.Window):
    THEMES = {
        "RED": (1, 0, 0),
        "GREEN": (0, 1, 0),
        "BLUE": (0, 0, 1),
        "PINK": (1, 0.41, 0.71),
        "PURPLE": (0.5, 0, 0.5),
        "CYAN": (0, 1, 1),
        "BLACK": (0, 0, 0),
        "DARKGREEN": (0, 0.39, 0)
    }

    def __init__(self):
        super().__init__(title="BlueShell Terminal")
        self.set_default_size(900, 600)
        self.users = load_json(USER_FILE)
        self.logged_user = None
        self.hostname = socket.gethostname()
        self.bg_color = (0, 0, 0.5)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(box)

        scrolled = Gtk.ScrolledWindow()
        self.textview = Gtk.TextView()
        self.textview.set_editable(False)
        self.textview.set_cursor_visible(False)
        font = Pango.FontDescription("Fira Code 11")
        self.textview.modify_font(font)
        self.buffer = self.textview.get_buffer()
        scrolled.add(self.textview)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Type a command...")
        self.entry.connect("activate", self.on_enter)

        box.pack_start(scrolled, True, True, 0)
        box.pack_start(self.entry, False, False, 0)

        self.connect("destroy", Gtk.main_quit)
        self.show_all()

        start_udp_listener(self.on_udp_message)

        self.append_text("[LOGIN]===\n")
        self.append_text('Use super signup/login commands before login.\n')

        self.update_bg_color()

    def update_bg_color(self):
        r, g, b = self.bg_color
        css = f"""
        textview, entry {{
            background-color: rgba({int(r*255)}, {int(g*255)}, {int(b*255)}, 1);
            color: white;
        }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def append_text(self, text):
        end_iter = self.buffer.get_end_iter()
        self.buffer.insert(end_iter, text)
        mark = self.buffer.create_mark(None, end_iter, False)
        self.textview.scroll_mark_onscreen(mark)

    def on_enter(self, entry):
        command = entry.get_text().strip()
        entry.set_text("")
        if not command:
            return
        self.append_text(f"> {command}\n")
        cmd_lower = command.lower()
        if cmd_lower == "super -help":
            self.append_text("Super commands:\n  super signup [user] [pass]\n  super login [user] [pass]\n  super LAN-create [network name] [password]\n  super LAN-join [network name] [password]\n  super LAN-leave [network name]\n  super LAN -local -list\n  super LAN [network name] -rm\n")
            return
        if cmd_lower == "-help":
            self.append_text("All commands:\n  nano [file]\n  config theme -list (show all themes)\n  config theme -color -set [Red,Green,Blue,Pink,Purple,Cyan,Black,DARKGREEN] (set background)\n  config theme -custom RGB -set [0,0,0] (set custom RGB)\n  config theme -custom HEX -set [#HEXVALUE] (set custom HEX)\n  super signup [user] [pass]\n  super login [user] [pass]\n  super LAN-create [network name] [password]\n  super LAN-join [network name] [password]\n  super LAN-leave [network name]\n  super LAN -local -list\n  super LAN [network name] -rm\n")
            return
        if not self.logged_user:
            if command.startswith("super signup") or command.startswith("super login"):
                self.handle_super(command)
            else:
                self.append_text("You must login or signup first using 'super signup' or 'super login'.\n")
        else:
            self.handle_user_command(command)

    def handle_super(self, cmd):
        parts = cmd.split()
        if len(parts) < 3:
            self.append_text("Usage: super signup/login [username] [password]\n")
            return
        action = parts[1]
        username = parts[2]
        password = parts[3] if len(parts) > 3 else ""
        if action == "signup":
            if username in self.users:
                self.append_text("Account already exists.\n")
            else:
                self.users[username] = {"password_hash": sha256(password)}
                save_json(USER_FILE, self.users)
                self.append_text(f"Account created for {username}.\n")
        elif action == "login":
            user = self.users.get(username)
            if user and user.get("password_hash") == sha256(password):
                self.logged_user = username
                self.append_text(f"Logged in as {username}.\n")
            else:
                self.append_text("Invalid username or password.\n")
        else:
            self.append_text("Only signup/login are allowed before login.\n")

    def handle_user_command(self, cmd):
        cmd_lower = cmd.lower()
        if cmd_lower.startswith("nano "):
            filename = cmd.split(maxsplit=1)[1]
            self.open_nano(filename)
        elif cmd_lower.startswith("config theme -list"):
            self.append_text("Available themes: RED, GREEN, BLUE, PINK, PURPLE, CYAN, BLACK, DARKGREEN\n")
        elif cmd_lower.startswith("config theme -color -set "):
            color_name = cmd.split()[-1].upper()
            if color_name in self.THEMES:
                self.bg_color = self.THEMES[color_name]
                self.update_bg_color()
                self.append_text(f"Theme set to {color_name}\n")
            else:
                self.append_text("Unknown color. Use config theme -list to see options.\n")
        else:
            self.append_text(f"[User command executed]: {cmd}\n")

    def open_nano(self, filename):
        dialog = Gtk.Dialog(title=f"Editing {filename}", parent=self, flags=0)
        dialog.set_default_size(600,400)
        box = dialog.get_content_area()
        textview = Gtk.TextView()
        textbuffer = textview.get_buffer()
        if Path(filename).exists():
            textbuffer.set_text(Path(filename).read_text())
        box.add(textview)
        dialog.add_button("Save", Gtk.ResponseType.OK)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            start, end = textbuffer.get_bounds()
            content = textbuffer.get_text(start, end, True)
            Path(filename).write_text(content)
            self.append_text(f"Saved {filename}\n")
        dialog.destroy()

    def on_udp_message(self, msg, addr):
        self.append_text(f"[LAN message from {addr[0]}]: {msg}\n")

if __name__ == "__main__":
    BlueShell()
    Gtk.main()

## if bugs, contact me via email. eeegodissa@gmail.com
