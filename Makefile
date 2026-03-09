# PropEdge v2 - Build & Deploy Automation
# Usage:
#   make dev          - Start Python backend + React UI locally
#   make dev-backend  - Start only the Python FastAPI backend
#   make dev-frontend - Start only the React frontend
#   make build        - Build Docker image + frontend assets
#   make deploy       - Full deploy: build image, push, deploy to EC2
#   make deploy-quick - Quick deploy: rsync code + restart container on EC2
#   make tauri-dev    - Start Tauri desktop app in dev mode
#   make tauri-build  - Build Tauri desktop app for distribution

# ── Configuration ─────────────────────────────────────────────────
EC2_HOST      ?= propedge-ec2
EC2_USER      ?= ec2-user
EC2_DIR       ?= /opt/propedge
EC2_KEY       ?= ~/.ssh/propedge-ec2.pem
DOCKER_IMAGE  ?= propedge-backend
DOCKER_TAG    ?= latest
API_PORT      ?= 8000
UI_PORT       ?= 3000
PYTHON        ?= python
PIP           ?= pip

# Detect OS
ifeq ($(OS),Windows_NT)
    SHELL := cmd.exe
    ACTIVATE = venv\Scripts\activate &&
    MKDIR = mkdir
    RM = del /Q /F
    SEP = \\
else
    ACTIVATE = . venv/bin/activate &&
    MKDIR = mkdir -p
    RM = rm -rf
    SEP = /
endif

.PHONY: help dev dev-backend dev-frontend build deploy deploy-quick \
        tauri-dev tauri-build docker-build docker-push \
        install install-backend install-frontend \
        test lint clean logs ssh

# ── Help ──────────────────────────────────────────────────────────
help: ## Show this help
	@echo PropEdge v2 - Adaptive Neural Trading System
	@echo.
	@echo DEVELOPMENT:
	@echo   make dev            Start Python backend + React UI locally
	@echo   make dev-backend    Start only the Python FastAPI backend
	@echo   make dev-frontend   Start only the React frontend
	@echo   make tauri-dev      Start Tauri desktop app in dev mode
	@echo.
	@echo BUILD:
	@echo   make build          Build Docker image + frontend assets
	@echo   make tauri-build    Build Tauri desktop app for distribution
	@echo   make docker-build   Build Docker image only
	@echo.
	@echo DEPLOY:
	@echo   make deploy         Full deploy to EC2 (build + push + restart)
	@echo   make deploy-quick   Quick deploy (rsync code + restart on EC2)
	@echo.
	@echo SETUP:
	@echo   make install        Install all dependencies (backend + frontend)
	@echo   make install-backend  Install Python backend dependencies
	@echo   make install-frontend Install React frontend dependencies
	@echo.
	@echo OTHER:
	@echo   make test           Run backend tests
	@echo   make lint           Run linting
	@echo   make logs           Tail EC2 container logs
	@echo   make ssh            SSH into EC2 instance
	@echo   make clean          Clean build artifacts

# ── Install ───────────────────────────────────────────────────────
install: install-backend install-frontend ## Install all dependencies

install-backend: ## Install Python backend dependencies
	cd . && $(PIP) install -r requirements.txt

install-frontend: ## Install React frontend dependencies
	cd ui && npm install

# ── Development ───────────────────────────────────────────────────
dev: ## Start backend + frontend locally (parallel)
ifeq ($(OS),Windows_NT)
	start "PropEdge Backend" cmd /c "$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port $(API_PORT) --reload"
	cd ui && npm run dev
else
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port $(API_PORT) --reload & \
	cd ui && npm run dev
endif

dev-backend: ## Start only the FastAPI backend with hot reload
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port $(API_PORT) --reload

dev-frontend: ## Start only the React frontend dev server
	cd ui && npm run dev

# ── Tauri ─────────────────────────────────────────────────────────
tauri-dev: ## Start Tauri desktop app in dev mode
	cd ui && npm run tauri dev

tauri-build: ## Build Tauri desktop app for distribution
	cd ui && npm run tauri build

# ── Docker ────────────────────────────────────────────────────────
docker-build: ## Build the Docker image
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .

docker-push: ## Push Docker image to registry (configure DOCKER_REGISTRY)
	docker tag $(DOCKER_IMAGE):$(DOCKER_TAG) $(DOCKER_REGISTRY)/$(DOCKER_IMAGE):$(DOCKER_TAG)
	docker push $(DOCKER_REGISTRY)/$(DOCKER_IMAGE):$(DOCKER_TAG)

# ── Build ─────────────────────────────────────────────────────────
build: docker-build ## Build Docker image + frontend assets
	cd ui && npm run build

# ── Deploy ────────────────────────────────────────────────────────
deploy: docker-build ## Full deploy: build image, transfer to EC2, restart
	@echo === Saving Docker image...
	docker save $(DOCKER_IMAGE):$(DOCKER_TAG) | gzip > /tmp/propedge-backend.tar.gz
	@echo === Transferring to EC2...
	scp -i $(EC2_KEY) /tmp/propedge-backend.tar.gz $(EC2_USER)@$(EC2_HOST):/tmp/
	scp -i $(EC2_KEY) docker-compose.prod.yml $(EC2_USER)@$(EC2_HOST):$(EC2_DIR)/docker-compose.yml
	scp -i $(EC2_KEY) -r configs/ $(EC2_USER)@$(EC2_HOST):$(EC2_DIR)/configs/
	@echo === Loading image + restarting on EC2...
	ssh -i $(EC2_KEY) $(EC2_USER)@$(EC2_HOST) "\
		docker load < /tmp/propedge-backend.tar.gz && \
		cd $(EC2_DIR) && \
		docker compose down && \
		docker compose up -d && \
		docker compose logs --tail 20 && \
		rm /tmp/propedge-backend.tar.gz"
	@echo === Deploy complete!

deploy-quick: ## Quick deploy: rsync Python code + restart container on EC2
	@echo === Syncing code to EC2...
	rsync -avz --exclude='__pycache__' --exclude='*.pyc' --exclude='venv' \
		--exclude='node_modules' --exclude='.git' --exclude='data' \
		-e "ssh -i $(EC2_KEY)" \
		core/ data_engine/ feature_engine/ agents/ backtester/ \
		allocator/ risk_manager/ execution/ evolution/ api/ configs/ \
		requirements.txt Dockerfile \
		$(EC2_USER)@$(EC2_HOST):$(EC2_DIR)/src/
	@echo === Rebuilding + restarting on EC2...
	ssh -i $(EC2_KEY) $(EC2_USER)@$(EC2_HOST) "\
		cd $(EC2_DIR) && \
		docker compose build --no-cache && \
		docker compose down && \
		docker compose up -d && \
		docker compose logs --tail 20"
	@echo === Quick deploy complete!

# ── EC2 Operations ────────────────────────────────────────────────
logs: ## Tail EC2 container logs
	ssh -i $(EC2_KEY) $(EC2_USER)@$(EC2_HOST) "cd $(EC2_DIR) && docker compose logs -f --tail 100"

ssh: ## SSH into EC2 instance
	ssh -i $(EC2_KEY) $(EC2_USER)@$(EC2_HOST)

ec2-setup: ## Initial EC2 setup (run once)
	ssh -i $(EC2_KEY) $(EC2_USER)@$(EC2_HOST) "\
		sudo yum update -y && \
		sudo yum install -y docker && \
		sudo systemctl start docker && \
		sudo systemctl enable docker && \
		sudo usermod -aG docker $(EC2_USER) && \
		sudo curl -L 'https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64' -o /usr/local/bin/docker-compose && \
		sudo chmod +x /usr/local/bin/docker-compose && \
		sudo mkdir -p $(EC2_DIR)/data $(EC2_DIR)/configs && \
		sudo chown -R $(EC2_USER):$(EC2_USER) $(EC2_DIR)"
	@echo === EC2 setup complete! Log out and back in for docker group.

# ── Testing ───────────────────────────────────────────────────────
test: ## Run backend tests
	$(PYTHON) -m pytest tests/ -v --tb=short

lint: ## Run linting
	$(PYTHON) -m flake8 core/ data_engine/ feature_engine/ agents/ api/ --max-line-length=120

# ── Clean ─────────────────────────────────────────────────────────
clean: ## Clean build artifacts
	$(RM) ui$(SEP)dist
	$(RM) /tmp/propedge-backend.tar.gz 2>/dev/null || true
	docker rmi $(DOCKER_IMAGE):$(DOCKER_TAG) 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
