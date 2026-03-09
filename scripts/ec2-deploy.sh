#!/bin/bash
# PropEdge v2 - EC2 Deploy Script
# Run this on the EC2 instance to set up and deploy PropEdge
#
# First-time setup:  ./ec2-deploy.sh setup
# Deploy / update:   ./ec2-deploy.sh deploy
# Quick restart:     ./ec2-deploy.sh restart
# View logs:         ./ec2-deploy.sh logs
# Status:            ./ec2-deploy.sh status

set -e

# Configuration
APP_DIR="/opt/propedge"
REPO_URL="https://github.com/growmysale/plasmatradinghub.git"
BRANCH="main"
CONTAINER_NAME="propedge-backend"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[PropEdge]${NC} $1"; }
warn() { echo -e "${YELLOW}[PropEdge]${NC} $1"; }
err() { echo -e "${RED}[PropEdge]${NC} $1"; }

case "${1:-help}" in

setup)
    log "=== PropEdge EC2 First-Time Setup ==="

    # Install Docker if not present
    if ! command -v docker &> /dev/null; then
        log "Installing Docker..."
        sudo yum update -y
        sudo yum install -y docker git
        sudo systemctl start docker
        sudo systemctl enable docker
        sudo usermod -aG docker $USER
        warn "Docker installed. You MUST log out and back in for group changes."
        warn "Then run: ./ec2-deploy.sh setup   (again to continue)"
        exit 0
    fi

    # Install Docker Compose plugin if not present
    if ! docker compose version &> /dev/null; then
        log "Installing Docker Compose..."
        sudo mkdir -p /usr/local/lib/docker/cli-plugins/
        sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
            -o /usr/local/lib/docker/cli-plugins/docker-compose
        sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
        log "Docker Compose installed: $(docker compose version)"
    fi

    # Create app directory
    sudo mkdir -p $APP_DIR/data/{duckdb,sqlite,models,logs}
    sudo chown -R $USER:$USER $APP_DIR

    # Clone repo
    if [ ! -d "$APP_DIR/src" ]; then
        log "Cloning PropEdge repository..."
        git clone $REPO_URL $APP_DIR/src
    else
        log "Repository already exists, pulling latest..."
        cd $APP_DIR/src && git pull origin $BRANCH
    fi

    # Create production .env
    if [ ! -f "$APP_DIR/src/.env" ]; then
        log "Creating production .env..."
        cat > $APP_DIR/src/.env <<'ENVEOF'
PROPEDGE_ENV=production
API_HOST=0.0.0.0
API_PORT=8000
PROPEDGE_DATA_DIR=/data
PROPEDGE_CONFIG=/app/configs/default.yaml
ENVEOF
    fi

    log "=== Setup complete! Run: ./ec2-deploy.sh deploy ==="
    ;;

deploy)
    log "=== Deploying PropEdge ==="

    if [ ! -d "$APP_DIR/src" ]; then
        err "Repository not found. Run: ./ec2-deploy.sh setup"
        exit 1
    fi

    cd $APP_DIR/src

    # Pull latest code
    log "Pulling latest code from $BRANCH..."
    git pull origin $BRANCH

    # Build and start
    log "Building Docker image..."
    docker compose -f docker-compose.prod.yml build

    log "Starting container..."
    docker compose -f docker-compose.prod.yml down 2>/dev/null || true
    docker compose -f docker-compose.prod.yml up -d

    # Wait for health check
    log "Waiting for health check..."
    for i in {1..30}; do
        if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
            log "=== PropEdge is LIVE! ==="
            curl -s http://localhost:8000/api/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8000/api/health
            echo ""
            log "API: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'YOUR_EC2_IP'):8000"
            log "Health: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'YOUR_EC2_IP'):8000/api/health"
            exit 0
        fi
        echo -n "."
        sleep 2
    done

    warn "Health check timed out. Checking logs..."
    docker compose -f docker-compose.prod.yml logs --tail 50
    ;;

restart)
    log "=== Restarting PropEdge ==="
    cd $APP_DIR/src
    docker compose -f docker-compose.prod.yml restart
    sleep 3
    docker compose -f docker-compose.prod.yml ps
    ;;

stop)
    log "=== Stopping PropEdge ==="
    cd $APP_DIR/src
    docker compose -f docker-compose.prod.yml down
    log "Stopped."
    ;;

logs)
    cd $APP_DIR/src
    docker compose -f docker-compose.prod.yml logs -f --tail 100
    ;;

status)
    log "=== PropEdge Status ==="
    cd $APP_DIR/src 2>/dev/null || { err "Not deployed yet"; exit 1; }
    docker compose -f docker-compose.prod.yml ps
    echo ""
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        log "API Health:"
        curl -s http://localhost:8000/api/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8000/api/health
    else
        warn "API not responding"
    fi
    ;;

update)
    log "=== Quick Update (pull + rebuild + restart) ==="
    cd $APP_DIR/src
    git pull origin $BRANCH
    docker compose -f docker-compose.prod.yml build --no-cache
    docker compose -f docker-compose.prod.yml down
    docker compose -f docker-compose.prod.yml up -d
    sleep 5
    log "Checking health..."
    curl -s http://localhost:8000/api/health | python3 -m json.tool 2>/dev/null || warn "Health check pending..."
    ;;

help|*)
    echo "PropEdge v2 EC2 Deploy Script"
    echo ""
    echo "Usage: $0 {setup|deploy|restart|stop|logs|status|update|help}"
    echo ""
    echo "  setup   - First-time: install Docker, clone repo, create dirs"
    echo "  deploy  - Pull latest code, build image, start container"
    echo "  restart - Restart the running container"
    echo "  stop    - Stop the container"
    echo "  logs    - Tail container logs"
    echo "  status  - Show container status + health check"
    echo "  update  - Quick: pull + rebuild + restart (no-cache)"
    echo "  help    - Show this help"
    ;;

esac
