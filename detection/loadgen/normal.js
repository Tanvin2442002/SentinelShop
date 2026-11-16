import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://edge:8080';
const JSON_HEADERS = { headers: { 'Content-Type': 'application/json' } };
const WORDS = ['a', 'bag', 'cup'];

export const options = {
  scenarios: {
    normal: {
      executor: 'constant-arrival-rate',
      rate: 20,
      timeUnit: '1s',
      duration: __ENV.DURATION || '5m',
      preAllocatedVUs: 20,
      maxVUs: 100,
    },
  },
  thresholds: { checks: ['rate>0.99'] },
};

export default function () {
  const r = Math.random();
  let res;
  if (r < 0.59) {
    res = http.get(`${BASE}/api/products`);
  } else if (r < 0.60) {
    res = http.post(`${BASE}/api/login`,
      JSON.stringify({ username: 'alice', password: 'alice-demo-pw' }), JSON_HEADERS);
  } else if (r < 0.85) {
    res = http.get(`${BASE}/api/products/${1 + Math.floor(Math.random() * 12)}`);
  } else if (r < 0.95) {
    res = http.get(`${BASE}/api/search?q=${WORDS[Math.floor(Math.random() * WORDS.length)]}`);
  } else {
    res = http.post(`${BASE}/api/orders`,
      JSON.stringify({ product_id: 1, quantity: 1 }), JSON_HEADERS);
  }
  check(res, { 'status is 2xx': (x) => x.status >= 200 && x.status < 300 });
}
