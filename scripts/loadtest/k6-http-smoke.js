import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    smoke: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 50 },
        { duration: '2m', target: 200 },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<400'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8000';

export default function () {
  const home = http.get(`${BASE_URL}/`);
  check(home, {
    'home status is 200/302': (r) => r.status === 200 || r.status === 302,
  });

  const randomVideo = http.get(`${BASE_URL}/random-video/`);
  check(randomVideo, {
    'random-video status is 200/302': (r) => r.status === 200 || r.status === 302,
  });

  sleep(1);
}
