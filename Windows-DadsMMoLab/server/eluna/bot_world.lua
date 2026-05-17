--[[
  bot_world.lua — Dad's MMO Lab server-side bot utility
  Requires AzerothCore + Eluna Lua Engine (AC_ALE_ENABLED = 1)

  Features
  ────────
  • Reports bot system status on server startup
  • Adds GM command:  .botworld <subcommand>
      .botworld status               — show wandering bot / playerbot counts
      .botworld ahpopulate [count]   — seed AH with random vendor items
      .botworld ahclear              — remove all bot-seeded AH listings
      .botworld help                 — list commands

  IMPORTANT: This script does NOT replace AzerothCore's built-in NpcBot or
  mod-playerbots systems.  It is purely a diagnostic and convenience layer.
  All real bot logic runs inside the C++ worldserver.

  Mounting:
    volumes:
      - ./eluna:/azerothcore/env/dist/data/luascripts
  The worldserver loads every *.lua file in that directory on startup.
--]]

-- ─────────────────────────────────────────────────────────────────────────────
-- Constants
-- ─────────────────────────────────────────────────────────────────────────────

local BOTWORLD_VERSION = "1.0.0"

-- Items seeded by ahpopulate are tagged with this comment in item_instance
-- so ahclear can remove only bot-seeded listings.
local AH_BOT_OWNER_GUID_FLAG = 0xBB07  -- arbitrary reserved GUID high bits marker

-- AH faction house IDs  (1=Alliance, 2=Horde, 3=Neutral)
local AH_HOUSE = { alliance = 1, horde = 2, neutral = 3 }

-- A curated list of common vendor items to seed the AH with.
-- Format: { entry, stackSize, priceCopper }
-- These are all items that exist in every 3.3.5a database.
local AH_SEED_ITEMS = {
    -- Consumables
    { 4604,  5,  15000  },  -- Lesser Healing Potion
    { 118,   5,  25000  },  -- Minor Healing Potion
    { 929,   5,  40000  },  -- Healing Potion
    { 1710,  5,  80000  },  -- Greater Healing Potion
    { 13446, 5,  150000 },  -- Superior Healing Potion
    { 22829, 5,  400000 },  -- Major Healing Potion
    { 33447, 5,  800000 },  -- Runic Healing Potion
    -- Mana
    { 2455,  5,  20000  },  -- Minor Mana Potion
    { 3385,  5,  45000  },  -- Mana Potion
    { 6149,  5,  90000  },  -- Greater Mana Potion
    { 13443, 5,  200000 },  -- Superior Mana Potion
    { 33448, 5,  900000 },  -- Runic Mana Potion
    -- Food / Buff
    { 34753, 20, 5000   },  -- Conjured Mana Biscuit (trainers sell these)
    { 5350,  10, 8000   },  -- Melon Juice
    { 27860, 10, 12000  },  -- Purified Draenic Water
    -- Reagents
    { 17020, 20, 3000   },  -- Elemental Earth
    { 7068,  20, 3000   },  -- Elemental Fire
    { 7078,  20, 3000   },  -- Elemental Water
    { 7080,  20, 3000   },  -- Elemental Air
    { 52328, 20, 10000  },  -- Volatile Fire
    { 52329, 20, 10000  },  -- Volatile Water
    { 52325, 20, 10000  },  -- Volatile Earth
    { 52328, 20, 10000  },  -- Volatile Air
    -- Trade goods
    { 2589,  5,  50000  },  -- Linen Cloth
    { 2592,  5,  80000  },  -- Wool Cloth
    { 4306,  5,  120000 },  -- Silk Cloth
    { 4338,  5,  180000 },  -- Mageweave Cloth
    { 14047, 5,  250000 },  -- Runecloth
    { 21877, 5,  400000 },  -- Netherweave Cloth
    { 33470, 5,  600000 },  -- Frostweave Cloth
}

-- ─────────────────────────────────────────────────────────────────────────────
-- Startup hook
-- ─────────────────────────────────────────────────────────────────────────────

local function OnServerStartup(event)
    print("[BotWorld] ====================================================")
    print("[BotWorld]  Dad's MMO Lab — Bot World mod v" .. BOTWORLD_VERSION)
    print("[BotWorld]  Type  .botworld help  in-game for commands.")
    print("[BotWorld] ====================================================")
end

RegisterServerEvent(3, OnServerStartup)  -- WORLD_EVENT_ON_STARTUP

-- ─────────────────────────────────────────────────────────────────────────────
-- Helpers
-- ─────────────────────────────────────────────────────────────────────────────

local function msg(player, text)
    player:SendBroadcastMessage("|cff00ccff[BotWorld]|r " .. text)
end

local function err(player, text)
    player:SendBroadcastMessage("|cffff4444[BotWorld]|r " .. text)
end

-- Return count of online players whose names begin with "RndBot" (NPCBots
-- wandering bots use account names starting with that prefix by default).
local function countWanderingBots()
    local result = WorldDBQuery(
        "SELECT COUNT(*) FROM characters WHERE name LIKE 'RndBot%'"
    )
    if result then
        return result:GetUInt32(0)
    end
    return 0
end

-- Count online playerbots (they have an account in acore_auth but no real
-- session — they appear in characters but not in the online player list).
local function countPlayerbots()
    local result = CharDBQuery(
        "SELECT COUNT(*) FROM characters c "
        .. "JOIN acore_auth.account a ON c.account = a.id "
        .. "WHERE a.username LIKE 'rndbot%' OR a.username LIKE 'bot%'"
    )
    if result then
        return result:GetUInt32(0)
    end
    return 0
end

-- Count AH listings that were seeded by this script.
-- We identify them by checking item_instance.data for our marker pattern.
local function countBotAHListings()
    local result = CharDBQuery(
        "SELECT COUNT(*) FROM auctionhouse WHERE itemowner = 0"
    )
    if result then
        return result:GetUInt32(0)
    end
    return 0
end

-- ─────────────────────────────────────────────────────────────────────────────
-- AH population
-- ─────────────────────────────────────────────────────────────────────────────

--[[
  Seed the Auction House with vendor items so players have something to buy
  even before other players have posted listings.

  We insert directly into `item_instance` and `auctionhouse` tables.
  - itemowner = 0 flags these as bot-seeded listings (cleaned by ahclear).
  - We generate item GUIDs using the current max guid + offset.
  - Auction IDs are similarly offset above the current max.
--]]
local function populateAH(player, houseId, count)
    count = math.min(count or 20, 100)  -- cap at 100 per call

    -- Get current max item GUID
    local guidRes = CharDBQuery("SELECT MAX(guid) FROM item_instance")
    local baseGuid = guidRes and guidRes:GetUInt32(0) or 10000000
    baseGuid = baseGuid + 1

    -- Get current max auction ID
    local auctRes = CharDBQuery("SELECT MAX(id) FROM auctionhouse")
    local baseAuct = auctRes and auctRes:GetUInt32(0) or 0
    baseAuct = baseAuct + 1

    -- Time values: 48-hour duration in seconds from now
    local expireTime = os.time() + 48 * 3600

    local inserted = 0
    for i = 1, count do
        -- Pick a random item from the seed list
        local item = AH_SEED_ITEMS[math.random(1, #AH_SEED_ITEMS)]
        local entry     = item[1]
        local stackSize = math.random(1, item[2])
        local buyout    = math.floor(item[3] * stackSize * (0.8 + math.random() * 0.4))
        local bid       = math.floor(buyout * 0.5)

        local guid = baseGuid + i - 1
        local auctId = baseAuct + i - 1

        -- Insert item instance (minimal columns; server fills the rest on load)
        CharDBExecute(string.format(
            "INSERT IGNORE INTO item_instance (guid, itemEntry, owner_guid, count, flags) "
            .. "VALUES (%d, %d, 0, %d, 0)",
            guid, entry, stackSize
        ))

        -- Insert auction listing (itemowner = 0 → bot-seeded marker)
        CharDBExecute(string.format(
            "INSERT IGNORE INTO auctionhouse "
            .. "(id, houseid, itemguid, itemowner, buyoutprice, time, buyguid, lastbid, startbid, deposit) "
            .. "VALUES (%d, %d, %d, 0, %d, %d, 0, 0, %d, %d)",
            auctId, houseId, guid, buyout, expireTime, bid, math.floor(buyout * 0.05)
        ))

        inserted = inserted + 1
    end

    return inserted
end

-- Remove all bot-seeded AH listings (itemowner = 0).
local function clearBotAH()
    -- Remove item instances linked to bot AH listings
    CharDBExecute(
        "DELETE ii FROM item_instance ii "
        .. "JOIN auctionhouse ah ON ah.itemguid = ii.guid "
        .. "WHERE ah.itemowner = 0"
    )
    -- Remove the auction rows
    CharDBExecute("DELETE FROM auctionhouse WHERE itemowner = 0")
end

-- ─────────────────────────────────────────────────────────────────────────────
-- .botworld command handler
-- ─────────────────────────────────────────────────────────────────────────────

local function onBotWorldCommand(event, player, command)
    -- Only intercept ".botworld" commands
    if not command:lower():find("^botworld") then
        return false
    end

    -- Must be a GM (security level 1+)
    if player:GetGMLevel() < 1 then
        err(player, "You must be a GM to use .botworld commands.")
        return true  -- consumed
    end

    local parts = {}
    for part in command:gmatch("%S+") do
        table.insert(parts, part:lower())
    end

    local sub = parts[2] or "help"

    -- ── .botworld status ─────────────────────────────────────────────────────
    if sub == "status" then
        local wandering  = countWanderingBots()
        local playerbots = countPlayerbots()
        local ahListings = countBotAHListings()

        msg(player, "═══════════ Bot World Status ═══════════")
        msg(player, string.format("  Wandering NpcBots  : %d", wandering))
        msg(player, string.format("  Playerbot accounts : %d", playerbots))
        msg(player, string.format("  AH bot listings    : %d (bot-seeded)", ahListings))
        msg(player, "Use  .botworld help  for available commands.")
        return true

    -- ── .botworld ahpopulate [count] [faction] ────────────────────────────
    elseif sub == "ahpopulate" then
        local count   = tonumber(parts[3]) or 20
        local faction = parts[4] or "neutral"

        local houseId = AH_HOUSE[faction]
        if not houseId then
            err(player, "Unknown faction '" .. (parts[4] or "") .. "'.  Use: alliance | horde | neutral")
            return true
        end

        msg(player, string.format("Seeding %d items into the %s AH…", count, faction))
        local inserted = populateAH(player, houseId, count)
        msg(player, string.format("✅ Inserted %d listings.  Relog or reload AH to see them.", inserted))
        return true

    -- ── .botworld ahclear ─────────────────────────────────────────────────
    elseif sub == "ahclear" then
        msg(player, "Removing all bot-seeded AH listings…")
        clearBotAH()
        msg(player, "✅ Bot AH listings cleared.")
        return true

    -- ── .botworld help ────────────────────────────────────────────────────
    else
        msg(player, "═════════ BotWorld Commands ═════════")
        msg(player, "  .botworld status")
        msg(player, "      Show wandering bot + AH listing counts")
        msg(player, "  .botworld ahpopulate [count] [faction]")
        msg(player, "      Seed AH with items.  faction: alliance | horde | neutral")
        msg(player, "      Default: 20 items, neutral AH")
        msg(player, "  .botworld ahclear")
        msg(player, "      Remove all bot-seeded AH listings")
        msg(player, "  .botworld help")
        msg(player, "      Show this message")
        return true
    end
end

-- Register the player command hook
-- PLAYER_EVENT_ON_COMMAND = 42
RegisterPlayerEvent(42, onBotWorldCommand)
