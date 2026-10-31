"""host_devcontainer: DEVS.yml decides, and it's off unless asked for."""

from devs_common.devs_config import DevsConfigLoader, DevsOptions


def test_off_by_default():
    assert DevsOptions().host_devcontainer is False


def test_set_in_the_user_project_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    env = tmp_path / ".devs" / "envs" / "myorg-myapp"
    env.mkdir(parents=True)
    (env / "DEVS.yml").write_text("host_devcontainer: true\n")
    repo = tmp_path / "repo"
    repo.mkdir()

    assert DevsConfigLoader.load("myorg-myapp", repo).host_devcontainer is True
    assert DevsConfigLoader.load("myorg-other", repo).host_devcontainer is False
