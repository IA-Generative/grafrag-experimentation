from locust import HttpUser, between, task


class GraphRAGUser(HttpUser):
    wait_time = between(1, 3)

    @task(2)
    def health(self) -> None:
        self.client.get("/healthz")

    @task(1)
    def query(self) -> None:
        self.client.post(
            "/query",
            json={"question": "Summarize the repository architecture."},
        )

