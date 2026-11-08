"""Exercise the CLI with isolated command and blockchain stubs; no network or keys."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "alamdunia.sh"
ADDRESS = "0x1234567890123456789012345678901234567890"


class WorkflowTests(unittest.TestCase):
    def run_workflow(self, failure=""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy(SCRIPT, root / SCRIPT.name)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            command = bin_dir / "stub"
            command.write_text('''#!/bin/sh
name=${0##*/}
printf '%s %s\\n' "$name" "$*" >> "$COMMAND_LOG"
[ "$FAIL_COMMAND" != "$name" ] || exit 1
if [ "$name" = sudo ] && [ "$2" = update ] && [ "$FAIL_COMMAND" = update ]; then exit 1; fi
case "$name" in
  wget) printf '#!/bin/sh\\nexit 0\\n' > loader.sh ;;
  curl) printf '#!/bin/sh\\nexit 0\\n' > logo.sh ;;
  npm) [ "$FAIL_COMMAND" != install ] || exit 1 ;;
  npx)
    if [ "$2" = compile ] && [ "$FAIL_COMMAND" = compile ]; then exit 1; fi
    if [ "$2" = run ]; then node "$3"; fi
    ;;
esac
''')
            command.chmod(0o755)
            for name in ("wget", "curl", "sleep", "sudo", "clear", "npm", "npx"):
                (bin_dir / name).symlink_to(command)
            modules = root / "node_modules"
            hardhat = modules / "hardhat"
            hardhat.mkdir(parents=True)
            (hardhat / "index.js").write_text('''
const assert = require("node:assert/strict");
const address = process.env.EXPECTED_ADDRESS;
const checkAddress = destination => assert.equal(destination, address);
const provider = { call: async ({ to }) => { checkAddress(to); return "response"; } };
const signer = {
  address: "test-signer", provider,
  sendTransaction: async ({ to }) => {
    checkAddress(to);
    return { wait: async () => {} };
  }
};
module.exports = {
  network: { config: { url: "mock-rpc" } },
  ethers: {
    deployContract: async () => ({
      target: address,
      waitForDeployment: async () => {
        if (process.env.FAIL_COMMAND === "deploy") throw Error("Deployment failed");
      }
    }),
    getSigners: async () => [signer],
    getContractFactory: async () => ({ attach: destination => {
      checkAddress(destination);
      return { interface: {
        encodeFunctionData: () => "encoded",
        decodeFunctionResult: () => ["test message"]
      } };
    } })
  }
};
''')
            utils = modules / "@swisstronik" / "utils"
            utils.mkdir(parents=True)
            (utils / "index.js").write_text('''
exports.encryptDataField = async () => ["encrypted", "key"];
exports.decryptNodeResponse = async () => "decrypted";
''')
            log = root / "commands.log"
            result = subprocess.run(
                ["sh", SCRIPT.name], cwd=root, input="test-only-not-a-real-key\n",
                text=True, capture_output=True,
                env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
                     "FAIL_COMMAND": failure, "COMMAND_LOG": str(log),
                     "EXPECTED_ADDRESS": ADDRESS},
                timeout=15,
            )
            return result, log.read_text()

    def test_bootstrap_failure_stops_before_install(self):
        for failure in ("wget", "curl", "update"):
            with self.subTest(failure=failure):
                result, commands = self.run_workflow(failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("npm install", commands)
                self.assertNotIn("Installation completed.", result.stdout)

    def test_install_failure_stops_without_success(self):
        result, commands = self.run_workflow("install")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Installation completed.", result.stdout)
        self.assertNotIn("npx", commands)

    def test_compile_failure_does_not_deploy(self):
        result, commands = self.run_workflow("compile")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Contract compiled.", result.stdout)
        self.assertNotIn("npx hardhat run", commands)

    def test_deploy_failure_does_not_set_message(self):
        result, commands = self.run_workflow("deploy")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Contract deployed.", result.stdout)
        self.assertNotIn("run scripts/setMessage.js", commands)

    def test_message_flow_uses_new_deployment(self):
        result, commands = self.run_workflow()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Message set.", result.stdout)
        self.assertIn("Decoded response: test message", result.stdout)
        self.assertIn("Message retrieved.", result.stdout)
        self.assertIn("sudo apt-get upgrade -y", commands)


if __name__ == "__main__":
    unittest.main()
