# Clausea Makefile
# Provides convenient commands for setting up and running the development environment

.PHONY: help setup dev clean install-deps setup-backend setup-frontend setup-extension setup-precommit setup-env run-backend run-frontend extension-dev extension-build extension-zip test lint format check-deps docker-build-streamlit docker-run-streamlit docker-stop-streamlit docker-rm-streamlit docker-restart-streamlit docker-logs-streamlit

# Default target
help:
	@echo "🚀 Clausea Development Commands"
	@echo "================================"
	@echo ""
	@echo "Setup Commands:"
	@echo "  make setup          - Complete project setup (dependencies, pre-commit, permissions)"
	@echo "  make install-deps   - Install all dependencies (backend + frontend)"
	@echo "  make setup-backend  - Setup backend only"
	@echo "  make setup-frontend - Setup frontend only"
	@echo "  make setup-extension - Setup extension only"
	@echo "  make setup-precommit - Setup pre-commit hooks"
	@echo ""
	@echo "Development Commands:"
	@echo "  make dev            - Start development servers (frontend + backend)"
	@echo "  make run-backend    - Start backend server only"
	@echo "  make run-frontend   - Start frontend server only"
	@echo "  make extension-dev  - Start extension development mode"
	@echo "  make extension-build - Build extension for production"
	@echo "  make extension-zip  - Create zip file for extension distribution"
	@echo ""
	@echo "Utility Commands:"
	@echo "  make test           - Run tests"
	@echo "  make lint           - Run linting"
	@echo "  make format         - Format code"
	@echo "  make clean          - Clean up temporary files"
	@echo "  make check-deps     - Check if required dependencies are installed"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make docker-build-streamlit  - Build Streamlit Docker image"
	@echo "  make docker-run-streamlit    - Run Streamlit container (requires MONGO_URI and DASHBOARD_PASSWORD)"
	@echo "  make docker-stop-streamlit   - Stop Streamlit container"
	@echo "  make docker-rm-streamlit    - Remove Streamlit container"
	@echo "  make docker-restart-streamlit - Restart Streamlit container"
	@echo "  make docker-logs-streamlit   - View Streamlit container logs"
	@echo ""

# Complete project setup
setup: check-deps setup-permissions setup-env install-deps setup-precommit
	@echo "✅ Clausea setup complete!"
	@echo "Run 'make dev' to start the development environment"

# Install all dependencies
install-deps: setup-backend setup-frontend
	@echo "✅ All dependencies installed"

# Setup backend dependencies
setup-backend:
	@echo "🔧 Setting up backend..."
	@cd packages/backend && uv sync
	@echo "✅ Backend setup complete"

# Setup frontend dependencies
setup-frontend:
	@echo "🔧 Setting up frontend..."
	@cd packages/frontend && bun install
	@echo "✅ Frontend setup complete"

# Setup extension dependencies
setup-extension:
	@echo "🔧 Setting up extension..."
	@cd packages/extension && bun install
	@echo "✅ Extension setup complete"

# Setup pre-commit hooks
setup-precommit: setup-permissions
	@echo "🔧 Setting up pre-commit hooks..."
	@./dev/setup-precommit.sh

# Setup environment files
setup-env:
	@echo "🔧 Setting up environment..."
	@if [ ! -f packages/backend/.env ]; then \
		echo "Creating backend .env file..."; \
		cp packages/backend/.env.example packages/backend/.env 2>/dev/null || echo "# Backend environment variables" > packages/backend/.env; \
	fi
	@if [ ! -f packages/frontend/.env.local ]; then \
		echo "Creating frontend .env.local file..."; \
		cp packages/frontend/.env.example packages/frontend/.env.local 2>/dev/null || echo "# Frontend environment variables" > packages/frontend/.env.local; \
	fi
	@echo "✅ Environment files created"

# Set executable permissions on scripts
setup-permissions:
	@echo "🔧 Setting executable permissions on scripts..."
	@chmod +x dev.sh
	@chmod +x dev/setup-precommit.sh
	@echo "✅ Script permissions set"

# Start development environment
dev: check-deps
	@echo "🚀 Starting Clausea development environment..."
	@./dev.sh

# Start backend server only
run-backend: check-deps
	@echo "🚀 Starting backend server..."
	@cd packages/backend && source .venv/bin/activate && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Start frontend server only
run-frontend: check-deps
	@echo "🚀 Starting frontend server..."
	@cd packages/frontend && bun run dev

# Start extension development mode
extension-dev: check-deps
	@echo "🚀 Starting extension development mode..."
	@cd packages/extension && bun run dev

# Build extension for production
extension-build: check-deps
	@echo "🏗️  Building extension..."
	@cd packages/extension && bun run build
	@echo "✅ Extension build complete"

# Create zip file for extension distribution
extension-zip: check-deps
	@echo "📦 Creating extension zip file..."
	@cd packages/extension && bun run zip
	@echo "✅ Extension zip file created"

# Run tests
test:
	@echo "🧪 Running tests..."
	@cd packages/backend && source .venv/bin/activate && python -m pytest tests/ -v
	@cd packages/frontend && bun test

# Run linting
lint:
	@echo "🔍 Running linting..."
	@cd packages/backend && source .venv/bin/activate && ruff check .
	@cd packages/frontend && bun run lint

# Format code
format:
	@echo "🎨 Formatting code..."
	@cd packages/backend && source .venv/bin/activate && ruff format .
	@cd packages/frontend && bun run format

# Clean up temporary files
clean:
	@echo "🧹 Cleaning up temporary files..."
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@find . -type d -name "*.egg-info" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type d -name ".mypy_cache" -exec rm -rf {} +
	@find . -type d -name ".ruff_cache" -exec rm -rf {} +
	@rm -rf packages/backend/.venv
	@rm -rf packages/frontend/node_modules
	@rm -rf packages/frontend/.next
	@rm -rf packages/extension/node_modules
	@rm -rf packages/extension/.output
	@echo "✅ Cleanup complete"

# Check if required dependencies are installed
check-deps:
	@echo "🔍 Checking dependencies..."
	@command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 is required but not installed"; exit 1; }
	@command -v uv >/dev/null 2>&1 || { echo "❌ uv is required but not installed. Install from https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
	@command -v node >/dev/null 2>&1 || { echo "❌ Node.js is required but not installed"; exit 1; }
	@command -v bun >/dev/null 2>&1 || { echo "❌ bun is required but not installed. Install from https://bun.sh/"; exit 1; }
	@echo "✅ All dependencies are installed"

# Run dashboard
dashboard:
	@echo "📊 Starting dashboard..."
	@cd packages/backend && source .venv/bin/activate && streamlit run src/dashboard/app.py

# Stop dashboard
stop-dashboard:
	@echo "🛑 Stopping dashboard..."
	@cd packages/backend && source .venv/bin/activate && python scripts/stop_dashboard.py

# Production build
build:
	@echo "🏗️ Building for production..."
	@cd packages/backend && source .venv/bin/activate && python -m build
	@cd packages/frontend && bun run build

# Docker commands
docker-build:
	@echo "🐳 Building Docker images..."
	@docker build -t clausea-backend packages/backend/
	@docker build -t clausea-frontend packages/frontend/

docker-run:
	@echo "🐳 Running with Docker Compose..."
	@docker-compose up -d

docker-stop:
	@echo "🐳 Stopping Docker containers..."
	@docker-compose down

# Docker Streamlit commands
docker-build-streamlit:
	@echo "🐳 Building Streamlit Docker image..."
	@cd packages/backend && docker build -f Dockerfile.streamlit -t clausea-streamlit .
	@echo "✅ Streamlit Docker image built successfully"
	@echo "Run 'make docker-run-streamlit' to start the container"

docker-run-streamlit:
	@echo "🐳 Running Streamlit container..."
	@echo "💡 Note: Use 'host.docker.internal' instead of 'localhost' to access MongoDB on your host machine"
	@echo "   Example: MONGO_URI='mongodb://host.docker.internal:27017/clausea'"
	@if [ -z "$$MONGO_URI" ]; then \
		echo "❌ Error: MONGO_URI environment variable is required"; \
		echo "Example: MONGO_URI='mongodb://host.docker.internal:27017/clausea' make docker-run-streamlit"; \
		echo "   (Use 'host.docker.internal' for Docker Desktop, or your host IP for remote MongoDB)"; \
		exit 1; \
	fi
	@if [ -z "$$DASHBOARD_PASSWORD" ]; then \
		echo "❌ Error: DASHBOARD_PASSWORD environment variable is required"; \
		echo "Example: DASHBOARD_PASSWORD='your-password' make docker-run-streamlit"; \
		exit 1; \
	fi
	@PORT=$${PORT:-8501}; \
	ENV_MODE=$${ENVIRONMENT:-production}; \
	docker run -d \
		--name clausea-streamlit \
		-p $$PORT:8501 \
		-e MONGO_URI="$$MONGO_URI" \
		-e DASHBOARD_PASSWORD="$$DASHBOARD_PASSWORD" \
		-e ENVIRONMENT="$$ENV_MODE" \
		-e PORT="8501" \
		$$([ -f packages/backend/.env ] && echo "--env-file packages/backend/.env" || true) \
		clausea-streamlit || \
		(docker start clausea-streamlit && echo "✅ Streamlit container started (was already created)"); \
	PORT=$${PORT:-8501}; \
	echo "✅ Streamlit container is running"; \
	echo "Access the dashboard at: http://localhost:$$PORT"

docker-stop-streamlit:
	@echo "🛑 Stopping Streamlit container..."
	@docker stop clausea-streamlit 2>/dev/null || echo "Container not running"
	@echo "✅ Streamlit container stopped"

docker-rm-streamlit:
	@echo "🗑️  Removing Streamlit container..."
	@docker rm -f clausea-streamlit 2>/dev/null || echo "Container not found"
	@echo "✅ Streamlit container removed"

docker-logs-streamlit:
	@echo "📋 Streamlit container logs (Ctrl+C to exit)..."
	@docker logs -f clausea-streamlit 2>/dev/null || echo "❌ Container 'clausea-streamlit' not found. Run 'make docker-run-streamlit' first"

docker-restart-streamlit: docker-stop-streamlit docker-run-streamlit
	@echo "✅ Streamlit container restarted"

# Development shortcuts
backend: run-backend
frontend: run-frontend
logs:
	@echo "📋 Showing logs..."
	@tail -f packages/backend/logs/*.log 2>/dev/null || echo "No log files found"

# Quick start for new developers
quick-start: setup dev
	@echo "🎉 Quick start complete! Development servers should be running."
	@echo "Frontend: http://localhost:3000"
	@echo "Backend:  http://localhost:8000"
