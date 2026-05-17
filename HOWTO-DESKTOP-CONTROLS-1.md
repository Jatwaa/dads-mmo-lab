# 🖥️ Desktop Mode Controls — Part 1
## Server Management & Account Creation

> **➡️ [Part 2 — GM Console, Bot Commands, Troubleshooting & Linux Basics](./HOWTO-DESKTOP-CONTROLS-2.md)**

---

## ⚡ The Only Commands You Need

Copy paste. That's it. No Linux knowledge required.

**Base WoW:**
```bash
# Start
cd ~/wow-server && docker compose up -d

# Stop
cd ~/wow-server && docker compose down
```

**NPCBots:**
```bash
# Start
cd ~/wow-server-npcbots && docker compose up -d

# Stop
cd ~/wow-server-npcbots && docker compose down
```

**Playerbots:**
```bash
# Start
cd ~/wow-server-playerbots && docker compose up -d

# Stop
cd ~/wow-server-playerbots && docker compose down
```

> ⚠️ Only run ONE server at a time — they share the same
> ports. Stop one before starting another.

> 💡 Gaming Mode handles start and stop automatically.
> These commands are only needed in Desktop Mode.

---

## 🧠 Understanding What's Actually Happening

Before diving in — here's what your WoW server actually is.
This will make everything click.

### What is Docker?

Think of Docker like a lunchbox. Inside are everything your
WoW server needs — the database, the game server, all the
settings. Docker keeps it all contained and neat so it does
not interfere with the rest of your Steam Deck.

When you run `docker compose up` you are opening the lunchbox.
When you run `docker compose down` you are closing it safely.

### What are Containers?

Your WoW server is actually THREE separate programs running
at the same time:

| Container | What it does |
|-----------|-------------|
| Database | Stores everything — characters, items, quests |
| Authserver | Handles login — checks username and password |
| Worldserver | The actual game world — NPCs, quests, combat |

They work together. If the database is not running nothing
else works. That is why we always use `docker compose` — it
starts all three in the right order automatically.

### Which Container is Which?

Different server versions use different container names:

| Server | Worldserver Container |
|--------|----------------------|
| Base WoW | `acore-docker-ac-worldserver-1` |
| NPCBots | `ac-worldserver` |
| Playerbots | `ac-worldserver` |

The universal way to always find the right one:

```bash
docker ps --format '{{.Names}}' | grep worldserver
```

Whatever it returns — that is your container.

---

## 📋 Quick Reference — Commands You Will Use Most

### Start the Server
```bash
cd ~/wow-server && docker compose up -d
```

Change `wow-server` to `wow-server-npcbots` or
`wow-server-playerbots` for other versions.

### Stop the Server Safely
```bash
cd ~/wow-server && docker compose down
```

### Check if Server is Running
```bash
docker ps
```

### Watch the Server Start Up
```bash
docker logs -f $(docker ps --format '{{.Names}}' | grep worldserver | head -1)
```

Press Ctrl+C to stop watching. The server keeps running.

### Open the GM Console
```bash
docker attach $(docker ps --format '{{.Names}}' | grep worldserver | head -1)
```

Exit with **Ctrl+P then Ctrl+Q** — never Ctrl+C!

---

## ⚡ Everyday Server Management

### Starting Your Server

```bash
cd ~/wow-server && docker compose up -d
```

The `-d` means run in the background. You can close Konsole
and the server keeps running!

For other server versions:
```bash
cd ~/wow-server-npcbots && docker compose up -d
cd ~/wow-server-playerbots && docker compose up -d
```

---

### Stopping Your Server Safely

```bash
cd ~/wow-server && docker compose down
```

Always use this to stop — never just turn off your Steam Deck
while the server is running. Docker needs to save the database
properly first.

---

### Checking Server Status

```bash
docker ps
```

If you see your worldserver, authserver and database containers
listed — your server is running. If the table is empty — it
is stopped.

---

### Restarting Just the Worldserver

Sometimes you change a setting and just need to restart the
game world without touching the database:

```bash
docker restart $(docker ps --format '{{.Names}}' | grep worldserver | head -1)
```

---

### Checking Server Logs

```bash
docker logs $(docker ps --format '{{.Names}}' | grep worldserver | head -1)
```

To watch live as it happens add `-f`:

```bash
docker logs -f $(docker ps --format '{{.Names}}' | grep worldserver | head -1)
```

Press Ctrl+C to stop following. The server keeps running.

---

## 👤 Account Management

### Creating a New Account

Open the GM console:

```bash
docker attach $(docker ps --format '{{.Names}}' | grep worldserver | head -1)
```

Then type:

```
account create USERNAME PASSWORD PASSWORD
account set gmlevel USERNAME 3 -1
```

Exit safely with **Ctrl+P then Ctrl+Q**

> Type the password twice — it is a confirmation step.
> Both must match or it will not create the account.

---

### Creating Multiple Accounts

Just repeat the process for each account:

```
account create caitlin mypassword mypassword
account set gmlevel caitlin 3 -1

account create kiddo simplepass simplepass
account set gmlevel kiddo 3 -1
```

---

### GM Level Explained

| Level | Role | Can do |
|-------|------|--------|
| 0 | Regular player | Nothing special |
| 1 | Moderator | Basic commands |
| 2 | Game Master | Most commands |
| 3 | Administrator | Full control |

---

### Changing a Password

```
account set password USERNAME OLDPASSWORD NEWPASSWORD
```

---

### Listing All Accounts

```
account list
```

---

## 🔀 Running Multiple Server Versions

If you have Base WoW AND NPCBots AND Playerbots installed
you can only run one at a time — they share the same ports.

**Switch from Base WoW to NPCBots:**

```bash
cd ~/wow-server && docker compose down
cd ~/wow-server-npcbots && docker compose up -d
```

**Switch from NPCBots to Playerbots:**

```bash
cd ~/wow-server-npcbots && docker compose down
cd ~/wow-server-playerbots && docker compose up -d
```

---

## 💾 Backing Up Your Characters

Before doing anything major — back up first:

```bash
DB=$(docker ps --format '{{.Names}}' | grep -iE "database" | head -1)
docker exec $DB mysqldump -uroot -ppassword --databases acore_characters acore_auth acore_world > ~/wow-backup-$(date +%Y%m%d).sql
```

This saves everything to a file named with today's date.

**To restore a backup:**

```bash
DB=$(docker ps --format '{{.Names}}' | grep -iE "database" | head -1)
docker exec -i $DB mysql -uroot -ppassword < ~/wow-backup-20260506.sql
```

---

## ➡️ Continue to Part 2

**[Part 2 — GM Console, Bot Commands, Troubleshooting & Linux Basics](./HOWTO-DESKTOP-CONTROLS-2.md)**

---

*Part of the Dad's MMO Lab project — offline MMO servers on Steam Deck, free forever.*

**youtube.com/@DadsMmoLab**
**github.com/DadsMmoLab/dads-mmo-lab**
