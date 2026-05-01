# Clausea Backend Tests

This directory contains the test suite for the Clausea backend, focusing on policy document intelligence and analysis accuracy.

## Test Structure

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Pytest configuration and shared fixtures
├── unit/                    # Unit tests for individual components
│   ├── __init__.py
│   ├── test_config.py       # Configuration management tests
│   ├── test_jwt.py          # JWT authentication tests
│   ├── test_models.py       # Data model tests
│   └── test_utils.py        # Utility function tests
└── README.md               # This file
```

## Running Tests

### All Tests

```bash
# From project root
make test

# From backend directory
cd packages/backend
source .venv/bin/activate
python -m pytest tests/ -v
```

### Specific Test Categories

```bash
# Unit tests only
python -m pytest tests/unit/ -v

# Specific test file
python -m pytest tests/unit/test_jwt.py -v

# Specific test method
python -m pytest tests/unit/test_jwt.py::TestClerkAuthService::test_auth_service_initialization -v
```

### Test Coverage

```bash
# Install coverage (if not already installed)
pip install coverage

# Run tests with coverage
coverage run -m pytest tests/
coverage report
coverage html  # Generate HTML report
```

## Test Categories

### Unit Tests (`tests/unit/`)

- **Configuration Tests**: Verify settings and environment configuration
- **Authentication Tests**: JWT token validation and user extraction
- **Model Tests**: Pydantic model validation and serialization
- **Utility Tests**: Helper function behavior

### Future Test Categories

- **Integration Tests**: API endpoint testing with real database
- **Legal Accuracy Tests**: Expert-validated document analysis
- **Performance Tests**: Sub-10-second analysis time validation
- **Security Tests**: Data protection and privacy compliance

## Test Fixtures

Common fixtures available in `conftest.py`:

- `mock_clerk_user`: Mock ClerkUser for authentication testing
- `mock_jwt_payload`: Sample JWT payload for token testing
- `mock_http_client`: Mock HTTP client for external API calls
- `mock_llm_service`: Mock LLM service for document analysis testing

## Writing New Tests

### Test Naming Convention

- Test files: `test_*.py`
- Test classes: `Test*`
- Test methods: `test_*`

### Example Test Structure

```python
import pytest
from unittest.mock import AsyncMock, patch

class TestMyService:
    """Test cases for MyService."""

    @pytest.fixture
    def service(self):
        """Create service instance for testing."""
        return MyService()

    def test_service_initialization(self, service):
        """Test service initialization."""
        assert service is not None
        assert hasattr(service, 'required_method')

    @pytest.mark.asyncio
    async def test_async_method(self, service):
        """Test async method behavior."""
        result = await service.async_method()
        assert result is not None
```

## Legal Testing Considerations

When writing tests for policy document analysis:

1. **Accuracy Requirements**: Tests should validate >95% accuracy on known legal patterns
2. **Confidence Scoring**: Verify AI confidence levels are realistic
3. **Jurisdiction Coverage**: Test across different legal systems (GDPR, CCPA, etc.)
4. **Risk Assessment**: Validate risk scoring algorithms
5. **Plain Language**: Ensure complex legal concepts are properly simplified

## CI/CD Integration

Tests run automatically on:

- Pull requests to `main` or `develop` branches
- Backend code changes trigger backend-specific CI
- Pre-commit hooks run basic tests before commits

## Performance Benchmarks

Target performance metrics:

- **Analysis Time**: <10 seconds for standard documents
- **API Response**: <2 seconds for cached results
- **Concurrent Load**: Support 50+ simultaneous analyses
- **Memory Usage**: <1GB per analysis process

## Contributing

When adding new tests:

1. Follow existing naming conventions
2. Add appropriate fixtures to `conftest.py`
3. Include both positive and negative test cases
4. Document any legal-specific test requirements
5. Ensure tests are deterministic and don't rely on external services
