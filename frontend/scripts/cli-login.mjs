import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";

export async function cliLogin(cli, env, key) {
  // Disable terminal echo before sending the key. Pass the secret only over stdin.
  const script = `import os,pty,select,signal,sys,termios,time
key = sys.stdin.readline().rstrip("\\n")
child, master = pty.fork()
if child == 0:
    os.execv(sys.argv[1], sys.argv[1:])
deadline = time.monotonic() + 45
output = b""
sent = False
try:
    while True:
        ended, status = os.waitpid(child, os.WNOHANG)
        if ended:
            raise SystemExit(os.waitstatus_to_exitcode(status))
        if time.monotonic() > deadline:
            os.kill(child, signal.SIGKILL)
            os.waitpid(child, 0)
            raise SystemExit(1)
        if select.select([master], [], [], 0.1)[0]:
            try: output = (output + os.read(master, 65536))[-4096:]
            except OSError: continue
        if (not sent and b"API key:" in output
                and not termios.tcgetattr(master)[3] & termios.ECHO):
            os.write(master, (key + "\\n").encode())
            sent = True
finally:
    os.close(master)`;
  const result = spawnSync(cli.python, ["-c", script, cli.executable, "cloud", "login"], {
    cwd: cli.project, env, input: key + "\n", encoding: "utf8", timeout: 60_000,
  });
  assert.equal(result.status, 0, "CLI API-key login failed");
}
