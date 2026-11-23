import socket
import sys

import uvicorn

PORT = 8700

if __name__ == "__main__":
    # an old server still holding the port would keep serving stale code; say so instead of exiting silently
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            print(f"Port {PORT} is already in use: an older MV Agent server is probably still running.\n"
                  f"Close its window (or end its python.exe in Task Manager) and start again.")
            input("Press Enter to exit...")
            sys.exit(1)
    # local only: the agent drives the GPU and the file system of this machine
    uvicorn.run("webagent.server:app", host="127.0.0.1", port=PORT, log_level="warning")
