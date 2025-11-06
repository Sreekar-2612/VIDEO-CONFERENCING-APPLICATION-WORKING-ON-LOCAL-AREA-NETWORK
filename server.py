#!/usr/bin/env python3
"""
Hybrid server (UDP video/audio + TCP general) updated for multi-user video tiles.
Video UDP packets carry fragmented pickled payloads {'username':..., 'frame': b'...'}.
"""

import socket, threading, pickle, logging, struct, time

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

SERVER_HOST = "172.17.177.78"
VIDEO_UDP_PORT = 60000
AUDIO_UDP_PORT = 60001
GENERAL_TCP_PORT = 50002

VIDEO_HDR_FMT = ">IHH"
VIDEO_HDR_SIZE = struct.calcsize(VIDEO_HDR_FMT)
MAX_UDP_PAYLOAD = 60000
AUDIO_UDP_MAX = 4096
FRAME_TTL = 2.0

# shared state
dict_lock = threading.Lock()
meet_general_clients = {}    # meet_id -> [ (conn, addr, username) ... ]
meet_video_addrs = {}        # meet_id -> set( (ip,port) )
meet_audio_addrs = {}        # meet_id -> set( (ip,port) )
udp_to_meet = {}             # (ip,port) -> meet_id
udp_to_user = {}             # (ip,port) -> username

# reassembly for incoming UDP fragments (payloads are pickled payloads)
reassembly_lock = threading.Lock()
video_reassembly = {}   # key: (sender_addr, frame_id) -> {'parts':{idx:bytes}, 'total':int, 'ts':float}

running = True

def recv_exact(conn, n):
    data = b''
    while len(data) < n:
        p = conn.recv(n - len(data))
        if not p:
            return None
        data += p
    return data

def recv_pickle_prefixed(conn):
    hdr = recv_exact(conn, 4)
    if not hdr:
        return None
    ln = struct.unpack(">L", hdr)[0]
    payload = recv_exact(conn, ln)
    if not payload:
        return None
    return pickle.loads(payload)

def send_pickle_prefixed(conn, obj):
    data = pickle.dumps(obj)
    conn.sendall(struct.pack(">L", len(data)) + data)

def cleanup_old_reassembly():
    while running:
        now = time.time()
        to_del = []
        with reassembly_lock:
            for k, v in list(video_reassembly.items()):
                if now - v['ts'] > FRAME_TTL:
                    to_del.append(k)
            for k in to_del:
                del video_reassembly[k]
        time.sleep(1.0)

# general TCP handler: handshake registers UDP ports and username
def handle_general(conn, addr):
    meet_id = None
    username = None
    try:
        info = recv_pickle_prefixed(conn)
        if not info:
            logging.info(f"[general] bad handshake from {addr}")
            conn.close()
            return
        username = info.get('username')
        meet_id = info.get('meet_id')
        vid_port = info.get('video_udp_port')
        aud_port = info.get('audio_udp_port')
        client_ip = addr[0]

        with dict_lock:
            meet_general_clients.setdefault(meet_id, []).append((conn, addr, username))
            if vid_port:
                meet_video_addrs.setdefault(meet_id, set()).add((client_ip, vid_port))
                udp_to_meet[(client_ip, vid_port)] = meet_id
                udp_to_user[(client_ip, vid_port)] = username
            if aud_port:
                meet_audio_addrs.setdefault(meet_id, set()).add((client_ip, aud_port))

        logging.info(f"[general] {username}@{meet_id} from {addr} registered UDP ports v:{vid_port} a:{aud_port}")

        # relay pickled messages to peers
        while running:
            msg = recv_pickle_prefixed(conn)
            if msg is None:
                break
            with dict_lock:
                peers = list(meet_general_clients.get(meet_id, []))
            for (p_conn, p_addr, p_user) in peers:
                if p_addr != addr:
                    try:
                        send_pickle_prefixed(p_conn, msg)
                    except Exception:
                        pass
            # handle file data relay if msg is file header
            if msg.get('msg_type') == 'file':
                size = msg.get('size', 0)
                remaining = size
                while remaining > 0:
                    chunk_size = min(1024, remaining)
                    chunk = recv_exact(conn, chunk_size)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    for (p_conn, p_addr, p_user) in peers:
                        if p_addr != addr:
                            try:
                                p_conn.sendall(chunk)
                            except Exception:
                                pass
    except Exception as e:
        logging.exception(f"[general] exception {addr}: {e}")
    finally:
        with dict_lock:
            if meet_id in meet_general_clients:
                meet_general_clients[meet_id] = [x for x in meet_general_clients[meet_id] if x[1] != addr]
                if not meet_general_clients[meet_id]:
                    del meet_general_clients[meet_id]
            # remove UDP registrations by client IP
            if meet_id:
                if meet_id in meet_video_addrs:
                    to_keep = {a for a in meet_video_addrs[meet_id] if a[0] != client_ip}
                    if to_keep:
                        meet_video_addrs[meet_id] = to_keep
                    else:
                        del meet_video_addrs[meet_id]
                if meet_id in meet_audio_addrs:
                    to_keep = {a for a in meet_audio_addrs[meet_id] if a[0] != client_ip}
                    if to_keep:
                        meet_audio_addrs[meet_id] = to_keep
                    else:
                        del meet_audio_addrs[meet_id]
                # remove reverse maps
                for k in list(udp_to_meet.keys()):
                    if k[0] == client_ip:
                        udp_to_meet.pop(k, None)
                        udp_to_user.pop(k, None)
        try:
            conn.close()
        except:
            pass
        logging.info(f"[general] {username}@{addr} disconnected")

# video UDP listener: receives fragmented pickled payloads from clients, reassembles, and forwards
def video_udp_listener(udp_sock):
    while running:
        try:
            pkt, sender = udp_sock.recvfrom(MAX_UDP_PAYLOAD + VIDEO_HDR_SIZE + 64)
            if not pkt or len(pkt) < VIDEO_HDR_SIZE:
                continue
            hdr = pkt[:VIDEO_HDR_SIZE]
            payload = pkt[VIDEO_HDR_SIZE:]
            frame_id, total_parts, part_idx = struct.unpack(VIDEO_HDR_FMT, hdr)
            key = (sender, frame_id)
            with reassembly_lock:
                entry = video_reassembly.get(key)
                if not entry:
                    entry = {'parts': {}, 'total': total_parts, 'ts': time.time()}
                    video_reassembly[key] = entry
                entry['parts'][part_idx] = payload
                entry['ts'] = time.time()
                if len(entry['parts']) == entry['total']:
                    parts = [entry['parts'][i] for i in range(entry['total'])]
                    payload_bytes = b''.join(parts)
                    del video_reassembly[key]
                    # determine meeting by sender address (exact ip+port mapping)
                    meet = udp_to_meet.get(sender)
                    if not meet:
                        # try by ip only
                        sender_ip = sender[0]
                        with dict_lock:
                            for mid, addrs in meet_video_addrs.items():
                                if any(a[0] == sender_ip for a in addrs):
                                    meet = mid
                                    break
                    if not meet:
                        continue
                    # forward the SAME payload_bytes (pickled) to other peers in meet
                    with dict_lock:
                        peers = set(meet_video_addrs.get(meet, set()))
                    for peer in peers:
                        if peer == sender:
                            continue
                        # fragment payload_bytes and send
                        max_payload = MAX_UDP_PAYLOAD
                        total = (len(payload_bytes) + max_payload - 1) // max_payload
                        frame_id_out = int(time.time() * 1000) & 0xFFFFFFFF
                        for idx in range(total):
                            start = idx * max_payload
                            part = payload_bytes[start:start + max_payload]
                            hdr_out = struct.pack(VIDEO_HDR_FMT, frame_id_out, total, idx)
                            try:
                                udp_sock.sendto(hdr_out + part, peer)
                            except Exception:
                                pass
        except Exception:
            logging.exception("video_udp_listener exception")

# audio UDP: simple relay (raw PCM)
def audio_udp_listener(udp_sock):
    while running:
        try:
            pkt, sender = udp_sock.recvfrom(AUDIO_UDP_MAX + 64)
            if not pkt:
                continue
            sender_ip = sender[0]
            with dict_lock:
                for mid, addrs in meet_audio_addrs.items():
                    if any(a[0] == sender_ip for a in addrs):
                        peers = set(addrs)
                        for peer in peers:
                            if peer != sender:
                                try:
                                    udp_sock.sendto(pkt, peer)
                                except:
                                    pass
        except Exception:
            logging.exception("audio_udp_listener exception")

def accept_general_tcp(tcp_sock):
    while running:
        try:
            conn, addr = tcp_sock.accept()
            threading.Thread(target=handle_general, args=(conn, addr), daemon=True).start()
        except Exception:
            logging.exception("accept_general_tcp exception")
            break

def main():
    global running
    logging.info("Starting server...")
    video_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    video_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    video_udp.bind((SERVER_HOST, VIDEO_UDP_PORT))
    logging.info(f"Video UDP bound {SERVER_HOST}:{VIDEO_UDP_PORT}")

    audio_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    audio_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    audio_udp.bind((SERVER_HOST, AUDIO_UDP_PORT))
    logging.info(f"Audio UDP bound {SERVER_HOST}:{AUDIO_UDP_PORT}")

    general_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    general_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    general_tcp.bind((SERVER_HOST, GENERAL_TCP_PORT))
    general_tcp.listen(50)
    logging.info(f"General TCP listening {SERVER_HOST}:{GENERAL_TCP_PORT}")

    threading.Thread(target=cleanup_old_reassembly, daemon=True).start()
    threading.Thread(target=video_udp_listener, args=(video_udp,), daemon=True).start()
    threading.Thread(target=audio_udp_listener, args=(audio_udp,), daemon=True).start()
    threading.Thread(target=accept_general_tcp, args=(general_tcp,), daemon=True).start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logging.info("Shutting down")
    finally:
        running = False
        try:
            general_tcp.close()
            video_udp.close()
            audio_udp.close()
        except:
            pass
        logging.info("Server terminated")

if __name__ == "__main__":
    main()
