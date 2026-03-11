# Use the optimized base image with all dependencies pre-installed
FROM agnostic-qa-base:latest

# Copy web GUI code (all dependencies already installed in base)
COPY --chown=agnostic:agnostic VERSION ./VERSION
COPY --chown=agnostic:agnostic webgui/ ./webgui/
COPY --chown=agnostic:agnostic agents/ ./agents/
COPY --chown=agnostic:agnostic config/ ./config/
COPY --chown=agnostic:agnostic shared/ ./shared/

# Set environment variables
ENV CHAINLIT_HOST=0.0.0.0
ENV CHAINLIT_PORT=8000
ENV CHAINLIT_ROOT_PATH=

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run the web GUI
LABEL org.opencontainers.image.source="https://github.com/MacCracken/agnostic"
LABEL org.opencontainers.image.description="Agnostic QA Platform - webgui"
LABEL org.opencontainers.image.licenses="MIT"

CMD ["chainlit", "run", "webgui/app.py", "--host", "0.0.0.0", "--port", "8000"]