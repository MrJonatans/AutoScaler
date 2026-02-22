from locust import HttpUser, task, between
import random

class LoadTestUser(HttpUser):
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks

    @task
    def load_endpoint(self):
        # Random n between 500 and 1500 to vary load
        n = random.randint(500, 1500)
        self.client.get(f"/load?n={n}")

# For running: locust -f tests/integration/load_test.py --host=http://localhost:8000
# Then access web UI at http://localhost:8089 and start test with ramp-up users