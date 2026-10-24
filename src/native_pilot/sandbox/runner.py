from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path


# Immutable digest of the locally verified official Python 3.12-slim image.
# Multi-architecture image resolution is recorded by qualification.
DEFAULT_IMAGE = "python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704"


class SandboxUnavailable(RuntimeError):
    pass


def normalize_output(text: str) -> str:
    """Exact tokens except inter-token whitespace; no numeric tolerance."""
    return " ".join(text.split())


class DockerSandbox:
    def __init__(self, image: str = DEFAULT_IMAGE, timeout: float = 5.0,
                 output_limit: int = 1_000_000, memory_mb: int = 256):
        if not re.fullmatch(r"[A-Za-z0-9._/:\-]+@sha256:[0-9a-f]{64}", image):
            raise ValueError("Sandbox image must be pinned by sha256 digest")
        if not 0 < timeout <= 60 or not 1024 <= output_limit <= 4_000_000 or not 32 <= memory_mb <= 1024:
            raise ValueError("Invalid sandbox resource limit")
        self.image, self.timeout = image, timeout
        self.output_limit, self.memory_mb = output_limit, memory_mb
        mac_docker = "/Applications/Docker.app/Contents/Resources/bin/docker"
        self.docker = shutil.which("docker") or (mac_docker if Path(mac_docker).is_file() else "docker")

    @staticmethod
    def _environment() -> dict[str, str]:
        # Docker CLI needs its endpoint configuration; never forward the host
        # environment to the container, or API keys even to this subprocess.
        allowed = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG",
                   "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "TMPDIR")
        return {key: os.environ[key] for key in allowed if key in os.environ}

    def available(self) -> dict:
        try:
            info = subprocess.run([self.docker, "info", "--format", "{{json .ServerVersion}}"],
                                  capture_output=True, text=True, timeout=15, env=self._environment())
            image = subprocess.run([self.docker, "image", "inspect", self.image,
                                    "--format", "{{json .}}"], capture_output=True,
                                   text=True, timeout=15, env=self._environment())
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SandboxUnavailable("Docker unavailable; no host fallback") from exc
        if info.returncode or image.returncode:
            raise SandboxUnavailable("Docker daemon or pinned image unavailable; pull the pinned image and rerun qualification")
        record = json.loads(image.stdout)
        return {"docker_version": json.loads(info.stdout), "image": self.image,
                "image_id": record["Id"], "architecture": record["Architecture"], "os": record["Os"]}

    def command(self, submission_dir: Path, name: str) -> list[str]:
        return [self.docker, "run", "--rm", "--pull=never", "--name", name,
                "--network", "none", "--read-only", "--user", "65534:65534",
                "--cpus", "1", "--memory", f"{self.memory_mb}m", "--memory-swap", f"{self.memory_mb}m",
                "--pids-limit", "32", "--ulimit", "nofile=64:64", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                "--mount", f"type=bind,src={submission_dir.resolve()},dst=/submission,readonly",
                "--workdir", "/submission", "--env", "PYTHONHASHSEED=0", "--env", "LANG=C.UTF-8",
                # An in-container PID1 deadline survives a crashed/interrupted
                # host runner. PID1 termination also ends descendant processes.
                "--entrypoint", "/usr/bin/timeout", "-i", self.image,
                "--signal=KILL", f"{self.timeout}s", "python", "-I", "-B", "/submission/main.py"]

    def run(self, code: str, stdin: str) -> dict:
        if not isinstance(stdin, str) or len(stdin.encode()) > 4_000_000:
            raise ValueError("stdin missing or exceeds sandbox limit")
        if not isinstance(code, str) or len(code.encode()) > 512_000:
            raise ValueError("program exceeds sandbox limit")
        name = "native-pilot-" + uuid.uuid4().hex
        with tempfile.TemporaryDirectory(prefix="native-pilot-") as temp:
            directory = Path(temp)
            directory.chmod(0o755)
            program = directory / "main.py"
            program.write_text(code)
            program.chmod(0o444)
            command = self.command(directory, name)
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, env=self._environment())
            except OSError as exc:
                raise SandboxUnavailable("Docker executable unavailable; no host fallback") from exc
            buffers = {"stdout": bytearray(), "stderr": bytearray()}
            exceeded = threading.Event()

            def drain(stream, key):
                while True:
                    chunk = stream.read(8192)
                    if not chunk:
                        break
                    remaining = self.output_limit - len(buffers[key])
                    buffers[key].extend(chunk[:max(0, remaining)])
                    if len(chunk) > remaining:
                        exceeded.set()

            def feed():
                try:
                    process.stdin.write(stdin.encode())
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass

            workers = [threading.Thread(target=drain, args=(process.stdout, "stdout"), daemon=True),
                       threading.Thread(target=drain, args=(process.stderr, "stderr"), daemon=True),
                       threading.Thread(target=feed, daemon=True)]
            for worker in workers:
                worker.start()
            deadline = time.monotonic() + self.timeout
            reason = "completed"
            while process.poll() is None:
                if exceeded.is_set():
                    reason = "output_limit"
                    break
                if time.monotonic() >= deadline:
                    reason = "timeout"
                    break
                time.sleep(0.01)
            if reason != "completed":
                # Killing only the Docker client can leave the container alive.
                subprocess.run([self.docker, "rm", "-f", name], capture_output=True,
                               timeout=15, env=self._environment())
                process.kill()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            for worker in workers:
                worker.join(timeout=1)
            if exceeded.is_set():
                reason = "output_limit"
            elif reason == "completed" and process.returncode in (124, 137):
                reason = "timeout_or_resource_limit"
            stdout = buffers["stdout"].decode("utf-8", errors="replace")
            stderr = buffers["stderr"].decode("utf-8", errors="replace")
            if reason == "completed" and process.returncode == 125:
                raise SandboxUnavailable("Docker failed to start isolated container")
            return {"status": reason, "returncode": process.returncode,
                    "stdout": stdout, "stderr": stderr}

    def evaluate(self, code: str, tests: list[dict]) -> dict:
        if not tests or len(tests) > 1000:
            raise ValueError("Nonempty, bounded authoritative tests required")
        results = []
        for test in tests:
            if not isinstance(test.get("stdin"), str) or not isinstance(test.get("stdout"), str):
                raise ValueError("Only plain-text stdin/stdout test format is qualified")
            result = self.run(code, test["stdin"])
            passed = (result["status"] == "completed" and result["returncode"] == 0
                      and normalize_output(result["stdout"]) == normalize_output(test["stdout"]))
            results.append({"passed": passed, "status": result["status"], "returncode": result["returncode"]})
        return {"passed": all(result["passed"] for result in results), "results": results}


def qualify_docker(image: str = DEFAULT_IMAGE) -> dict:
    """Software-only fixtures; this never qualifies missing source graders."""
    box = DockerSandbox(image=image)
    report = {"scope": "software_sandbox_only", "source_grading_qualified": False,
              "image": image, "checks": {}}
    try:
        report.update(box.available())
        checks = report["checks"]
        original = [{"stdin": "3\n", "stdout": "6\n"}]
        updated = [{"stdin": "3\n", "stdout": "9\n"}]
        good = "n = int(input())\nprint(n * 3)\n"
        equivalent = "import sys\nn = int(sys.stdin.read())\nsys.stdout.write(str(n+n+n)+'\\n')\n"
        stale = "print(int(input()) * 2)\n"
        checks["correct_accept"] = box.evaluate(good, updated)["passed"]
        checks["equivalent_accept"] = box.evaluate(equivalent, updated)["passed"]
        checks["wrong_reject"] = not box.evaluate("print(0)\n", updated)["passed"]
        checks["stale_reject_update"] = not box.evaluate(stale, updated)["passed"]
        checks["old_reference_accept"] = box.evaluate(stale, original)["passed"]
        checks["updated_reference_fails_original"] = not box.evaluate(good, original)["passed"]
        probe = r'''import json, os, pathlib, socket
def denied(path):
    try:
        pathlib.Path(path).write_text('forbidden')
        return False
    except OSError:
        return True
try:
    socket.create_connection(('1.1.1.1', 443), timeout=0.5)
    network_denied = False
except OSError:
    network_denied = True
print(json.dumps({'unprivileged': os.getuid() == 65534,
 'root_readonly': denied('/forbidden'), 'program_readonly': denied('/submission/main.py'),
 'network_denied': network_denied,
 'no_credentials': not any(any(s in k.upper() for s in ['TOKEN','SECRET','API_KEY','PASSWORD']) for k in os.environ),
 'only_program_mounted': sorted(os.listdir('/submission')) == ['main.py']}))
'''
        probe_result = box.run(probe, "")
        checks.update(json.loads(probe_result["stdout"]))
        limited = DockerSandbox(image=image, timeout=1.0, output_limit=2048)
        checks["runtime_bounded"] = limited.run("while True: pass", "")["status"] == "timeout"
        checks["output_bounded"] = limited.run("while True: print('x'*8192)", "")["status"] == "output_limit"
        # Verify cgroup limits from inside the container rather than trusting
        # command construction alone; v1 hosts remain explicitly unqualified.
        resource_probe = "from pathlib import Path\nfor f in ('memory.max','pids.max','cpu.max'):\n print(Path('/sys/fs/cgroup', f).read_text().strip())\n"
        resource = box.run(resource_probe, "")
        lines = resource["stdout"].splitlines()
        checks["memory_limit"] = bool(lines) and lines[0] == str(256 * 1024 * 1024)
        checks["process_limit"] = len(lines) > 1 and lines[1] == "32"
        checks["cpu_limit"] = len(lines) > 2 and len(lines[2].split()) == 2 and lines[2].split()[0] == lines[2].split()[1]
        report["passed"] = all(checks.values())
        report["status"] = "passed" if report["passed"] else "failed"
    except (SandboxUnavailable, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        report.update(status="not_run_or_failed", passed=False, blocker=str(exc))
    return report
