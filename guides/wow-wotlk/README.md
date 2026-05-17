# ⚔️ World of Warcraft — Offline Private Server on Steam Deck

> Run a fully featured WoW 3.3.5a (Wrath of the Lich King) server completely offline on your Steam Deck using AzerothCore and Docker.

**Difficulty:** Medium | **Time:** ~1.5 hours | **Storage:** ~15GB

---

## 📋 What You'll Have When Done

- A fully working WoW WotLK 3.3.5a private server running on your Steam Deck
- Full single-player experience — all quests, dungeons, raids available
- NPCBots to fill your party and raid groups (optional but awesome)
- Works completely offline — on the couch, on a plane, anywhere
- Launches from Steam game mode like any other game

---

## 🧰 Prerequisites

Before starting, you'll need:

1. **A WoW 3.3.5a client** — this is the game client files. You must obtain these yourself. Search for "WoW 3.3.5a client download" — many legal backups exist since this version is no longer sold by Blizzard.
2. **Steam Deck in Desktop Mode** — press the STEAM button → Power → Switch to Desktop
3. **At least 15GB free storage**
4. **A keyboard and mouse** — highly recommended for this setup (Bluetooth works fine)

---

## 🐋 Step 1 — Install Docker

Open a terminal (Konsole) in Desktop Mode and run:

```bash
# Install Docker using the community script
curl -fsSL https://get.docker.com | sh

# Add your user to the docker group
sudo usermod -aG docker $USER

# Start Docker service
sudo systemctl enable docker
sudo systemctl start docker

# Verify it works
docker --version
```

> ⚠️ You may need to reboot after this step for group permissions to take effect.

---

## 📁 Step 2 — Create Your Server Directory

```bash
# Create a directory for your WoW server
mkdir -p ~/wow-server
cd ~/wow-server
```

---

## 📝 Step 3 — Create the Docker Compose File

Create a file called `docker-compose.yml` in your `~/wow-server` folder with the following content:

```yaml
version: '3.8'

services:
  ac-database:
    image: azerothcore/azerothcore:database
    container_name: ac_database
    environment:
      MYSQL_ROOT_PASSWORD: password
      MYSQL_DATABASE: acore_world
    volumes:
      - ac-database:/var/lib/mysql
    restart: unless-stopped
    networks:
      - ac-network

  ac-worldserver:
    image: azerothcore/azerothcore:worldserver
    container_name: ac_worldserver
    depends_on:
      - ac-database
    volumes:
      - ./config:/azerothcore/env/dist/etc
      - ./logs:/azerothcore/env/dist/logs
    ports:
      - "8085:8085"
    restart: unless-stopped
    networks:
      - ac-network
    stdin_open: true
    tty: true

  ac-authserver:
    image: azerothcore/azerothcore:authserver
    container_name: ac_authserver
    depends_on:
      - ac-database
    ports:
      - "3724:3724"
    restart: unless-stopped
    networks:
      - ac-network

volumes:
  ac-database:

networks:
  ac-network:
    driver: bridge
```

---

## 🚀 Step 4 — Start the Server

```bash
cd ~/wow-server

# Pull the images and start everything
docker compose up -d

# Watch the logs to see when it's ready
# (first launch takes 5-10 minutes to populate the database)
docker logs -f ac_worldserver
```

You're looking for this line in the logs:
```
World of Warcraft Daemon -- Version ...
>> World initialized
```

When you see that — your server is running! ✅

---

## 🔧 Step 5 — Configure Your WoW Client

Navigate to your WoW 3.3.5a client folder and find the file called `realmlist.wtf`. Open it with a text editor and change it to:

```
set realmlist 127.0.0.1
```

Save the file.

---

## 👤 Step 6 — Create Your Account

With the server running, open a terminal and run:

```bash
# Access the world server console
docker attach ac_worldserver

# Create your account (replace USERNAME and PASSWORD)
account create USERNAME PASSWORD

# Give yourself GM permissions (optional but useful)
account set gmlevel USERNAME 3 -1

# Detach from console without stopping server
# Press: Ctrl+P then Ctrl+Q
```

---

## 🎮 Step 7 — Add to Steam and Play

1. Open Steam in Desktop Mode
2. Click **Games** → **Add a Non-Steam Game**
3. Browse to your WoW 3.3.5a client folder and select `Wow.exe`
4. Right-click the new entry → **Properties**
5. Under **Compatibility** → Check **Force the use of a specific Steam Play compatibility tool** → Select **Proton Experimental**
6. Launch the game!

At the login screen, enter the account credentials you created in Step 6.

---

## 🤖 Step 8 (Optional) — Add NPCBots for Solo Play

NPCBots let you fill your party with AI companions so you can run dungeons and raids solo. This is what makes the offline experience truly shine.

```bash
# Stop your current server first
docker compose down

# The AzerothCore Docker image includes NPC bots
# Enable them in your worldserver.conf:
nano ~/wow-server/config/worldserver.conf
```

Find and set:
```ini
NpcBot.Enable = 1
NpcBot.MaxBots = 5
```

Restart the server:
```bash
docker compose up -d
```

In-game, find any NpcBot trainer NPC to hire your companions.

---

## 🛠️ Useful Commands

```bash
# Start the server
cd ~/wow-server && docker compose up -d

# Stop the server
cd ~/wow-server && docker compose down

# Check if server is running
docker ps

# View server logs
docker logs -f ac_worldserver

# Access the GM console
docker attach ac_worldserver
```

---

## 🔄 Auto-Start on Boot (Optional)

If you want the server to start automatically when your Steam Deck boots:

```bash
sudo systemctl enable docker
# Docker Compose services with restart: unless-stopped
# will restart automatically when Docker starts
```

---

## ❓ Troubleshooting

**Game says "Unable to connect"**
- Make sure the server is running: `docker ps`
- Check realmlist.wtf is set to `127.0.0.1`
- Give the worldserver 5-10 minutes on first launch

**Server crashes on startup**
- Check logs: `docker logs ac_worldserver`
- Make sure you have enough storage space: `df -h`

**Can't log in with my account**
- Double-check you ran the `account create` command
- Account name and password are case-sensitive

**Proton/WoW client crashes**
- Try switching to Proton Experimental or GE-Proton
- Make sure your client is specifically version 3.3.5a (build 12340)

---

## 📺 Video Tutorial

Prefer to watch? Full video walkthrough on YouTube:

**▶️ [Watch the full video guide](https://youtube.com/@DadsMmoLab)** *(coming soon)*

---

## 🙏 Credits

- [AzerothCore](https://github.com/azerothcore/azerothcore-wotlk) — the incredible open source WoW emulator
- [NPCBots Module](https://github.com/trickerer/Trinity-Bots) — solo play AI companions
- The entire WoW emulator community for years of work

---

*Part of the [Dad's MMO Lab](../../README.md) project.*
