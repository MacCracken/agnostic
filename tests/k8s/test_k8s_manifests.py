"""
Kubernetes manifest and Helm values validation tests.

These tests validate YAML syntax, structural correctness, and security
posture of all k8s manifests and Helm values without requiring a live cluster.
"""

from pathlib import Path

import pytest
import yaml

# Root of the repository
REPO_ROOT = Path(__file__).parent.parent.parent
K8S_DIR = REPO_ROOT / "k8s"
MANIFESTS_DIR = K8S_DIR / "manifests"
HELM_DIR = K8S_DIR / "helm" / "agentic-qa"
HELM_TEMPLATES_DIR = HELM_DIR / "templates"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_yaml_file(path: Path) -> list[dict]:
    """Load a YAML file that may contain multiple documents (--- separator)."""
    with open(path) as f:
        content = f.read()
    docs = list(yaml.safe_load_all(content))
    return [d for d in docs if d is not None]


def all_manifest_files() -> list[Path]:
    """Return all YAML files in k8s/manifests/."""
    return sorted(MANIFESTS_DIR.glob("*.yaml"))


def all_helm_value_files() -> list[Path]:
    """Return all values*.yaml files in the Helm chart root."""
    return sorted(HELM_DIR.glob("values*.yaml"))


# ---------------------------------------------------------------------------
# YAML Syntax Tests
# ---------------------------------------------------------------------------


class TestYamlSyntax:
    """All manifest files must be parseable YAML."""

    @pytest.mark.parametrize(
        "manifest_path", all_manifest_files(), ids=lambda p: p.name
    )
    def test_manifest_is_valid_yaml(self, manifest_path: Path):
        docs = load_yaml_file(manifest_path)
        assert len(docs) >= 1, f"{manifest_path.name} parsed to zero documents"

    @pytest.mark.parametrize(
        "values_path", all_helm_value_files(), ids=lambda p: p.name
    )
    def test_helm_values_is_valid_yaml(self, values_path: Path):
        docs = load_yaml_file(values_path)
        assert len(docs) == 1, f"{values_path.name} should be a single YAML document"

    def test_kustomization_is_valid_yaml(self):
        docs = load_yaml_file(K8S_DIR / "kustomization.yaml")
        assert len(docs) == 1


# ---------------------------------------------------------------------------
# Manifest Structure Tests
# ---------------------------------------------------------------------------


class TestManifestStructure:
    """Every Kubernetes resource document must have the required top-level fields."""

    REQUIRED_FIELDS = {"apiVersion", "kind", "metadata"}

    @pytest.mark.parametrize(
        "manifest_path", all_manifest_files(), ids=lambda p: p.name
    )
    def test_required_top_level_fields(self, manifest_path: Path):
        docs = load_yaml_file(manifest_path)
        for doc in docs:
            missing = self.REQUIRED_FIELDS - set(doc.keys())
            assert not missing, (
                f"{manifest_path.name}: document kind={doc.get('kind', '?')} "
                f"missing required fields: {missing}"
            )

    @pytest.mark.parametrize(
        "manifest_path", all_manifest_files(), ids=lambda p: p.name
    )
    def test_namespace_set(self, manifest_path: Path):
        """All resources should target the agentic-qa namespace."""
        docs = load_yaml_file(manifest_path)
        for doc in docs:
            kind = doc.get("kind", "")
            # Namespace resource itself doesn't have namespace in metadata
            if kind in ("Namespace", "ClusterRole", "ClusterRoleBinding"):
                continue
            ns = doc.get("metadata", {}).get("namespace")
            assert ns == "agentic-qa", (
                f"{manifest_path.name}: {kind}/{doc.get('metadata', {}).get('name', '?')} "
                f"namespace is '{ns}', expected 'agentic-qa'"
            )


# ---------------------------------------------------------------------------
# Security Context Tests
# ---------------------------------------------------------------------------


class TestSecurityContexts:
    """Agent and WebGUI deployments must have hardened security contexts.

    Infrastructure services (redis, rabbitmq) use upstream images that require
    root access or writable filesystems and are excluded from these checks.
    """

    # Upstream images (Redis, RabbitMQ) require root / writable FS
    EXCLUDED_DEPLOYMENTS = {"redis", "rabbitmq"}

    def _get_deployments(self) -> list[tuple[str, dict]]:
        """Return (filename, deployment_doc) for non-infrastructure Deployments."""
        deployments = []
        for path in all_manifest_files():
            for doc in load_yaml_file(path):
                if doc.get("kind") == "Deployment":
                    name = doc.get("metadata", {}).get("name", "")
                    if name not in self.EXCLUDED_DEPLOYMENTS:
                        deployments.append((path.name, doc))
        return deployments

    def test_all_deployments_run_as_non_root(self):
        for fname, dep in self._get_deployments():
            pod_spec = dep.get("spec", {}).get("template", {}).get("spec", {})
            sec_ctx = pod_spec.get("securityContext", {})
            assert sec_ctx.get("runAsNonRoot") is True, (
                f"{fname}: deployment '{dep['metadata']['name']}' "
                "missing runAsNonRoot: true in pod securityContext"
            )

    def test_all_containers_read_only_root(self):
        for fname, dep in self._get_deployments():
            pod_spec = dep.get("spec", {}).get("template", {}).get("spec", {})
            containers = pod_spec.get("containers", [])
            for container in containers:
                sec_ctx = container.get("securityContext", {})
                assert sec_ctx.get("readOnlyRootFilesystem") is True, (
                    f"{fname}: container '{container.get('name', '?')}' in deployment "
                    f"'{dep['metadata']['name']}' missing readOnlyRootFilesystem: true"
                )

    def test_all_containers_drop_all_capabilities(self):
        for fname, dep in self._get_deployments():
            pod_spec = dep.get("spec", {}).get("template", {}).get("spec", {})
            containers = pod_spec.get("containers", [])
            for container in containers:
                caps = container.get("securityContext", {}).get("capabilities", {})
                dropped = caps.get("drop", [])
                assert "ALL" in dropped, (
                    f"{fname}: container '{container.get('name', '?')}' in deployment "
                    f"'{dep['metadata']['name']}' does not drop ALL capabilities"
                )

    def test_all_containers_no_privilege_escalation(self):
        for fname, dep in self._get_deployments():
            pod_spec = dep.get("spec", {}).get("template", {}).get("spec", {})
            containers = pod_spec.get("containers", [])
            for container in containers:
                sec_ctx = container.get("securityContext", {})
                assert sec_ctx.get("allowPrivilegeEscalation") is False, (
                    f"{fname}: container '{container.get('name', '?')}' in deployment "
                    f"'{dep['metadata']['name']}' missing allowPrivilegeEscalation: false"
                )


# ---------------------------------------------------------------------------
# Resource Limits Tests
# ---------------------------------------------------------------------------


class TestResourceLimits:
    """All containers must declare resource requests and limits."""

    def test_all_containers_have_resource_limits(self):
        for path in all_manifest_files():
            for doc in load_yaml_file(path):
                if doc.get("kind") != "Deployment":
                    continue
                pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
                for container in pod_spec.get("containers", []):
                    resources = container.get("resources", {})
                    assert "limits" in resources and "requests" in resources, (
                        f"{path.name}: container '{container.get('name', '?')}' in "
                        f"'{doc['metadata']['name']}' missing resource limits or requests"
                    )
                    limits = resources["limits"]
                    requests = resources["requests"]
                    assert "cpu" in limits and "memory" in limits, (
                        f"{path.name}: container '{container.get('name', '?')}' "
                        "missing cpu/memory in limits"
                    )
                    assert "cpu" in requests and "memory" in requests, (
                        f"{path.name}: container '{container.get('name', '?')}' "
                        "missing cpu/memory in requests"
                    )


# ---------------------------------------------------------------------------
# Health Probe Tests
# ---------------------------------------------------------------------------


class TestHealthProbes:
    """All agent and WebGUI deployments must have liveness and readiness probes."""

    EXCLUDED_DEPLOYMENTS = {"redis", "rabbitmq"}

    def test_all_deployments_have_liveness_probe(self):
        for path in all_manifest_files():
            for doc in load_yaml_file(path):
                if doc.get("kind") != "Deployment":
                    continue
                name = doc["metadata"]["name"]
                if name in self.EXCLUDED_DEPLOYMENTS:
                    continue
                pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
                for container in pod_spec.get("containers", []):
                    assert "livenessProbe" in container, (
                        f"{path.name}: deployment '{name}' container "
                        f"'{container.get('name', '?')}' missing livenessProbe"
                    )

    def test_all_deployments_have_readiness_probe(self):
        for path in all_manifest_files():
            for doc in load_yaml_file(path):
                if doc.get("kind") != "Deployment":
                    continue
                name = doc["metadata"]["name"]
                if name in self.EXCLUDED_DEPLOYMENTS:
                    continue
                pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
                for container in pod_spec.get("containers", []):
                    assert "readinessProbe" in container, (
                        f"{path.name}: deployment '{name}' container "
                        f"'{container.get('name', '?')}' missing readinessProbe"
                    )


# ---------------------------------------------------------------------------
# Kustomization Tests
# ---------------------------------------------------------------------------


class TestKustomization:
    """kustomization.yaml must reference all manifests that exist on disk."""

    def test_kustomization_references_all_manifests(self):
        kustomization = load_yaml_file(K8S_DIR / "kustomization.yaml")[0]
        referenced = set()
        for resource in kustomization.get("resources", []):
            referenced.add(Path(resource).name)

        on_disk = {p.name for p in MANIFESTS_DIR.glob("*.yaml")}
        missing = on_disk - referenced
        assert not missing, (
            f"kustomization.yaml does not reference these manifest files: {missing}"
        )

    def test_kustomization_no_dangling_references(self):
        kustomization = load_yaml_file(K8S_DIR / "kustomization.yaml")[0]
        on_disk = {p.name for p in MANIFESTS_DIR.glob("*.yaml")}
        for resource in kustomization.get("resources", []):
            fname = Path(resource).name
            assert fname in on_disk, (
                f"kustomization.yaml references '{resource}' which does not exist on disk"
            )


# ---------------------------------------------------------------------------
# HPA Tests
# ---------------------------------------------------------------------------


class TestHPA:
    """HPA resources must reference valid deployments."""

    EXPECTED_HPA_TARGETS = {
        "qa-manager",
        "senior-qa",
        "junior-qa",
        "qa-analyst",
        "security-compliance",
        "performance-agent",
        "agnostic",
    }

    def test_hpa_targets_exist(self):
        hpa_path = MANIFESTS_DIR / "horizontal-pod-autoscalers.yaml"
        hpa_docs = load_yaml_file(hpa_path)

        deployment_names = set()
        for path in all_manifest_files():
            for doc in load_yaml_file(path):
                if doc.get("kind") == "Deployment":
                    deployment_names.add(doc["metadata"]["name"])

        for hpa in hpa_docs:
            target = hpa.get("spec", {}).get("scaleTargetRef", {}).get("name")
            assert target in deployment_names, (
                f"HPA '{hpa['metadata']['name']}' targets deployment '{target}' "
                "which does not exist in manifests"
            )

    def test_all_agents_have_hpa(self):
        hpa_path = MANIFESTS_DIR / "horizontal-pod-autoscalers.yaml"
        hpa_docs = load_yaml_file(hpa_path)
        targets = {
            doc.get("spec", {}).get("scaleTargetRef", {}).get("name")
            for doc in hpa_docs
        }
        missing = self.EXPECTED_HPA_TARGETS - targets
        assert not missing, f"Missing HPAs for deployments: {missing}"

    def test_hpa_min_max_replicas_valid(self):
        hpa_path = MANIFESTS_DIR / "horizontal-pod-autoscalers.yaml"
        for hpa in load_yaml_file(hpa_path):
            spec = hpa.get("spec", {})
            min_r = spec.get("minReplicas", 0)
            max_r = spec.get("maxReplicas", 0)
            assert min_r >= 1, f"HPA '{hpa['metadata']['name']}' minReplicas < 1"
            assert max_r >= min_r, (
                f"HPA '{hpa['metadata']['name']}' maxReplicas ({max_r}) < minReplicas ({min_r})"
            )


# ---------------------------------------------------------------------------
# PDB Tests
# ---------------------------------------------------------------------------


class TestPDB:
    """PDB resources must cover all agent and WebGUI deployments."""

    EXPECTED_PDB_SELECTORS = {
        "qa-manager",
        "senior-qa",
        "junior-qa",
        "qa-analyst",
        "security-compliance",
        "performance-agent",
        "agnostic",
    }

    def test_all_agents_have_pdb(self):
        pdb_path = MANIFESTS_DIR / "pod-disruption-budgets.yaml"
        pdb_docs = load_yaml_file(pdb_path)
        selectors = {
            next(
                iter(
                    doc.get("spec", {})
                    .get("selector", {})
                    .get("matchLabels", {})
                    .values()
                )
            )
            for doc in pdb_docs
            if doc.get("spec", {}).get("selector", {}).get("matchLabels")
        }
        missing = self.EXPECTED_PDB_SELECTORS - selectors
        assert not missing, f"Missing PDBs for: {missing}"

    def test_pdb_min_available_at_least_one(self):
        pdb_path = MANIFESTS_DIR / "pod-disruption-budgets.yaml"
        for pdb in load_yaml_file(pdb_path):
            min_avail = pdb.get("spec", {}).get("minAvailable", 0)
            assert min_avail >= 1, (
                f"PDB '{pdb['metadata']['name']}' minAvailable is {min_avail}, expected >= 1"
            )


# ---------------------------------------------------------------------------
# NetworkPolicy Tests
# ---------------------------------------------------------------------------


class TestNetworkPolicies:
    """NetworkPolicy resources must exist for all major pod selectors."""

    EXPECTED_POLICIES = {
        "qa-agents-network-policy",
        "redis-network-policy",
        "rabbitmq-network-policy",
        "agnostic-network-policy",
    }

    def test_all_expected_policies_present(self):
        np_path = MANIFESTS_DIR / "network-policies.yaml"
        np_docs = load_yaml_file(np_path)
        found = {doc["metadata"]["name"] for doc in np_docs}
        missing = self.EXPECTED_POLICIES - found
        assert not missing, f"Missing NetworkPolicies: {missing}"

    def test_policies_have_both_ingress_egress_types(self):
        np_path = MANIFESTS_DIR / "network-policies.yaml"
        for np in load_yaml_file(np_path):
            policy_types = np.get("spec", {}).get("policyTypes", [])
            assert "Ingress" in policy_types, (
                f"NetworkPolicy '{np['metadata']['name']}' missing 'Ingress' policyType"
            )
            assert "Egress" in policy_types, (
                f"NetworkPolicy '{np['metadata']['name']}' missing 'Egress' policyType"
            )


# ---------------------------------------------------------------------------
# ResourceQuota Tests
# ---------------------------------------------------------------------------


class TestResourceQuota:
    """ResourceQuota must define all expected hard limits."""

    EXPECTED_QUOTA_KEYS = {
        "requests.cpu",
        "requests.memory",
        "limits.cpu",
        "limits.memory",
        "pods",
        "services",
        "secrets",
        "configmaps",
        "persistentvolumeclaims",
    }

    def test_quota_has_all_expected_limits(self):
        quota_path = MANIFESTS_DIR / "resource-quota.yaml"
        docs = load_yaml_file(quota_path)
        assert len(docs) == 1, "resource-quota.yaml should have exactly one document"
        hard = docs[0].get("spec", {}).get("hard", {})
        missing = self.EXPECTED_QUOTA_KEYS - set(hard.keys())
        assert not missing, f"ResourceQuota missing limits: {missing}"


# ---------------------------------------------------------------------------
# Helm values.yaml Tests
# ---------------------------------------------------------------------------


class TestHelmValues:
    """values.yaml must define all expected top-level configuration keys."""

    REQUIRED_TOP_LEVEL_KEYS = {
        "image",
        "namespace",
        "secrets",
        "redis",
        "rabbitmq",
        "agents",
        "webgui",
        "ingress",
        "env",
        "podSecurityContext",
        "securityContext",
        "serviceAccount",
        "autoscaling",
        "startupProbe",
        "networkPolicy",
        "podDisruptionBudget",
        "resourceQuota",
    }

    REQUIRED_AGENTS = {
        "qaManager",
        "seniorQa",
        "juniorQa",
        "qaAnalyst",
        "securityCompliance",
        "performance",
    }

    def _load_values(self) -> dict:
        return load_yaml_file(HELM_DIR / "values.yaml")[0]

    def test_required_top_level_keys_present(self):
        values = self._load_values()
        missing = self.REQUIRED_TOP_LEVEL_KEYS - set(values.keys())
        assert not missing, f"values.yaml missing top-level keys: {missing}"

    def test_all_agents_defined(self):
        values = self._load_values()
        agents = set(values.get("agents", {}).keys())
        missing = self.REQUIRED_AGENTS - agents
        assert not missing, f"values.yaml agents section missing: {missing}"

    def test_autoscaling_has_required_fields(self):
        values = self._load_values()
        autoscaling = values.get("autoscaling", {})
        for field in (
            "enabled",
            "minReplicas",
            "maxReplicas",
            "targetCPUUtilizationPercentage",
            "targetMemoryUtilizationPercentage",
            "juniorQaMaxReplicas",
            "webguiMaxReplicas",
        ):
            assert field in autoscaling, f"autoscaling.{field} missing from values.yaml"

    def test_network_policy_flag_present(self):
        values = self._load_values()
        assert "enabled" in values.get("networkPolicy", {}), (
            "values.yaml missing networkPolicy.enabled"
        )

    def test_pod_disruption_budget_fields(self):
        values = self._load_values()
        pdb = values.get("podDisruptionBudget", {})
        assert "enabled" in pdb, "values.yaml missing podDisruptionBudget.enabled"
        assert "minAvailable" in pdb, (
            "values.yaml missing podDisruptionBudget.minAvailable"
        )

    def test_resource_quota_fields(self):
        values = self._load_values()
        rq = values.get("resourceQuota", {})
        assert "enabled" in rq, "values.yaml missing resourceQuota.enabled"
        for field in ("requests", "limits", "pods"):
            assert field in rq, f"values.yaml missing resourceQuota.{field}"

    def test_security_context_hardened(self):
        values = self._load_values()
        sec = values.get("securityContext", {})
        assert sec.get("readOnlyRootFilesystem") is True, (
            "values.yaml securityContext.readOnlyRootFilesystem must be true"
        )
        assert sec.get("allowPrivilegeEscalation") is False, (
            "values.yaml securityContext.allowPrivilegeEscalation must be false"
        )
        assert sec.get("runAsNonRoot") is True, (
            "values.yaml securityContext.runAsNonRoot must be true"
        )
        caps = sec.get("capabilities", {}).get("drop", [])
        assert "ALL" in caps, (
            "values.yaml securityContext.capabilities.drop must include ALL"
        )
