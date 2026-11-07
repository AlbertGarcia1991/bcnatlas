import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
const python = process.env.BCN_PYTHON || '.venv/bin/python';
if (!existsSync(python)) { console.error('Run npm run setup:api first (Python 3.10+ required).'); process.exit(1); }
const api = spawn(python, ['-m', 'uvicorn', 'server.app:app', '--host', '127.0.0.1', '--port', '8000'], { stdio: 'inherit', env: { ...process.env, OPENBLAS_NUM_THREADS: '1' } });
const frontend = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '0.0.0.0', ...process.argv.slice(2)], { stdio: 'inherit' });
let stopping=false;
function stop(code=0) { if (stopping) return; stopping=true; api.kill(); frontend.kill(); setTimeout(()=>process.exit(code),200); }
api.on('exit', code=>stop(code||0));frontend.on('exit',code=>stop(code||0));
process.on('SIGINT',()=>stop());process.on('SIGTERM',()=>stop());
