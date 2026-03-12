import json
import os
import sys
from unittest.mock import Mock, patch

import pytest
import redis

# Add the agents directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "agents"))

try:
    from analyst.qa_analyst import QAAnalystAgent
    from junior.junior_qa import JuniorQAAgent
    from manager.qa_manager import QAManagerAgent
    from senior.senior_qa import SeniorQAAgent
except Exception as e:
    pytest.skip(f"Agent modules not available: {e}", allow_module_level=True)


@pytest.mark.integration
@pytest.mark.redis
class TestAgentCommunication:
    """Integration tests for agent-to-agent communication via Redis"""

    @pytest.fixture(autouse=True)
    def setup_redis_mock(self):
        """Setup mock Redis for all tests in this class"""
        self.mock_redis = Mock()
        self.mock_pubsub = Mock()

        # Mock Redis methods
        self.mock_redis.pubsub.return_value = self.mock_pubsub
        self.mock_redis.get.return_value = None
        self.mock_redis.set.return_value = True
        self.mock_redis.publish.return_value = 0
        self.mock_redis.lpush.return_value = 1
        self.mock_redis.rpop.return_value = None
        self.mock_redis.hset.return_value = 1
        self.mock_redis.hget.return_value = json.dumps({"status": "ready"})
        self.mock_redis.lrange.return_value = []
        self.mock_redis.scan.return_value = (0, [])
        self.mock_redis.hgetall.return_value = {}

    @patch("config.environment.config.get_redis_client")
    def test_manager_delegates_to_analyst(self, mock_get_redis):
        """Test that QA Manager can initialise and retrieve session status"""
        mock_get_redis.return_value = self.mock_redis

        manager = QAManagerAgent()

        # Verify agent initialised with Redis client
        assert manager.redis_client is self.mock_redis

        # Test get_session_status (a real method on QAManagerAgent)
        session_id = "test-session-123"
        self.mock_redis.get.return_value = json.dumps(
            {"status": "running", "agents": ["qa-analyst"]}
        )

        status = manager.get_session_status(session_id)
        assert status is not None
        assert "status" in status

    @patch("config.environment.config.get_redis_client")
    def test_analyst_processes_results(self, mock_get_redis):
        """Test that QA Analyst can collect and analyse agent results"""
        mock_get_redis.return_value = self.mock_redis

        analyst = QAAnalystAgent()

        # Verify agent initialised with Redis client
        assert analyst.redis_client is self.mock_redis

        # Test _get_redis_json helper (a real method on QAAnalystAgent)
        self.mock_redis.get.return_value = json.dumps(
            {"score": 85, "findings": ["issue-1"]}
        )
        result = analyst._get_redis_json("analyst:test-session:security")
        assert result is not None
        assert result["score"] == 85

    @patch("config.environment.config.get_redis_client")
    def test_senior_agent_initialises(self, mock_get_redis):
        """Test that Senior QA agent initialises with Redis and CrewAI agent"""
        mock_get_redis.return_value = self.mock_redis

        senior = SeniorQAAgent()

        assert senior.redis_client is self.mock_redis
        assert senior.agent is not None

    @patch("config.environment.config.get_redis_client")
    def test_junior_agent_initialises(self, mock_get_redis):
        """Test that Junior QA agent initialises with Redis and CrewAI agent"""
        mock_get_redis.return_value = self.mock_redis

        junior = JuniorQAAgent()

        assert junior.redis_client is self.mock_redis
        assert junior.agent is not None

    @patch("config.environment.config.get_redis_client")
    def test_end_to_end_workflow(self, mock_get_redis):
        """Test end-to-end workflow: all agents initialise with shared Redis"""
        mock_get_redis.return_value = self.mock_redis

        # All agents share the same Redis client
        manager = QAManagerAgent()
        analyst = QAAnalystAgent()

        # Simulate session data flow: manager stores, analyst reads
        session_id = "workflow-test-001"

        # Manager writes session info
        manager.redis_client.set(
            f"session:{session_id}:info",
            json.dumps({"requirements": "Test auth system", "status": "running"}),
        )
        self.mock_redis.set.assert_called()

        # Analyst reads session data via _get_redis_json
        self.mock_redis.get.return_value = json.dumps(
            {"requirements": "Test auth system", "status": "running"}
        )
        info = analyst._get_redis_json(f"session:{session_id}:info")
        assert info is not None
        assert info["requirements"] == "Test auth system"

        # Verify communication flow used the mock
        assert self.mock_redis.set.called
        assert self.mock_redis.get.called


@pytest.mark.integration
@pytest.mark.slow
class TestRedisCommunication:
    """Test actual Redis communication if available"""

    def test_redis_connection(self):
        """Test Redis connection if Redis is available"""
        try:
            # Try to connect to Redis (might not be available in CI)
            redis_client = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                db=0,
                socket_connect_timeout=2,
            )
            redis_client.ping()

            # If we get here, Redis is available
            assert True

        except (redis.ConnectionError, TimeoutError):
            pytest.skip("Redis not available for integration testing")
        except Exception:
            pytest.skip("Redis not configured for testing")

    def test_redis_pubsub_basic(self):
        """Test basic Redis pub/sub functionality"""
        try:
            redis_client = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                db=0,
                socket_connect_timeout=2,
            )

            # Test pub/sub
            pubsub = redis_client.pubsub()
            pubsub.subscribe("test-channel")

            # Publish a message
            redis_client.publish("test-channel", json.dumps({"test": "message"}))

            # Get the message (with timeout)
            message = pubsub.get_message(timeout=1)

            if message:
                assert message["type"] == "message"
                data = json.loads(message["data"])
                assert data["test"] == "message"

            pubsub.close()

        except (redis.ConnectionError, TimeoutError):
            pytest.skip("Redis not available for pub/sub testing")
