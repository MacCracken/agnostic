# Kubernetes Deployment Guide

This guide provides comprehensive instructions for deploying the Agentic QA Team System to Kubernetes using both direct manifests and Helm charts.

## Prerequisites

### System Requirements
- **Kubernetes cluster**: v1.20+ (local: minikube, kind; cloud: EKS, GKE, AKS)
- **Helm**: v3.x (for Helm-based deployment)
- **kubectl**: Configured to connect to your cluster
- **Memory**: Minimum 8GB RAM for production deployment
- **Storage**: 20GB+ for persistent volumes

### Required Secrets
- **OpenAI API Key**: For LLM functionality
- **RabbitMQ Password**: For message broker authentication

## Option 1: Direct Kubernetes Manifests

### Step 1: Set Up Namespace and Secrets

```bash
# Create namespace
kubectl create namespace agentic-qa

# Set OpenAI API key (base64 encoded)
echo -n "your-openai-api-key" | base64

# Create secrets with your encoded values
kubectl create secret generic qa-secrets \
  --from-literal=openai-api-key=YOUR_ENCODED_OPENAI_KEY \
  --from-literal=rabbitmq-password=$(echo -n "your-rabbitmq-password" | base64) \
  -n agentic-qa
```

### Step 2: Deploy Infrastructure

```bash
# Apply all manifests using Kustomize
kubectl apply -k k8s/

# Or apply manifests individually
kubectl apply -f k8s/manifests/namespace.yaml
kubectl apply -f k8s/manifests/config.yaml
kubectl apply -f k8s/manifests/redis.yaml
kubectl apply -f k8s/manifests/rabbitmq.yaml
```

### Step 3: Deploy Agents and WebGUI

```bash
# Deploy all agents and web interface
kubectl apply -f k8s/manifests/qa-manager.yaml
kubectl apply -f k8s/manifests/qa-agents-1.yaml  # All 5 non-manager agents
kubectl apply -f k8s/manifests/webgui.yaml

# Optional: Add ingress for external access
kubectl apply -f k8s/manifests/ingress.yaml

# Production readiness (apply after agents are running)
kubectl apply -f k8s/manifests/network-policies.yaml
kubectl apply -f k8s/manifests/horizontal-pod-autoscalers.yaml
kubectl apply -f k8s/manifests/pod-disruption-budgets.yaml
kubectl apply -f k8s/manifests/resource-quota.yaml
```

> **Tip**: When using `kubectl apply -k k8s/`, all of the above including production-readiness manifests are applied in one step.

### Step 4: Verify Deployment

```bash
# Check pod status
kubectl get pods -n agentic-qa -w

# Check services
kubectl get services -n agentic-qa

# Check persistent volumes
kubectl get pvc -n agentic-qa

# Access WebGUI (port forwarding)
kubectl port-forward service/webgui-service 8000:8000 -n agentic-qa
# Open http://localhost:8000

# Access RabbitMQ Management
kubectl port-forward service/rabbitmq-service 15672:15672 -n agentic-qa
# Open http://localhost:15672 (guest/guest)
```

## Option 2: Helm Chart (Recommended)

### Step 1: Install Chart

```bash
# Install with default values
helm install agentic-qa ./k8s/helm/agentic-qa \
  --namespace agentic-qa \
  --create-namespace \
  --set secrets.openaiApiKey=$(echo -n "your-openai-key" | base64)

# Or create values file first
cat > qa-values.yaml << EOF
secrets:
  openaiApiKey: "$(echo -n "your-openai-key" | base64)"
  
ingress:
  enabled: true
  host: qa.yourdomain.com
  
agents:
  juniorQa:
    replicaCount: 3  # Scale up workers
  
webgui:
  service:
    type: LoadBalancer
EOF

# Install with custom values
helm install agentic-qa ./k8s/helm/agentic-qa \
  --namespace agentic-qa \
  --create-namespace \
  -f qa-values.yaml
```

### Step 2: Configure External Access

```bash
# Get LoadBalancer IP (if using cloud provider)
kubectl get service webgui-service -n agentic-qa

# Or use port forwarding for local access
kubectl port-forward service/webgui-service 8000:8000 -n agentic-qa
```

## Configuration Options

### Agent Scaling
```bash
# Scale specific agents manually
helm upgrade agentic-qa ./k8s/helm/agentic-qa \
  --namespace agentic-qa \
  --set agents.juniorQa.replicaCount=5 \
  --set agents.seniorQa.replicaCount=2

# HPA is enabled by default (autoscaling.enabled=true)
# Adjust thresholds:
helm upgrade agentic-qa ./k8s/helm/agentic-qa \
  --namespace agentic-qa \
  --set autoscaling.minReplicas=2 \
  --set autoscaling.maxReplicas=10 \
  --set autoscaling.juniorQaMaxReplicas=10

# Disable HPA (use fixed replicas only):
helm upgrade agentic-qa ./k8s/helm/agentic-qa \
  --namespace agentic-qa \
  --set autoscaling.enabled=false
```

> **Note**: HPA requires the [Kubernetes Metrics Server](https://github.com/kubernetes-sigs/metrics-server) to be installed. For kind/minikube, enable it with `minikube addons enable metrics-server`.

### Resource Configuration
```yaml
# In values.yaml
agents:
  qaManager:
    resources:
      requests:
        memory: "1Gi"
        cpu: "500m"
      limits:
        memory: "2Gi"
        cpu: "1000m"
```

### Ingress Configuration
```yaml
# Enable HTTPS and custom domain
ingress:
  enabled: true
  className: "nginx"
  host: "qa.yourdomain.com"
  tls:
    enabled: true
    secretName: "agentic-qa-tls"
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
```

## Monitoring and Troubleshooting

### Health Checks
```bash
# Check pod health
kubectl get pods -n agentic-qa -o wide

# View pod logs
kubectl logs -f deployment/qa-manager -n agentic-qa
kubectl logs -f deployment/webgui -n agentic-qa

# Check events
kubectl get events -n agentic-qa --sort-by=.metadata.creationTimestamp
```

### Resource Monitoring
```bash
# Resource usage
kubectl top pods -n agentic-qa

# Describe specific pod
kubectl describe pod <pod-name> -n agentic-qa

# Check resource limits
kubectl describe deployment qa-manager -n agentic-qa
```

### Common Issues

**Pods not starting:**
```bash
# Check resource limits
kubectl describe pod <pod-name> -n agentic-qa | grep -A 10 "Events"

# Check node resources
kubectl describe nodes
```

**Connection issues:**
```bash
# Check service endpoints
kubectl get endpoints -n agentic-qa

# Test network connectivity
kubectl exec -it <pod-name> -n agentic-qa -- nslookup redis-service
```

**Secret errors:**
```bash
# Verify secrets exist
kubectl get secrets -n agentic-qa

# Decode secret values
kubectl get secret qa-secrets -n agentic-qa -o yaml
```

## Production Best Practices

### Security

All pods run with hardened security contexts by default:

```yaml
# Pod-level security context
podSecurityContext:
  fsGroup: 1000
  runAsNonRoot: true
  runAsUser: 1000

# Container-level security context
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
  seccompProfile:
    type: RuntimeDefault

# Writable directories use emptyDir volumes:
# /tmp and /app/logs are mounted as emptyDir for each pod
```

```yaml
# Network policies (if supported)
networkPolicy:
  enabled: true
```

### High Availability (PodDisruptionBudgets)

PDBs are enabled by default and ensure at least one pod is always available during voluntary disruptions (node drains, cluster upgrades):

```bash
# View PDB status
kubectl get pdb -n agentic-qa

# Disable PDBs (not recommended in production)
helm upgrade agentic-qa ./k8s/helm/agentic-qa \
  --namespace agentic-qa \
  --set podDisruptionBudget.enabled=false
```

> **Note**: A `minAvailable: 1` PDB on a single-replica deployment will block `kubectl drain` until the pod is rescheduled. Ensure your cluster has spare capacity or temporarily scale to 2 replicas before draining.

### Network Policies

NetworkPolicies enforce least-privilege traffic between pods:

| Policy | Allows Ingress From | Allows Egress To |
|---|---|---|
| `qa-agents-network-policy` | Other agents, WebGUI, ingress-nginx | Redis, RabbitMQ, DNS, public internet (LLM APIs) |
| `redis-network-policy` | Agents, WebGUI | None |
| `rabbitmq-network-policy` | Agents, WebGUI | None |
| `webgui-network-policy` | ingress-nginx | Redis, RabbitMQ, agents (health), DNS, public internet |

```bash
# View network policies
kubectl get networkpolicies -n agentic-qa

# Disable network policies (e.g., on clusters without CNI support)
helm upgrade agentic-qa ./k8s/helm/agentic-qa \
  --namespace agentic-qa \
  --set networkPolicy.enabled=false
```

> **CNI requirement**: NetworkPolicies require a CNI plugin that supports them (Calico, Cilium, WeaveNet, GKE Dataplane V2, AWS VPC CNI with network policy enabled).

### Resource Quotas

Namespace-level quotas cap total resource consumption and prevent runaway pods from starving other services:

```bash
# View current quota usage
kubectl describe resourcequota agentic-qa-quota -n agentic-qa

# Enable quota via Helm (disabled by default to allow minimal local deployments)
helm upgrade agentic-qa ./k8s/helm/agentic-qa \
  --namespace agentic-qa \
  --set resourceQuota.enabled=true
```

### Backup and Recovery
```bash
# Backup Redis data
kubectl exec -it deployment/redis -n agentic-qa -- redis-cli BGSAVE

# Backup persistent volumes
kubectl get pvc -n agentic-qa
# Use cloud provider backup solutions
```

### Multi-Environment Deployment

Example values files are provided for common deployment scenarios:

```bash
# Development (reduced resources, no HPA, no quota)
helm install agentic-qa-dev ./k8s/helm/agentic-qa \
  --namespace agentic-qa-dev \
  --create-namespace \
  -f k8s/helm/agentic-qa/values-dev.yaml \
  --set secrets.openaiApiKey=$(echo -n "your-key" | base64)

# Production (full HA, HPA, quota, TLS ingress)
helm install agentic-qa-prod ./k8s/helm/agentic-qa \
  --namespace agentic-qa-prod \
  --create-namespace \
  -f k8s/helm/agentic-qa/values-prod.yaml \
  --set secrets.openaiApiKey=$(echo -n "your-key" | base64) \
  --set secrets.rabbitmqPasswordPlain=your-password
```

See `k8s/helm/agentic-qa/values-dev.yaml` and `values-prod.yaml` for full annotated examples.

## Upgrades and Maintenance

### Upgrade Deployment
```bash
# Upgrade with Helm
helm upgrade agentic-qa ./k8s/helm/agentic-qa \
  --namespace agentic-qa \
  -f qa-values.yaml

# Rollback if needed
helm rollback agentic-qa 1 -n agentic-qa
```

### Maintenance Windows
```bash
# Scale down for maintenance
kubectl scale deployment --all --replicas=0 -n agentic-qa

# Scale back up
kubectl scale deployment qa-manager --replicas=1 -n agentic-qa
kubectl scale deployment webgui --replicas=1 -n agentic-qa
# ... other deployments
```

## Uninstallation

### Remove Helm Deployment
```bash
helm uninstall agentic-qa --namespace agentic-qa
kubectl delete namespace agentic-qa
```

### Remove Manifest Deployment
```bash
kubectl delete -k k8s/
kubectl delete namespace agentic-qa
```

## Next Steps

- Set up monitoring with Prometheus and Grafana
- Configure centralized logging with ELK stack
- Implement backup strategies for persistent data
- Set up CI/CD pipelines for automated deployments
- Configure alerting for system health

For additional help, check the [Helm chart README](../../k8s/helm/agentic-qa/README.md) or the [Development Setup](../development/setup.md).