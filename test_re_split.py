import re

buffer = "log\nprogress\r"
parts = re.split(r"[\r\n]+", buffer)
buffer = parts.pop()
for line in parts:
    if line.strip():
        print(repr(line.strip().lower()))
print("Remaining buffer:", repr(buffer))
