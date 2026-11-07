"""Resume the frozen R2 mirror plan, with a single-job lock and durable status."""
import argparse
import fcntl
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from server import storage
from scripts.r2_verify import verify

FOLDER = storage.ROOT / '.cache/r2-mirror'

def status(state, **fields):
    payload = {'state': state, 'pid': os.getpid(), 'updatedAt': datetime.now(timezone.utc).isoformat(), **fields}
    temporary = FOLDER / 'mirror-job.tmp'
    temporary.write_text(json.dumps(payload, indent=2))
    temporary.replace(FOLDER / 'mirror-job.json')
    print(json.dumps(payload), flush=True)

def running(pid):
    try: os.kill(pid, 0); return True
    except ProcessLookupError: return False

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait-pid', type=int, help='Adopt an already-running transfer, then retry its missing files')
    parser.add_argument('--remote', default='bcnatlasCloudflareR2')
    parser.add_argument('--passes', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.passes <= 10: parser.error('--passes must be between 1 and 10')
    FOLDER.mkdir(parents=True, exist_ok=True)
    with (FOLDER / 'mirror.lock').open('w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit('A mirror supervisor is already running. See mirror-job.json.')
        if args.wait_pid:
            command = (storage.ROOT / f'/proc/{args.wait_pid}/cmdline')
            if running(args.wait_pid):
                actual = command.read_bytes().replace(b'\0', b' ').decode()
                if 'rclone copyurl ' not in actual or storage.raw_bucket() not in actual or storage.raw_prefix() not in actual:
                    raise SystemExit('Refusing to adopt a process that is not this mirror transfer.')
                while running(args.wait_pid):
                    report = verify()
                    status('transferring', transferPid=args.wait_pid, uploaded=report['uploadedResources'], missing=report['missingResources'])
                    time.sleep(60)
        for attempt in range(1, args.passes + 1):
            report = verify()
            if not report['missingResources']:
                status('complete', uploaded=report['uploadedResources'], missing=0)
                return
            command = ['rclone', 'copyurl', '--urls', str(FOLDER / 'missing-resources.csv'),
                       f'{args.remote}:{storage.raw_bucket()}/{storage.raw_prefix()}',
                       '--transfers', '6', '--tpslimit', '4', '--tpslimit-burst', '4',
                       '--contimeout', '10s', '--timeout', '90s', '--retries', '2',
                       '--retries-sleep', '10s', '--no-clobber',
                       '--log-file', str(FOLDER / 'upload.log'), '--log-level', 'INFO',
                       '--stats', '30s', '--stats-one-line']
            # Freeze each pass: periodic verification rewrites missing-resources.csv.
            pass_plan = FOLDER / f'pass-{attempt}.csv'
            pass_plan.write_bytes((FOLDER / 'missing-resources.csv').read_bytes())
            command[3] = str(pass_plan)
            with (FOLDER / 'transfer-output.log').open('a') as output:
                child = subprocess.Popen(command, cwd=storage.ROOT, stdout=output, stderr=subprocess.STDOUT)
                while child.poll() is None:
                    status('transferring', attempt=attempt, transferPid=child.pid, uploaded=report['uploadedResources'], missing=report['missingResources'])
                    try: child.wait(timeout=60)
                    except subprocess.TimeoutExpired: report = verify()
                status('verifying', attempt=attempt, transferExitCode=child.returncode)
        report = verify()
        status('complete' if not report['missingResources'] else 'needs-retry', uploaded=report['uploadedResources'], missing=report['missingResources'])
        if report['missingResources']: raise SystemExit(2)

if __name__ == '__main__':
    try: main()
    except Exception as exc:
        status('failed', errorType=type(exc).__name__, message='Inspect the supervisor log and storage/network configuration, then resume.')
        raise
