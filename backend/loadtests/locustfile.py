"""HTTP load tests for public analytics endpoints.

Run against a warmed API with at least one imported season, e.g.:

  cd backend && uv run locust -f loadtests/locustfile.py --host http://localhost:8317
"""

from locust import HttpUser, between, task


class AnalyticsUser(HttpUser):
    wait_time = between(0.05, 0.2)

    @task(4)
    def team_comparison(self) -> None:
        self.client.get(
            "/api/v1/analytics/team-comparison",
            params={"team_a": "KC", "team_b": "PHI", "season": 2024},
            name="/api/v1/analytics/team-comparison",
        )

    @task(3)
    def situational(self) -> None:
        self.client.get(
            "/api/v1/analytics/situational",
            params={"team": "DET", "season": 2024, "group_by": "down"},
            name="/api/v1/analytics/situational",
        )

    @task(2)
    def efficiency(self) -> None:
        self.client.get(
            "/api/v1/analytics/efficiency",
            params={"team": "DET", "season": 2024},
            name="/api/v1/analytics/efficiency",
        )

    @task(1)
    def trends(self) -> None:
        self.client.get(
            "/api/v1/analytics/trends",
            params={"team": "DET", "season": 2024},
            name="/api/v1/analytics/trends",
        )
