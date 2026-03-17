# LLM Integration API

## Overview

The LLM Integration service provides unified access to multiple language model providers for intelligent analysis capabilities across all agent crews.

## Configuration

### Provider Setup
```python
from config.llm_integration import LLMIntegrationService

# Initialize with environment variables
llm_service = LLMIntegrationService()
```

### Supported Providers
- **OpenAI** (primary) - GPT-4, GPT-3.5-turbo
- **Anthropic** - Claude-3.5-sonnet, Claude-3-haiku
- **Google** - Gemini Pro
- **Local** - Ollama, LM Studio

### Environment Variables
```bash
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
GOOGLE_API_KEY=your_google_key
PRIMARY_MODEL_PROVIDER=openai
FALLBACK_MODEL_PROVIDERS=anthropic,google
ENABLE_SELF_HEALING=true
ENABLE_FUZZY_VERIFICATION=true
```

## Available Services

### Scenario Generation
```python
scenarios = await llm_service.generate_test_scenarios(
    requirements="User authentication flow",
    context={"app_type": "web", "complexity": "medium"}
)
```

### Risk Identification
```python
risks = await llm_service.identify_risks(
    test_plan="Login form validation",
    code_changes=["auth.py", "models.py"]
)
```

### Fuzzy Verification
```python
quality_score = await llm_service.fuzzy_verify(
    test_result="Test passed with warnings",
    expectations="All validations should pass cleanly"
)
```

### Security Analysis
```python
security_issues = await llm_service.analyze_security(
    endpoint="/api/login",
    headers={"Authorization": "Bearer token"},
    response_data={"user_id": 123}
)
```

### Performance Profiling
```python
performance_insights = await llm_service.profile_performance(
    metrics={"response_time": 250, "cpu_usage": 85, "memory": 512},
    baseline={"response_time": 100, "cpu_usage": 50, "memory": 256}
)
```

## Error Handling

### Fallback Chain
The service automatically falls back through providers:
1. Primary provider (OpenAI)
2. First fallback (Anthropic)  
3. Second fallback (Google)
4. Local model (Ollama)

### Error Response Format
```python
{
    "success": False,
    "error": "Provider unavailable",
    "fallback_used": "anthropic",
    "retry_count": 2
}
```

## Rate Limiting

### Provider Limits
- OpenAI: 60 requests/minute
- Anthropic: 50 requests/minute  
- Google: 60 requests/minute

### Automatic Retry
- Exponential backoff: 1s, 2s, 4s, 8s
- Maximum retries: 3 per provider
- Total timeout: 30 seconds

## Response Format

### Successful Response
```python
{
    "success": True,
    "provider": "openai",
    "model": "gpt-4",
    "tokens_used": 150,
    "response_time": 1.2,
    "data": {...}
}
```

### Usage Tracking
The service tracks usage metrics:
- Tokens consumed per provider
- Response times
- Error rates
- Fallback frequency

## Integration Examples

### QA Manager Integration
```python
from config.llm_integration import LLMIntegrationService
from agents.manager.qa_manager import QAManager

llm_service = LLMIntegrationService()
qa_manager = QAManager(llm_service=llm_service)

# Use LLM for intelligent task decomposition
await qa_manager.decompose_test_requirements(
    requirements="E-commerce checkout flow",
    use_llm=True
)
```

### Tool Integration
```python
from crewai_tools import BaseTool
from config.llm_integration import LLMIntegrationService

class LLMEnhancedTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.llm_service = LLMIntegrationService()
    
    async def run_with_llm(self, input_data):
        # Enhance tool output with LLM analysis
        base_result = await self.basic_operation(input_data)
        enhanced_result = await self.llm_service.enhance_result(
            base_result, 
            analysis_type="test_optimization"
        )
        return enhanced_result
```