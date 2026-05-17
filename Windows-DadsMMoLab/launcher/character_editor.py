"""
Character editor — reads and writes player characters from acore_characters.
Queries run via docker exec on ac_database (no extra ports needed).

Editable fields: level, money (stored as copper), current XP, rested XP bonus.
All other stats are recalculated by the server on login and are read-only here.
"""
import re
import subprocess
from dataclasses import dataclass
from typing import Tuple

import log_handler as log

DB_CONTAINER = "ac_database"
MYSQL_USER   = "root"
MYSQL_PASS   = "azeroth"
CHAR_DB      = "acore_characters"

MAX_LEVEL = 80

RACE_NAMES = {
    1: "Human",      2: "Orc",        3: "Dwarf",      4: "Night Elf",
    5: "Undead",     6: "Tauren",     7: "Gnome",      8: "Troll",
    10: "Blood Elf", 11: "Draenei",
}

CLASS_NAMES = {
    1: "Warrior",      2: "Paladin",  3: "Hunter",  4: "Rogue",
    5: "Priest",       6: "Death Knight", 7: "Shaman", 8: "Mage",
    9: "Warlock",      11: "Druid",
}

CLASS_ICONS = {
    1: "⚔", 2: "🛡", 3: "🏹", 4: "🗡", 5: "✨",
    6: "💀", 7: "⚡", 8: "🔥", 9: "🔮", 11: "🌿",
}

# Faction by race
RACE_FACTION = {
    1: "Alliance", 3: "Alliance", 4: "Alliance", 7: "Alliance", 11: "Alliance",
    2: "Horde",    5: "Horde",    6: "Horde",    8: "Horde",    10: "Horde",
}

FACTION_COLOR = {"Alliance": "#4080c0", "Horde": "#c04040", "Unknown": "#808080"}

GM_LEVEL_LABELS = {
    0: "Player",
    1: "Moderator",
    2: "GM",
    3: "Admin",
    4: "Console",
}

# Ordered list for the UI dropdown  (label → int)
GM_LEVEL_OPTIONS = [
    ("Player (0)",     0),
    ("Moderator (1)",  1),
    ("GM (2)",         2),
    ("Admin (3)",      3),
    ("Console (4)",    4),
]


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Character:
    guid:         int
    account_id:   int
    account_name: str
    name:         str
    race:         int
    cls:          int    # 'class' is a Python keyword
    gender:       int
    level:        int
    xp:           int
    money:        int    # copper
    health:       int
    max_health:   int
    online:       bool
    total_time:   int    # seconds
    logout_time:  int    # unix timestamp (0 if never logged out)
    map_id:       int
    zone:         int
    pos_x:        float
    pos_y:        float
    pos_z:        float
    rest_bonus:   float
    gm_level:     int    # from account_access.gmlevel (0 = player)

    # ── derived helpers ───────────────────────────────────────────────────────

    @property
    def gm_label(self) -> str:
        return GM_LEVEL_LABELS.get(self.gm_level, f"Level {self.gm_level}")

    @property
    def race_name(self) -> str:
        return RACE_NAMES.get(self.race, f"Race {self.race}")

    @property
    def class_name(self) -> str:
        return CLASS_NAMES.get(self.cls, f"Class {self.cls}")

    @property
    def class_icon(self) -> str:
        return CLASS_ICONS.get(self.cls, "⚔")

    @property
    def faction(self) -> str:
        return RACE_FACTION.get(self.race, "Unknown")

    @property
    def gold(self) -> int:
        return self.money // 10000

    @property
    def silver(self) -> int:
        return (self.money % 10000) // 100

    @property
    def copper_remainder(self) -> int:
        return self.money % 100

    @property
    def play_time_str(self) -> str:
        h = self.total_time // 3600
        m = (self.total_time % 3600) // 60
        return f"{h}h {m}m"

    @property
    def last_seen_str(self) -> str:
        if self.online:
            return "Online now"
        if not self.logout_time:
            return "Never logged in"
        from datetime import datetime
        try:
            return datetime.fromtimestamp(self.logout_time).strftime("%b %d, %Y %I:%M %p")
        except (OSError, OverflowError):
            return str(self.logout_time)


@dataclass
class CharacterStats:
    maxhealth:           int
    maxpower1:           int    # mana
    maxpower2:           int    # rage
    maxpower3:           int    # focus
    maxpower4:           int    # energy
    maxpower5:           int    # happiness
    maxpower6:           int    # runic power
    maxpower7:           int    # soul shards
    strength:            int
    agility:             int
    stamina:             int
    intellect:           int
    spirit:              int
    armor:               int
    res_holy:            int
    res_fire:            int
    res_nature:          int
    res_frost:           int
    res_shadow:          int
    res_arcane:          int
    block_pct:           float
    dodge_pct:           float
    parry_pct:           float
    crit_pct:            float
    ranged_crit_pct:     float
    spell_crit_pct:      float
    attack_power:        int
    ranged_attack_power: int
    spell_power:         int
    resilience:          float

    def primary_power(self, cls: int) -> Tuple[str, int]:
        """Return (label, value) for the main resource of this class."""
        if cls == 1:   return "Rage",         self.maxpower2
        if cls == 4:   return "Energy",        self.maxpower4
        if cls == 6:   return "Runic Power",   self.maxpower6
        return             "Mana",         self.maxpower1


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def list_characters() -> Tuple[bool, object]:
    """
    Return (True, list[Character]) on success,
    or     (False, error_string)   on failure.
    max_health comes from character_stats (a separate cache table) via LEFT JOIN.
    """
    sql = (
        "SELECT c.guid, c.account, "
        "IFNULL(a.username, '?') AS acct_name, "
        "c.name, c.race, c.class, c.gender, c.level, c.xp, c.money, "
        "c.health, IFNULL(cs.maxhealth, 0) AS maxhealth, "
        "c.online, c.totaltime, c.logout_time, "
        "c.map, c.zone, c.position_x, c.position_y, c.position_z, c.rest_bonus, "
        "IFNULL(aa.gmlevel, 0) AS gmlevel "
        "FROM characters c "
        "LEFT JOIN acore_auth.account a ON c.account = a.id "
        "LEFT JOIN character_stats cs ON c.guid = cs.guid "
        "LEFT JOIN acore_auth.account_access aa ON a.id = aa.id AND aa.RealmID = -1 "
        "ORDER BY c.name;"
    )
    ok, output = _mysql(sql)
    if not ok:
        return False, output   # caller displays the real error

    lines = output.strip().splitlines()
    log.log(f"Character editor: query returned {len(lines)} line(s) (including header).", "INFO")

    chars = []
    for line in lines[1:]:   # skip header row
        parts = line.split("\t")
        if len(parts) < 22:
            log.log(f"Character editor: short row ({len(parts)} cols) — {line[:80]}", "WARN")
            continue
        try:
            chars.append(Character(
                guid         = _int(parts[0]),
                account_id   = _int(parts[1]),
                account_name = parts[2].strip(),
                name         = parts[3].strip(),
                race         = _int(parts[4]),
                cls          = _int(parts[5]),
                gender       = _int(parts[6]),
                level        = _int(parts[7]),
                xp           = _int(parts[8]),
                money        = _int(parts[9]),
                health       = _int(parts[10]),
                max_health   = _int(parts[11]),
                online       = parts[12].strip() == "1",
                total_time   = _int(parts[13]),
                logout_time  = _int(parts[14]),
                map_id       = _int(parts[15]),
                zone         = _int(parts[16]),
                pos_x        = _float(parts[17]),
                pos_y        = _float(parts[18]),
                pos_z        = _float(parts[19]),
                rest_bonus   = _float(parts[20]),
                gm_level     = _int(parts[21]),
            ))
        except Exception as exc:
            log.log(f"Character editor: failed to parse row — {exc} | {line[:120]}", "WARN")

    return True, chars


def set_account_gm_level(account_name: str, level: int) -> Tuple[bool, str]:
    """
    Upsert the GM level for the given account in acore_auth.account_access.
    level=0 removes the row (player access).
    Change takes effect on the character's next login.
    """
    uname = account_name.strip().upper()
    if level == 0:
        sql = (
            f"DELETE FROM acore_auth.account_access "
            f"WHERE id = (SELECT id FROM acore_auth.account WHERE username='{uname}') "
            f"AND RealmID = -1;"
        )
        action = "removed"
    else:
        sql = (
            f"INSERT INTO acore_auth.account_access (id, gmlevel, RealmID) "
            f"SELECT id, {level}, -1 FROM acore_auth.account WHERE username='{uname}' "
            f"ON DUPLICATE KEY UPDATE gmlevel={level};"
        )
        action = f"set to {GM_LEVEL_LABELS.get(level, str(level))} ({level})"

    ok, msg = _mysql(sql)
    if ok:
        log.log(f"Character editor: GM level {action} for account {uname}", "INFO")
        return True, f"GM role {action} for '{uname}'. Relog required."
    return False, msg


def set_health_to_max(
    guid: int,
    max_health: int = 0,
    char_class: int = 0,
    char_level: int = 1,
) -> Tuple[bool, str]:
    """
    Set characters.health to the character's max health.

    Resolution order:
      1. max_health argument (caller supplies char.max_health from memory)
      2. Live SELECT from character_stats (populated by server on save cycle)
      3. Base HP from acore_world.player_classlevelstats (always available,
         doesn't include item/talent bonuses but is always a valid number)
    """
    # ── 1. Try the value the caller already knows ─────────────────────────────
    if max_health <= 0:
        ok2, out2 = _mysql(
            f"SELECT maxhealth FROM character_stats WHERE guid={guid};"
        )
        if ok2:
            for line in out2.strip().splitlines()[1:]:
                try:
                    v = int(line.strip())
                    if v > 0:
                        max_health = v
                    break
                except ValueError:
                    pass

    # ── 2. Fall back to world DB base-HP table ────────────────────────────────
    source = "character_stats"
    if max_health <= 0 and char_class > 0:
        ok3, out3 = _mysql(
            f"SELECT basehp FROM acore_world.player_classlevelstats "
            f"WHERE class={char_class} AND level={char_level};"
        )
        if ok3:
            for line in out3.strip().splitlines()[1:]:
                try:
                    v = int(line.strip())
                    if v > 0:
                        max_health = v
                        source = "base stats (no item/talent bonuses)"
                    break
                except ValueError:
                    pass

    if max_health <= 0:
        return False, (
            "Could not determine max health — character_stats is empty and "
            "player_classlevelstats lookup failed. Check logs."
        )

    sql = f"UPDATE characters SET health = {max_health} WHERE guid = {guid};"
    ok, msg = _mysql(sql)
    if not ok:
        return False, msg

    log.log(
        f"Character editor: guid={guid} health set to {max_health} (source: {source})",
        "INFO",
    )
    return True, f"Health set to {max_health:,}." + (
        "  (base HP — server will recalculate full max on next save)" if source != "character_stats" else ""
    )


def save_character(
    guid: int,
    level: int,
    money_copper: int,
    xp: int,
    rest_bonus: float,
) -> Tuple[bool, str]:
    """
    Persist editable fields for one character.
    Returns (success, message).
    """
    if not (1 <= level <= MAX_LEVEL):
        return False, f"Level must be between 1 and {MAX_LEVEL}."
    if money_copper < 0:
        return False, "Money cannot be negative."
    if xp < 0:
        return False, "XP cannot be negative."
    if rest_bonus < 0:
        rest_bonus = 0.0

    sql = (
        f"UPDATE characters SET "
        f"level={level}, money={money_copper}, xp={xp}, rest_bonus={rest_bonus:.4f} "
        f"WHERE guid={guid};"
    )
    ok, msg = _mysql(sql)
    if ok:
        log.log(
            f"Character editor: guid={guid} saved "
            f"(level={level}, money={money_copper}cu, xp={xp}, rest={rest_bonus:.1f})",
            "INFO",
        )
        return True, "Character saved."
    return False, msg


def get_stats(guid: int) -> "Tuple[bool, object]":
    """
    Return (True, CharacterStats) or (False, error_string).
    character_stats is only populated when the character has logged in at least once.
    """
    sql = (
        f"SELECT maxhealth, maxpower1, maxpower2, maxpower3, maxpower4, maxpower5, "
        f"maxpower6, maxpower7, strength, agility, stamina, intellect, spirit, "
        f"armor, resHoly, resFire, resNature, resFrost, resShadow, resArcane, "
        f"blockPct, dodgePct, parryPct, critPct, rangedCritPct, spellCritPct, "
        f"attackPower, rangedAttackPower, spellPower, resilience "
        f"FROM character_stats WHERE guid={guid};"
    )
    ok, output = _mysql(sql)
    if not ok:
        return False, output

    lines = output.strip().splitlines()
    if len(lines) < 2:
        return False, "No stats row found (character may never have logged in)."

    parts = lines[1].split("\t")
    if len(parts) < 30:
        return False, f"Stats row too short ({len(parts)} cols)."

    try:
        cs = CharacterStats(
            maxhealth          = _int(parts[0]),
            maxpower1          = _int(parts[1]),
            maxpower2          = _int(parts[2]),
            maxpower3          = _int(parts[3]),
            maxpower4          = _int(parts[4]),
            maxpower5          = _int(parts[5]),
            maxpower6          = _int(parts[6]),
            maxpower7          = _int(parts[7]),
            strength           = _int(parts[8]),
            agility            = _int(parts[9]),
            stamina            = _int(parts[10]),
            intellect          = _int(parts[11]),
            spirit             = _int(parts[12]),
            armor              = _int(parts[13]),
            res_holy           = _int(parts[14]),
            res_fire           = _int(parts[15]),
            res_nature         = _int(parts[16]),
            res_frost          = _int(parts[17]),
            res_shadow         = _int(parts[18]),
            res_arcane         = _int(parts[19]),
            block_pct          = _float(parts[20]),
            dodge_pct          = _float(parts[21]),
            parry_pct          = _float(parts[22]),
            crit_pct           = _float(parts[23]),
            ranged_crit_pct    = _float(parts[24]),
            spell_crit_pct     = _float(parts[25]),
            attack_power       = _int(parts[26]),
            ranged_attack_power= _int(parts[27]),
            spell_power        = _int(parts[28]),
            resilience         = _float(parts[29]),
        )
        return True, cs
    except Exception as exc:
        return False, str(exc)


def db_reachable() -> bool:
    ok, _ = _mysql("SELECT 1;")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _int(s: str, default: int = 0) -> int:
    s = s.strip()
    return int(s) if s and s.upper() != "NULL" else default


def _float(s: str, default: float = 0.0) -> float:
    s = s.strip()
    return float(s) if s and s.upper() != "NULL" else default


def _mysql(sql: str) -> Tuple[bool, str]:
    try:
        r = subprocess.run(
            [
                "docker", "exec", DB_CONTAINER,
                "mysql",
                f"-u{MYSQL_USER}",
                f"-p{MYSQL_PASS}",
                "--batch",          # tab-separated, always outputs column headers
                CHAR_DB,
                "-e", sql,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if r.returncode == 0:
            return True, r.stdout
        err = (r.stderr or r.stdout).strip()
        err = re.sub(r"mysql: \[Warning\].*\n?", "", err).strip()
        return False, err or f"mysql exited {r.returncode}"
    except FileNotFoundError:
        return False, "docker not found"
    except subprocess.TimeoutExpired:
        return False, "DB query timed out — is the server running?"
    except Exception as exc:
        return False, str(exc)
