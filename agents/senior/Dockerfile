# Use the optimized base image with all dependencies pre-installed
FROM agnostic-qa-base:latest

# Copy agent-specific code (all dependencies already installed in base)
COPY --chown=appuser:appuser VERSION ./VERSION
COPY --chown=appuser:appuser agents/senior/ ./agents/senior/
COPY --chown=appuser:appuser advanced_testing/ ./advanced_testing/
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser shared/ ./shared/

# Set agent-specific environment variable
ENV AGENT_ROLE=senior

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Expose port for health checks
EXPOSE 8002

# Run the Senior QA agent
CMD ["python", "-m", "agents.senior.senior_qa"]