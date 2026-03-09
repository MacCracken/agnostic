# Contributing to Agentic QA Team System

We welcome contributions! This document provides guidelines for developers who want to contribute to this project.

## Development Setup

1. **Fork and Clone**
   ```bash
   git clone <your-fork>
   cd agnostic
   ```

2. **Install Dependencies**
   ```bash
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

3. **Environment Setup**
   ```bash
   cp .env.example .env
   # Set OPENAI_API_KEY and other required variables
   ```

4. **Pre-commit Hooks**
   ```bash
   pre-commit install
   ```

## Code Standards

### Code Quality
- **Type Hints**: Required for all function signatures
- **Linting**: Use `ruff check` and `ruff format`
- **Type Checking**: Use `mypy` for static analysis
- **Testing**: Maintain 85%+ test coverage

### Code Style
- Follow PEP 8 with Black formatting (88-char line length)
- Use descriptive variable and function names
- Add docstrings for all public functions and classes
- Include type hints for all parameters and return values

## Testing

### Running Tests
```bash
# Unit tests
.venv/bin/python -m pytest tests/unit/ -q

# E2E tests (requires running containers)
.venv/bin/python -m pytest tests/e2e/ -q

# With coverage
.venv/bin/python -m pytest tests/unit/ --cov=agents --cov=webgui --cov=config
```

### Test Structure
- `tests/unit/` - Unit tests for individual components (816 tests)
- `tests/e2e/` - End-to-end tests requiring Docker services (24 tests)

## Pull Request Process

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**
   - Write code following our standards
   - Add tests for new functionality
   - Update documentation as needed

3. **Quality Checks**
   ```bash
   ruff check .
   ruff format .
   .venv/bin/python -m pytest tests/unit/ -q
   ```

4. **Submit PR**
   - Use descriptive title and description
   - Link to related issues
   - Ensure all CI checks pass

## Adding New Agents

1. **Create Agent Module**
   ```
   agents/new_agent/
   ├── __init__.py
   ├── qa_new_agent.py
   └── README.md
   ```

2. **Implement Agent Class**
   - Extend CrewAI Agent base class
   - Implement required tools
   - Add configuration validation

3. **Add Service Configuration**
   - Register in `config/agent_registry.py`
   - Update WebGUI routing

4. **Add Tests**
   - Unit tests for agent tools
   - Integration tests for communication

## Documentation Updates

When adding features:
- Update relevant sections in `README.md`
- Update `docs/development/setup.md` if architecture changes
- Add API documentation to `docs/api/`
- Update agent index in `docs/agents/index.md`

## Security Considerations

- Never commit secrets or API keys
- Use environment variables for configuration
- Follow OWASP security guidelines
- Run security scans before submitting PRs

## Getting Help

- Check `docs/getting-started/quick-start.md` for common issues
- Review existing issues and discussions
- Ask questions in GitHub discussions
- Check `docs/development/setup.md` for development guidance

Thank you for contributing! 🚀