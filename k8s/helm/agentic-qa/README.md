# Agentic QA Helm Chart

This directory contains the Helm chart for deploying the Agentic QA Team System to Kubernetes.

## Prerequisites

- Kubernetes cluster (v1.20+)
- Helm 3.x
- `kubectl` configured to connect to your cluster
- Sufficient resources (minimum 4 CPU, 8GB RAM)

## Quick Start

1. **Create namespace and set up secrets:**
   ```bash
   # Create namespace (if not using helm to create it)
   kubectl create namespace agentic-qa
   
   # Set your OpenAI API key (base64 encoded)
   echo -n "your-openai-api-key" | base64
   # Copy the output and update the secrets.yaml file
   ```

2. **Install the chart:**
   ```bash
   # Install with default values
   helm install agentic-qa ./k8s/helm/agentic-qa --namespace agentic-qa
   
   # Install with custom values
   helm install agentic-qa ./k8s/helm/agentic-qa \
     --namespace agentic-qa \
     --set secrets.openaiApiKey=$(echo -n "your-openai-key" | base64) \
     --set ingress.enabled=true \
     --set ingress.host=qa.yourdomain.com
   ```

3. **Verify deployment:**
   ```bash
   # Check pod status
   kubectl get pods -n agentic-qa
   
   # Check services
   kubectl get services -n agentic-qa
   
   # Access the web interface
   kubectl port-forward service/agnostic-service 8000:8000 -n agentic-qa
   ```

## Chart Templates

The chart includes templates for all system components:

| Template | Description |
|---|---|
| `qa-manager.yaml` | QA Manager orchestrator deployment + service |
| `senior-qa.yaml` | Senior QA Engineer agent deployment + service |
| `junior-qa.yaml` | Junior QA Worker agent deployment + service |
| `qa-analyst.yaml` | QA Analyst agent deployment + service |
| `security-compliance.yaml` | Security & Compliance agent deployment + service |
| `performance.yaml` | Performance & Resilience agent deployment + service |
| `webgui.yaml` | Agnostic (Chainlit WebGUI) deployment + service |
| `rabbitmq.yaml` | RabbitMQ deployment + PVC + service |
| `redis.yaml` | Redis deployment + PVC + service |
| `serviceaccount.yaml` | ServiceAccount for pod identity |
| `ingress.yaml` | Ingress for external WebGUI access |
| `network-policy.yaml` | NetworkPolicies for least-privilege traffic isolation |
| `hpa.yaml` | HorizontalPodAutoscalers for all agents + Agnostic |
| `pdb.yaml` | PodDisruptionBudgets for HA during node maintenance |
| `resource-quota.yaml` | Namespace-level resource quota (opt-in) |
| `configmap.yaml` | Shared environment configuration |
| `secret.yaml` | OpenAI API key and RabbitMQ password |

## Configuration

Key configuration options in `values.yaml`:

- **Infrastructure**: Enable/disable Redis and RabbitMQ
- **Agents**: Configure which QA agents to deploy and their resource limits
- **WebGUI**: Frontend service configuration
- **Ingress**: External access configuration (WebGUI only; RabbitMQ management is not exposed)
- **Security**: Hardened by default — read-only root filesystem, drop all capabilities, seccomp RuntimeDefault
- **Resources**: CPU and memory limits for each component (aligned with docker-compose)
- **Autoscaling** (`autoscaling.*`): HPA for all deployments — CPU/memory targets, min/max replicas
- **Network Policies** (`networkPolicy.enabled`): Least-privilege ingress/egress rules per pod type
- **Pod Disruption Budgets** (`podDisruptionBudget.*`): Minimum available pods during voluntary disruptions
- **Resource Quota** (`resourceQuota.*`): Namespace-level caps on CPU, memory, pods, etc. (disabled by default)

## Scaling

You can scale individual agents:

```bash
# Scale junior QA workers
helm upgrade agentic-qa ./k8s/helm/agentic-qa \
  --namespace agentic-qa \
  --set agents.juniorQa.replicaCount=3

# Enable autoscaling
helm upgrade agentic-qa ./k8s/helm/agentic-qa \
  --namespace agentic-qa \
  --set autoscaling.enabled=true
```

## Monitoring

- Check logs: `kubectl logs -f deployment/agnostic -n agentic-qa`
- Monitor resource usage: `kubectl top pods -n agentic-qa`
- Access RabbitMQ management: `kubectl port-forward service/rabbitmq-service 15672:15672 -n agentic-qa`

## Uninstall

```bash
helm uninstall agentic-qa --namespace agentic-qa
```

## Environment-Specific Values

Pre-built values files are provided for common environments:

```bash
# Development (minimal resources, autoscaling and quotas off)
helm install agentic-qa ./k8s/helm/agentic-qa -f values-dev.yaml

# Production (full HA, HPA, quotas, TLS)
helm install agentic-qa ./k8s/helm/agentic-qa -f values-prod.yaml
```

## Troubleshooting

1. **Pods not starting**: Check resource limits and node availability (`kubectl describe pod <name> -n agentic-qa`)
2. **Connection issues**: Verify service names and check network policies (`kubectl get networkpolicies -n agentic-qa`)
3. **Secret errors**: Ensure OpenAI API key is properly base64 encoded
4. **HPA not scaling**: Confirm `metrics-server` is running (`kubectl get deployment metrics-server -n kube-system`)
5. **Node drain blocked**: A PDB with `minAvailable: 1` on a single-replica pod blocks drain — scale to 2 replicas first or set `podDisruptionBudget.enabled=false` temporarily

For more details, see the [Kubernetes Deployment Guide](../../docs/deployment/kubernetes.md).