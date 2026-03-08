# Use the optimized base image with all dependencies pre-installed
FROM agnostic-qa-base:latest

# Copy agent-specific code (all dependencies already installed in base)
COPY --chown=appuser:appuser VERSION ./VERSION
COPY --chown=appuser:appuser ./agents/security_compliance/qa_security_compliance.py /app/qa_security_compliance.py
COPY --chown=appuser:appuser shared/ ./shared/

# Set agent-specific environment variable
ENV AGENT_ROLE=security_compliance

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import redis; import pika; print('healthy')" || exit 1

# Default command
CMD ["python", "qa_security_compliance.py"]