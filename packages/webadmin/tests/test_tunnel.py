"""Regression tests for VS Code tunnels over a Docker proxy."""

import io
import subprocess
import tarfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from devs_webadmin.api import routes
from devs_webadmin.api import tunnel_exec
from devs_webadmin.app import app

PROJECT = {"project_name": "org-demo", "dev_name": "work"}
CONTAINER = "dev-org-demo-work"


def fake_execution():
    """A TunnelExec stand-in: mock poll/output, with the real wait() over them."""
    execution = Mock()
    execution.wait.side_effect = lambda *args, **kwargs: tunnel_exec.TunnelExec.wait(
        execution, *args, **kwargs
    )
    return execution


@pytest.fixture
def fake_docker(monkeypatch):
    docker = Mock()
    docker.api.exec_create.return_value = {"Id": "exec-id"}
    docker.api.exec_inspect.return_value = {"Running": False, "ExitCode": 0}
    data = b'{"tunnel":null}\n'
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo("output")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    docker.api.get_archive.return_value = (iter([buffer.getvalue()]), {})
    monkeypatch.setattr(tunnel_exec, "_client", docker)
    return docker


@pytest.mark.parametrize("returncode", [0, 127])
def test_exec_reads_output_and_status_without_attaching(fake_docker, returncode):
    fake_docker.api.exec_inspect.side_effect = [
        {"Running": True, "ExitCode": None},
        {"Running": False, "ExitCode": returncode},
    ]
    command = ["/usr/local/bin/code", "tunnel", "status"]
    result = tunnel_exec.run_tunnel_exec(CONTAINER, command, timeout=2)

    assert result.returncode == returncode
    assert result.stdout == '{"tunnel":null}\n'
    assert all(
        call.kwargs == {"detach": True}
        for call in fake_docker.api.exec_start.call_args_list
    )
    assert fake_docker.api.exec_create.call_args_list[0].args[1][-3:] == command
    output_path = fake_docker.api.get_archive.call_args.args[1]
    cleanup = fake_docker.api.exec_create.call_args.args[1]
    assert cleanup[-1] == output_path
    assert "rm -f" in cleanup[2] and "kill" not in cleanup[2]
    fake_docker.close.assert_not_called()  # the client is shared


def test_close_stops_a_command_that_is_still_running(fake_docker):
    fake_docker.api.exec_inspect.return_value = {"Running": True, "ExitCode": None}
    tunnel_exec.TunnelExec(CONTAINER, ["sleep", "100"]).close()
    cleanup = fake_docker.api.exec_create.call_args.args[1]
    assert 'kill "$pid"' in cleanup[2]
    assert "rm -f" in cleanup[2]


def test_release_leaves_the_command_running(fake_docker):
    execution = tunnel_exec.TunnelExec(CONTAINER, ["sleep", "100"], output_path="/tmp/log")
    execution.release()
    execution.close()  # no-op once released
    assert fake_docker.api.exec_create.call_count == 1
    assert fake_docker.api.exec_create.call_args.args[1][4] == "/tmp/log"
    fake_docker.close.assert_not_called()  # the client is shared


def test_exec_times_out_when_command_never_reports_completion(fake_docker):
    fake_docker.api.exec_inspect.return_value = {"Running": True, "ExitCode": None}
    with pytest.raises(subprocess.TimeoutExpired):
        tunnel_exec.run_tunnel_exec(CONTAINER, ["true"], timeout=0.1)
    fake_docker.api.get_archive.assert_not_called()
    fake_docker.close.assert_not_called()  # the client is shared


def test_exec_allows_output_file_to_be_created_after_start(fake_docker):
    fake_docker.api.get_archive.side_effect = tunnel_exec.NotFound("not created yet")
    execution = tunnel_exec.TunnelExec(CONTAINER, ["true"])
    try:
        assert execution.output() == ""
    finally:
        execution.close()


def test_tunnel_status_uses_connected_name(monkeypatch):
    monkeypatch.setattr(routes, "container_workspace_dir", Mock(return_value=None))
    monkeypatch.setattr(
        routes,
        "run_tunnel_exec",
        Mock(
            return_value=subprocess.CompletedProcess(
                [],
                0,
                'diagnostic\n{"tunnel":{"tunnel":"Connected","name":"actual-name"}}\n',
            )
        ),
    )
    response = TestClient(app).get("/api/tunnel/status", params=PROJECT)
    assert response.status_code == 200
    assert response.json()["running"] is True
    assert (
        response.json()["web_url"]
        == "https://vscode.dev/tunnel/actual-name/workspaces/org-demo-work"
    )


def test_start_requests_sign_in_when_credentials_are_missing(monkeypatch):
    exec_command = Mock(
        return_value=subprocess.CompletedProcess([], 1, "not logged in\n")
    )
    monkeypatch.setattr(routes, "run_tunnel_exec", exec_command)
    response = TestClient(app).post("/api/tunnel/start", json=PROJECT)
    assert response.json()["status"] == "auth_required"
    exec_command.assert_called_once_with(
        CONTAINER, [routes._TUNNEL_CLI, "tunnel", "user", "show"]
    )


def test_start_reports_missing_standalone_cli(monkeypatch):
    monkeypatch.setattr(
        routes,
        "run_tunnel_exec",
        Mock(return_value=subprocess.CompletedProcess([], 127, "CLI missing\n")),
    )
    response = TestClient(app).post("/api/tunnel/start", json=PROJECT)
    assert response.status_code == 400
    assert "Install the standalone VS Code CLI" in response.json()["detail"]


class FakeTunnelCli:
    """Stand-in for run_tunnel_exec, answering by command."""

    def __init__(self, status='{"tunnel":null}', kill_rc=0):
        self.status = status
        self.kill_rc = kill_rc
        self.calls = []

    def __call__(self, container, command, timeout=10):
        self.calls.append(command)
        if command[-1] == "show":
            return subprocess.CompletedProcess(command, 0, "logged in\n")
        if command[-1] == "status":
            return subprocess.CompletedProcess(command, 0, self.status + "\n")
        if command[-1] == "kill":
            return subprocess.CompletedProcess(command, self.kill_rc, "No tunnel is running\n")
        return subprocess.CompletedProcess(command, 1, "")  # pkill: nothing matched


@pytest.fixture
def launched(monkeypatch):
    launch = fake_execution()
    launch.poll.return_value = None
    launch.output.return_value = "Open this link in your browser https://vscode.dev/tunnel/x\n"
    factory = Mock(return_value=launch)
    monkeypatch.setattr(routes, "TunnelExec", factory)
    monkeypatch.setattr(routes, "_START_GRACE_SECONDS", 1)
    return factory


def test_start_launches_detached_tunnel(monkeypatch, launched):
    cli = FakeTunnelCli()
    monkeypatch.setattr(routes, "run_tunnel_exec", cli)
    response = TestClient(app).post("/api/tunnel/start", json=PROJECT)
    assert response.json()["status"] == "starting"
    command = launched.call_args.args[1]
    assert command[-2:] == ["--name", CONTAINER]
    assert launched.call_args.kwargs["output_path"] == routes._TUNNEL_LOG
    launched.return_value.release.assert_called_once()
    launched.return_value.close.assert_not_called()
    assert ["pkill", "-f", routes._TUNNEL_PATTERN] not in cli.calls


def test_start_replaces_a_tunnel_that_is_not_connected(monkeypatch, launched):
    cli = FakeTunnelCli(status='{"tunnel":{"tunnel":"Disconnected","name":"old"}}')
    monkeypatch.setattr(routes, "run_tunnel_exec", cli)
    response = TestClient(app).post("/api/tunnel/start", json=PROJECT)
    assert response.json()["status"] == "starting"
    assert [routes._TUNNEL_CLI, "tunnel", "kill"] in cli.calls
    assert ["pkill", "-f", routes._TUNNEL_PATTERN] in cli.calls
    launched.assert_called_once()


def test_start_leaves_a_connected_tunnel_alone(monkeypatch, launched):
    cli = FakeTunnelCli(status='{"tunnel":{"tunnel":"Connected","name":"live"}}')
    monkeypatch.setattr(routes, "run_tunnel_exec", cli)
    response = TestClient(app).post("/api/tunnel/start", json=PROJECT)
    assert response.json() == {"status": "running", "tunnel_name": "live"}
    assert [routes._TUNNEL_CLI, "tunnel", "kill"] not in cli.calls
    launched.assert_not_called()


def test_start_returns_the_tunnels_device_login(monkeypatch, launched):
    # Stored credentials that no longer work: `user show` passes, the tunnel asks.
    monkeypatch.setattr(routes, "run_tunnel_exec", FakeTunnelCli())
    launched.return_value.output.return_value = (
        "To grant access to the server, please log into "
        "https://github.com/login/device and use code WXYZ-9876\n"
    )
    data = TestClient(app).post("/api/tunnel/start", json=PROJECT).json()
    assert data["status"] == "waiting_for_browser"
    assert data["device_code"] == "WXYZ-9876"
    launched.return_value.release.assert_called_once()


def test_start_reports_a_tunnel_that_exits(monkeypatch, launched):
    monkeypatch.setattr(routes, "run_tunnel_exec", FakeTunnelCli())
    launched.return_value.poll.return_value = 1
    launched.return_value.output.return_value = "error: something broke\n"
    response = TestClient(app).post("/api/tunnel/start", json=PROJECT)
    assert response.status_code == 400
    assert "something broke" in response.json()["detail"]


def test_kill_succeeds_when_no_tunnel_is_running(monkeypatch):
    cli = FakeTunnelCli(kill_rc=1)
    monkeypatch.setattr(routes, "run_tunnel_exec", cli)
    response = TestClient(app).post("/api/tunnel/kill", json=PROJECT)
    assert response.status_code == 200
    assert cli.calls[-1] == ["pkill", "-f", routes._TUNNEL_PATTERN]


def test_kill_falls_back_to_pkill_when_the_cli_hangs(monkeypatch):
    calls = []

    def cli(container, command, timeout=10):
        calls.append(command)
        if command[-1] == "kill":
            raise subprocess.TimeoutExpired(command, timeout)
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr(routes, "run_tunnel_exec", cli)
    assert TestClient(app).post("/api/tunnel/kill", json=PROJECT).status_code == 200
    assert calls[-1] == ["pkill", "-f", routes._TUNNEL_PATTERN]


def test_workspace_dir_follows_the_mount(monkeypatch):
    client = Mock()
    client.api.inspect_container.return_value = {
        "Mounts": [
            {"Destination": "/home/node/bridge"},
            {"Destination": "/workspaces/myapp"},
        ]
    }
    monkeypatch.setattr(tunnel_exec, "_client", client)
    assert routes._workspace_dir(CONTAINER, "/workspaces/default") == "/workspaces/myapp"


def test_workspace_dir_falls_back_without_a_workspace_mount(monkeypatch):
    monkeypatch.setattr(routes, "container_workspace_dir", Mock(return_value=None))
    assert routes._workspace_dir(CONTAINER, "/workspaces/default") == "/workspaces/default"


def test_device_flow_uses_remote_completion(monkeypatch):
    execution = fake_execution()
    execution.poll.return_value = None
    execution.output.return_value = (
        "Go to https://github.com/login/device\nand use code ABCD-1234\n"
    )
    monkeypatch.setattr(routes, "TunnelExec", Mock(return_value=execution))
    monkeypatch.setattr(routes, "_auth_processes", {})
    client = TestClient(app)

    auth = client.post("/api/tunnel/auth", json=PROJECT).json()
    assert auth["status"] == "waiting_for_browser"
    assert auth["device_code"] == "ABCD-1234"
    assert (
        client.get("/api/tunnel/auth/status", params=PROJECT).json()["status"]
        == "waiting_for_browser"
    )

    execution.poll.return_value = 0
    assert (
        client.get("/api/tunnel/auth/status", params=PROJECT).json()["status"]
        == "authenticated"
    )


def test_overlapping_auth_requests_share_one_login(monkeypatch):
    execution = fake_execution()
    execution.poll.return_value = None
    outputs = iter(["", "", "", ""])
    execution.output.side_effect = lambda: next(
        outputs, "https://github.com/login/device code ABCD-1234"
    )
    factory = Mock(return_value=execution)
    monkeypatch.setattr(routes, "TunnelExec", factory)
    monkeypatch.setattr(routes, "_auth_processes", {})
    monkeypatch.setattr(tunnel_exec.time, "sleep", lambda _: None)
    client = TestClient(app)

    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(lambda _: client.post("/api/tunnel/auth", json=PROJECT).json(), [1, 2])
        )
    assert [r["device_code"] for r in results] == ["ABCD-1234", "ABCD-1234"]
    factory.assert_called_once()
    execution.close.assert_not_called()
