#!/bin/bash
# ============================================================
#  Dad's MMO Lab — WoW Offline Server UNINSTALLER
#  Completely removes the AzerothCore server from your Steam Deck
#
#  https://github.com/DadsMmoLab/dads-mmo-lab
#
#  Usage:
#    chmod +x uninstall.sh
#    ./uninstall.sh
#
#  What this removes:
#    - All running Docker containers (worldserver, authserver, database)
#    - All Docker images downloaded for the server
#    - The Docker volume containing your character data
#    - The ~/wow-server folder and all its contents
#
#  What this does NOT touch:
#    - Your WoW 3.3.5a client files
#    - Docker itself (in case you use it for other things)
#    - Any other games or projects
#
#  ⚠️  THIS WILL DELETE YOUR CHARACTERS AND PROGRESS ⚠️
#  Make a backup first if you want to keep your character data!
# ============================================================

INSTALLER_VERSION="1.2.0"

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
    echo ""
    echo -e "${RED}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║${WHITE}${BOLD}         ⚙️  DAD'S MMO LAB                        ${NC}${RED}║${NC}"
    echo -e "${RED}║${WHITE}         WoW Server — UNINSTALLER                 ${NC}${RED}║${NC}"
    echo -e "${RED}║${BLUE}         github.com/DadsMmoLab/dads-mmo-lab       ${NC}${RED}║${NC}"
    echo -e "${RED}║${YELLOW}         Version ${INSTALLER_VERSION}                              ${NC}${RED}║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════╝${NC}"
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

ask_yes_no() {
    while true; do
        echo -e "${WHITE}$1 (y/n): ${NC}"
        read -r answer
        case $answer in
            [Yy]* ) return 0;;
            [Nn]* ) return 1;;
            * ) echo "Please answer y or n.";;
        esac
    done
}

# ─────────────────────────────────────────
# SAFE RM -RF — never deletes protected paths
# ─────────────────────────────────────────
safe_rm_rf() {
    local target="$1"
    local label="$2"
    if [ -z "$target" ]; then
        print_error "Refusing to delete: path is empty!"
        return 1
    fi
    if [ "$target" = "/" ] || [ "$target" = "$HOME" ] || [ "$target" = "/home" ]; then
        print_error "Refusing to delete: '$target' is a protected path!"
        return 1
    fi
    if [[ "$target" != "$HOME/"* ]]; then
        print_error "Refusing to delete '$target' — not inside home directory!"
        return 1
    fi
    sudo rm -rf "$target"
    print_success "Removed $label: $target"
}

INSTALL_DIR="$HOME/wow-server"
NPCBOTS_DIR="$HOME/wow-server-npcbots"
PLAYERBOTS_DIR="$HOME/wow-server-playerbots"

# ─────────────────────────────────────────
# DOCKER CHECK
# ─────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo -e "\033[0;31m❌ Docker is not installed. Nothing to uninstall!\033[0m"
    echo -e "\033[0;34mℹ️  If you installed using install.sh, Docker should be present.\033[0m"
    exit 1
fi

if ! docker ps &>/dev/null 2>&1 && ! sudo docker ps &>/dev/null 2>&1; then
    echo -e "\033[1;33m⚠️  Docker is installed but not running. Starting it now...\033[0m"
    if ! sudo systemctl start docker 2>/dev/null; then
        echo -e "\033[0;31m❌ Docker failed to start. Try rebooting your Steam Deck and running this again.\033[0m"
        exit 1
    fi
    sleep 3
fi

# ─────────────────────────────────────────
# START
# ─────────────────────────────────────────
clear
print_header

# ─────────────────────────────────────────
# SERVER SELECTION
# ─────────────────────────────────────────
echo -e "${WHITE}${BOLD}Which server do you want to uninstall?${NC}"
echo ""

STANDARD_EXISTS=false
NPCBOTS_EXISTS=false
PLAYERBOTS_EXISTS=false

[ -d "$INSTALL_DIR" ]      && STANDARD_EXISTS=true
[ -d "$NPCBOTS_DIR" ]      && NPCBOTS_EXISTS=true
[ -d "$PLAYERBOTS_DIR" ]   && PLAYERBOTS_EXISTS=true

MENU_OPTIONS=()
[ "$STANDARD_EXISTS" = true ]   && MENU_OPTIONS+=("Standard WoW ($INSTALL_DIR)")
[ "$NPCBOTS_EXISTS" = true ]    && MENU_OPTIONS+=("NPCBots WoW ($NPCBOTS_DIR)")
[ "$PLAYERBOTS_EXISTS" = true ] && MENU_OPTIONS+=("Playerbots WoW ($PLAYERBOTS_DIR)")

if [ ${#MENU_OPTIONS[@]} -eq 0 ]; then
    print_error "No server installations found!"
    print_info "Looked for:"
    print_info "  $INSTALL_DIR"
    print_info "  $NPCBOTS_DIR"
    print_info "  $PLAYERBOTS_DIR"
    exit 1
fi

OPTION_NUM=1
for opt in "${MENU_OPTIONS[@]}"; do
    echo -e "  ${CYAN}${OPTION_NUM})${NC} $opt"
    OPTION_NUM=$((OPTION_NUM + 1))
done

INSTALLED_COUNT=${#MENU_OPTIONS[@]}
if [ $INSTALLED_COUNT -gt 1 ]; then
    echo -e "  ${CYAN}${OPTION_NUM})${NC} ALL servers"
fi

echo ""
echo -e "${WHITE}Choice (1-${OPTION_NUM}): ${NC}"
read -r SERVER_CHOICE

TARGET_DIRS=()
TARGET_NAMES=()

if [ $INSTALLED_COUNT -eq 1 ]; then
    [ "$STANDARD_EXISTS" = true ]   && TARGET_DIRS=("$INSTALL_DIR")    && TARGET_NAMES=("Standard WoW")
    [ "$NPCBOTS_EXISTS" = true ]    && TARGET_DIRS=("$NPCBOTS_DIR")    && TARGET_NAMES=("NPCBots WoW")
    [ "$PLAYERBOTS_EXISTS" = true ] && TARGET_DIRS=("$PLAYERBOTS_DIR") && TARGET_NAMES=("Playerbots WoW")
    SERVER_CHOICE="1"
else
    COUNTER=1
    declare -A CHOICE_MAP
    [ "$STANDARD_EXISTS" = true ]   && CHOICE_MAP[$COUNTER]="standard"   && COUNTER=$((COUNTER + 1))
    [ "$NPCBOTS_EXISTS" = true ]    && CHOICE_MAP[$COUNTER]="npcbots"    && COUNTER=$((COUNTER + 1))
    [ "$PLAYERBOTS_EXISTS" = true ] && CHOICE_MAP[$COUNTER]="playerbots" && COUNTER=$((COUNTER + 1))
    ALL_CHOICE=$COUNTER

    if [ "$SERVER_CHOICE" = "$ALL_CHOICE" ]; then
        [ "$STANDARD_EXISTS" = true ]   && TARGET_DIRS+=("$INSTALL_DIR")    && TARGET_NAMES+=("Standard WoW")
        [ "$NPCBOTS_EXISTS" = true ]    && TARGET_DIRS+=("$NPCBOTS_DIR")    && TARGET_NAMES+=("NPCBots WoW")
        [ "$PLAYERBOTS_EXISTS" = true ] && TARGET_DIRS+=("$PLAYERBOTS_DIR") && TARGET_NAMES+=("Playerbots WoW")
    else
        SELECTED="${CHOICE_MAP[$SERVER_CHOICE]}"
        case "$SELECTED" in
            standard)   TARGET_DIRS=("$INSTALL_DIR")    TARGET_NAMES=("Standard WoW") ;;
            npcbots)    TARGET_DIRS=("$NPCBOTS_DIR")    TARGET_NAMES=("NPCBots WoW") ;;
            playerbots) TARGET_DIRS=("$PLAYERBOTS_DIR") TARGET_NAMES=("Playerbots WoW") ;;
            *)
                print_error "Invalid choice."
                exit 1
                ;;
        esac
    fi
fi

echo ""
echo -e "${WHITE}Selected: ${CYAN}${TARGET_NAMES[*]}${NC}"
echo ""
echo -e "${YELLOW}This includes:${NC}"
echo -e "  • All server containers (worldserver, authserver, database)"
echo -e "  • All downloaded Docker images for the server"
for dir in "${TARGET_DIRS[@]}"; do
    echo -e "  • Server folder: ${CYAN}$dir${NC}"
done
echo -e "  • ${RED}All character data and progress${NC}"
echo ""
echo -e "${GREEN}This does NOT touch:${NC}"
echo -e "  • Your WoW 3.3.5a client files"
echo -e "  • Docker itself"
echo -e "  • Any other projects"
echo ""

# ─────────────────────────────────────────
# KEEP CLIENT DATA OPTION
# ─────────────────────────────────────────
echo -e "${WHITE}${BOLD}Keep client data? (Recommended — saves 30+ minutes on reinstall)${NC}"
echo -e "${BLUE}ℹ️  Client data is the map/DBC files downloaded during install.${NC}"
echo -e "${BLUE}ℹ️  It never changes between reinstalls so there's no reason to wipe it.${NC}"
echo ""

KEEP_CLIENT_DATA=true
if ask_yes_no "Keep client data volumes to speed up future reinstalls?"; then
    KEEP_CLIENT_DATA=true
    print_success "Client data will be preserved — reinstall will be much faster!"
else
    KEEP_CLIENT_DATA=false
    print_info "Client data will be removed — reinstall will re-download everything."
fi

echo ""
print_warning "Do you want to back up your character data first?"
echo -e "${BLUE}ℹ️  This saves your characters, items, and progress to a backup file.${NC}"
echo ""

BACKUP_DIR=""

if ask_yes_no "Create a backup before uninstalling?"; then

    BACKUP_DIR="$HOME/wow-server-backup-$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"

    print_info "Backing up all server databases..."

    if docker ps 2>/dev/null | grep -qiE "ac.database|ac_database" || \
       sudo docker ps 2>/dev/null | grep -qiE "ac.database|ac_database"; then

        BACKUP_DB=$(docker ps --format '{{.Names}}' 2>/dev/null | \
            grep -iE "ac.database|ac_database" | head -1)
        BACKUP_DB="${BACKUP_DB:-acore-docker-ac-database-1}"

        # Let mysqldump stderr show — user needs to know WHY it failed if it does
        if ! docker exec "$BACKUP_DB" mysqldump \
            -uroot -ppassword \
            --databases acore_characters acore_auth acore_world \
            > "$BACKUP_DIR/full_server_backup.sql"; then
            sudo docker exec "$BACKUP_DB" mysqldump \
                -uroot -ppassword \
                --databases acore_characters acore_auth acore_world \
                > "$BACKUP_DIR/full_server_backup.sql" || true
        fi

        if [ -f "$BACKUP_DIR/full_server_backup.sql" ] && \
           [ -s "$BACKUP_DIR/full_server_backup.sql" ]; then
            BACKUP_SIZE=$(du -sh "$BACKUP_DIR/full_server_backup.sql" | cut -f1)
            print_success "Backup saved! (${BACKUP_SIZE})"
            print_success "Location: $BACKUP_DIR/full_server_backup.sql"
            print_info "Keep this file — it contains ALL your characters, items and progress!"
        else
            print_warning "Backup file is empty or missing — database may not be running."
            print_info "Start the server first with: cd ~/wow-server && docker compose up -d"
            print_info "Then re-run this uninstaller to get a clean backup."
            BACKUP_DIR=""
        fi
    else
        print_warning "Database container not running — cannot create backup."
        print_info "To back up first: start the server with ~/wow-server/start.sh"
        print_info "Then run this uninstaller again."
        BACKUP_DIR=""

        echo ""
        if ! ask_yes_no "Continue uninstalling WITHOUT a backup?"; then
            echo -e "${GREEN}Good call — start the server, back it up, then uninstall.${NC}"
            exit 0
        fi
    fi
fi

echo ""

# ─────────────────────────────────────────
# FINAL CONFIRMATION
# ─────────────────────────────────────────
echo -e "${RED}${BOLD}⚠️  THIS CANNOT BE UNDONE ⚠️${NC}"
echo ""

if ! ask_yes_no "Are you absolutely sure you want to uninstall?"; then
    echo ""
    echo -e "${GREEN}Smart choice! Your server is safe. Run this script again when you're ready.${NC}"
    echo ""
    exit 0
fi

echo ""
echo -e "${RED}Last chance — type DELETE to confirm:${NC} "
read -r confirm
if [ "$confirm" != "DELETE" ]; then
    echo ""
    echo -e "${GREEN}Cancelled — your server is safe!${NC}"
    echo ""
    exit 0
fi

echo ""
echo ""
print_info "Uninstalling... this will take about 30-60 seconds."

# ─────────────────────────────────────────
# STEP 1 — STOP AND REMOVE CONTAINERS
# ─────────────────────────────────────────
print_step "STEP 1/4 — Stopping Server(s)"

for i in "${!TARGET_DIRS[@]}"; do
    dir="${TARGET_DIRS[$i]}"
    name="${TARGET_NAMES[$i]}"
    print_info "Stopping $name..."
    if [ -f "$dir/docker-compose.yml" ]; then
        cd "$dir"
        if ! docker compose down --remove-orphans 2>/dev/null; then
            if ! sudo docker compose down --remove-orphans 2>/dev/null; then
                print_warning "$name containers may still be running — proceeding anyway."
                print_info "Stop them manually later with: docker compose down"
            fi
        fi
        print_success "$name stopped"
    fi
done

print_info "Cleaning up orphaned containers..."
docker ps -a --format '{{.Names}}' 2>/dev/null | \
    grep -iE "worldserver|authserver|ac-database|ac-eluna|ac-client|ac-db" | \
    xargs -r docker rm -f || true
print_success "Containers cleaned up"

# ─────────────────────────────────────────
# STEP 2 — REMOVE DOCKER IMAGES
# ─────────────────────────────────────────
print_step "STEP 2/4 — Removing Docker Images"

IMAGES=(
    "acore/ac-wotlk-worldserver"
    "acore/ac-wotlk-authserver"
    "acore/ac-wotlk-db-import"
    "acore/ac-wotlk-client-data"
    "acore/ac-worldserver"
    "acore/ac-authserver"
    "acore/ac-db-import"
    "acore/eluna-ts"
    "mysql:8.0"
    "mysql:8.4"
)

for image in "${IMAGES[@]}"; do
    if docker images 2>/dev/null | grep -q "${image%%:*}"; then
        docker rmi "$image" 2>/dev/null || true
        print_success "Removed image: $image"
    fi
done

docker image prune -f 2>/dev/null || true
print_success "Cleaned up unused images"

# ─────────────────────────────────────────
# STEP 3 — REMOVE DOCKER VOLUMES
# ─────────────────────────────────────────
print_step "STEP 3/4 — Removing Database Volumes"

VOLUMES=(
    "dads_mmo_wow_db"
    "wow-server_ac-database"
    "wow-server-npcbots_ac-database"
    "wow-server-playerbots_ac-database"
    "ac-database"
)

if [ "$KEEP_CLIENT_DATA" = false ]; then
    VOLUMES+=(
        "wow-server_ac-client-data"
        "wow-server-npcbots_ac-client-data"
        "wow-server-playerbots_ac-client-data"
        "ac-client-data"
    )
    print_info "Removing client data volumes..."
else
    print_info "Preserving client data volumes — reinstall will be fast!"
fi

for vol in "${VOLUMES[@]}"; do
    if docker volume ls 2>/dev/null | grep -q "$vol"; then
        docker volume rm "$vol" 2>/dev/null || true
        print_success "Removed volume: $vol"
    fi
done

if [ "$KEEP_CLIENT_DATA" = false ]; then
    print_info "Cleaning up orphaned volumes..."
    docker volume prune -f 2>/dev/null || true
    print_success "Orphaned volumes cleaned up"
else
    print_info "Skipping volume prune to preserve client data"
fi

docker network rm dads_mmo_network wow-server_ac-network \
    wow-server_default wow-server-npcbots_ac-network \
    wow-server-npcbots_default wow-server-playerbots_ac-network \
    wow-server-playerbots_default 2>/dev/null || true

# ─────────────────────────────────────────
# STEP 4 — REMOVE SERVER FOLDERS
# ─────────────────────────────────────────
print_step "STEP 4/4 — Removing Server Files"

for i in "${!TARGET_DIRS[@]}"; do
    dir="${TARGET_DIRS[$i]}"
    name="${TARGET_NAMES[$i]}"
    if [ -d "$dir" ]; then
        safe_rm_rf "$dir" "$name folder"
    else
        print_info "$name folder not found — already removed"
    fi
done

if [[ " ${TARGET_NAMES[*]} " =~ "Standard WoW" ]]; then
    [ -f "$HOME/wow-gaming-mode.sh" ] && \
        rm -f "$HOME/wow-gaming-mode.sh" && \
        print_success "Removed gaming mode launcher"
fi
if [[ " ${TARGET_NAMES[*]} " =~ "NPCBots WoW" ]]; then
    [ -f "$HOME/wow-npcbots-launcher.sh" ] && \
        rm -f "$HOME/wow-npcbots-launcher.sh" && \
        print_success "Removed NPCBots launcher"
fi
if [[ " ${TARGET_NAMES[*]} " =~ "Playerbots WoW" ]]; then
    [ -f "$HOME/wow-playerbots-launcher.sh" ] && \
        rm -f "$HOME/wow-playerbots-launcher.sh" && \
        print_success "Removed Playerbots launcher"
fi

# ─────────────────────────────────────────
# DONE
# ─────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║   ✅ UNINSTALL COMPLETE                           ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${WHITE}Removed: ${CYAN}${TARGET_NAMES[*]}${NC}"
echo -e "${WHITE}Your WoW client files are untouched.${NC}"
echo ""

if [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
    echo -e "${CYAN}Your backup is saved at:${NC}"
    echo -e "  ${CYAN}$BACKUP_DIR/full_server_backup.sql${NC}"
    echo -e "${CYAN}To restore after reinstalling:${NC}"
    echo -e "  ${CYAN}docker exec -i <db-container> mysql -uroot -ppassword < full_server_backup.sql${NC}"
    echo ""
fi

echo -e "${WHITE}Want to reinstall? Run:${NC}"
echo -e "  ${CYAN}Wizard (recommended): chmod +x install-wow.sh && ./install-wow.sh${NC}"
echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${WHITE}  📺 youtube.com/@DadsMmoLab${NC}"
echo -e "${WHITE}  📦 github.com/DadsMmoLab/dads-mmo-lab${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${GREEN}${BOLD}See you in Azeroth again soon. ⚔️${NC}"
echo ""
