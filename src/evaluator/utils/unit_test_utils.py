from abc import ABC, abstractmethod
from contextlib import contextmanager
import os
import json
import subprocess
from typing import Dict, Any, List, Optional
from pathlib import Path
from typing_extensions import override


class PytestRunner(ABC):
    @abstractmethod
    def run_pytest(self, args, kwargs) -> None:
        pass


class DockerPytestRunner(PytestRunner):
    def __init__(self, container_name: str, repo_path: Path):
        self.container_name = container_name
        self.repo_path = repo_path

    @override
    def run_pytest(self, args, kwargs) -> None:
        pass


class UTPRGitManager(ABC):
    @abstractmethod
    def _run_git(self, command: List[str]) -> subprocess.CompletedProcess:
        pass

    def create_branch_from_patch(
        self, old_branch_name: str, new_branch_name: str, patch_content: str
    ):
        """
        Inside the container, create a branch from patch
        """

        """
        Either write patch to tempfile to git apply, or apply from stdin directly like this:
        git apply - << 'EOF'
        <diff content>
        EOF
        """
        pass

    def delete_branch(self, branch_name: str):
        """
        Inside the container, delete a branch
        """
        pass

    @contextmanager
    def branch_context(self, branch_name: str):
        # Get current branch
        result = self._run_git(["branch", "--show-current"])
        original_branch = result.stdout.strip() if result.returncode == 0 else None

        try:
            self._run_git(["checkout", branch_name])
            # return control to the caller and once returned it will restore the original branch
            yield self
        finally:
            if original_branch and original_branch != branch_name:
                self._run_git(["checkout", original_branch])


class DockerUTPRGitManager(UTPRGitManager):
    """
    Manage a Git repo inside a docker container
    """

    def __init__(self, container_name: str, repo_path: Path):
        self.container_name = container_name
        self.repo_path = repo_path

    @override
    def _run_git(self, command: List[str]) -> subprocess.CompletedProcess:
        def _does_container_exist(container_name: str) -> bool:
            return False

        def _does_repo_exist(container_name: str, repo_path: Path) -> bool:
            return False

        if not _does_container_exist(self.container_name):
            raise RuntimeError(
                f"Can't find repo container with name '{self.container_name}'"
            )

        if not _does_repo_exist(self.container_name, self.repo_path):
            raise RuntimeError(
                f"Can't find repo at path '{self.repo_path}' in container with name '{self.container_name}'"
            )

        git_command_list = ["git"]
        git_command_list.extend(command)
        git_command = " ".join(git_command_list)
        bash_script = f"cd {self.repo_path} && {git_command}"
        return subprocess.run(
            ["docker", "exec", self.container_name, "/bin/bash", "-c", bash_script]
            + command,
            capture_output=True,
            text=True,
        )
