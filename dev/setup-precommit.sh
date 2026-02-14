#!/bin/bash

# Clausea AI Pre-commit Setup Script
# Installs and configures pre-commit hooks for both frontend and backend

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if pre-commit is installed
check_precommit() {
    if ! command -v pre-commit &> /dev/null; then
        print_error "pre-commit is not installed"
        print_status "Installing pre-commit..."

        # Try different installation methods
        if command -v uv &> /dev/null; then
            uv tool install pre-commit
        elif command -v pip &> /dev/null; then
            pip install pre-commit
        elif command -v pip3 &> /dev/null; then
            pip3 install pre-commit
        else
            print_error "No Python package manager found. Please install pre-commit manually:"
            print_status "uv tool install pre-commit"
            exit 1
        fi
    fi

    if ! command -v pre-commit &> /dev/null; then
        print_error "pre-commit installation failed or is not on PATH"
        exit 1
    fi

    print_success "pre-commit is installed"
}

# Install backend development dependencies
setup_backend_dev() {
    print_status "Setting up backend development dependencies..."
    cd packages/backend

    # Install dev dependencies using uv
    print_status "Installing backend dev dependencies..."
    uv sync --group dev

    cd ../..
    print_success "Backend development dependencies installed"
}

# Install frontend development dependencies
setup_frontend_dev() {
    print_status "Setting up frontend development dependencies..."
    cd packages/frontend

    # Install additional dev dependencies for pre-commit
    print_status "Installing frontend dev dependencies..."
    bun add -D @typescript-eslint/eslint-plugin @typescript-eslint/parser

    cd ../..
    print_success "Frontend development dependencies installed"
}

# Install pre-commit hooks
install_hooks() {
    print_status "Installing pre-commit hooks..."

    # Install the git hook scripts
    pre-commit install

    # Install commit-msg hook for conventional commits
    pre-commit install --hook-type commit-msg

    print_success "Pre-commit hooks installed"
}

# Run initial pre-commit on all files
run_initial_check() {
    print_status "Running initial pre-commit check on all files..."

    # Run pre-commit on all files
    pre-commit run --all-files

    print_success "Initial pre-commit check completed"
}

# Create .gitignore entries for pre-commit
setup_gitignore() {
    print_status "Setting up .gitignore for pre-commit..."

    # Add pre-commit related entries to .gitignore if they don't exist
    if [ ! -f ".gitignore" ]; then
        touch .gitignore
    fi

    # Add entries if they don't exist
    if ! grep -q "bandit-report.json" .gitignore; then
        echo "# Pre-commit reports" >> .gitignore
        echo "bandit-report.json" >> .gitignore
    fi

    print_success ".gitignore updated"
}

# Main execution
main() {
    echo "🔧 Setting up Pre-commit for Clausea AI"
    echo "====================================="

    # Check and install pre-commit
    check_precommit

    # Setup development dependencies
    setup_backend_dev
    setup_frontend_dev

    # Install hooks
    install_hooks

    # Setup gitignore
    setup_gitignore

    # Run initial check
    run_initial_check

    echo ""
    echo "🎉 Pre-commit setup complete!"
    echo "============================="
    echo "Pre-commit hooks are now active and will run on every commit."
    echo ""
    echo "Available commands:"
    echo "  pre-commit run --all-files    # Run all hooks on all files"
    echo "  pre-commit run                # Run hooks on staged files"
    echo "  pre-commit run <hook-name>    # Run specific hook"
    echo ""
    echo "The following checks will run on commit:"
    echo "  ✅ Python code formatting (black)"
    echo "  ✅ Python import sorting (isort)"
    echo "  ✅ Python linting (flake8)"
    echo "  ✅ Python type checking (ty)"
    echo "  ✅ Python security checks (bandit)"
    echo "  ✅ JavaScript/TypeScript linting (eslint)"
    echo "  ✅ Frontend code formatting (prettier)"
    echo "  ✅ TypeScript type checking"
    echo "  ✅ Backend tests"
    echo "  ✅ Frontend build check"
    echo "  ✅ Conventional commit messages"
    echo ""
}

# Run main function
main
