"""Evaluator-owned process boundary for the trusted, data-only G3 DSL.

OS CPU/memory limits plus bounded pipes and a wall watchdog are mandatory.
The staged Python worker has no model tools and installs an I/O audit guard.
This is NOT a sandbox for arbitrary Python/native code: audit hooks can be
bypassed by executable code. Only the validated declarative DSL is admitted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import io
import hashlib
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
from uuid import uuid4

from .candidate_spec import CandidateError, MAX_SPEC_BYTES, load_candidate
from .contracts import Observation, ScopeContract, SequenceResult, TargetKind


class ExecutionUnavailable(RuntimeError):
    """Required containment could not be established; no unbounded fallback."""


@dataclass(frozen=True)
class CandidateExecutionLimits:
    max_actions: int = 64
    max_input_bytes: int = 128_000
    max_output_bytes: int = 128_000
    max_records: int = 10_000
    wall_seconds: float = 5.0
    cpu_seconds: float = 3.0
    memory_bytes: int = 256 * 1024 * 1024

    def __post_init__(self):
        for name in ("max_actions", "max_input_bytes", "max_output_bytes", "max_records", "memory_bytes"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError("Execution limits must be positive trusted numbers")
        if self.max_actions > 64 or self.max_output_bytes < 512 or self.memory_bytes < 32 * 1024 * 1024:
            raise ValueError("Unsupported execution limits")
        for value in (self.wall_seconds, self.cpu_seconds):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("Execution limits must be finite positive numbers")


def _checked_json(raw: bytes, maximum: int):
    """Bound depth before parsing, reject duplicate keys/non-JSON numbers."""
    if not isinstance(raw, bytes) or len(raw) > maximum:
        raise ValueError("JSON byte limit exceeded")
    depth = 0
    quoted = escaped = False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            if depth > 32:
                raise ValueError("JSON nesting limit exceeded")
        elif char in (93, 125):
            depth -= 1

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value

    def invalid_constant(value):
        raise ValueError("Nonfinite JSON number")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid_constant)


def _encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _minimal_environment() -> dict[str, str]:
    # Do not copy/inspect credentials, HOME, PATH, proxy, Python or user variables.
    env = {"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    if sys.platform == "win32":
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if not ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer)):
            raise ExecutionUnavailable("Windows runtime directory unavailable")
        env["SystemRoot"] = buffer.value
    return env


class _WindowsJob:
    """Assign before any untrusted bytes are sent to the waiting worker."""
    def __init__(self, process, limits):
        import ctypes as c
        from ctypes import wintypes as w

        class Basic(c.Structure):
            _fields_ = [("process_time", c.c_int64), ("job_time", c.c_int64),
                        ("flags", w.DWORD), ("min_working_set", c.c_size_t),
                        ("max_working_set", c.c_size_t), ("active", w.DWORD),
                        ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]

        class IO(c.Structure):
            _fields_ = [(name, c.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read", "write", "other")]

        class Extended(c.Structure):
            _fields_ = [("basic", Basic), ("io", IO), ("process_memory", c.c_size_t),
                        ("job_memory", c.c_size_t), ("peak_process", c.c_size_t), ("peak_job", c.c_size_t)]

        self.api = c.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.api.GetProcessTimes.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p]
        self.process_handle = w.HANDLE(int(process._handle))
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ExecutionUnavailable("Windows Job Object unavailable")
        info = Extended()
        # PROCESS_TIME | ACTIVE_PROCESS | PROCESS_MEMORY | KILL_ON_JOB_CLOSE
        info.basic.flags = 0x2 | 0x8 | 0x100 | 0x2000
        info.basic.process_time = max(1, int(limits.cpu_seconds * 10_000_000))
        info.basic.active = 1
        info.process_memory = limits.memory_bytes
        if (not self.api.SetInformationJobObject(self.handle, 9, c.byref(info), c.sizeof(info))
                or not self.api.AssignProcessToJobObject(self.handle, w.HANDLE(int(process._handle)))):
            self.close()
            raise ExecutionUnavailable("Windows Job limits could not be applied")
        try:
            self.cpu_seconds()  # Fail admission if the CPU watchdog cannot measure usage.
        except ExecutionUnavailable:
            self.close()
            raise

    def cpu_seconds(self):
        import ctypes as c
        created, exited, kernel, user = (c.c_uint64() for _ in range(4))
        if not self.api.GetProcessTimes(self.process_handle, c.byref(created), c.byref(exited),
                                       c.byref(kernel), c.byref(user)):
            raise ExecutionUnavailable("Windows process CPU accounting unavailable")
        return (kernel.value + user.value) / 10_000_000

    def terminate(self):
        if self.handle:
            self.api.TerminateJobObject(self.handle, 1)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


_CANDIDATE_MODULES = (
    "__init__", "contracts", "scope_guard", "candidate_spec", "candidate_runtime", "candidate_adapter",
)
_GENERATION_MODULES = _CANDIDATE_MODULES + (
    "candidate_generation", "model_gateway", "budgets", "runner", "reference", "evidence", "schema_validate",
)


class _LinuxCPU:
    def __init__(self, pid):
        self.path = Path(f"/proc/{pid}/stat")
        self.ticks = os.sysconf("SC_CLK_TCK")
        self.cpu_seconds()

    def cpu_seconds(self):
        try:
            # /proc/PID/stat fields 14/15; comm (field 2) can contain spaces.
            fields = self.path.read_text(encoding="utf-8").rsplit(")", 1)[1].split()
            return (int(fields[11]) + int(fields[12])) / self.ticks
        except (OSError, ValueError, IndexError):
            raise ExecutionUnavailable("Linux process CPU accounting unavailable") from None


def _run_worker(mode: str, payload: dict, limits: CandidateExecutionLimits) -> dict:
    """Fixed trusted entry point, immutable JSON IPC, no model-written argv/code."""
    if sys.platform not in ("win32", "linux"):
        raise ExecutionUnavailable("No verified resource backend on this platform")
    source = Path(__file__).resolve().parent
    wire = _encode({"mode": mode, "limits": asdict(limits), "payload": payload})
    # Spec/scope are separate bounded metadata; actions/context have their own input cap.
    if len(wire) > limits.max_input_bytes + MAX_SPEC_BYTES * 3:
        raise ValueError("Worker request exceeds envelope limit")
    with tempfile.TemporaryDirectory(prefix="second-source-worker-") as directory:
        stage = Path(directory)
        package = stage / "second_source"
        package.mkdir()
        modules = _GENERATION_MODULES if mode in {"generation", "generation_probe"} else _CANDIDATE_MODULES
        for name in modules:
            original = source / (name + ".py")
            if original.is_symlink() or original.resolve().parent != source:
                raise ExecutionUnavailable("Trusted runtime bundle contains an unsafe path")
            (package / original.name).write_bytes(original.read_bytes())
        if mode == "reference":
            original = source.parents[1] / "fixtures/owned_ledger/reference.py"
            if original.is_symlink() or original.resolve() != original:
                raise ExecutionUnavailable("Unsafe trusted reference location")
            reference_bytes = original.read_bytes()
            if "sha256:" + hashlib.sha256(reference_bytes).hexdigest() != payload["reference_digest"]:
                raise ExecutionUnavailable("Trusted reference changed during evaluation")
            (stage / "_owned_reference.py").write_bytes(reference_bytes)
        # -I -S excludes CWD, environment injection, user site and executable .pth files.
        bootstrap = (
            "import sys;sys.dont_write_bytecode=True;"
            f"sys.path[:0]={str(stage)!r}, {sysconfig.get_path('purelib')!r}, {sysconfig.get_path('platlib')!r};"
            "from second_source.candidate_adapter import _worker_main;_worker_main()"
        )
        try:
            process = subprocess.Popen(
                [getattr(sys, "_base_executable", sys.executable), "-I", "-S", "-B", "-c", bootstrap], cwd=stage,
                env=_minimal_environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                close_fds=True, start_new_session=sys.platform != "win32",
                creationflags=0x08000000 if sys.platform == "win32" else 0,
            )
        except OSError:
            raise ExecutionUnavailable("Trusted worker could not start") from None
        job = None
        cpu_meter = None
        exceeded = threading.Event()
        cpu_exceeded = threading.Event()
        cpu_unavailable = threading.Event()
        finished = threading.Event()
        output = bytearray()
        errors = bytearray()
        # IPC carries observations too; bound metadata independently of output-body bytes.
        wire_output_cap = limits.max_output_bytes + limits.max_input_bytes + 32_768

        def terminate():
            if process.poll() is None:
                if job is not None:
                    job.terminate()
                elif sys.platform == "linux":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()

        def drain(pipe, destination, cap):
            try:
                while block := pipe.read(4096):
                    if len(destination) + len(block) > cap:
                        exceeded.set()
                        terminate()
                        return
                    destination.extend(block)
            finally:
                pipe.close()

        def send():
            try:
                process.stdin.write(wire)
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        def watch_cpu():
            # Some nested Windows jobs do not honor the native CPU-time flag.
            # An independent parent measurement enforces the declared CPU budget.
            while not finished.wait(0.02):
                if process.poll() is not None:
                    return
                try:
                    if cpu_meter.cpu_seconds() >= limits.cpu_seconds:
                        cpu_exceeded.set()
                        terminate()
                        return
                except ExecutionUnavailable:
                    if process.poll() is not None:
                        return
                    cpu_unavailable.set()
                    terminate()
                    return

        try:
            if sys.platform == "win32":
                job = _WindowsJob(process, limits)
                cpu_meter = job
            else:
                cpu_meter = _LinuxCPU(process.pid)
            cpu_watcher = threading.Thread(target=watch_cpu, daemon=True)
            cpu_watcher.start()
            readers = [threading.Thread(target=drain, args=(process.stdout, output, wire_output_cap), daemon=True),
                       threading.Thread(target=drain, args=(process.stderr, errors, 4096), daemon=True)]
            for reader in readers:
                reader.start()
            writer = threading.Thread(target=send, daemon=True)
            writer.start()
            try:
                process.wait(timeout=limits.wall_seconds)
            except subprocess.TimeoutExpired:
                terminate()
                process.wait(timeout=2)
                return {"failure": "timeout"}
            finally:
                finished.set()
                if cpu_watcher:
                    cpu_watcher.join(timeout=2)
                writer.join(timeout=2)
                for reader in readers:
                    reader.join(timeout=2)
            if exceeded.is_set():
                return {"failure": "output_limit"}
            if cpu_unavailable.is_set():
                raise ExecutionUnavailable("CPU accounting became unavailable")
            if cpu_exceeded.is_set():
                return {"failure": "cpu_limit"}
            if process.returncode != 0 or errors:
                return {"failure": "worker_failure"}
            result = _checked_json(bytes(output), wire_output_cap)
            if type(result) is not dict:
                return {"failure": "worker_protocol"}
            if result.get("failure") == "containment_unavailable":
                raise ExecutionUnavailable("Worker CPU/memory enforcement unavailable")
            return result
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise ExecutionUnavailable("Worker could not be contained or decoded") from exc
        finally:
            finished.set()
            terminate()
            process.wait(timeout=2)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe and not pipe.closed:
                    pipe.close()
            if job is not None:
                job.close()


def _install_io_guard():
    """Defense in depth for trusted Python with data-only inputs, not native code."""
    def guard(event, args):
        if (event == "open" or event.startswith(("socket.", "subprocess.", "ctypes."))
                or event in {"os.system", "os.listdir", "os.scandir", "os.chdir", "os.remove", "os.rename",
                             "os.mkdir", "os.rmdir", "os.link", "os.symlink", "os.truncate"}
                or event.startswith(("os.exec", "os.spawn", "os.fork"))):
            raise PermissionError("worker_io_denied")
    sys.addaudithook(guard)


def _worker_main():
    # Only this trusted code runs before resource admission. No untrusted code is loaded.
    request = _checked_json(sys.stdin.buffer.read(400_000), 400_000)
    limits = CandidateExecutionLimits(**request["limits"])
    if sys.platform == "linux":
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
            cpu = max(1, math.ceil(limits.cpu_seconds))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        except (ImportError, ValueError, OSError):
            sys.stdout.buffer.write(_encode({"failure": "containment_unavailable"}))
            return
    mode, data = request["mode"], request["payload"]
    from .candidate_runtime import CandidateInterpreter
    # Resolve imports and Pydantic lazy attributes before denying all filesystem opens.
    if mode in {"generation", "generation_probe"}:
        from .candidate_generation import request_candidate_spec, request_guided_spec
        from .model_gateway import GatewayError, ModelGateway, MockProvider
        from .budgets import RunBudget
        from .contracts import Budgets
    elif mode == "reference":
        import importlib.util
        spec = importlib.util.spec_from_file_location("_owned_reference", Path.cwd() / "_owned_reference.py")
        reference_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference_module)
    _install_io_guard()
    try:
        if mode == "candidate":
            contract = ScopeContract.model_validate(data["contract"])
            loaded = load_candidate(data["spec"].encode("utf-8"), contract)
            interpreter = CandidateInterpreter(loaded.spec, max_actions=limits.max_actions,
                                               max_records=limits.max_records, max_output_bytes=limits.max_output_bytes)
            result = interpreter.execute_sequence(data["actions"], sequence_id=data["sequence_id"])
            if sum(len(_encode(obs.output)) for obs in result.observations) > limits.max_output_bytes:
                response = {"failure": "output_limit"}
            else:
                response = {"result": result.model_dump(mode="json"), "spec_digest": loaded.digest}
        elif mode == "reference":
            class BoundedOutput(io.StringIO):
                size = 0
                def write(self, text):
                    self.size += len(text.encode("utf-8"))
                    if self.size > limits.max_output_bytes:
                        raise ValueError("reference_output_limit")
                    return super().write(text)
            incoming, outgoing = sys.stdin, sys.stdout
            capture = BoundedOutput()
            started = time.monotonic()
            try:
                sys.stdin = io.StringIO("".join(_encode(action).decode("utf-8") + "\n" for action in data["actions"]))
                sys.stdout = capture
                reference_module.run()
            finally:
                sys.stdin, sys.stdout = incoming, outgoing
            lines = capture.getvalue().splitlines()
            if len(lines) != len(data["actions"]):
                raise ValueError("reference_protocol")
            observations = []
            for i, (action, line) in enumerate(zip(data["actions"], lines)):
                output = _checked_json(line.encode("utf-8"), limits.max_output_bytes)
                if type(output) is not dict or type(output.get("ok")) is not bool:
                    raise ValueError("reference_protocol")
                observations.append(Observation(
                    observation_id=f"{data['sequence_id']}:{i}", sequence_id=data["sequence_id"],
                    action_index=i, input_action=action, output=output, exit_code=0,
                    duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                    status="ok" if output["ok"] else "target_error",
                ))
            response = {"result": SequenceResult(sequence_id=data["sequence_id"],
                        observations=tuple(observations), status="ok").model_dump(mode="json")}
        elif mode == "generation":
            captured = []
            def capture(request):
                captured.append(request)
                # Stop before any response: inspect the real gateway's final wire request.
                raise GatewayError("capture_complete")
            gateway = ModelGateway(MockProvider(responder=capture), RunBudget(Budgets(max_estimated_model_spend_usd=0)))
            try:
                synthesis = data.get("synthesis", "full")
                if synthesis not in ("full", "guided"):
                    raise GatewayError("Unsupported synthesis protocol")
                repair = data.get("repair")
                if repair is None:
                    generate = request_guided_spec if synthesis == "guided" else request_candidate_spec
                    generate(data["context"], gateway)
                else:
                    # Feedback-conditioned repair: guided only, aggregate
                    # counts only. Anything else fails closed here, before
                    # any request bytes are built.
                    from .candidate_generation import (
                        build_guided_repair_request, build_spec_skeleton,
                        sanitize_repair_feedback,
                    )
                    if synthesis != "guided":
                        raise GatewayError("Unsupported repair protocol")
                    guidance = sanitize_repair_feedback(
                        repair.get("feedback") if isinstance(repair, dict) else None)
                    repair_round = repair.get("round")
                    if type(repair_round) is not int or repair_round < 1:
                        raise GatewayError("Repair round rejected")
                    skeleton = build_spec_skeleton(data["context"]["public_commands"])
                    gateway.generate(build_guided_repair_request(
                        data["context"], skeleton, guidance,
                        repair_round=repair_round))
            except GatewayError:
                pass
            response = {"request": captured[0].model_dump(mode="json")} if len(captured) == 1 else {"failure": "generation_rejected"}
        elif mode in {"probe", "generation_probe"}:
            # Fixed evaluator probes, never arbitrary instructions or code.
            import socket
            checks = {}
            for name, action in (("file", lambda: open(data["path"], "rb")),
                                 ("network", lambda: socket.socket()),
                                 ("process", lambda: subprocess.Popen([sys.executable, "-c", "pass"]))):
                try:
                    action()
                    checks[name] = False
                except PermissionError:
                    checks[name] = True
            checks["environment_empty"] = not any(key.upper() not in {"SYSTEMROOT", "PYTHONIOENCODING", "PYTHONDONTWRITEBYTECODE", "LC_CTYPE"} for key in os.environ)
            checks["evaluator_not_imported"] = "second_source.g3_verification" not in sys.modules
            checks["reference_not_staged"] = not (Path.cwd() / "_owned_reference.py").exists()
            if "inherited_fd" in data:
                try:
                    os.fstat(data["inherited_fd"])
                    checks["inherited_fd_closed"] = False
                except OSError:
                    checks["inherited_fd_closed"] = True
            response = {"checks": checks}
        elif mode == "limit_probe":
            if data["kind"] == "wall":
                time.sleep(limits.wall_seconds * 3)
            elif data["kind"] == "cpu":
                while True:
                    pass
            elif data["kind"] == "memory":
                bytearray(limits.memory_bytes * 2)
            elif data["kind"] == "output":
                sys.stdout.buffer.write(b"x" * (limits.max_output_bytes + limits.max_input_bytes + 40_000))
            response = {"unexpected_success": True}
        else:
            response = {"failure": "unknown_worker_mode"}
    except MemoryError:
        response = {"failure": "memory_limit"}
    except Exception:
        response = {"failure": "worker_failure"}
    sys.stdout.buffer.write(_encode(response))


class CandidateReferenceAdapter:
    def __init__(self, spec_bytes: bytes, contract: ScopeContract, *, limits: CandidateExecutionLimits | None = None):
        self.limits = limits or CandidateExecutionLimits()
        try:
            _checked_json(spec_bytes, MAX_SPEC_BYTES)
            loaded = load_candidate(spec_bytes, contract)
        except Exception:
            raise CandidateError("Candidate admission rejected") from None
        if contract.target.kind != TargetKind.CLI:
            raise CandidateError("Candidate adapter requires an authorized CLI scope")
        self._spec_bytes = bytes(spec_bytes)
        self._contract_bytes = contract.model_dump_json().encode("utf-8")
        self._digest = loaded.digest

    @property
    def spec_digest(self) -> str:
        return self._digest

    def check_containment(self) -> None:
        response = _run_worker("probe", {"path": "not-an-input-file"}, self.limits)
        checks = response.get("checks")
        if type(checks) is not dict or not checks or not all(checks.values()):
            raise ExecutionUnavailable("Required worker containment probes failed")

    def execute_sequence(self, actions: list[dict], *, sequence_id: str | None = None) -> SequenceResult:
        seq = sequence_id or uuid4().hex
        try:
            if type(actions) is not list or len(actions) > self.limits.max_actions:
                raise ValueError("action limit")
            raw = _encode(actions)
            snapshot = _checked_json(raw, self.limits.max_input_bytes)
            if any(type(action) is not dict for action in snapshot):
                raise ValueError("actions must be objects")
        except Exception:
            return SequenceResult(sequence_id=seq, observations=(), status="protocol_error", stderr="input_limit_or_shape")
        response = _run_worker("candidate", {"spec": self._spec_bytes.decode("utf-8"),
            "contract": json.loads(self._contract_bytes), "actions": snapshot, "sequence_id": seq}, self.limits)
        if response.get("spec_digest") == self._digest and "result" in response:
            try:
                return SequenceResult.model_validate(response["result"])
            except Exception:
                pass
        status = "timeout" if response.get("failure") == "timeout" else "protocol_error"
        return SequenceResult(sequence_id=seq, observations=(), status=status, stderr="candidate_worker_failed")
