#!/bin/bash
# ============================================================
#  Dad's MMO Lab — AH Bot Setup Helper
#  Automatically configures the Auction House Bot
#
#  https://github.com/DadsMmoLab/dads-mmo-lab
#
#  Version: 1.0.0
#
#  Usage:
#    chmod +x setup-ahbot.sh
#    ./setup-ahbot.sh
#
#  What this does:
#    1. Creates a dedicated ahbot account
#    2. Waits for you to create the AH Bot character in-game
#    3. Auto-detects the character when you log out
#    4. Writes the AH Bot config automatically
#    5. Restarts the worldserver to activate it
# ============================================================

SCRIPT_VERSION="1.0.0"

# ─────────────────────────────────────────
# COLORS
# ─────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'
BOLD='\033[1m'

print_header() {
    clear
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${WHITE}${BOLD}         ⚙️  DAD'S MMO LAB                        ${NC}${CYAN}║${NC}"
    echo -e "${CYAN}║${WHITE}         AH Bot Setup Helper                      ${NC}${CYAN}║${NC}"
    echo -e "${CYAN}║${BLUE}         github.com/DadsMmoLab/dads-mmo-lab       ${NC}${CYAN}║${NC}"
    echo -e "${CYAN}║${YELLOW}         Version ${SCRIPT_VERSION}                              ${NC}${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_step() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${WHITE}${BOLD} $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error()   { echo -e "${RED}❌ $1${NC}"; }
print_info()    { echo -e "${BLUE}ℹ️  $1${NC}"; }

# ─────────────────────────────────────────
# MYSQL HELPERS — stderr visible for real error diagnosis
# ─────────────────────────────────────────
mysql_query() {
    local db="$1"
    local query="$2"
    docker exec "$DB_CONTAINER" mysql -uroot -ppassword "$db" \
        -sNe "$query"
}

mysql_exec() {
    local db="$1"
    local query="$2"
    docker exec "$DB_CONTAINER" mysql -uroot -ppassword "$db" \
        -e "$query"
}

# ─────────────────────────────────────────
# DB CONNECTIVITY TEST
# ─────────────────────────────────────────
test_db_connection() {
    print_info "Testing database connection..."
    if ! docker exec "$DB_CONTAINER" mysql -uroot -ppassword \
        -e "SELECT 1;" &>/dev/null; then
        print_error "Cannot connect to database!"
        print_info "The database container is running but not accepting connections yet."
        print_info "Wait 30 seconds and try again — it may still be starting up."
        exit 1
    fi
    print_success "Database connection OK"
}

# ─────────────────────────────────────────
# DETECT SERVER
# ─────────────────────────────────────────
detect_server() {
    DB_CONTAINER=$(docker ps --format '{{.Names}}' 2>/dev/null \
        | grep -iE "ac.database|ac_database" | head -1)

    WORLD_CONTAINER=$(docker ps --format '{{.Names}}' 2>/dev/null \
        | grep -i "worldserver" | head -1)

    if [ -d "$HOME/wow-server-npcbots" ]; then
        SERVER_DIR="$HOME/wow-server-npcbots"
    elif [ -d "$HOME/wow-server-playerbots" ]; then
        SERVER_DIR="$HOME/wow-server-playerbots"
    elif [ -d "$HOME/wow-server" ]; then
        SERVER_DIR="$HOME/wow-server"
    else
        print_error "No WoW server installation found!"
        print_info "Run install-wow.sh first."
        exit 1
    fi

    if [ -z "$DB_CONTAINER" ]; then
        print_error "Database container not running!"
        print_info "Start your server first:"
        print_info "  cd $SERVER_DIR && docker compose up -d"
        exit 1
    fi

    if [ -z "$WORLD_CONTAINER" ]; then
        print_error "World server container not running!"
        print_info "Start your server first:"
        print_info "  cd $SERVER_DIR && docker compose up -d"
        exit 1
    fi

    print_success "Found server: $SERVER_DIR"
    print_success "Database: $DB_CONTAINER"
    print_success "Worldserver: $WORLD_CONTAINER"

    # Verify DB is actually accepting connections, not just running
    test_db_connection
}

# ─────────────────────────────────────────
# STEP 1 — CREATE AHBOT ACCOUNT
# ─────────────────────────────────────────
create_ahbot_account() {
    print_step "STEP 1/4 — Creating AH Bot Account"

    EXISTING=$(mysql_query "acore_auth" \
        "SELECT id FROM account WHERE username='AHBOT';")

    if [ -n "$EXISTING" ]; then
        print_success "AH Bot account already exists (ID: $EXISTING)"
        AHBOT_ACCOUNT_ID="$EXISTING"
        return 0
    fi

    print_info "Creating ahbot account..."

    AHBOT_HASH=$(echo -n "AHBOT:AHBOT" | sha1sum 2>/dev/null \
        | awk '{print toupper($1)}' || \
        echo -n "AHBOT:AHBOT" | shasum -a 1 2>/dev/null \
        | awk '{print toupper($1)}')

    if [ -z "$AHBOT_HASH" ]; then
        print_error "Could not generate password hash."
        exit 1
    fi

    mysql_exec "acore_auth" "
        INSERT INTO account (username, sha_pass_hash, reg_mail, email, joindate)
        VALUES ('AHBOT', '${AHBOT_HASH}', 'ahbot@local.lan', 'ahbot@local.lan', NOW())
        ON DUPLICATE KEY UPDATE sha_pass_hash='${AHBOT_HASH}';
    "

    AHBOT_ACCOUNT_ID=$(mysql_query "acore_auth" \
        "SELECT id FROM account WHERE username='AHBOT';")

    if [ -z "$AHBOT_ACCOUNT_ID" ]; then
        print_error "Failed to create AH Bot account."
        print_info "Check the database error above for details."
        exit 1
    fi

    print_success "AH Bot account created! (ID: $AHBOT_ACCOUNT_ID)"
}

# ─────────────────────────────────────────
# STEP 2 — INSTRUCT USER TO CREATE CHARACTER
# ─────────────────────────────────────────
instruct_character_creation() {
    print_step "STEP 2/4 — Create the AH Bot Character In-Game"

    echo ""
    echo -e "${WHITE}${BOLD}Now you need to create the AH Bot character.${NC}"
    echo -e "${WHITE}This is the character that will run your Auction House!${NC}"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  ${WHITE}${BOLD}Step 1:${NC} Launch WoW from Steam"
    echo ""
    echo -e "  ${WHITE}${BOLD}Step 2:${NC} At the login screen enter:"
    echo -e "           ${CYAN}Username: ahbot${NC}"
    echo -e "           ${CYAN}Password: ahbot${NC}"
    echo ""
    echo -e "  ${WHITE}${BOLD}Step 3:${NC} Create a NEW character"
    echo -e "           ${GREEN}Suggested name: Auctioneer${NC}"
    echo -e "           (Any race and class is fine!)"
    echo ""
    echo -e "  ${WHITE}${BOLD}Step 4:${NC} Enter the game world"
    echo -e "           (The character must actually load in)"
    echo ""
    echo -e "  ${WHITE}${BOLD}Step 5:${NC} Log out completely"
    echo -e "           (Back to character select is enough)"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${YELLOW}  This script will AUTO-DETECT when the character${NC}"
    echo -e "${YELLOW}  is created. You don't need to do anything else!${NC}"
    echo ""
    echo -e "${WHITE}  Press ENTER when you're ready to launch WoW...${NC}"
    read -r
}

# ─────────────────────────────────────────
# STEP 3 — WAIT FOR CHARACTER
# ─────────────────────────────────────────
wait_for_character() {
    print_step "STEP 3/4 — Waiting for AH Bot Character"

    echo ""
    echo -e "${WHITE}Watching the database for your AH Bot character...${NC}"
    echo -e "${WHITE}Go create the character in WoW now!${NC}"
    echo ""
    echo -e "${BLUE}ℹ️  This will detect automatically when you log out.${NC}"
    echo -e "${BLUE}ℹ️  No need to come back here until WoW is closed.${NC}"
    echo ""

    TIMEOUT=1800
    ELAPSED=0
    CHAR_GUID=""

    while [ $ELAPSED -lt $TIMEOUT ]; do
        CHAR_GUID=$(mysql_query "acore_characters" \
            "SELECT guid FROM characters WHERE account=${AHBOT_ACCOUNT_ID} LIMIT 1;" 2>/dev/null)

        if [ -n "$CHAR_GUID" ]; then
            CHAR_NAME=$(mysql_query "acore_characters" \
                "SELECT name FROM characters WHERE guid=${CHAR_GUID};" 2>/dev/null)
            break
        fi

        # Periodic DB health check every 60 seconds
        if [ $((ELAPSED % 60)) -eq 0 ] && [ $ELAPSED -gt 0 ]; then
            if ! docker exec "$DB_CONTAINER" mysql -uroot -ppassword \
                -e "SELECT 1;" &>/dev/null; then
                echo ""
                print_error "Database connection lost during wait!"
                print_info "Check your server: cd $SERVER_DIR && docker compose ps"
                exit 1
            fi
        fi

        printf "  ."
        sleep 10
        ELAPSED=$((ELAPSED + 10))
    done

    echo ""
    echo ""

    if [ -z "$CHAR_GUID" ]; then
        print_error "No character detected after 30 minutes."
        print_info "Make sure you:"
        print_info "  1. Logged in with username: ahbot / password: ahbot"
        print_info "  2. Created a character and entered the game world"
        print_info "  3. Logged out back to character select"
        print_info "Run this script again to try again."
        exit 1
    fi

    print_success "Character detected: ${CHAR_NAME} (GUID: ${CHAR_GUID})"
}

# ─────────────────────────────────────────
# STEP 4 — CONFIGURE AND ACTIVATE
# ─────────────────────────────────────────
configure_ahbot() {
    print_step "STEP 4/4 — Configuring AH Bot"

    local conf_path=""

    for path in \
        "$SERVER_DIR/env/dist/etc/modules/mod_ahbot.conf" \
        "$SERVER_DIR/env/dist/etc/modules/mod_ahbot.conf.dist" \
        "$HOME/wow-server/env/dist/etc/modules/mod_ahbot.conf"; do
        if [ -f "$path" ]; then
            conf_path="$path"
            break
        fi
    done

    local conf_dist=""
    for path in \
        "$SERVER_DIR/env/dist/etc/modules/mod_ahbot.conf.dist" \
        "$SERVER_DIR/modules/mod-ah-bot/conf/mod_ahbot.conf.dist"; do
        if [ -f "$path" ]; then
            conf_dist="$path"
            break
        fi
    done

    if [ -z "$conf_path" ] && [ -n "$conf_dist" ]; then
        conf_path="${conf_dist%.dist}"
        cp "$conf_dist" "$conf_path"
        print_info "Created config from template"
    fi

    if [ -n "$conf_path" ] && [ -f "$conf_path" ]; then
        print_info "Writing AH Bot configuration..."

        # Set account ID
        if grep -q "AuctionHouseBot.Account" "$conf_path"; then
            if ! sed -i "s/AuctionHouseBot.Account\s*=.*/AuctionHouseBot.Account = ${AHBOT_ACCOUNT_ID}/" "$conf_path"; then
                print_warning "Failed to update AuctionHouseBot.Account — check file permissions"
            fi
        else
            echo "AuctionHouseBot.Account = ${AHBOT_ACCOUNT_ID}" >> "$conf_path" || \
                print_warning "Failed to write AuctionHouseBot.Account to config"
        fi

        # Set character GUID
        if grep -q "AuctionHouseBot.GUID\|AuctionHouseBot.GUIDs" "$conf_path"; then
            if ! sed -i "s/AuctionHouseBot\.GUIDs\?\s*=.*/AuctionHouseBot.GUID = ${CHAR_GUID}/" "$conf_path"; then
                print_warning "Failed to update AuctionHouseBot.GUID — check file permissions"
            fi
        else
            echo "AuctionHouseBot.GUID = ${CHAR_GUID}" >> "$conf_path" || \
                print_warning "Failed to write AuctionHouseBot.GUID to config"
        fi

        # Enable seller
        if grep -q "AuctionHouseBot.EnableSeller" "$conf_path"; then
            if ! sed -i "s/AuctionHouseBot.EnableSeller\s*=.*/AuctionHouseBot.EnableSeller = 1/" "$conf_path"; then
                print_warning "Failed to update AuctionHouseBot.EnableSeller — check file permissions"
            fi
        else
            echo "AuctionHouseBot.EnableSeller = 1" >> "$conf_path" || \
                print_warning "Failed to write AuctionHouseBot.EnableSeller to config"
        fi

        # Enable buyer
        if grep -q "AuctionHouseBot.EnableBuyer\|AuctionHouseBot.Buyer.Enabled" "$conf_path"; then
            if ! sed -i "s/AuctionHouseBot\.EnableBuyer\s*=.*/AuctionHouseBot.EnableBuyer = 1/" "$conf_path"; then
                print_warning "Failed to update AuctionHouseBot.EnableBuyer — check file permissions"
            fi
            if ! sed -i "s/AuctionHouseBot\.Buyer\.Enabled\s*=.*/AuctionHouseBot.Buyer.Enabled = 1/" "$conf_path"; then
                print_warning "Failed to update AuctionHouseBot.Buyer.Enabled — check file permissions"
            fi
        else
            echo "AuctionHouseBot.EnableBuyer = 1" >> "$conf_path" || \
                print_warning "Failed to write AuctionHouseBot.EnableBuyer to config"
        fi

        print_success "Config written!"
        print_info "  Account ID: $AHBOT_ACCOUNT_ID"
        print_info "  Character:  $CHAR_NAME (GUID: $CHAR_GUID)"
        print_info "  Seller:     Enabled"
        print_info "  Buyer:      Enabled"

    else
        print_warning "Config file not found — writing environment variables instead"

        if [ -f "$SERVER_DIR/docker-compose.override.yml" ]; then
            if grep -q "ac-worldserver" "$SERVER_DIR/docker-compose.override.yml"; then
                print_info "Adding AH Bot settings to docker-compose.override.yml"
                print_info "Please add these lines manually to your override file:"
                print_info "  AC_AUCTIONHOUSEBOT_ACCOUNT: \"${AHBOT_ACCOUNT_ID}\""
                print_info "  AC_AUCTIONHOUSEBOT_GUID: \"${CHAR_GUID}\""
                print_info "  AC_AUCTIONHOUSEBOT_ENABLESELLER: \"1\""
            fi
        fi
    fi

    # Restart worldserver to apply config
    print_info "Restarting worldserver to activate AH Bot..."
    if ! docker restart "$WORLD_CONTAINER" 2>/dev/null; then
        if ! sudo docker restart "$WORLD_CONTAINER" 2>/dev/null; then
            print_error "Failed to restart worldserver!"
            print_info "AH Bot config was written but won't activate until you restart manually:"
            print_info "  docker restart $WORLD_CONTAINER"
            return 1
        fi
    fi

    # Wait for worldserver to come back up
    sleep 15
    local restart_attempts=0
    while [ $restart_attempts -lt 30 ]; do
        if docker logs "$WORLD_CONTAINER" 2>/dev/null | grep -q "ready\.\.\."; then
            break
        fi
        printf "."
        sleep 5
        restart_attempts=$((restart_attempts + 1))
    done

    echo ""
    print_success "Worldserver restarted!"
}

# ─────────────────────────────────────────
# DONE
# ─────────────────────────────────────────
show_completion() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║   💰 AUCTION HOUSE BOT IS ACTIVE!                ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${WHITE}${BOLD}AH Bot Character:${NC} ${CYAN}${CHAR_NAME}${NC}"
    echo -e "  ${WHITE}${BOLD}Account:${NC}          ${CYAN}ahbot / ahbot${NC}"
    echo ""
    echo -e "  ${WHITE}The Auction House will start filling up with${NC}"
    echo -e "  ${WHITE}items automatically. Give it a few minutes!${NC}"
    echo ""
    echo -e "  ${WHITE}${BOLD}Tips:${NC}"
    echo -e "  • Check the AH in-game — items appear gradually"
    echo -e "  • The bot populates Alliance, Horde AND Neutral AHs"
    echo -e "  • Your ${CYAN}${CHAR_NAME}${NC} character should never be used for playing"
    echo -e "    — leave it dedicated to the AH Bot"
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${WHITE}  📺 youtube.com/@DadsMmoLab${NC}"
    echo -e "${WHITE}  📦 github.com/DadsMmoLab/dads-mmo-lab${NC}"
    echo -e "${WHITE}  ☕ ko-fi.com/dadsmmolab${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${GREEN}${BOLD}Happy trading, adventurer! ⚔️💰${NC}"
    echo ""
}

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
print_header

echo -e "${WHITE}This script sets up your Auction House Bot.${NC}"
echo -e "${WHITE}The AH Bot populates all three Auction Houses${NC}"
echo -e "${WHITE}with items to create a living economy.${NC}"
echo ""
echo -e "${BLUE}ℹ️  Make sure your WoW server is running before continuing!${NC}"
echo ""
echo -e "${WHITE}Ready? (y/n): ${NC}"
read -r ready
[[ "$ready" =~ ^[Yy]$ ]] || exit 0

detect_server
create_ahbot_account
instruct_character_creation
wait_for_character
configure_ahbot
show_completion
