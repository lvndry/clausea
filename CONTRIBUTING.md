# Contributing to Clausea 🌊

Thank you for your interest in contributing to Clausea! We're building the definitive legal document intelligence platform.

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+** with [uv](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js 18+** with [bun](https://bun.sh/)
- **Git** for version control
- **MongoDB** (local or cloud) for development

### Setup

```bash
# Clone the repository
git clone https://github.com/your-org/clausea.git
cd clausea

# Complete project setup
make setup

# Start development servers
make dev
```

For a complete list of available commands, run `make help`.

## 📋 How to Open a Pull Request

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/your-username/clausea.git
cd clausea

# Add upstream remote
git remote add upstream https://github.com/your-org/clausea.git
```

### 2. Create a Feature Branch

```bash
# Create and switch to a new branch
git checkout -b feature/your-feature-name

# Or for bug fixes
git checkout -b fix/your-bug-description
```

### 3. Make Your Changes

Make your code changes, then ensure quality:

```bash
# Format your code
make format

# Lint your code
make lint

# Run tests
make test
```

### 4. Commit Your Changes

We use [Conventional Commits](https://www.conventionalcommits.org/):

```bash
# Format: type(scope): description
git commit -m "feat(legal-analysis): add GDPR compliance checker"
git commit -m "fix(api): resolve rate limiting issue"
git commit -m "docs(readme): update installation instructions"
```

**Commit Types:**

- `feat`: New features
- `fix`: Bug fixes
- `docs`: Documentation changes
- `style`: Code style changes
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

### 5. Push and Create Pull Request

```bash
# Push your branch
git push origin feature/your-feature-name

# Create a Pull Request on GitHub
```

## ✅ Quality Checklist

Before submitting your PR, ensure:

- ✅ **Tests pass** - Run `make test` and all tests pass
- ✅ **Code is formatted** - Run `make format` and `make lint`
- ✅ **Type hints** - Python functions have type hints
- ✅ **Documentation** - New features have docstrings/comments
- ✅ **No breaking changes** - Unless explicitly intended

### Code Standards

**Backend (Python/FastAPI):**

- Python 3.11+ with type hints
- FastAPI for API development
- Ruff for linting and formatting

**Frontend (Next.js/TypeScript):**

- Next.js 15 with App Router
- TypeScript 5.6 for type safety
- ESLint + Prettier for code quality

## 🧪 Testing

```bash
# Run all tests
make test

# Run backend tests only
cd packages/backend && source .venv/bin/activate && python -m pytest tests/ -v

# Run frontend tests only
cd packages/frontend && bun test
```

## 📄 License

By contributing to Clausea, you agree that your contributions will be licensed under the [AGPL-3.0 License](LICENSE).
