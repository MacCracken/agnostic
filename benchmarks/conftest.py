"""Shared fixtures for the benchmark suite."""

from __future__ import annotations

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--crewai-url",
        default=os.getenv("CREWAI_BENCH_URL", "http://localhost:8000"),
        help="Base URL for the Agnostic (CrewAI) server",
    )
    parser.addoption(
        "--agnosai-url",
        default=os.getenv("AGNOSAI_BENCH_URL", "http://localhost:8080"),
        help="Base URL for the AgnosAI Rust server",
    )
    parser.addoption(
        "--ollama-url",
        default=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        help="Base URL for the Ollama server",
    )
    parser.addoption(
        "--ollama-model",
        default=os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b"),
        help="Ollama model to use for benchmarks",
    )
    parser.addoption(
        "--bench-rounds",
        default=int(os.getenv("BENCH_ROUNDS", "5")),
        type=int,
        help="Number of rounds per benchmark",
    )
    parser.addoption(
        "--api-key",
        default=os.getenv("AGNOSTIC_API_KEY", ""),
        help="API key for both servers",
    )


@pytest.fixture(scope="session")
def crewai_url(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--crewai-url")


@pytest.fixture(scope="session")
def agnosai_url(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--agnosai-url")


@pytest.fixture(scope="session")
def ollama_url(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--ollama-url")


@pytest.fixture(scope="session")
def ollama_model(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--ollama-model")


@pytest.fixture(scope="session")
def bench_rounds(request: pytest.FixtureRequest) -> int:
    return request.config.getoption("--bench-rounds")


@pytest.fixture(scope="session")
def api_key(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--api-key")
