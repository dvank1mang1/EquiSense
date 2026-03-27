import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    api_smoke: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "30s", target: 5 },
        { duration: "60s", target: 10 },
        { duration: "30s", target: 0 },
      ],
      gracefulRampDown: "10s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<1500"],
    "http_req_duration{endpoint:history}": ["p(95)<1800"],
    "http_req_duration{endpoint:prediction}": ["p(95)<1500"],
    "http_req_duration{endpoint:compare}": ["p(95)<2000"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const TICKER = __ENV.TICKER || "AAPL";

export default function () {
  const history = http.get(`${BASE_URL}/api/v1/stocks/${TICKER}/history?period=1y`, {
    tags: { endpoint: "history" },
  });
  check(history, {
    "history status is 200": (r) => r.status === 200,
  });

  const prediction = http.get(`${BASE_URL}/api/v1/predictions/${TICKER}?model=model_d`, {
    tags: { endpoint: "prediction" },
  });
  check(prediction, {
    "prediction status is 200 or 4xx/5xx with envelope": (r) =>
      r.status === 200 || (r.status >= 400 && r.body && r.body.includes("error")),
  });

  const compare = http.get(`${BASE_URL}/api/v1/predictions/${TICKER}/compare`, {
    tags: { endpoint: "compare" },
  });
  check(compare, {
    "compare status is 200": (r) => r.status === 200,
  });

  sleep(1);
}
