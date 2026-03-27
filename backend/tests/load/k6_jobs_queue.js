import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    jobs_enqueue_and_poll: {
      executor: "constant-vus",
      vus: 3,
      duration: "90s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.1"],
    http_req_duration: ["p(95)<2000"],
    "http_req_duration{endpoint:enqueue}": ["p(95)<1200"],
    "http_req_duration{endpoint:poll_status}": ["p(95)<1200"],
    "http_req_duration{endpoint:worker_metrics}": ["p(95)<1200"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const TICKERS = (__ENV.TICKERS || "AAPL,MSFT")
  .split(",")
  .map((s) => s.trim().toUpperCase())
  .filter(Boolean);
const RUN_ETL = (__ENV.RUN_ETL || "false").toLowerCase() === "true";
const REFRESH_NEWS = (__ENV.REFRESH_NEWS || "false").toLowerCase() === "true";

function enqueueRefresh() {
  const payload = JSON.stringify({
    tickers: TICKERS,
    force_full: false,
    refresh_quote: true,
    refresh_fundamentals: true,
    run_etl: RUN_ETL,
    refresh_news: REFRESH_NEWS,
    background: true,
  });
  return http.post(`${BASE_URL}/api/v1/jobs/refresh-universe`, payload, {
    headers: { "Content-Type": "application/json" },
    tags: { endpoint: "enqueue" },
  });
}

export default function () {
  const enqueue = enqueueRefresh();
  const enqueueOk = check(enqueue, {
    "enqueue status is 200": (r) => r.status === 200,
    "enqueue returns run_id": (r) => {
      try {
        return !!JSON.parse(r.body).run_id;
      } catch (_e) {
        return false;
      }
    },
  });
  if (!enqueueOk) {
    sleep(1);
    return;
  }

  const runId = JSON.parse(enqueue.body).run_id;
  const status = http.get(`${BASE_URL}/api/v1/jobs/refresh-universe/${runId}`, {
    tags: { endpoint: "poll_status" },
  });
  check(status, {
    "status endpoint returns 200": (r) => r.status === 200,
  });

  const workerMetrics = http.get(`${BASE_URL}/api/v1/jobs/worker/metrics`, {
    tags: { endpoint: "worker_metrics" },
  });
  check(workerMetrics, {
    "worker metrics returns 200": (r) => r.status === 200,
  });

  sleep(1);
}
