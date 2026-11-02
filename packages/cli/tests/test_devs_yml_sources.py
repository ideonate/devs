"""DEVS.yml comes from ~/.devs/envs only, never from the repository."""

from devs_common.devs_config import DevsConfigLoader


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_a_repo_devs_yml_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    _write(repo / "DEVS.yml", "direct_commit: true\ndefault_branch: dev\n")
    monkeypatch.chdir(repo)

    options = DevsConfigLoader.load("myorg-myapp")
    assert options.direct_commit is False
    assert options.default_branch == "main"


def test_project_env_overrides_default(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    envs = home / ".devs" / "envs"
    _write(envs / "default" / "DEVS.yml",
           "default_branch: dev\nenv_vars:\n  default:\n    A: '1'\n    B: '1'\n")
    _write(envs / "myorg-myapp" / "DEVS.yml",
           "single_queue: true\nenv_vars:\n  default:\n    B: '2'\n")

    options = DevsConfigLoader.load("myorg-myapp")
    assert options.default_branch == "dev"
    assert options.single_queue is True
    assert options.get_env_vars() == {"A": "1", "B": "2"}
    assert DevsConfigLoader.load("myorg-other").single_queue is False
