# 🖥️ Desktop Mode Controls — Part 2
## GM Console, Commands, Troubleshooting & Linux Basics

> **⬅️ [Back to Part 1 — Server Management & Account Creation](./HOWTO-DESKTOP-CONTROLS-1.md)**

---

## 🖥️ The GM Console — Full Guide

The GM Console is your direct line to the WoW worldserver.
Think of it like texting the game engine directly. You can
create accounts, run commands and check server status —
all without being logged into the game.

---

### Opening the GM Console

Make sure your server is running first, then run:

```bash
docker attach $(docker ps --format '{{.Names}}' | grep worldserver | head -1)
```

You will see the server output scrolling and a cursor waiting
for input. You are now in the GM console!

---

### The Most Important Thing — How to Exit Safely

**NEVER press Ctrl+C inside the GM console.**

Ctrl+C kills the worldserver completely — everyone gets
disconnected and you will have to restart.

**The correct way to exit:**
1. Press and hold **Ctrl+P**
2. Then immediately press **Ctrl+Q**

This detaches you from the console safely while leaving the
server running perfectly.

> Memory trick: P for Pause, Q for Quit the console.
> Two keystrokes, always in that order.

---

### Common GM Console Commands

```
account create USERNAME PASSWORD PASSWORD
account set gmlevel USERNAME 3 -1
account list
account delete USERNAME
reload config
server info
server shutdown 10
```

---

### If the Console Will Not Accept Input

Sometimes the console appears stuck or ignores typing.
This usually means it is printing log messages over your input.

Press Enter once to get a clean line then type your command.
The command still registers even if you cannot see it clearly.

---

## 🎮 Useful In-Game GM Commands

Type these in the WoW chat box while playing:

### Teleport Anywhere
```
.tele stormwind
.tele orgrimmar
.tele dalaran
.tele ironforge
```

### Level Up
```
.levelup
.levelup 10
```

### Modify Speed
```
.modify speed 3
```

1 is normal, 3 is fast, 10 is very fast.

### Give Yourself Gold
```
.modify money 999999
```

### Spawn Any Item
```
.additem ITEM_ID
```

Look up item IDs on wowhead.com

### Change Time of Day
```
.modify time 12
```

0 through 23 for hour of day.

### See All Commands
```
.commands
```

---

## 🤖 NPCBot Commands

These work if you are running the NPCBots server version.

### Spawn a Bot Near You
```
.npcbot spawn CLASS_ID
```

Class IDs:
```
1  Warrior    2  Paladin
3  Hunter     4  Rogue
5  Priest     6  Death Knight
7  Shaman     8  Mage
9  Warlock    11 Druid
```

### Add a Bot to Your Party
Target the bot in-game then type:
```
.npcbot add
```

### Remove a Bot
Target the bot then type:
```
.npcbot remove
```

### Set Bot Role
```
.npcbot set role tank
.npcbot set role heal
.npcbot set role dps
```

### Bot Movement
```
.npcbot set follow
.npcbot set standstill
```

### List Your Bots
```
.npcbot list
```

> Install the NetherBot addon for a full UI so you never
> have to type these commands!
> `github.com/NetherstormX/NetherBot`

---

## 🔧 Troubleshooting Common Problems

### Cannot Connect to the Server

Check the server is running:
```bash
docker ps
```

If you do not see the containers start the server:
```bash
cd ~/wow-server && docker compose up -d
```

Check your realmlist.wtf contains:
```
set realmlist 127.0.0.1
```

Give it time — first launch takes 5-15 minutes.

---

### Login Says Information Not Valid

Create the account manually via the GM console:

```bash
docker attach $(docker ps --format '{{.Names}}' | grep worldserver | head -1)
```

Then type:
```
account create admin admin admin
account set gmlevel admin 3 -1
```

Exit with Ctrl+P then Ctrl+Q.

---

### The Server Will Not Start

Check what is wrong:
```bash
docker compose logs | tail -50
```

Most common fix — remove old containers and restart:
```bash
docker compose down
docker compose up -d
```

---

### Docker Stopped Working After a SteamOS Update

Run the fix script:
```bash
chmod +x fix-after-update.sh && ./fix-after-update.sh
```

See HOWTO-FIX-AFTER-UPDATE.md for full details.

---

### I Pressed Ctrl+C in the GM Console

Restart the worldserver:
```bash
docker restart $(docker ps --format '{{.Names}}' | grep worldserver | head -1)
```

Remember — always exit with Ctrl+P then Ctrl+Q.

---

## 📚 A Little Bit of Linux

Here are a few Linux basics that will make everything easier.
Each one takes 30 seconds to learn.

### Navigating Folders
```bash
cd ~/wow-server      # go into wow-server folder
cd ~                 # go back to home folder
cd ..                # go up one folder
ls                   # list what is in the current folder
pwd                  # show where you currently are
```

### Reading Files
```bash
cat filename.txt     # print the whole file
tail -20 filename    # print the last 20 lines
```

### Stopping a Running Command

**Ctrl+C** stops whatever is running in the terminal.

Never press Ctrl+C inside the GM console though. Use
Ctrl+P then Ctrl+Q instead.

### Running a Script
```bash
chmod +x script.sh   # give it permission to run
./script.sh          # run it
```

### The Pipe Symbol

The `|` symbol sends the output of one command to another:

```bash
docker logs ac-worldserver | grep "error"
```

This gets the logs AND searches them for the word error.
Very useful for finding problems!

---

## 🎓 What You Have Learned

If you have read both parts of this guide you now know:

- What Docker containers are and why we use them
- How to start and stop your server safely
- How to create and manage accounts
- How to use the GM console safely
- How to use in-game GM commands
- How to manage NPCBots
- How to diagnose and fix common problems
- Basic Linux navigation

That is genuinely more Linux knowledge than most people have.
And you learned it by setting up a WoW server. Not bad! 😄

---

## 📺 Video Guides

Full video tutorials at:
**youtube.com/@DadsMmoLab**

## 📦 More Guides

- HOWTO-INSTALL.md — install the server
- HOWTO-UNINSTALL.md — remove the server
- HOWTO-MIGRATE.md — move characters between servers
- HOWTO-SETUP-AHBOT.md — set up the Auction House Bot
- HOWTO-FIX-AFTER-UPDATE.md — fix Docker after SteamOS updates

---

*Part of the Dad's MMO Lab project — offline MMO servers
on Steam Deck, free forever.*

**youtube.com/@DadsMmoLab**
**github.com/DadsMmoLab/dads-mmo-lab**
**ko-fi.com/dadsmmolab**
