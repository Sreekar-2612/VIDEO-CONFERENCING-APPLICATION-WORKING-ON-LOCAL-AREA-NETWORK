#!/usr/bin/env python3
"""
Client (UDP video/audio + TCP general) updated for multi-user dynamic grid tiles.
Clients send pickled payloads {'username':..., 'frame': b'...'} fragmented over UDP.
"""

import socket, threading, pickle, struct, time, logging, os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import cv2, numpy as np, pyaudio
from PIL import Image, ImageTk
import pyautogui

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SERVER_IP = "10.176.196.154"
VIDEO_UDP_PORT = 60000
AUDIO_UDP_PORT = 60001
GENERAL_TCP_PORT = 50002

VIDEO_HDR_FMT = ">IHH"
VIDEO_HDR_SIZE = struct.calcsize(VIDEO_HDR_FMT)
MAX_UDP_PAYLOAD = 60000
AUDIO_UDP_MAX = 4096

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

STALE_TIMEOUT = 6.0   # remove participants idle > this

def send_pickle_prefixed(sock, obj):
    data = pickle.dumps(obj)
    sock.sendall(struct.pack(">L", len(data)) + data)

def recv_exact(sock, n):
    data = b''
    while len(data) < n:
        p = sock.recv(n - len(data))
        if not p:
            return None
        data += p
    return data

def recv_pickle_prefixed(sock):
    header = recv_exact(sock, 4)
    if not header:
        return None
    ln = struct.unpack(">L", header)[0]
    payload = recv_exact(sock, ln)
    if not payload:
        return None
    return pickle.loads(payload)

class VideoConferenceClient:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Multi-user Video (UDP)")
        self.root.geometry("1200x820")

        self.username = "User"
        self.meet_id = "default"
        self.server_ip = SERVER_IP

        self.general_sock = None

        self.video_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.video_udp.bind(('', 0))
        self.local_video_port = self.video_udp.getsockname()[1]

        self.audio_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.audio_udp.bind(('', 0))
        self.local_audio_port = self.audio_udp.getsockname()[1]

        self.pyaudio_inst = pyaudio.PyAudio()

        self.video_running = False
        self.screen_sharing = False
        self.audio_running = False
        self.running = True

        # incoming reassembly key: frame_id -> {'parts':{}, 'total':int, 'ts':float}
        self.recv_reassembly = {}
        self.recv_reassembly_lock = threading.Lock()
        self.REASSEMBLY_TTL = 2.0

        # GUI tiles
        self.video_canvases = {}  # username -> canvas
        self.last_active = {}     # username -> timestamp of last frame
        self.grid_frame = None
        self.participants = set()

        # File queue for manual download
        self.file_queue = []  # list of (header_msg, data_bytes)

        self.setup_gui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_gui(self):
        # Apply modern theme
        style = ttk.Style()
        style.theme_use('clam')

        # Define themes
        self.themes = {
            'Light Blue': {
                'TFrame': {'background': 'lightblue'},
                'TLabelFrame': {'background': 'lightblue', 'foreground': 'black'},
                'TLabel': {'background': 'lightblue', 'foreground': 'black'},
                'TButton': {'background': 'lightblue', 'foreground': 'black'},
                'TEntry': {'fieldbackground': 'white', 'foreground': 'black'},
                'Text': {'bg': 'white', 'fg': 'black'}
            },
            'Dark Mode': {
                'TFrame': {'background': '#2b2b2b'},
                'TLabelFrame': {'background': '#2b2b2b', 'foreground': 'white'},
                'TLabel': {'background': '#2b2b2b', 'foreground': 'white'},
                'TButton': {'background': '#4a4a4a', 'foreground': 'white'},
                'TEntry': {'fieldbackground': '#4a4a4a', 'foreground': 'white'},
                'Text': {'bg': '#4a4a4a', 'fg': 'white'}
            },
            'Classic': {
                'TFrame': {'background': 'gray'},
                'TLabelFrame': {'background': 'gray', 'foreground': 'black'},
                'TLabel': {'background': 'gray', 'foreground': 'black'},
                'TButton': {'background': 'gray', 'foreground': 'black'},
                'TEntry': {'fieldbackground': 'white', 'foreground': 'black'},
                'Text': {'bg': 'white', 'fg': 'black'}
            },
            'Green': {
                'TFrame': {'background': 'lightgreen'},
                'TLabelFrame': {'background': 'lightgreen', 'foreground': 'black'},
                'TLabel': {'background': 'lightgreen', 'foreground': 'black'},
                'TButton': {'background': 'lightgreen', 'foreground': 'black'},
                'TEntry': {'fieldbackground': 'white', 'foreground': 'black'},
                'Text': {'bg': 'white', 'fg': 'black'}
            },
            'Purple': {
                'TFrame': {'background': 'lavender'},
                'TLabelFrame': {'background': 'lavender', 'foreground': 'black'},
                'TLabel': {'background': 'lavender', 'foreground': 'black'},
                'TButton': {'background': 'lavender', 'foreground': 'black'},
                'TEntry': {'fieldbackground': 'white', 'foreground': 'black'},
                'Text': {'bg': 'white', 'fg': 'black'}
            }
        }

        # Default theme
        self.current_theme = 'Light Blue'
        self.apply_theme(self.current_theme)

        # Increase window size for better layout
        self.root.geometry("1400x900")

        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top section: Connection and Theme
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 20))

        # Theme selection
        theme_frame = ttk.LabelFrame(top_frame, text="Theme", padding="10")
        theme_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 20))

        ttk.Label(theme_frame, text="Select Theme:").pack(anchor=tk.W)
        self.theme_var = tk.StringVar(value=self.current_theme)
        self.theme_combo = ttk.Combobox(theme_frame, textvariable=self.theme_var, values=list(self.themes.keys()), state="readonly")
        self.theme_combo.pack(fill=tk.X, pady=(5,0))
        self.theme_combo.bind("<<ComboboxSelected>>", self.change_theme)

        # Connection
        conn_frame = ttk.LabelFrame(top_frame, text="Connection", padding="10")
        conn_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Username, Meeting ID, and Server IP in rows
        entry_frame = ttk.Frame(conn_frame)
        entry_frame.pack(fill=tk.X)

        ttk.Label(entry_frame, text="Username:", font=("Arial", 10)).grid(row=0, column=0, sticky=tk.W, padx=(0,10))
        self.username_entry = ttk.Entry(entry_frame, font=("Arial", 10))
        self.username_entry.insert(0, "User")
        self.username_entry.grid(row=0, column=1, sticky=tk.EW, padx=(0,20))

        ttk.Label(entry_frame, text="Meeting ID:", font=("Arial", 10)).grid(row=0, column=2, sticky=tk.W, padx=(0,10))
        self.meetid_entry = ttk.Entry(entry_frame, font=("Arial", 10))
        self.meetid_entry.insert(0, "Room1")
        self.meetid_entry.grid(row=0, column=3, sticky=tk.EW)

        ttk.Label(entry_frame, text="Server IP:", font=("Arial", 10)).grid(row=1, column=0, sticky=tk.W, padx=(0,10), pady=(10,0))
        self.server_entry = ttk.Entry(entry_frame, font=("Arial", 10))
        self.server_entry.insert(0, SERVER_IP)
        self.server_entry.grid(row=1, column=1, sticky=tk.EW, padx=(0,20), pady=(10,0))

        entry_frame.columnconfigure(1, weight=1)
        entry_frame.columnconfigure(3, weight=1)

        # Connect button centered below
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.connect, padding="10")
        self.connect_btn.pack(pady=(10,0))

        # Middle section: Video Grid (larger)
        self.video_label_frame = ttk.LabelFrame(main_frame, text="Video Conference (0 participants)", padding="10")
        self.video_label_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        self.grid_frame = ttk.Frame(self.video_label_frame)
        self.grid_frame.pack(fill=tk.BOTH, expand=True)

        # Bottom section: Controls, Participants, and Chat
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X)

        # Controls
        ctrl_frame = ttk.LabelFrame(bottom_frame, text="Controls", padding="10")
        ctrl_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        # Buttons with larger size and padding
        self.cam_btn = ttk.Button(ctrl_frame, text="Start Camera", command=self.toggle_camera, padding="15 10")
        self.cam_btn.pack(fill=tk.X, pady=5)

        self.screen_btn = ttk.Button(ctrl_frame, text="Share Screen", command=self.toggle_screen, padding="15 10")
        self.screen_btn.pack(fill=tk.X, pady=5)

        self.audio_btn = ttk.Button(ctrl_frame, text="Start Audio", command=self.toggle_audio, padding="15 10")
        self.audio_btn.pack(fill=tk.X, pady=5)

        self.file_btn = ttk.Button(ctrl_frame, text="Send File", command=self.send_file, padding="15 10")
        self.file_btn.pack(fill=tk.X, pady=5)

        self.leave_btn = ttk.Button(ctrl_frame, text="Leave Call", command=self.leave_call, padding="15 10")
        self.leave_btn.pack(fill=tk.X, pady=5)

        # Participants
        participants_frame = ttk.LabelFrame(bottom_frame, text="Participants", padding="10")
        participants_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        self.participants_listbox = tk.Listbox(participants_frame, height=10, font=("Arial", 10))
        self.participants_listbox.pack(fill=tk.BOTH, expand=True)

        # Files
        files_frame = ttk.LabelFrame(bottom_frame, text="Files", padding="10")
        files_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        self.files_listbox = tk.Listbox(files_frame, height=10, font=("Arial", 10))
        self.files_listbox.pack(fill=tk.BOTH, expand=True)

        self.download_btn = ttk.Button(files_frame, text="Download Selected", command=self.download_selected_file, padding="10")
        self.download_btn.pack(fill=tk.X, pady=(5, 0))

        # Chat
        chat_frame = ttk.LabelFrame(bottom_frame, text="Chat", padding="10")
        chat_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.chat_text = tk.Text(chat_frame, height=12, wrap=tk.WORD, font=("Arial", 10), bg='white', fg='black')
        self.chat_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill=tk.X)

        self.msg_entry = ttk.Entry(input_frame, font=("Arial", 10))
        self.msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.msg_entry.bind('<Return>', lambda e: self.send_chat())

        self.send_btn = ttk.Button(input_frame, text="Send", command=self.send_chat, padding="10")
        self.send_btn.pack(side=tk.RIGHT, padx=(10, 0))

    # Connect and register UDP ports
    def connect(self):
        un = self.username_entry.get().strip(); mid = self.meetid_entry.get().strip(); sip = self.server_entry.get().strip()
        if not un or not mid or not sip: messagebox.showerror("Error", "Username, Meeting ID & Server IP required"); return
        self.username, self.meet_id, self.server_ip = un, mid, sip
        try:
            self.general_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.general_sock.connect((self.server_ip, GENERAL_TCP_PORT))
            handshake = {'username': self.username, 'meet_id': self.meet_id,
                         'video_udp_port': self.local_video_port, 'audio_udp_port': self.local_audio_port}
            send_pickle_prefixed(self.general_sock, handshake)
            threading.Thread(target=self.tcp_general_receiver, daemon=True).start()
            threading.Thread(target=self.udp_video_receiver, daemon=True).start()
            threading.Thread(target=self.udp_audio_receiver, daemon=True).start()
            threading.Thread(target=self.cleanup_stale_task, daemon=True).start()
            self.connect_btn.config(text="Connected", state="disabled")
            self.chat_text.insert(tk.END, f"Connected to {self.meet_id} at {self.server_ip}\n"); self.chat_text.see(tk.END)
            logging.info("Connected and registered UDP ports")
        except Exception:
            logging.exception("connect failed"); messagebox.showerror("Error", "Connect failed")

    # TCP general receive
    def tcp_general_receiver(self):
        while True:
            try:
                msg = recv_pickle_prefixed(self.general_sock)
                if msg is None:
                    break
                if isinstance(msg, dict) and msg.get('msg_type') == 'chat':
                    self.chat_text.insert(tk.END, f"{msg['username']}: {msg['message']}\n"); self.chat_text.see(tk.END)
                elif isinstance(msg, dict) and msg.get('msg_type') == 'file':
                    self.receive_file_to_queue(msg)
            except Exception:
                logging.exception("tcp_general_receiver ended"); break
        logging.info("tcp_general_receiver exiting")

    # camera
    def toggle_camera(self):
        if not getattr(self, 'general_sock', None): messagebox.showwarning("Warning", "Connect first"); return
        if self.screen_sharing:
            messagebox.showinfo("Info", "Stop screen sharing first"); return
        if not self.video_running:
            self.video_running = True
            self.cam_btn.config(text="📸 Stop Camera")
            threading.Thread(target=self.send_camera_loop, daemon=True).start()
        else:
            self.video_running = False; self.cam_btn.config(text="Start Camera")

    def send_camera_loop(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("Error", "Cannot open webcam"); self.video_running=False; self.cam_btn.config(text="Start Camera"); return
        fid = 0
        try:
            while self.video_running:
                ret, frame = cap.read()
                if not ret: continue
                frame = cv2.resize(frame, (640,480))
                # convert to RGB for local display
                display_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # local preview displayed in own tile
                self.enqueue_local_frame(self.username, display_frame)
                # pack payload
                payload = {'username': self.username, 'frame': cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY),70])[1].tobytes()}
                data = pickle.dumps(payload)
                # fragment and send
                max_payload = MAX_UDP_PAYLOAD; total = (len(data)+max_payload-1)//max_payload
                fid = (fid+1) & 0xFFFFFFFF
                for idx in range(total):
                    start = idx*max_payload; part = data[start:start+max_payload]
                    hdr = struct.pack(VIDEO_HDR_FMT, fid, total, idx)
                    try:
                        self.video_udp.sendto(hdr+part, (self.server_ip, VIDEO_UDP_PORT))
                    except:
                        pass
                time.sleep(0.04)
        finally:
            try: cap.release()
            except: pass
            self.video_running=False; self.cam_btn.config(text="Start Camera")

    # screen share (same channel but not sending separate flag)
    def toggle_screen(self):
        if not getattr(self, 'general_sock', None): messagebox.showwarning("Warning", "Connect first"); return
        if self.video_running: self.video_running=False; self.cam_btn.config(text="Start Camera")
        if not self.screen_sharing:
            self.screen_sharing=True; self.screen_btn.config(text="Stop Sharing"); threading.Thread(target=self.send_screen_loop, daemon=True).start()
        else:
            self.screen_sharing=False; self.screen_btn.config(text="Share Screen")

    def send_screen_loop(self):
        fid = int(time.time()*1000) & 0xFFFFFFFF
        try:
            while self.screen_sharing:
                shot = pyautogui.screenshot(); frame = cv2.cvtColor(np.array(shot), cv2.COLOR_BGR2RGB)
                frame = cv2.resize(frame, (960,540))
                self.enqueue_local_frame(self.username, frame)
                payload = {'username': self.username, 'frame': cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY),60])[1].tobytes()}
                data = pickle.dumps(payload)
                max_payload=MAX_UDP_PAYLOAD; total=(len(data)+max_payload-1)//max_payload
                fid=(fid+1)&0xFFFFFFFF
                for idx in range(total):
                    start=idx*max_payload; part=data[start:start+max_payload]
                    hdr=struct.pack(VIDEO_HDR_FMT, fid, total, idx)
                    try:
                        self.video_udp.sendto(hdr+part, (self.server_ip, VIDEO_UDP_PORT))
                    except:
                        pass
                time.sleep(0.12)
        finally:
            self.screen_sharing=False; self.screen_btn.config(text="Share Screen")

    # udp video receiver: reassemble a pickled payload, then display under username
    def udp_video_receiver(self):
        while True:
            try:
                pkt, src = self.video_udp.recvfrom(MAX_UDP_PAYLOAD + VIDEO_HDR_SIZE + 64)
                if not pkt or len(pkt) < VIDEO_HDR_SIZE: continue
                hdr = pkt[:VIDEO_HDR_SIZE]; payload = pkt[VIDEO_HDR_SIZE:]
                frame_id, total_parts, part_idx = struct.unpack(VIDEO_HDR_FMT, hdr)
                key = (src, frame_id)
                with self.recv_reassembly_lock:
                    entry = self.recv_reassembly.get(key)
                    if not entry:
                        entry = {'parts':{}, 'total':total_parts, 'ts':time.time()}
                        self.recv_reassembly[key] = entry
                    entry['parts'][part_idx] = payload
                    entry['ts'] = time.time()
                    if len(entry['parts']) == entry['total']:
                        parts=[entry['parts'][i] for i in range(entry['total'])]
                        data = b''.join(parts)
                        del self.recv_reassembly[key]
                        try:
                            payload_obj = pickle.loads(data)
                            uname = payload_obj.get('username')
                            frame_bytes = payload_obj.get('frame')
                            arr = np.frombuffer(frame_bytes, dtype=np.uint8)
                            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            if frame is not None:
                                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                self.enqueue_remote_frame(uname, frame)
                        except Exception:
                            logging.exception("udp_video_receiver - unpickle/decoding failed")
            except Exception:
                logging.exception("udp_video_receiver ended")
                break

    # helpers for tile management and display
    def enqueue_local_frame(self, username, frame):
        # treat own frame similar to incoming remote frames
        self.enqueue_remote_frame(username, frame)

    def enqueue_remote_frame(self, username, frame):
        # create canvas if missing
        if username not in self.video_canvases:
            self.create_canvas_for_user(username)
            self.participants.add(username)
            self.update_participants_list()
        # update last active
        self.last_active[username] = time.time()
        # convert and display
        photo = ImageTk.PhotoImage(Image.fromarray(cv2.resize(frame, (640,480))))
        # store last photo reference in canvas object to prevent GC
        canvas = self.video_canvases.get(username)
        if canvas:
            self.root.after(0, self.update_canvas_image, canvas, photo)

    def create_canvas_for_user(self, username):
        canvas = tk.Canvas(self.grid_frame, bg='black')
        label = ttk.Label(self.grid_frame, text=username)
        # store both label and canvas as a small frame for layout
        frame = ttk.Frame(self.grid_frame)
        label.pack = label.pack
        # we will pack label at top of canvas area
        # store container
        frame.columnconfigure(0, weight=1)
        canvas.pack_forget()
        with threading.Lock():
            self.video_canvases[username] = canvas
            self.last_active[username] = time.time()
        self.refresh_video_grid()

    def remove_canvas_for_user(self, username):
        canvas = self.video_canvases.pop(username, None)
        self.last_active.pop(username, None)
        self.participants.discard(username)
        self.update_participants_list()
        if canvas:
            try:
                canvas.destroy()
            except:
                pass
        self.refresh_video_grid()

    def update_canvas_image(self, canvas, photo):
        try:
            canvas.delete("all")
            canvas.create_image(0, 0, anchor=tk.NW, image=photo)
            canvas.image = photo
        except Exception:
            logging.exception("update_canvas_image")

    def refresh_video_grid(self):
        # Clear grid_frame
        for w in self.grid_frame.winfo_children():
            w.grid_forget()
        users = list(self.video_canvases.keys())
        n = len(users)
        self.video_label_frame.config(text=f"Video Conference ({n} participants)")
        if n == 0:
            return
        import math
        grid_size = int(math.ceil(math.sqrt(n)))
        idx = 0
        for r in range(grid_size):
            for c in range(grid_size):
                if idx >= n:
                    break
                uname = users[idx]
                canvas = self.video_canvases[uname]
                canvas.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
                # label on top-left corner (username)
                lbl = ttk.Label(self.grid_frame, text=uname, background='black', foreground='white')
                lbl.grid(row=r, column=c, sticky='nw', padx=6, pady=6)
                idx += 1
        for i in range(grid_size):
            self.grid_frame.rowconfigure(i, weight=1)
            self.grid_frame.columnconfigure(i, weight=1)

    def cleanup_stale_task(self):
        while True:
            now = time.time()
            to_remove = []
            for uname, ts in list(self.last_active.items()):
                if now - ts > STALE_TIMEOUT:
                    to_remove.append(uname)
            for u in to_remove:
                self.remove_canvas_for_user(u)
            time.sleep(1.0)

    def update_participants_list(self):
        self.participants_listbox.delete(0, tk.END)
        for participant in sorted(self.participants):
            self.participants_listbox.insert(tk.END, participant)

    # audio
    def toggle_audio(self):
        if not getattr(self, 'general_sock', None): messagebox.showwarning("Warning", "Connect first"); return
        if not self.audio_running:
            self.audio_running=True; self.audio_btn.config(text="Stop Audio"); threading.Thread(target=self.send_audio_loop, daemon=True).start()
        else:
            self.audio_running=False; self.audio_btn.config(text="Start Audio")

    def send_audio_loop(self):
        try:
            stream = self.pyaudio_inst.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        except Exception:
            logging.exception("send_audio_loop open failed"); self.audio_running=False; return
        try:
            while self.audio_running:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    self.audio_udp.sendto(data, (self.server_ip, AUDIO_UDP_PORT))
                except Exception:
                    pass
        finally:
            try: stream.stop_stream(); stream.close()
            except: pass
            self.audio_running=False; self.audio_btn.config(text="Start Audio")

    def udp_audio_receiver(self):
        try:
            stream = self.pyaudio_inst.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)
        except Exception:
            logging.exception("udp_audio_receiver open failed"); return
        while True:
            try:
                pkt, src = self.audio_udp.recvfrom(AUDIO_UDP_MAX + 64)
                if not pkt: continue
                try: stream.write(pkt, exception_on_underflow=False)
                except: pass
            except Exception:
                logging.exception("udp_audio_receiver ended"); break
        try: stream.stop_stream(); stream.close()
        except: pass

    # chat & file
    def send_chat(self):
        if not getattr(self, 'general_sock', None): messagebox.showwarning("Warning", "Connect first"); return
        msg = self.msg_entry.get().strip()
        if not msg: return
        payload = {'msg_type':'chat','username':self.username,'message':msg,'to':'send-all'}
        try:
            send_pickle_prefixed(self.general_sock, payload)
            self.chat_text.insert(tk.END, f"You: {msg}\n"); self.chat_text.see(tk.END); self.msg_entry.delete(0, tk.END)
        except Exception:
            logging.exception("send_chat failed")

    def send_file(self):
        if not getattr(self, 'general_sock', None): messagebox.showwarning("Warning", "Connect first"); return
        path = filedialog.askopenfilename()
        if not path: return
        size = os.path.getsize(path)
        hdr = {'msg_type':'file','username':self.username,'filename':os.path.basename(path),'size':size,'to':'send-all'}
        try:
            send_pickle_prefixed(self.general_sock, hdr)
            with open(path,'rb') as f:
                while True:
                    chunk = f.read(1024)
                    if not chunk: break
                    self.general_sock.sendall(chunk)
            self.chat_text.insert(tk.END, f"File sent: {path}\n"); self.chat_text.see(tk.END)
        except Exception:
            logging.exception("send_file failed")

    def receive_file(self, header_msg):
        filename = header_msg.get('filename'); size = header_msg.get('size',0)
        save = filedialog.asksaveasfilename(initialfile=filename)
        if not save:
            remaining=size
            while remaining>0:
                chunk=self.general_sock.recv(min(1024,remaining))
                if not chunk: break
                remaining-=len(chunk)
            return
        try:
            with open(save,'wb') as f:
                remaining=size
                while remaining>0:
                    chunk=self.general_sock.recv(min(1024,remaining))
                    if not chunk: break
                    f.write(chunk); remaining-=len(chunk)
            self.chat_text.insert(tk.END, f"File received: {filename}\n"); self.chat_text.see(tk.END)
        except Exception:
            logging.exception("receive_file failed")

    def receive_file_to_queue(self, header_msg):
        filename = header_msg.get('filename'); size = header_msg.get('size',0)
        data = b''
        remaining = size
        received = 0
        last_percent = 0
        while remaining > 0:
            chunk = self.general_sock.recv(min(1024, remaining))
            if not chunk: break
            data += chunk
            received += len(chunk)
            remaining -= len(chunk)
            percent = int((received / size) * 100) if size > 0 else 100
            if percent >= last_percent + 10 or percent == 100:
                self.chat_text.insert(tk.END, f"Downloading {filename}: {percent}%\n"); self.chat_text.see(tk.END)
                last_percent = percent
        self.file_queue.append((header_msg, data))
        self.files_listbox.insert(tk.END, filename)
        self.chat_text.insert(tk.END, f"File queued for download: {filename}\n"); self.chat_text.see(tk.END)

    def download_selected_file(self):
        selection = self.files_listbox.curselection()
        if not selection: return
        index = selection[0]
        header, data = self.file_queue[index]
        filename = header.get('filename')
        save = filedialog.asksaveasfilename(initialfile=filename)
        if save:
            try:
                with open(save, 'wb') as f:
                    f.write(data)
                self.chat_text.insert(tk.END, f"File downloaded: {filename}\n"); self.chat_text.see(tk.END)
            except Exception:
                logging.exception("download_selected_file failed")
        self.file_queue.pop(index)
        self.files_listbox.delete(index)

    def leave_call(self):
        if self.general_sock:
            try:
                self.general_sock.close()
            except: pass
        self.general_sock = None
        self.connect_btn.config(text="Connect", state="normal")
        self.chat_text.insert(tk.END, "Left the call.\n"); self.chat_text.see(tk.END)
        self.video_running = False
        self.screen_sharing = False
        self.audio_running = False
        self.cam_btn.config(text="Start Camera")
        self.screen_btn.config(text="Share Screen")
        self.audio_btn.config(text="Start Audio")
        for uname in list(self.video_canvases.keys()):
            self.remove_canvas_for_user(uname)
        self.participants.clear()
        self.update_participants_list()
        self.file_queue.clear()
        self.files_listbox.delete(0, tk.END)

    def change_theme(self, event=None):
        selected_theme = self.theme_var.get()
        if selected_theme != self.current_theme:
            self.current_theme = selected_theme
            self.apply_theme(selected_theme)

    def apply_theme(self, theme_name):
        theme = self.themes[theme_name]
        style = ttk.Style()
        for widget, config in theme.items():
            if widget == 'Text':
                # Apply to chat_text
                if hasattr(self, 'chat_text'):
                    self.chat_text.config(bg=config.get('bg', 'white'), fg=config.get('fg', 'black'))
            else:
                style.configure(widget, **config)

    def on_closing(self):
        try:
            if self.general_sock: self.general_sock.close()
        except: pass
        try: self.video_udp.close(); self.audio_udp.close()
        except: pass
        try: self.pyaudio_inst.terminate()
        except: pass
        try: self.root.destroy()
        except: pass

    def run(self): self.root.mainloop()

if __name__ == "__main__":
    client = VideoConferenceClient()
    client.run()
