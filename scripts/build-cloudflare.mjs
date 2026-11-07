import { spawnSync } from 'node:child_process';
// One origin for assets and APIs; local .env overrides cannot accidentally bypass the Worker.
for (const args of [['run', 'check:worker'], ['run', 'build']]) {
  const result = spawnSync('npm', args, { stdio: 'inherit', env: { ...process.env, VITE_DATA_BASE_URL: '/api/data' } });
  if (result.status !== 0) process.exit(result.status || 1);
}
