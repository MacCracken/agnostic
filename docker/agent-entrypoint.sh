#!/bin/sh
# Resolve AGENT_ROLE to the correct Python module and run it.
set -e

case "${AGENT_ROLE}" in
    manager)              exec python -m agents.manager.qa_manager ;;
    senior)               exec python -m agents.senior.senior_qa ;;
    junior)               exec python -m agents.junior.junior_qa ;;
    analyst)              exec python -m agents.analyst.qa_analyst ;;
    security_compliance)  exec python -m agents.security_compliance.qa_security_compliance ;;
    performance)          exec python -m agents.performance.qa_performance ;;
    *)
        echo "ERROR: Unknown AGENT_ROLE '${AGENT_ROLE}'"
        echo "Valid roles: manager, senior, junior, analyst, security_compliance, performance"
        exit 1
        ;;
esac
