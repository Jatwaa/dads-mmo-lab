#!/bin/bash
# Dad's MMO Lab — Playerbots worldserver entrypoint
set -e

ETC=/azerothcore/env/dist/etc
BIN=/azerothcore/env/dist/bin
LOGDIR=/azerothcore/env/dist/logs

mkdir -p "$LOGDIR" /azerothcore/luascripts

# ── 1. Bootstrap every *.conf.dist → *.conf ──────────────────────────────────
# Covers worldserver.conf AND any module configs in etc/modules/
for dist in "$ETC"/*.conf.dist "$ETC"/modules/*.conf.dist; do
    [ -f "$dist" ] || continue
    conf="${dist%.dist}"
    if [ ! -f "$conf" ]; then
        echo "[entrypoint] bootstrapping $(basename "$conf")"
        cp "$dist" "$conf"
    fi
done

# ── 2. Patch every conf file for known empty-path values ─────────────────────
patch_conf() {
    local f="$1"
    [ -f "$f" ] || return 0

    # Core AzerothCore paths
    sed -i 's|^DataDir[[:space:]]*=.*|DataDir = "/azerothcore/env/dist/data"|'     "$f"
    sed -i 's|^LogsDir[[:space:]]*=.*|LogsDir = "/azerothcore/env/dist/logs"|'     "$f"
    sed -i 's|^ConfigsDir[[:space:]]*=.*|ConfigsDir = "/azerothcore/env/dist/etc"|' "$f"

    # Eluna — canonical("") throws EINVAL
    sed -i 's|^Eluna\.LuaScriptDir[[:space:]]*=.*|Eluna.LuaScriptDir = "/azerothcore/luascripts"|' "$f"

    # PidFile — leave empty intentionally (server skips it when blank)
    # Generic catch-all: any key that ends with Dir or Path whose value is ""
    sed -i 's|^\([A-Za-z._]*[Dd]ir\)[[:space:]]*=[[:space:]]*""|'"\1"' = "/azerothcore/env/dist/data"|' "$f"
    sed -i 's|^\([A-Za-z._]*[Pp]ath\)[[:space:]]*=[[:space:]]*""|'"\1"' = "/azerothcore/env/dist/data"|' "$f"
}

patch_conf "$ETC/worldserver.conf"
for mconf in "$ETC"/modules/*.conf; do
    [ -f "$mconf" ] || continue
    echo "[entrypoint] patching module config: $(basename "$mconf")"
    patch_conf "$mconf"
done

# ── 3. Apply AC_* env var overrides directly via sed ─────────────────────────
# The official run-worldserver.sh does this; we replicate it here so we do
# NOT have to delegate to that script (which would regenerate the conf and
# undo our patches above).
CONF="$ETC/worldserver.conf"
apply_env() {
    local key="$1" val="$2"
    [ -z "$val" ] && return 0
    if grep -q "^${key}[[:space:]]*=" "$CONF" 2>/dev/null; then
        sed -i "s|^${key}[[:space:]]*=.*|${key} = \"${val}\"|" "$CONF"
    else
        echo "${key} = \"${val}\"" >> "$CONF"
    fi
}

apply_env "DataDir"               "${AC_DATA_DIR}"
apply_env "LogsDir"               "${AC_LOGS_DIR}"
apply_env "ConfigsDir"            "${AC_CONFIG_DIR}"
apply_env "LoginDatabaseInfo"     "${AC_LOGIN_DATABASE_INFO}"
apply_env "WorldDatabaseInfo"     "${AC_WORLD_DATABASE_INFO}"
apply_env "CharacterDatabaseInfo" "${AC_CHARACTER_DATABASE_INFO}"
apply_env "Eluna.LuaScriptDir"    "${AC_ELUNA_LUASCRIPTDIR}"

# ── Playerbots module config (lives in etc/modules/playerbots.conf) ───────────
# patch_conf already bootstrapped the .conf from .dist; now apply overrides.
PBCONF="$ETC/modules/playerbots.conf"
pb_apply_env() {
    local key="$1" val="$2"
    [ -z "$val" ] && return 0
    [ ! -f "$PBCONF" ] && return 0
    if grep -q "^${key}[[:space:]]*=" "$PBCONF" 2>/dev/null; then
        sed -i "s|^${key}[[:space:]]*=.*|${key} = \"${val}\"|" "$PBCONF"
    else
        echo "${key} = \"${val}\"" >> "$PBCONF"
    fi
}
pb_apply_env "PlayerbotsDatabaseInfo"          "${AC_PLAYERBOTS_DATABASE_INFO}"

# ── AiPlayerbot settings (live in playerbots.conf, NOT worldserver.conf) ─────
pb_apply_env "AiPlayerbot.Enabled"                "${AC_AIPLAYERBOT_ENABLED}"
pb_apply_env "AiPlayerbot.RandomBotAutologin"     "${AC_AIPLAYERBOT_RANDOMBOTAUTOLOGIN}"
pb_apply_env "AiPlayerbot.MaxRandomBots"          "${AC_AIPLAYERBOT_MAXRANDOMBOTS}"
pb_apply_env "AiPlayerbot.MinRandomBots"          "${AC_AIPLAYERBOT_MINRANDOMBOTS}"
pb_apply_env "AiPlayerbot.RandomBotAllianceRatio" "${AC_AIPLAYERBOT_ALLIANCERATIO}"
pb_apply_env "AiPlayerbot.RandomBotHordeRatio"    "${AC_AIPLAYERBOT_HORDERATIO}"
pb_apply_env "AiPlayerbot.RandomBotMaxLevel"      "${AC_AIPLAYERBOT_RANDOMBOTMAXLEVEL}"
pb_apply_env "AiPlayerbot.RandomBotLoginAtStartup" "${AC_AIPLAYERBOT_LOGINATSTARTUP}"
# Trading = 1 → bots trade / post AH listings / bid on AH items
pb_apply_env "AiPlayerbot.EnableRandomBotTrading" "${AC_AIPLAYERBOT_ENABLERANDOMBOTTRADING}"
# Give bots starting gold so they can buy gear and post AH listings
pb_apply_env "AiPlayerbot.RandomBotStartingGold"  "${AC_AIPLAYERBOT_STARTINGGOLD}"

# ── MySQLExecutable — DBUpdater calls std::filesystem::absolute() on this value;
#    if it is "" the call throws EINVAL and the server crashes immediately after
#    DB pools open.  Point it at the real mysql client we installed in the image.
MYSQL_BIN=$(command -v mysql 2>/dev/null || echo "/usr/bin/mysql")
apply_env "MySQLExecutable" "$MYSQL_BIN"

# ── SourceDirectory — the compiled binary has /acore baked in as the cmake
#    source path.  The DBUpdater checks this directory exists before running;
#    we copied /acore/data/sql and /acore/modules/mod-playerbots into the image
#    so this value is correct as-is, but set it explicitly to be safe.
apply_env "SourceDirectory" "/acore"

# ── 4. Ensure fork-specific DBC tables exist ─────────────────────────────────
# The liyunfan1223 fork added sCharSectionsStore (CharSections.dbc) but did not
# add the corresponding SQL table.  Create it idempotently before the server
# starts so the DBC loader can do SELECT * FROM charsections_dbc without error.
# Connection params come from AC_WORLD_DATABASE_INFO: host;port;user;pass;dbname
_WDBINFO="${AC_WORLD_DATABASE_INFO:-ac-database;3306;root;azeroth;acore_world}"
_DB_HOST=$(echo "$_WDBINFO" | cut -d';' -f1)
_DB_PORT=$(echo "$_WDBINFO" | cut -d';' -f2)
_DB_USER=$(echo "$_WDBINFO" | cut -d';' -f3)
_DB_PASS=$(echo "$_WDBINFO" | cut -d';' -f4)
_DB_NAME=$(echo "$_WDBINFO" | cut -d';' -f5)

# Ensure the playerbots database itself exists (mod-playerbots DBUpdater creates
# the tables on first start, but the database must exist first).
mysql -h "$_DB_HOST" -P "$_DB_PORT" -u "$_DB_USER" -p"$_DB_PASS" \
    --connect-timeout=30 2>/dev/null \
    -e "CREATE DATABASE IF NOT EXISTS acore_playerbots DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
echo "[entrypoint] acore_playerbots database ensured"

mysql -h "$_DB_HOST" -P "$_DB_PORT" -u "$_DB_USER" -p"$_DB_PASS" "$_DB_NAME" \
    --connect-timeout=30 2>/dev/null <<'SQL'
-- CharSections.dbc (format "diiixxxiii" = 10 columns)
-- Added by liyunfan1223 fork but missing from standard db-import schema
CREATE TABLE IF NOT EXISTS `charsections_dbc` (
  `ID`       int NOT NULL DEFAULT '0',
  `Race`     int NOT NULL DEFAULT '0',
  `Gender`   int NOT NULL DEFAULT '0',
  `GenType`  int NOT NULL DEFAULT '0',
  `Field4_1` int NOT NULL DEFAULT '0',
  `Field4_2` int NOT NULL DEFAULT '0',
  `Field4_3` int NOT NULL DEFAULT '0',
  `Flags`    int NOT NULL DEFAULT '0',
  `Type`     int NOT NULL DEFAULT '0',
  `Color`    int NOT NULL DEFAULT '0',
  PRIMARY KEY (`ID`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- EmotesTextSound.dbc (format "niiii" = 5 columns)
-- Present in liyunfan1223 binary but absent from standard db-import schema
CREATE TABLE IF NOT EXISTS `emotetextsound_dbc` (
  `ID`           int unsigned NOT NULL DEFAULT '0',
  `EmotesTextId` int unsigned NOT NULL DEFAULT '0',
  `RaceId`       int unsigned NOT NULL DEFAULT '0',
  `SexId`        int unsigned NOT NULL DEFAULT '0',
  `SoundId`      int unsigned NOT NULL DEFAULT '0',
  PRIMARY KEY (`ID`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
SQL
echo "[entrypoint] fork-specific DBC tables ensured"

# ── 5. Save debug copy + report remaining empty strings ──────────────────────
cp "$CONF" "$LOGDIR/worldserver.conf.debug"
echo "[entrypoint] saved patched config → $LOGDIR/worldserver.conf.debug"

EMPTY=$(grep -nE '=[[:space:]]*""[[:space:]]*$' "$CONF" || true)
if [ -n "$EMPTY" ]; then
    echo "[entrypoint] WARNING: the following config values are still empty strings:"
    echo "$EMPTY"
fi

# ── 5. Start worldserver directly (skip official entrypoint — it regenerates ─
#       the conf from .dist, undoing our patches above)
echo "[entrypoint] starting worldserver"
exec "$BIN/worldserver"
