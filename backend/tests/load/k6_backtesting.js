import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    backtesting_read_heavy: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "30s", target: 3 },
        { duration: "60s", target: 6 },
        { duration: "30s", target: 0 },
      ],
      gracefulRampDown: "10s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.1"],
    http_req_duration: ["p(95)<2500"],
    "http_req_duration{endpoint:backtest_single}": ["p(95)<2500"],
    "http_req_duration{endpoint:backtest_compare}": ["p(95)<3500"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const TICKER = __ENV.TICKER || "AAPL";
const START_DATE = __ENV.START_DATE || "2024-01-01";
const END_DATE = __ENV.END_DATE || "2024-12-31";
const INITIAL_CAPITAL = __ENV.INITIAL_CAPITAL || "10000";

export default function () {
  const single = http.get(
    `${BASE_URL}/api/v1/backtesting/${TICKER}?model=model_d&start_date=${START_DATE}&end_date=${END_DATE}&initial_capital=${INITIAL_CAPITAL}`,
    { tags: { endpoint: "backtest_single" } }
  );
  check(single, {
    "single backtest status 200/4xx": (r) =>
      r.status === 200 || (r.status >= 400 && r.status < 500 && r.body.includes("error")),
  });

  const compare = http.get(
    `${BASE_URL}/api/v1/backtesting/${TICKER}/compare?start_date=${START_DATE}&end_date=${END_DATE}&initial_capital=${INITIAL_CAPITAL}`,
    { tags: { endpoint: "backtest_compare" } }
  );
  check(compare, {
    "compare backtest status is 200": (r) => r.status === 200,
  });

  sleep(1);
}
