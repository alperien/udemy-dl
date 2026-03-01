buffer = "some log\nprogress 10%\r"
while "\r" in buffer or "\n" in buffer:
    if "\r" in buffer:
        line, buffer = buffer.split("\r", 1)
    else:
        line, buffer = buffer.split("\n", 1)
    if line.strip():
        print(repr(line.strip().lower()))
