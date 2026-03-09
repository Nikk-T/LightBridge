# LightBridge Web Interface

Flask-based web dashboard for the LightBridge SLS960 controller.

## Project Structure

```
LightBridgeWEB/
├── app.py                  ← Flask web server (NEW)
├── bridge_service.py       ← WebSocket bridge (existing)
├── serialdriver.py         ← SLS960 serial driver (existing)
├── mdp_protocol.py         ← MDP packet builder (existing)
├── maps.yaml               ← Unit/floor/colour config (existing)
├── templates/
│   └── index.html          ← Web dashboard (NEW)
└── requirements.txt        ← Python dependencies (NEW)
```

## Setup

```bash
pip install -r requirements.txt
```

## Running

Start both services (two terminals or use a process manager):

**Terminal 1 — WebSocket bridge:**
```bash
python bridge_service.py
```

**Terminal 2 — Flask web interface:**
```bash
python app.py
```

Then open: `http://<raspberry-pi-ip>:5000`

## Features

- **Unit grid** — click any unit card to cycle through statuses
- **Right-click menu** — set any specific status on a unit
- **Sync to Bridge** — push all current statuses to the SLS960 at once
- **Floor Highlight** — illuminate all LEDs on a given floor
- **Scenes** — Idle (warm white), Presentation, Blackout
- **Channel Direct** — send raw RGB to any channel (0–959)
- **Live ping** — connection badge shows ONLINE/OFFLINE + uptime

## Running as a Service (optional)

Create `/etc/systemd/system/lightbridge-web.service`:

```ini
[Unit]
Description=LightBridge Web Interface
After=network.target lightbridge.service

[Service]
WorkingDirectory=/home/pi/LightBridgeWEB
ExecStart=/usr/bin/python3 app.py
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable lightbridge-web
sudo systemctl start lightbridge-web
```
