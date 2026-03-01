import select
import subprocess
import sys
import time

proc = subprocess.Popen(
    [
        sys.executable,
        "-c",
        "import sys, time; sys.stderr.write('hello\\n'); sys.stderr.close(); time.sleep(2)",
    ],
    stderr=subprocess.PIPE,
)

while True:
    if proc.stderr is None:
        break
    ready, _, _ = select.select([proc.stderr], [], [], 0.1)
    if not ready:
        continue

    char = proc.stderr.read(1)
    if not char:
        print("EOF reached")
        if proc.poll() is not None:
            print("Process exited")
            break
        print("Process still running, looping...")
        time.sleep(0.5)  # slow down for test
        continue
    print(f"Read: {char.decode('utf-8', errors='replace')}")
