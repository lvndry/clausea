# Clausea - Policy Document Intelligence API

> The definitive platform for policy document analysis, privacy policy intelligence, and compliance monitoring.

Clausea transforms complex policy documents into actionable insights using advanced AI and LLM orchestration. Our API provides legal-grade accuracy with sub-10-second response times, helping individuals and businesses understand what they're agreeing to.

## 🚀 Features

- **Policy Document Analysis**: Privacy policies, terms of service, cookie policies, and other agreements
- **AI-Powered Risk Assessment**: Quantified risk scoring with confidence levels
- **Compliance Monitoring**: GDPR, CCPA, and regulatory compliance checking
- **Real-time Processing**: Sub-10-second analysis with async processing
- **Multi-Model LLM Orchestration**: Best models from OpenAI, Anthropic, Gemini, xAI,...
- **Document Comparison**: Side-by-side policy analysis and change tracking
- **Enterprise Scalability**: Bulk processing and team collaboration features

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │    │   Document      │    │   Vector DB     │
│   (Main API)    │◄──►│   Processor     │◄──►│   (Pinecone)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   LLM Service   │    │   Crawler       │    │   MongoDB       │
│   (Multi-Model) │    │   (Web Scraping)│    │   (Documents)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📋 Prerequisites

- **Python 3.11+**
- **uv** - Fast Python package manager
- **MongoDB** - Document storage
- **Pinecone** - Vector database for embeddings
- **OpenAI API Key** - GPT-4o and GPT-4o-mini access
- **Anthropic API Key** - Claude models access
- **xAI API Key** - Grok models access (optional)

## 🛠️ Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd packages/backend
```

### 2. Install Dependencies

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv sync
```

### 3. Environment Configuration

Create a `.env` file in the backend directory:

```bash
# Application
ENVIRONMENT=development
PORT=8000

# Database
MONGODB_URI=mongodb://localhost:27017/clausea

# Vector Database
PINECONE_API_KEY=your_pinecone_api_key

# LLM Services
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
XAI_API_KEY=your_xai_api_key  # Optional, for Grok models

# Authentication
CLERK_JWKS_URL=https://your-clerk-instance.clerk.accounts.dev/.well-known/jwks.json

# CORS
CORS_ORIGINS=http://localhost:3000,https://your-frontend-domain.com
```

### 4. Run the Application

```bash
# Development mode
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

## 🐳 Docker Deployment

```bash
# Build the image
docker build -t clausea-api .

# Run the container
docker run -p 8000:8000 --env-file .env clausea-api
```

## 📚 API Documentation

Once the server is running, visit:

- **Interactive API Docs**: http://localhost:8000/docs
- **OpenAPI Schema**: http://localhost:8000/openapi.json
- **Health Check**: http://localhost:8000/health

## 🔌 API Endpoints

### Core Analysis Endpoints

| Endpoint                       | Method   | Description                       |
| ------------------------------ | -------- | --------------------------------- |
| `/q`                           | POST     | Submit document for analysis      |
| `/products`                    | GET      | List all products                 |
| `/products/{slug}`             | GET      | Get product details and documents |
| `/conversations`               | GET/POST | Manage analysis conversations     |
| `/conversations/{id}/messages` | GET/POST | Chat with analyzed documents      |

### Document Processing

| Endpoint     | Method | Description                     |
| ------------ | ------ | ------------------------------- |
| `/crawler`   | POST   | Crawl and process web documents |
| `/promotion` | POST   | Promote data between systems    |
| `/list`      | GET    | List documents with filters     |

### User Management

| Endpoint                     | Method | Description              |
| ---------------------------- | ------ | ------------------------ |
| `/users/me`                  | GET    | Get current user profile |
| `/users/complete-onboarding` | POST   | Complete user onboarding |

## 🔄 Document Processing Pipeline

### 1. Document Crawling & Ingestion

```python
# Automated web crawling for policy documents
1. Fetch product base URLs
2. Crawl and extract content
3. Detect policy document types
4. Language detection and filtering
5. Store in MongoDB with metadata
```

### 2. Document Processing & Embedding

```python
# AI-powered document analysis
1. Extract text content from various formats (PDF, DOCX, HTML)
2. Split documents into semantic chunks using NLTK
3. Generate embeddings using Mistral AI
4. Store embeddings in Pinecone vector database
5. Index for fast similarity search
```

### 3. Legal Analysis & Risk Assessment

```python
# Multi-model LLM orchestration
1. Route documents to appropriate LLM based on complexity
2. Perform legal entity extraction and classification
3. Analyze privacy practices and data usage
4. Assess compliance with regulations (GDPR, CCPA, etc.)
5. Generate risk scores and confidence levels
6. Create plain-language summaries and recommendations
```

## 🧪 Testing

```bash
# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src --cov-report=html

# Run specific test file
uv run pytest tests/test_embedding_service.py

# Run linting
uv run ruff check .

# Run type checking
uv run ty check
```

## 🔧 Development

### Code Quality

```bash
# Install development dependencies
uv sync --group dev

# Run pre-commit hooks
uv run pre-commit install
uv run pre-commit run --all-files

# Format code
uv run ruff format .

# Sort imports
uv run ruff check --select I --fix
```

### Database Migrations

```bash
# Run migrations
uv run python scripts/migrate_users.py
```

### Dashboard Development

```bash
# Start the Streamlit dashboard
uv run streamlit run src/dashboard/app.py
```

## 📊 Monitoring & Observability

### Health Checks

- **Application Health**: `GET /health`
- **Database Connection**: Automatic connection testing
- **LLM Service Status**: Real-time model availability

### Logging

Structured logging with `structlog`:

- Request/response logging
- LLM performance metrics
- Error tracking and alerting
- Business metrics for analytics

### Metrics

- Document processing throughput
- LLM response times and costs
- User engagement and conversion metrics
- Error rates and system health

## 🔒 Security

- **Authentication**: JWT-based auth with Clerk integration
- **CORS**: Configurable cross-origin resource sharing
- **Rate Limiting**: Usage-based rate limiting by user tier
- **Data Privacy**: Automatic PII detection and redaction
- **Secure Storage**: Encrypted document storage and processing

## 🚀 Performance

### Optimization Strategies

- **Async Processing**: Non-blocking document analysis
- **Caching**: Redis-based caching for common analyses
- **Batch Processing**: Efficient bulk document handling
- **Token Optimization**: Smart prompt engineering for cost efficiency
- **CDN Integration**: Fast document delivery worldwide

### SLA Targets

- **Response Time**: <10 seconds for standard documents
- **Accuracy**: >95% legal analysis accuracy
- **Uptime**: 99.9% availability
- **Throughput**: 1000+ documents per hour

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines
- Write comprehensive tests for new features
- Update documentation for API changes
- Ensure legal accuracy for all analysis features
- Optimize for both speed and accuracy

## 📄 License

This project is proprietary software. All rights reserved.

## 🆘 Support

- **Documentation**: Check the `/docs` endpoint for API documentation
- **Issues**: Report bugs and feature requests via GitHub Issues
- **Discussions**: Join our community discussions for questions and ideas

## 🎯 Roadmap

- [ ] Enhanced compliance monitoring
- [ ] Real-time policy change alerts
- [ ] Advanced document comparison tools
- [ ] Enterprise team collaboration features
- [ ] Mobile API optimization
- [ ] Multi-language support expansion

---

**Built with ❤️ by the Clausea team**

_Empowering legal understanding through intelligent document analysis._
