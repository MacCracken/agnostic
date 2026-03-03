// Dashboard JavaScript
class Dashboard {
    constructor() {
        this.sessions = [];
        this.metrics = {};
        this.ws = null;
        this.init();
    }

    init() {
        this.loadDashboard();
        this.initWebSocket();
        this.startAutoRefresh();
    }

    async loadDashboard() {
        try {
            const response = await fetch('/api/dashboard');
            const data = await response.json();
            
            this.updateMetrics(data.metrics);
            this.updateSessions(data.sessions);
            this.updateAgents(data.agents);
        } catch (error) {
            console.error('Error loading dashboard:', error);
            this.showError('Failed to load dashboard data');
        }
    }

    initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/realtime`;
        
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.updateConnectionStatus('connected');
            // Subscribe to active sessions for real-time updates
            this.subscribeToActiveSessions();
        };
        
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleRealtimeUpdate(data);
        };
        
        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.updateConnectionStatus('disconnected');
            // Attempt to reconnect after 5 seconds
            setTimeout(() => this.initWebSocket(), 5000);
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateConnectionStatus('disconnected');
        };
    }

    handleRealtimeUpdate(data) {
        switch (data.type) {
            case 'session_status_changed':
                this.updateSessionStatus(data.session_id, data.data);
                break;
            case 'agent_status_changed':
                this.updateAgentStatus(data.agent_name, data.data);
                break;
            case 'resource_update':
                this.updateMetrics(data.data);
                break;
            case 'notification':
                this.showNotification(data.data);
                break;
        }
    }

    updateMetrics(metrics) {
        this.metrics = metrics;
        
        // Update metric cards
        document.getElementById('total-sessions').textContent = metrics.total_sessions || 0;
        document.getElementById('active-sessions').textContent = metrics.active_sessions || 0;
        document.getElementById('active-agents').textContent = metrics.active_agents || 0;
        document.getElementById('redis-memory').textContent = this.formatBytes(metrics.redis_memory_usage || 0);
        
        // Update resource charts
        this.updateResourceChart(metrics);
    }

    updateSessions(sessions) {
        this.sessions = sessions;
        const container = document.getElementById('sessions-container');
        
        if (!sessions || sessions.length === 0) {
            container.innerHTML = '<p class="text-muted">No active sessions</p>';
            return;
        }
        
        container.innerHTML = sessions.map(session => this.createSessionCard(session)).join('');
    }

    createSessionCard(session) {
        const statusClass = `status-${session.status}`;
        const progressWidth = session.progress || 0;
        
        return `
            <div class="session-card" data-session-id="${session.session_id}">
                <div class="session-header">
                    <span class="status-indicator ${statusClass}"></span>
                    <h6 class="session-title">${session.title}</h6>
                    <div class="session-actions">
                        <button class="btn btn-sm btn-outline-primary" onclick="dashboard.viewSession('${session.session_id}')">
                            View
                        </button>
                    </div>
                </div>
                <div class="session-meta">
                    <small class="text-muted">
                        Created: ${this.formatDate(session.created_at)} | 
                        Progress: ${session.scenarios_completed || 0}/${session.scenarios_total || 0}
                    </small>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${progressWidth}%"></div>
                </div>
                <div class="session-stats">
                    <span class="badge badge-info">Score: ${session.verification_score || 'N/A'}</span>
                    <span class="badge badge-secondary">Agent: ${session.agent_count || 0}</span>
                </div>
            </div>
        `;
    }

    updateAgents(agents) {
        const container = document.getElementById('agents-container');
        
        if (!agents || agents.length === 0) {
            container.innerHTML = '<p class="text-muted">No agents available</p>';
            return;
        }
        
        container.innerHTML = agents.map(agent => this.createAgentCard(agent)).join('');
    }

    createAgentCard(agent) {
        const statusClass = `agent-status ${agent.status}`;
        const agentColor = this.getAgentColor(agent.agent_type);
        
        return `
            <div class="agent-card">
                <div class="agent-header">
                    <div class="agent-icon" style="background-color: ${agentColor}">
                        ${agent.agent_name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                        <div class="agent-name">${agent.agent_name}</div>
                        <small class="text-muted">${agent.current_task || 'Idle'}</small>
                    </div>
                    <span class="${statusClass}">${agent.status.toUpperCase()}</span>
                </div>
                <div class="agent-metrics">
                    <div class="metric-row">
                        <span>Tasks:</span>
                        <span>${agent.tasks_completed}</span>
                    </div>
                    <div class="metric-row">
                        <span>CPU:</span>
                        <span>${agent.cpu_usage.toFixed(1)}%</span>
                    </div>
                    <div class="metric-row">
                        <span>Memory:</span>
                        <span>${agent.memory_usage.toFixed(1)}%</span>
                    </div>
                </div>
            </div>
        `;
    }

    updateSessionStatus(sessionId, data) {
        const session = this.sessions.find(s => s.session_id === sessionId);
        if (session) {
            Object.assign(session, data);
            this.updateSessions(this.sessions);
        }
    }

    updateAgentStatus(agentName, data) {
        const agentCard = document.querySelector(`[data-agent="${agentName}"]`);
        if (agentCard) {
            // Update agent card with new status
            agentCard.querySelector('.agent-status').className = `agent-status ${data.status}`;
            agentCard.querySelector('.agent-status').textContent = data.status.toUpperCase();
        }
    }

    updateConnectionStatus(status) {
        const statusElement = document.getElementById('connection-status');
        statusElement.className = `connection-status ${status}`;
        statusElement.textContent = status.toUpperCase();
    }

    subscribeToActiveSessions() {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        
        // Subscribe to all active sessions for real-time updates
        this.sessions.forEach(session => {
            this.ws.send(JSON.stringify({
                type: 'subscribe_session',
                session_id: session.session_id
            }));
        });
    }

    showNotification(data) {
        const container = document.getElementById('notifications-container');
        const notification = document.createElement('div');
        notification.className = `notification ${data.type || 'info'}`;
        notification.innerHTML = `
            <strong>${data.title || 'Notification'}</strong>
            <p>${data.message}</p>
        `;
        
        container.appendChild(notification);
        
        // Remove notification after 5 seconds
        setTimeout(() => {
            notification.remove();
        }, 5000);
    }

    showError(message) {
        this.showNotification({ type: 'error', title: 'Error', message });
    }

    showSuccess(message) {
        this.showNotification({ type: 'success', title: 'Success', message });
    }

    viewSession(sessionId) {
        window.location.href = `/session/${sessionId}`;
    }

    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleString();
    }

    getAgentColor(agentType) {
        const colors = {
            'manager': '#007bff',
            'senior': '#28a745',
            'junior': '#ffc107',
            'analyst': '#17a2b8',
            'sre': '#6f42c1',
            'accessibility': '#fd7e14',
            'api': '#20c997',
            'mobile': '#e83e8c',
            'compliance': '#6c757d',
            'chaos': '#dc3545'
        };
        return colors[agentType] || '#6c757d';
    }

    updateResourceChart(metrics) {
        // Implementation for resource usage charts
        // This would typically use Chart.js or similar library
        const ctx = document.getElementById('resource-chart');
        if (ctx && this.resourceChart) {
            this.resourceChart.data.datasets[0].data = [
                metrics.redis_memory_usage || 0,
                metrics.system_load || 0,
                metrics.redis_connections || 0
            ];
            this.resourceChart.update();
        }
    }

    startAutoRefresh() {
        // Refresh dashboard data every 30 seconds
        setInterval(() => {
            this.loadDashboard();
        }, 30000);
    }
}

// Initialize dashboard when DOM is ready
let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new Dashboard();
});

// Export for global access
window.dashboard = dashboard;