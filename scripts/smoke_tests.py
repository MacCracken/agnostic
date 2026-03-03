#!/usr/bin/env python3
"""
Smoke tests for post-deployment verification.
Tests basic functionality of the QA System.
"""

import os
import sys

import requests

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_webgui_health() -> bool:
    """Test WebGUI health endpoint."""
    try:
        response = requests.get("http://localhost:8000/health", timeout=10)
        if response.status_code == 200:
            print("✓ WebGUI health check passed")
            return True
        else:
            print(f"✗ WebGUI health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ WebGUI health check error: {e}")
        return False


def test_redis_connection() -> bool:
    """Test Redis connection."""
    try:
        import redis
        client = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=5)
        client.ping()
        print("✓ Redis connection test passed")
        return True
    except Exception as e:
        print(f"✗ Redis connection test failed: {e}")
        return False


def test_rabbitmq_connection() -> bool:
    """Test RabbitMQ connection."""
    try:
        import pika
        rmq_user = os.getenv("RABBITMQ_USER", "")
        rmq_pass = os.getenv("RABBITMQ_PASSWORD", "")
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host='localhost',
                port=5672,
                credentials=pika.PlainCredentials(rmq_user, rmq_pass),
                socket_timeout=5
            )
        )
        connection.close()
        print("✓ RabbitMQ connection test passed")
        return True
    except Exception as e:
        print(f"✗ RabbitMQ connection test failed: {e}")
        return False


def test_agent_configuration() -> bool:
    """Test agent configuration."""
    try:
        from config.environment import config

        # Test configuration validation
        validation = config.validate_required_env_vars()
        if all(validation.values()):
            print("✓ Agent configuration validation passed")
            return True
        else:
            missing = [k for k, v in validation.items() if not v]
            print(f"✗ Agent configuration validation failed: {missing}")
            return False
    except Exception as e:
        print(f"✗ Agent configuration test failed: {e}")
        return False


def test_basic_functionality() -> bool:
    """Test basic system functionality."""
    try:
        # Test configuration module
        from config.environment import config

        # Test Redis client creation
        config.get_redis_client()

        # Test Celery app creation
        config.get_celery_app('smoke_test')

        print("✓ Basic functionality test passed")
        return True
    except Exception as e:
        print(f"✗ Basic functionality test failed: {e}")
        return False


def main():
    """Run all smoke tests."""
    print("Running smoke tests...")

    tests = [
        ("WebGUI Health", test_webgui_health),
        ("Redis Connection", test_redis_connection),
        ("RabbitMQ Connection", test_rabbitmq_connection),
        ("Agent Configuration", test_agent_configuration),
        ("Basic Functionality", test_basic_functionality),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\nRunning {test_name} test...")
        result = test_func()
        results.append((test_name, result))

    # Summary
    print("\n" + "=" * 50)
    print("SMOKE TEST SUMMARY")
    print("=" * 50)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name:.<30} {status}")
        if result:
            passed += 1

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("All smoke tests passed!")
        return 0
    else:
        print(f"{total - passed} smoke test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
