import os

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379").rstrip("/")
TEST_BROKER_URL = f"{TEST_REDIS_URL}/14"
TEST_CACHE_URL = f"{TEST_REDIS_URL}/15"

# Set when the package is imported, i.e. before conftest imports the app and before
# anything imports app.worker.celery_app (both read settings at import time).
os.environ["BROKER_URL"] = TEST_BROKER_URL
os.environ["CACHE_URL"] = TEST_CACHE_URL
