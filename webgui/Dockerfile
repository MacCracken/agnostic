# Use the optimized base image with all dependencies pre-installed
FROM agnostic-qa-base:latest

# Copy web GUI code (all dependencies already installed in base)
COPY --chown=appuser:appuser webgui/ ./webgui/
COPY --chown=appuser:appuser agents/ ./agents/
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser shared/ ./shared/

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
CMD ["chainlit", "run", "webgui/app.py", "--host", "0.0.0.0", "--port", "8000"]