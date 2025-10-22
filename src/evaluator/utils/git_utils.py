import os
import subprocess
from contextlib import contextmanager


class GitManager:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def _run_git(self, command: list) -> subprocess.CompletedProcess:
        original_cwd = os.getcwd()
        try:
            os.chdir(self.repo_path)
            return subprocess.run(["git"] + command, capture_output=True, text=True)
        finally:
            os.chdir(original_cwd)

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
