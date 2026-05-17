# ⚙️ Dad's MMO Lab — Steam Deck Offline MMO Server Project

> *"The games we grew up with deserve to live forever. This project makes that possible on a single handheld device."*

**By [u/Kingspoken](https://reddit.com/u/Kingspoken)**

---

## 🖥️ Windows Launcher *(New)*

A full GUI launcher for Windows is now included — no terminal, no bash, no Linux knowledge required.

**First time setup — run once:**
```
Windows-DadsMMoLab\setup.bat
```
Installs Python dependencies into a local virtual environment. Internet required for this step only.

**Every time you want to play — run this:**
```
Windows-DadsMMoLab\launch.bat
```
Opens the launcher GUI. From here you can start/stop the server, choose your bot type, configure settings, and launch WoW — all with one click.

**Optional — build a standalone `.exe`:**
```
Windows-DadsMMoLab\build_exe.bat
```
Packages the launcher into a single `dist\DadsMmoLab.exe` you can pin to your taskbar or desktop. No Python installation required to run the output.

> **Quick flow:** `setup.bat` once → `launch.bat` every session → click **Start** → wait for *AZEROTH IS READY!* → click **Launch WoW** → play → close WoW → server shuts down automatically.

---

## 🔄 Recent Updates

### Windows Launcher
- ✅ Full GUI launcher added (`Windows-DadsMMoLab/`) — Start/Stop server, pick bot flavour, configure WoW path, live log viewer
- ✅ Prerequisite checker on first launch — guides you through Docker Desktop and Python setup

### Playerbots (liyunfan1223 fork) — Fixed
- ✅ **mod-playerbots now actually compiled** — the bot module lives in a separate git repo and must be cloned before cmake; without this, all bot code was silently compiled out even though the server showed `(Playerbot branch)` in its title. Fixed by explicitly cloning `liyunfan1223/mod-playerbots` into `modules/` before the build step.
- ✅ **AiPlayerbot settings now correctly applied** — all `AiPlayerbot.*` config keys live in `playerbots.conf`, not `worldserver.conf`. The entrypoint now patches the right file, so bot counts, faction ratios, and trading behaviour actually take effect.
- ✅ **Auction House bot properly wired** — replaced invented `AhBotEnabled/Buyer/Seller` env vars (which mapped to nothing) with the real key `AiPlayerbot.EnableRandomBotTrading = 1`.
- ✅ **Default bot count raised to 500** — tuned for modern gaming hardware (Ryzen 7 5800X class). Override with `PLAYERBOT_TOTAL_COUNT` in a `.env` file next to the compose file.
- ✅ **DBC table fixes for the liyunfan1223 fork** — the fork references `charsections_dbc` and `emotetextsound_dbc` tables that the standard db-import image doesn't create; the entrypoint now creates them automatically on first start.
- ✅ **MySQLExecutable crash fixed** — the DBUpdater called `std::filesystem::absolute("")` on an empty path and crashed immediately after DB pools opened. Now resolved by installing `mysql-client` in the runtime image and setting the path in config.

### Launcher
- ✅ **"Waiting for World Server" no longer gets stuck** — removed a `--tail 80` log limit that caused the `ready...` sentinel to be missed when 500+ bots log in simultaneously, pushing the line hundreds of positions back.

---

## 🎯 What Is This?

This is a collection of **step-by-step guides, Docker scripts, and automated installers** for running classic MMO private servers **completely offline** on a Steam Deck (or any Linux machine).

No subscription. No internet required. No servers getting shut down. Just you and the games you love — forever.

Every guide here is built around:
- ✅ **Open source emulators only** — no copyrighted assets, no game files distributed
- ✅ **Docker-based** — clean, repeatable, easy to remove
- ✅ **Steam Deck tested** — every setup verified on SteamOS
- ✅ **Dad-friendly** — written for people who love games, not just developers
- ✅ **One command install** — automated installers handle everything

---

## 🌍 The Story

I'm a dad who grew up on MMOs. Like a lot of you, I watched the servers for games I loved get shut down one by one. Nostalrius. Felmyst. Turtle WoW. Games that meant something — gone.

Then I got a Steam Deck.

And I started wondering: *what if I could bring them back? Offline. On a handheld. Forever.*

Turns out — for a lot of classic MMOs — you can. The emulator community has done incredible work over the years. This project is about packaging that work into something any dad (or mom, or kid) can actually use.

**This is not piracy.** We use open source server emulators. You supply your own legally obtained game clients. We just help you run them.

---

## 📺 Videos

**▶️ [Dad's MMO Lab — YouTube Channel](https://youtube.com/@DadsMmoLab)**

| Video | Description |
|-------|-------------|
| [It Still Lives](https://youtu.be/0XwLmaz3tao) | The proof of concept — WoW running offline on Steam Deck |
| [Full Install Guide](https://youtu.be/GVUVnngY93I) | Complete walkthrough from scratch using the auto-installer |

---

## ✅ Currently Working

| Game | Emulator | Bot Support | Status | Guide |
|------|----------|-------------|--------|-------|
| ⚔️ WoW WotLK 3.3.5a (Standard) | AzerothCore | Playerbots | ✅ Complete | [View Guide](./guides/wow-wotlk/README.md) |
| ⚔️ WoW WotLK 3.3.5a (NPCBots) | AzerothCore + trickerer fork | NPCBots | ✅ Complete | [View Guide](./guides/wow-wotlk-npcbots/README.md) |
| 🌿 Ragnarok Online | rAthena | — | ✅ Working | Guide coming soon |

---

## 🔥 In Progress

| Game | Emulator | Status |
|------|----------|--------|
| 🐉 Monster Hunter Frontier Z | Erupe CE | 🔨 Building |
| ⚔️ WoW Vanilla 1.12 | VMaNGOS | 🔨 Planned — easy build |
| ⚔️ WoW The Burning Crusade | TrinityCore | 🔨 Planned — easy build |
| 🏰 Dark Age of Camelot | OpenDAoC | 🔨 Docker ready — coming soon |
| 🎮 Warframe | OpenWF / SpaceNinjaServer | 🔨 Researching |

---

## 📋 Planned

| Game | Emulator | Notes |
|------|----------|-------|
| 🍄 MapleStory (v83 Pre-Big Bang) | Cosmic | Wife's pick 👩 |
| ⚡ PSO Blue Burst | newserv / Archon | Steam Deck proven |
| 🌌 Phantasy Star Universe | Clementine | Community server |
| 💎 Mu Online | OpenMU | Docker native |
| 🧱 LEGO Universe | Darkflame Universe | For the kids |
| 🏨 Habbo Hotel | Havana | Browser client |
| ⚔️ Tibia | The Forgotten Server | |
| 🗡️ Cabal Online | Freya | |
| 🌟 Final Fantasy XI | LandSandBoat | High demand |
| 🌟 Final Fantasy XIV | Sapphire | High demand |
| 🏰 EverQuest 1 | EQEmu | |
| 🚀 Star Wars Galaxies | SWGEmu | |
| ⚔️ Lineage 2 | L2J / Mobius | |
| 🌐 Ultima Online | ServUO | |
| 🦸 City of Heroes | Homecoming | |
| 🏹 Asheron's Call | ACEmulator | |
| 🌿 RuneScape (2006-2012) | 2009Scape / Darkan | |

---

## 📦 What's In This Repo

### 🖥️ Windows Launcher (`Windows-DadsMMoLab/`)

| File | When to run |
|------|-------------|
| `setup.bat` | **Once** — installs Python deps into local venv |
| `launch.bat` | **Every session** — opens the GUI launcher |
| `build_exe.bat` | Optional — compiles a standalone `.exe` |
| `launcher/` | Python source for the GUI (CustomTkinter) |
| `server/docker-compose.yml` | Base WoW — standard AzerothCore |
| `server/docker-compose-playerbots.yml` | Playerbots — AI bots that roam, quest, and use the AH |
| `server/docker-compose-npcbots.yml` | NPCBots — hireable NPC companions |
| `server/Dockerfile.playerbots` | Builds the Playerbots worldserver from source |
| `server/entrypoint-playerbots.sh` | Container entrypoint — patches config, creates DB tables, starts server |

### 🐧 Linux / Steam Deck (`guides/wow-wotlk/`)

| File | What it does |
|------|-------------|
| `install.sh` | Full automated installer — one command does everything |
| `install-npcbots.sh` | NPCBots version — compiles from source (2-4 hours) |
| `uninstall.sh` | Safe removal with character backup |
| `docker-compose.yml` | Server configuration |
| `wow-gaming-mode.sh` | Gaming Mode launcher — auto-shuts down with WoW |
| `migrate.sh` | Move characters and accounts between server versions |
| `fix-after-update.sh` | Fix Docker after a SteamOS update breaks it |
| `HOWTO-INSTALL.md` | Beginner install guide — zero Linux knowledge needed |
| `HOWTO-UNINSTALL.md` | Beginner uninstall guide |
| `HOWTO-DESKTOP-CONTROLS.md` | Full Desktop Mode control guide with GM console |

---

## 🚀 Quick Start

```bash
chmod +x install.sh && ./install.sh
```

The installer handles everything automatically:
- ✅ Detects SteamOS and fixes the pacman keyring
- ✅ Installs Docker if needed
- ✅ Downloads AzerothCore
- ✅ Creates a default **admin / admin** account with GM Level 3
- ✅ Builds a Gaming Mode launcher

**First time on Linux?** Read [HOWTO-INSTALL.md](./guides/wow-wotlk/HOWTO-INSTALL.md) first — every step explained in plain English, zero assumed knowledge.

---

## 🤖 Bot Options

Two different bot systems — pick the experience you want:

| | Standard | NPCBots |
|---|---|---|
| **Script** | `install.sh` | `install-npcbots.sh` |
| **Bots** | Playerbots (roam the world) | NPCBots (hired companions) |
| **Feel** | Living populated world | Personal party members |
| **Install time** | ~30 minutes | 2-4 hours (compiles from source) |
| **Folder** | `~/wow-server` | `~/wow-server-npcbots` |

---

## 🎮 Gaming Mode Setup

Play entirely from Steam Gaming Mode — no Desktop Mode needed after setup:

1. Add `wow-gaming-mode.sh` as a Non-Steam game via Konsole
2. Launch **"WoW Server"** from your Steam library
3. Watch the dots... **"AZEROTH IS READY!"**
4. Press Steam button → launch WoW from your library
5. Play your session
6. Close WoW → **server auto-shuts down**

Full setup instructions in [HOWTO-INSTALL.md](./guides/wow-wotlk/HOWTO-INSTALL.md)

---

## 🔀 Character Migration

Move characters and accounts between server versions:

```bash
chmod +x migrate.sh && ./migrate.sh
```

- Migrate full account + all characters between servers
- Copy a single character to another server
- Move characters between accounts on the same server
- Automatic backups before every operation

---

## 🔧 After a SteamOS Update

If Docker stops working after a Steam Deck update:

```bash
chmod +x fix-after-update.sh && ./fix-after-update.sh
```

Rebuilds the pacman keyring and reinstalls Docker automatically.

---

## 🛠️ How It Works

```
Steam Deck Gaming Mode
        │
        ▼
   Docker Container      ← Runs silently in background
   (Server Emulator)
        │
        ▼
  MySQL Database
   (Game Database)
        │
        ▼
Game Client via Proton
   → connects to localhost
   → completely offline
```

---

## ⚠️ Legal & Ethical Notes

This project:
- ✅ Uses **only open source server emulators**
- ✅ Does **not** distribute game assets, client files, or copyrighted content
- ✅ Requires you to **supply your own game client**
- ✅ Is intended for **personal, offline, single-player use**
- ❌ Does **not** help run public servers
- ❌ Does **not** support monetization of private servers

Huge credit to the communities that make this possible:
- **[AzerothCore](https://github.com/azerothcore/azerothcore-wotlk)** — the incredible open source WoW emulator
- **[liyunfan1223](https://github.com/liyunfan1223/azerothcore-wotlk)** — the Playerbots fork (core server)
- **[liyunfan1223/mod-playerbots](https://github.com/liyunfan1223/mod-playerbots)** — the Playerbots module
- **[trickerer](https://github.com/trickerer/AzerothCore-wotlk-with-NPCBots)** — the NPCBots fork
- Every emulator project linked in our guides

Go give them a star. They deserve it.

> *"This is preservation, not piracy."*

---

## 🤝 Contributing

Found a bug? Got a game working that's not listed? PRs are welcome!

Please read [CONTRIBUTING.md](./CONTRIBUTING.md) before submitting.

Special thanks to the community testers who have helped improve these installers through real-world bug reports. You know who you are. 🙏

---

## 💬 Community

- **Reddit:** [u/Kingspoken](https://reddit.com/u/Kingspoken)
- **Reddit Thread:** [The post that started it all](https://www.reddit.com/r/SteamDeck/s/A8SvXK0eOc)
- **YouTube:** [youtube.com/@DadsMmoLab](https://youtube.com/@DadsMmoLab)

---

## ☕ Support the Project

This project is free and always will be.

If it helped you relive something you thought was gone forever — a coffee goes a long way toward keeping this going and eventually making it a full time mission:

**[☕ ko-fi.com/dadsmmolab](https://ko-fi.com/dadsmmolab)**

Or just:
- ⭐ **Star this repo** — helps more people find it
- 📢 **Share it** with other dads who miss their old games
- 💬 **Comment** on the YouTube videos

---

## 📜 License

Scripts and guides in this repo are released under [MIT License](./LICENSE).

Game emulators linked here are subject to their own licenses. Game assets belong to their respective owners and are NOT included here.

---

*Built with love by a dad who just wanted to play WoW on the couch without a subscription.*

*And then things got out of hand.* 😄

*5,400 views. 565 likes. Two videos. A community. In 48 hours.*

*We're just getting started.* ⚔️
