<div align="center">
  <img src="packages/frontend/public/static/favicons/logo.png" alt="Clausea Logo" width="200"/>
</div>

# Clausea

**The definitive policy document intelligence platform** - Transform complex policy documents into clear, actionable insights with AI-powered analysis.

<a href="https://clausea.co" style="display: inline-block; padding: 6px 14px; background: #0070f3; color: white; text-decoration: none; border-radius: 4px; font-weight: 500;">Try now</a>

## 🎯 Mission

Clausea democratizes legal understanding by making complex privacy policies, terms of service, and contracts accessible to everyone. We help:

- **Individuals** understand what they're agreeing to before signing up
- **Small businesses** assess vendor risks without expensive legal review
- **Enterprise teams** automate compliance monitoring and contract review
- **Developers** integrate legal intelligence into their applications

## Features

### Core Capabilities

- **Plain Language Summaries**: Complex legal jargon made accessible
- **Risk Scoring**: Get quantified risk assessments (0-10 scale)
- **Compliance Checking**: Verify GDPR, CCPA, and other regulatory compliance
- **Document Analysis**: Upload any policy document for instant AI analysis
- **Change Monitoring**: Track policy changes across websites
- **Comparison Tools**: Side-by-side policy comparisons

### Technical Features

- **Multi-Model AI**: Combines GPT-4, Claude, and specialized models
- **Real-time Processing**: <10 second analysis for standard documents
- **95%+ Accuracy**: Validated against legal expert annotations
- **API-First**: RESTful API with webhook support
- **Enterprise Ready**: SOC2 compliance, data encryption, team collaboration

## Quick Start

### Prerequisites

- **Python 3.11+** with [uv](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js 18+** with [bun](https://bun.sh/)
- **MongoDB** (local or cloud)
- **OpenAI API key** and **Anthropic API key**

### 1 Development Setup

We provide a comprehensive Makefile for easy development setup and workflow:

```bash
git clone https://github.com/lvndry/clausea.git

# Complete project setup (recommended for new developers)
make setup
```

For a complete list of commands, run `make help`.

### 2. Environment Configuration

```bash
# Backend environment
cp packages/backend/.env.example packages/backend/.env
# Edit with your API keys and database URLs

# Frontend environment
cp packages/frontend/.env.example packages/frontend/.env
# Edit with your Clerk and API configuration
```

### 3. Start Development

```bash
# Start both frontend and backend
make dev

# Or run individual components
make run-backend    # Backend only
make run-frontend   # Frontend only
```

### 4. Access the Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### 5. Streamlit Dashboard

```bash
# Start Streamlit dashboard
make run-streamlit
```

- **Streamlit Dashboard**: http://localhost:8501 (see [Streamlit Setup Guide](packages/backend/docs/STREAMLIT_SETUP.md))

## 📄 License

This project is licensed under the AGPL-3.0 License. See the [LICENSE](LICENSE) file for details.

## 🆘 Support

<!-- - **Documentation**: [docs.clausea.co](https://docs.clausea.co) -->
<!-- - **API Reference**: [api.clausea.co](https://api.clausea.co) -->
<!-- - **Community**: [Discord](https://discord.gg/clausea) -->

- **Email**: lvndry@proton.me

---

**Built with ❤️ by the Clausea team**

_Making legal intelligence accessible to everyone._
