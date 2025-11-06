# VIDEO-CONFERENCING-APPLICATION-WORKING-ON-LOCAL-AREA-NETWORK


A **robust, standalone, and server-based collaboration system** designed to function entirely over a **Local Area Network (LAN)** — no internet required.  
This project enables real-time **video conferencing, audio conferencing, screen sharing, group text chat, and file sharing** among multiple users within the same network.

Built using **Python 3.8+** and a collection of **open-source libraries**, the system leverages **socket programming** to handle direct, low-level communication using both **UDP** (for real-time media) and **TCP** (for reliable data transmission).

---

## 📜 Table of Contents
- [Features](#-features)
- [Architecture Overview](#-architecture-overview)
- [Modules and Libraries](#-modules-and-libraries)
- [Performance Parameters](#-performance-parameters)
- [Environment Setup](#-environment-setup)
- [Usage Guide](#-usage-guide)
- [Screenshots](#-screenshots)
- [Conclusion](#-conclusion)

---

## 💡 Features
- 🎥 **Video Conferencing** — Real-time webcam video sharing  
- 🎙️ **Audio Conferencing** — Live voice communication  
- 🖥️ **Screen Sharing** — Share desktop or slides for collaboration  
- 💬 **Group Text Chat** — Multi-user chat via reliable TCP messaging  
- 📁 **File Sharing** — Send and receive files directly between participants  

All features run over **LAN**, ensuring full privacy and zero dependency on internet connectivity.

---

## 🏗️ Architecture Overview

The system follows a **Client–Server model**:

### 🖥️ Server
- Acts as a **central relay hub**
- Manages multiple concurrent **TCP and UDP** connections  
- Handles **user registration, media broadcasting, and session control**

### 💻 Clients
- Capture and transmit **audio/video data**  
- Receive and render media from other participants  
- Offer a unified, interactive **GUI interface**

### ⚙️ Protocols Used
| Protocol | Purpose |
|-----------|----------|
| **UDP** | Low-latency transmission for real-time video/audio |
| **TCP** | Reliable transport for chat messages and file sharing |

---

## 🧩 Modules and Libraries

### 🎥 Video Conferencing Module
**Purpose:** Capture webcam frames, compress them, and transmit via UDP.  

| Library | Version | Purpose | Why Chosen |
|----------|----------|----------|-------------|
| OpenCV (`cv2`) | 4.5+ | Capture and compress video frames | Fast, real-time image ops |
| Numpy | 1.21+ | Manage image array buffers | Lightweight array manipulation |
| Pillow (PIL) | 8.0+ | Display images in GUI | Integrates OpenCV with Tkinter |
| socket | Built-in | UDP communication | Low-level LAN operations |
| threading | Built-in | Concurrent frame handling | Enables smooth streaming |
| pickle | Built-in | Serialization | Simplifies frame transmission |
| struct | Built-in | Packet headers | Defines fixed UDP packet format |

---

### 🎧 Audio Conferencing Module
**Purpose:** Capture live audio, transmit via UDP, and mix received audio streams.  

| Library | Version | Purpose | Why Chosen |
|----------|----------|----------|-------------|
| PyAudio | 0.2.11+ | Capture and playback | Low-latency, cross-platform |
| socket | Built-in | Audio streaming | Real-time communication |
| threading | Built-in | Parallel capture/playback | Prevents lag |
| time | Built-in | Synchronization | Controls transmission timing |

---

### 🖥️ Screen & Slide Sharing Module
**Purpose:** Capture desktop frames for presentation-style sharing.  

| Library | Version | Purpose | Why Chosen |
|----------|----------|----------|-------------|
| PyAutoGUI | 0.9.53+ | Capture screenshots | Platform-independent |
| OpenCV | 4.5+ | Frame compression | Efficient encoding |
| Numpy | 1.21+ | Array conversion | Smooth OpenCV operations |
| socket, pickle, threading, struct | Built-in | Transmission | Real-time screen updates |

---

### 💬 Group Text Chat Module
**Purpose:** Send and receive messages among all participants.  

| Library | Version | Purpose | Why Chosen |
|----------|----------|----------|-------------|
| socket | Built-in | TCP communication | Reliable message delivery |
| threading | Built-in | Asynchronous receiving | Non-blocking chat UI |
| pickle | Built-in | Message serialization | Consistent structure |
| Tkinter | Built-in | GUI chat panel | Lightweight & interactive |

---

### 📁 File Sharing Module
**Purpose:** Transfer files over TCP with metadata.  

| Library | Version | Purpose | Why Chosen |
|----------|----------|----------|-------------|
| socket | Built-in | File transfer | Ensures reliability |
| os | Built-in | File I/O operations | Cross-platform support |
| pickle | Built-in | Metadata transmission | File info encapsulation |
| tkinter.filedialog | Built-in | File selection dialogs | Easy upload/download |

---

### 🪟 GUI and User Experience Module
**Purpose:** Combine all modules into a unified interface.  

| Library | Version | Purpose | Why Chosen |
|----------|----------|----------|-------------|
| Tkinter, ttk | Built-in | GUI design | Lightweight, native |
| Pillow (PIL) | 8.0+ | Image rendering | Smooth integration |
| threading | Built-in | Real-time UI updates | Responsive interface |

---

## ⚙️ Performance Parameters

| Parameter | Value | Explanation |
|------------|--------|-------------|
| Frame Resolution | 640×480 | Compact, clear video |
| Camera Frame Rate | 25 FPS | Smooth motion |
| Screen Share FPS | 8 FPS | Ideal for slides |
| JPEG Quality | 70 | Balanced compression |
| Audio Sampling Rate | 44100 Hz | CD-quality |
| Audio Channels | Mono | Saves bandwidth |
| Audio Chunk Size | 1024 | 23 ms latency |
| UDP Payload Limit | 60000 bytes | MTU-safe |
| Frame Timeout | 2 sec | Removes stale data |
| Inactive Timeout | 6 sec | Auto-cleanup |
| Cleanup Interval | 1 sec | Ensures performance |

---

## 🧠 Versions and Environment

| Component | Version |
|------------|----------|
| Python | 3.8+ |
| OpenCV | 4.5+ |
| Numpy | 1.21+ |
| Pillow | 8.0+ |
| PyAudio | 0.2.11+ |
| PyAutoGUI | 0.9.53+ |
| Tkinter | Built-in |

---

## ⚙️ Environment Setup

1. Install **Python 3.8+** and **pip**.  
2. Clone the repository:
   ```bash
   git clone https://github.com/<your-username>/LAN-Communication-App.git
   cd LAN-Communication-App
   Install dependencies:

pip install -r requirements.txt


Ensure all devices are connected to the same LAN (e.g., via mobile hotspot or Wi-Fi).



 Usage Guide


 Run the Server

Open server.py in your code editor.

Locate the line where the server host/IP is defined, usually like this:

SERVER_HOST = '192.168.x.x'


Replace '192.168.x.x' with your system’s local network IP address.

Find it using:

ipconfig   # (on Windows)
ifconfig   # (on Linux/macOS)


Example:

SERVER_HOST = '192.168.1.5'


Start the server:

python server.py

 Run the Client

Open client.py and ensure it connects to the same server IP:

SERVER_IP = '192.168.1.5'


Start the client:

python client.py


In the GUI:

Enter your Username, Meeting ID, and the Server IP (the same IP used in the server).

Click Connect.

Use the side buttons to:

 Start/Stop Camera

 Mute/Unmute Audio

 Start/Stop Screen Share

 Chat using the message box.

 Send or receive files via Send File.




This LAN-based communication suite demonstrates real-time multi-threaded networking using Python.
It successfully integrates:

25 FPS video streaming

44.1 kHz audio transmission

Seamless GUI responsiveness

By blending Python’s simplicity with low-level socket programming, this project achieves speed, clarity, and maintainability, a fully functional collaboration tool that runs completely offline.
