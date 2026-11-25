"""Run VS Code tunnel commands without an attached Docker exec stream."""

import io
import subprocess
import tarfile
import threading
import time
from contextlib import closing, suppress
from typing import Callable, Optional, Tuple
from uuid import uuid4

import docker
from docker.errors import DockerException, NotFound

# Run the command with its output in a file, and record its PID next to it so the
# command can be stopped from a later exec. After `exec`, $$ is the command's PID.
_WRAPPER = (
    'umask 077; output=$1; shift; echo $$ > "$output.pid"; '
    'exec "$@" > "$output" 2>&1'
)
# Stop the command if it is still running, then remove its files.
_STOP = 'pid=$(cat "$1.pid" 2>/dev/null) && kill "$pid" 2>/dev/null; '
_CLEANUP = 'rm -f -- "$1" "$1.pid"'

_client: Optional[docker.DockerClient] = None
_client_lock = threading.Lock()


def docker_client() -> docker.DockerClient:
    """One Docker client, and connection pool, shared by every tunnel call."""
    global _client
    with _client_lock:
        if _client is None:
            _client = docker.from_env(timeout=5)
        return _client


class TunnelExec:
    """Read output and exit status through ordinary Docker API requests.

    ``close()`` stops the command inside the container if it is still running and
    removes its output. ``release()`` leaves the command running and its output in
    place, for long-running processes such as the tunnel itself.
    """

    def __init__(
        self, container_name: str, command: list, output_path: Optional[str] = None
    ) -> None:
        # TCP proxies can forward the first exec output frame but lose the remaining
        # output and EOF. Use detached exec, inspect, and an output file.
        self._container = container_name
        self._path = output_path or f"/tmp/.devs-tunnel-{uuid4().hex}"
        self._closed = False
        self._id: Optional[str] = None
        self._returncode: Optional[int] = None
        self._api = docker_client().api
        try:
            self._id = self._start(
                ["/bin/sh", "-c", _WRAPPER, "sh", self._path, *command]
            )
        except BaseException:
            self.close()
            raise

    def _start(self, command: list) -> str:
        exec_id: str = self._api.exec_create(self._container, command)["Id"]
        self._api.exec_start(exec_id, detach=True)
        return exec_id

    def poll(self) -> Optional[int]:
        if self._returncode is None and self._id is not None:
            state = self._api.exec_inspect(self._id)
            if not state["Running"]:
                self._returncode = state["ExitCode"]
        return self._returncode

    def output(self) -> str:
        try:
            archive, _ = self._api.get_archive(self._container, self._path)
        except NotFound:
            # The command may not have opened the output file yet.
            return ""
        with tarfile.open(fileobj=io.BytesIO(b"".join(archive))) as stream:
            member = stream.next()
            output = stream.extractfile(member) if member is not None else None
            return output.read().decode("utf-8", errors="replace") if output else ""

    def wait(
        self,
        timeout: float,
        interval: float,
        until: Optional[Callable[[str], object]] = None,
    ) -> Tuple[Optional[int], str]:
        """Poll until the command exits, ``until(output)`` is true, or the timeout.

        Returns the exit code (None if still running) and the output so far.
        Without ``until``, the output is read only once the command has exited.
        """
        deadline = time.monotonic() + timeout
        while True:
            returncode = self.poll()
            output = self.output() if returncode is not None or until else ""
            if returncode is not None or (until and until(output)):
                return returncode, output
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None, output
            time.sleep(min(interval, remaining))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with suppress(DockerException, OSError):
            running = self._id is not None and self.poll() is None
            script = (_STOP if running else "") + _CLEANUP
            self._start(["/bin/sh", "-c", script, "sh", self._path])

    def release(self) -> None:
        self._closed = True


def run_tunnel_exec(
    container_name: str, command: list, timeout: float = 10
) -> subprocess.CompletedProcess:
    """Return the remote exit code and output within the polling deadline."""
    with closing(TunnelExec(container_name, command)) as execution:
        returncode, output = execution.wait(timeout, 0.1)
    if returncode is None:
        raise subprocess.TimeoutExpired(command, timeout)
    return subprocess.CompletedProcess(command, returncode, stdout=output)


def container_workspace_dir(container_name: str) -> Optional[str]:
    """Return the /workspaces/<name> folder a container actually mounts.

    Live-mode containers mount the host folder under its own name, so the path
    can't be derived from the container name.
    """
    mounts = docker_client().api.inspect_container(container_name).get("Mounts") or []
    for mount in mounts:
        destination = mount.get("Destination") or ""
        parts = destination.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "workspaces" and parts[1]:
            return destination
    return None
