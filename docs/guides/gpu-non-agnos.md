# GPU Features on Non-AGNOS Hosts

Agnostic's GPU features are **OS-agnostic by design**. They work on any Linux or Windows host with NVIDIA drivers installed. Running on AGNOS provides additional benefits, but is not required.

## What works everywhere

| Feature | How it works | Requirements |
|---------|-------------|--------------|
| GPU detection | `nvidia-smi` CLI probe | NVIDIA drivers + `nvidia-smi` in PATH |
| GPU-aware scheduling | Agents assigned to GPUs by VRAM/requirements | Any host with GPU |
| CUDA_VISIBLE_DEVICES | Per-agent GPU isolation | NVIDIA drivers |
| GPU memory budgets | `gpu_memory_budget_mb` on crew requests | Any host with GPU |
| Multi-GPU spread | Agents spread across devices | Multi-GPU host |
| VRAM monitoring | Before/after snapshots per agent | Any host with GPU |
| Local LLM inference | Routes to Ollama/vLLM when GPU available | Local inference server |
| GPU tool registration | `@register_gpu_tool` decorator | None (code-level) |
| Cross-crew GPU tracking | `GPUSlotTracker` reservations | None (in-process) |
| GPU API endpoints | `/api/v1/gpu/status`, `/gpu/memory`, etc. | Any host |

## What AGNOS adds

| Feature | AGNOS benefit |
|---------|---------------|
| `agnosys` GPU probe | Richer hardware data via `/var/lib/agnosys/gpu.json` — preferred over `nvidia-smi` when available |
| Fleet GPU aggregation | `GET /api/v1/fleet/gpu` aggregates across fleet nodes |
| GPU status in HUD | aethersafha displays VRAM bars and utilization |
| GPU placement in crew cards | HUD shows which agents are GPU vs CPU |
| agnoshi GPU intents | Voice/text commands: "show gpu status" |
| Fleet scheduling policies | `gpu-affinity`, `balanced`, `cost-aware` across fleet |
| Daimon event forwarding | GPU allocation events in fleet-wide event stream |
| GPU budget recommendations | Recommended `gpu_memory_budget_mb` from observed usage |

## Configuration

All GPU features are controlled via environment variables:

```bash
# GPU detection (works everywhere)
AGNOS_GPU_ENABLED=true              # Master switch (default: true)
AGNOS_GPU_PROBE_INTERVAL=30         # Seconds between re-probes

# Local inference (works everywhere)
AGNOS_LOCAL_INFERENCE_ENABLED=false  # Route eligible models locally
AGNOS_LOCAL_INFERENCE_URL=http://localhost:11434  # Ollama/vLLM URL
AGNOS_LOCAL_INFERENCE_PROVIDER=ollama             # ollama, vllm, openai
AGNOS_LOCAL_INFERENCE_MODELS=llama3.1:8b,nomic-embed-text
AGNOS_LOCAL_INFERENCE_MAX_PARAMS_B=14             # Max model size for local
AGNOS_LOCAL_INFERENCE_GPU_MIN_FREE_MB=2000        # Min VRAM to route locally

# AGNOS-specific (ignored on non-AGNOS hosts)
AGNOS_GPU_PROBE_PATH=/var/lib/agnosys/gpu.json   # agnosys probe file path
```

## Behavior on hosts without GPU

When no GPU is detected:
- `gpu_required=False` agents run on CPU (normal)
- `gpu_required=True` agents fall back to CPU with a warning
- `gpu_required=True, gpu_strict=True` agents cause the crew to fail
- `GET /api/v1/gpu/status` returns `{"available": false, "error": "..."}`
- Local inference offload is disabled (falls back to cloud)
- All other Agnostic features work normally
