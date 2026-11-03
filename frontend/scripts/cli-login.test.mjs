import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "vitest";
import { cliLogin } from "./cli-login.mjs";

test.skipIf(process.platform === "win32")(
  "waits for hidden input after the CLI prints the key caption",
  async () => {
    const directory = mkdtempSync(join(tmpdir(), "infralens-cli-prompt-"));
    try {
      const executable = join(directory, "cli");
      // Click/Typer prints the caption before getpass disables echo and flushes
      // pending input. A prompt-only detector sends too early and loses the key.
      writeFileSync(executable, `#!/usr/bin/env python3
import getpass,sys,time
print("API key:", end="", flush=True)
time.sleep(0.2)
key = getpass.getpass(" ")
sys.exit(0 if key == "synthetic-test-key" else 1)
`, { mode: 0o700 });
      await expect(cliLogin(
        { python: "python3", executable, project: directory },
        process.env,
        "synthetic-test-key",
      )).resolves.toBeUndefined();
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  },
);
