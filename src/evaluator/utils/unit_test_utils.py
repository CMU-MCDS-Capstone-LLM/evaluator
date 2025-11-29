from abc import ABC, abstractmethod
from contextlib import contextmanager
import os
import json
import subprocess
from typing import Dict, Any, List, Optional
from pathlib import Path
from typing_extensions import override
import pytest


class CollectResultsPlugin:
    """
    Pytest plugin to collect test results.
    Stores a dict per test like:
    {
        "nodeid": str,
        "outcome": "passed" | "failed" | "skipped" | "xfailed" | "xpassed" | "error",
        "when": str,
        "duration": float,
        "longrepr": str or None,
    }
    """

    def __init__(self):
        # nodeid -> result dict
        self.results = {}  # type: Dict[str, Dict[str, Any]]

    def _ensure_result(self, report):
        nodeid = report.nodeid
        if nodeid not in self.results:
            self.results[nodeid] = {
                "nodeid": nodeid,
                "outcome": "",
                "when": report.when,
                "duration": 0.0,
                "longrepr": None,
            }
        return self.results[nodeid]

    def pytest_runtest_logreport(self, report):
        """
        Called for each test phase: setup/call/teardown.
        """
        result = self._ensure_result(report)

        # accumulate duration across phases
        result["duration"] += getattr(report, "duration", 0.0) or 0.0
        result["when"] = report.when

        def set_outcome(o):
            # precedence: error > failed/xpassed > xfailed > skipped > passed
            precedence = {
                "error": 5,
                "failed": 4,
                "xpassed": 4,
                "xfailed": 3,
                "skipped": 2,
                "passed": 1,
                "": 0,
            }
            current = result.get("outcome", "")
            if precedence[o] >= precedence.get(current, 0):
                result["outcome"] = o

        # setup/teardown failures -> error
        if report.when in ("setup", "teardown") and report.failed:
            set_outcome("error")
            result["longrepr"] = str(report.longrepr)
            return

        # only 'call' phase represents the logical test result
        if report.when != "call":
            return

        # base outcome: "passed", "failed", "skipped"
        outcome = report.outcome

        # handle xfail/xpass
        if hasattr(report, "wasxfail"):
            if report.skipped:
                outcome = "xfailed"
            elif report.failed:
                outcome = "xpassed"

        set_outcome(outcome)

        if outcome != "passed":
            result["longrepr"] = str(report.longrepr)


class PytestRunner(ABC):
    @abstractmethod
    def run_pytest(
        self, test_path: Path, args: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Run pytest and return list of test result dictionaries.

        Parameters:
            test_path: Path to test file or directory
            args: Additional pytest arguments

        Returns:
            List of test result dictionaries
        """
        pass


class LocalPytestRunner(PytestRunner):
    """Run pytest locally using programmatic API"""

    def __init__(self, repo_path: Optional[Path] = None):
        """
        Parameters:
            repo_path: Root path of repository (for changing directory before running tests)
        """
        raise NotImplementedError("Local pytest runner not implemented!")
        self.repo_path = repo_path

    @override
    def run_pytest(
        self, test_path: Path, args: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Run pytest programmatically and return test results.

        Parameters:
            test_path: Path to test file or directory
            args: Additional pytest arguments

        Returns:
            List of test result dictionaries from CollectResultsPlugin
        """
        if args is None:
            args = []

        plugin = CollectResultsPlugin()
        pytest_args = [str(test_path)] + args + ["-q"]

        # Change to repo directory if specified
        original_cwd = None
        if self.repo_path:
            original_cwd = os.getcwd()
            os.chdir(self.repo_path)

        try:
            # Run pytest with our custom plugin
            exit_code = pytest.main(pytest_args, plugins=[plugin])
            return list(plugin.results.values())
        finally:
            # Restore original directory
            if original_cwd:
                os.chdir(original_cwd)


class DockerPytestRunner(PytestRunner):
    """Run pytest inside a Docker container"""

    def __init__(self, container_name: str, repo_path: Path):
        """
        Parameters:
            container_name: Name of the Docker container
            repo_path: Path to repository inside the container
        """
        self.container_name = container_name
        self.repo_path = repo_path

    @override
    def run_pytest(
        self, test_path: Path, args: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Run pytest inside Docker container and return test results.

        Parameters:
            test_path: Path to test file or directory (relative to repo_path or absolute)
            args: Additional pytest arguments

        Returns:
            List of test result dictionaries
        """
        # breakpoint()
        if args is None:
            args = []

        # Create a temporary Python script that runs pytest with our plugin
        plugin_script = self._create_pytest_runner_script()

        # Write the script to a temp file in the container
        temp_script_path = f"/tmp/pytest_runner_{os.getpid()}.py"
        temp_json_path = f"/tmp/pytest_runner_{os.getpid()}.json"

        try:
            # Write the plugin script to container
            write_cmd = [
                "docker",
                "exec",
                "-i",
                self.container_name,
                "tee",
                temp_script_path,
            ]
            subprocess.run(
                write_cmd, input=plugin_script.encode(), check=True, capture_output=True
            )

            # Build pytest command
            pytest_args_str = " ".join([f"'{arg}'" for arg in args])
            test_path_str = str(test_path)

            # Run the script inside the container (will write results to temp_json_path)
            run_script_cmd = [
                "docker",
                "exec",
                self.container_name,
                "/bin/bash",
                "-c",
                f"cd {self.repo_path} && python {temp_script_path} {test_path_str} {pytest_args_str}",
            ]
            subprocess.run(run_script_cmd, check=False, capture_output=True, text=True)

            # Read the results from the JSON file written by the script
            read_cmd = ["docker", "exec", self.container_name, "cat", temp_json_path]
            result = subprocess.run(
                read_cmd, check=True, capture_output=True, text=True
            )

            # Parse JSON results
            results_data = json.loads(result.stdout)
            return results_data

        finally:
            # Clean up temp files in container
            cleanup_cmd = [
                "docker",
                "exec",
                self.container_name,
                "/bin/bash",
                "-c",
                f"rm -f {temp_script_path} {temp_json_path}",
            ]
            subprocess.run(cleanup_cmd, check=False, capture_output=True)

    def _create_pytest_runner_script(self) -> str:
        """Create a Python script that runs pytest with CollectResultsPlugin and outputs JSON"""
        return '''
import pytest
import json
import sys

class CollectResultsPlugin:
    """Pytest plugin to collect test results."""

    def __init__(self):
        self.results = {}

    def _ensure_result(self, report):
        nodeid = report.nodeid
        if nodeid not in self.results:
            self.results[nodeid] = {
                "nodeid": nodeid,
                "outcome": "",
                "when": report.when,
                "duration": 0.0,
                "longrepr": None,
            }
        return self.results[nodeid]

    def pytest_runtest_logreport(self, report):
        """Called for each test phase: setup/call/teardown."""
        result = self._ensure_result(report)

        result["duration"] += getattr(report, "duration", 0.0) or 0.0
        result["when"] = report.when

        def set_outcome(o):
            precedence = {
                "error": 5,
                "failed": 4,
                "xpassed": 4,
                "xfailed": 3,
                "skipped": 2,
                "passed": 1,
                "": 0,
            }
            current = result.get("outcome", "")
            if precedence[o] >= precedence.get(current, 0):
                result["outcome"] = o

        if report.when in ("setup", "teardown") and report.failed:
            set_outcome("error")
            result["longrepr"] = str(report.longrepr)
            return

        if report.when != "call":
            return

        outcome = report.outcome

        if hasattr(report, "wasxfail"):
            if report.skipped:
                outcome = "xfailed"
            elif report.failed:
                outcome = "xpassed"

        set_outcome(outcome)

        if outcome != "passed":
            result["longrepr"] = str(report.longrepr)

if __name__ == "__main__":
    import os
    plugin = CollectResultsPlugin()
    pytest_args = sys.argv[1:] + ["-q"]
    pytest.main(pytest_args, plugins=[plugin])

    results = list(plugin.results.values())

    # Get absolute path of this script file and change suffix to .json
    script_path = os.path.abspath(__file__)
    json_output_path = script_path.replace('.py', '.json')

    # Write results to JSON file
    with open(json_output_path, 'w') as f:
        json.dump(results, f, indent=2)
'''


class UTPRGitManager(ABC):
    """Abstract base class for managing git operations for unit test pass rate evaluation"""

    @abstractmethod
    def _run_git(self, command: List[str]) -> subprocess.CompletedProcess:
        """Execute a git command and return the result"""
        pass

    def create_branch_from_patch(
        self, old_branch_name: str, new_branch_name: str, patch_content: str
    ):
        """
        Create a new branch from an existing branch and apply a patch.

        Parameters:
            old_branch_name: Branch to create from
            new_branch_name: Name of new branch
            patch_content: Patch content as string
        """
        # Checkout old branch
        self._run_git(["checkout", old_branch_name])

        # Create and checkout new branch
        self._run_git(["checkout", "-b", new_branch_name])

        # Apply patch from stdin
        result = subprocess.run(
            ["git", "apply", "--3way"],
            input=patch_content.encode(),
            capture_output=True,
            text=False,
        )

        if result.returncode != 0:
            # Try with --reject if 3-way merge fails
            result = subprocess.run(
                ["git", "apply", "--reject"],
                input=patch_content.encode(),
                capture_output=True,
                text=False,
            )

        return result.returncode == 0

    def delete_branch(self, branch_name: str):
        """
        Delete a branch.

        Parameters:
            branch_name: Name of branch to delete
        """
        self._run_git(["branch", "-D", branch_name])

    @contextmanager
    def branch_context(self, branch_name: str):
        """
        Context manager to temporarily checkout a branch and restore original branch on exit.

        Parameters:
            branch_name: Branch to checkout
        """
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


class LocalUTPRGitManager(UTPRGitManager):
    """Manage git operations locally"""

    def __init__(self, repo_path: Path):
        """
        Parameters:
            repo_path: Path to git repository
        """
        raise NotImplementedError("Local pytest runner not implemented!")
        self.repo_path = repo_path

    @override
    def _run_git(self, command: List[str]) -> subprocess.CompletedProcess:
        """Execute git command in local repository"""
        git_command = ["git"] + command
        return subprocess.run(
            git_command,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )

    @override
    def create_branch_from_patch(
        self, old_branch_name: str, new_branch_name: str, patch_content: str
    ) -> bool:
        """
        Create a new branch from an existing branch and apply a patch locally.

        Parameters:
            old_branch_name: Branch to create from
            new_branch_name: Name of new branch
            patch_content: Patch content as string

        Returns:
            True if patch applied successfully, False otherwise
        """
        # Checkout old branch
        self._run_git(["checkout", old_branch_name])

        # Create and checkout new branch
        self._run_git(["checkout", "-b", new_branch_name])

        # Apply patch from stdin with 3-way merge
        result = subprocess.run(
            ["git", "apply", "--3way"],
            input=patch_content.encode(),
            capture_output=True,
            text=False,
            cwd=self.repo_path,
        )

        if result.returncode != 0:
            # Try with --reject if 3-way merge fails
            result = subprocess.run(
                ["git", "apply", "--reject"],
                input=patch_content.encode(),
                capture_output=True,
                text=False,
                cwd=self.repo_path,
            )

        return result.returncode == 0


class DockerUTPRGitManager(UTPRGitManager):
    """Manage a Git repo inside a docker container"""

    def __init__(self, container_name: str, repo_path: Path):
        """
        Parameters:
            container_name: Name of Docker container
            repo_path: Path to repository inside container
        """
        self.container_name = container_name
        self.repo_path = repo_path

    @override
    def _run_git(self, command: List[str]) -> subprocess.CompletedProcess:
        """Execute git command inside Docker container"""

        def _does_container_exist(container_name: str) -> bool:
            """Check if Docker container exists and is running"""
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={container_name}"],
                capture_output=True,
                text=True,
            )
            return bool(result.stdout.strip())

        def _does_repo_exist(container_name: str, repo_path: Path) -> bool:
            """Check if repo path exists inside container"""
            result = subprocess.run(
                ["docker", "exec", container_name, "test", "-d", str(repo_path)],
                capture_output=True,
            )
            return result.returncode == 0

        if not _does_container_exist(self.container_name):
            raise RuntimeError(
                f"Can't find running container with name '{self.container_name}'"
            )

        if not _does_repo_exist(self.container_name, self.repo_path):
            raise RuntimeError(
                f"Can't find repo at path '{self.repo_path}' in container '{self.container_name}'"
            )

        # Build git command
        git_command_list = ["git"] + command
        git_command = " ".join(
            [f"'{arg}'" if " " in arg else arg for arg in git_command_list]
        )
        bash_script = f"cd {self.repo_path} && {git_command}"

        result = subprocess.run(
            ["docker", "exec", self.container_name, "/bin/bash", "-c", bash_script],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to run git with command {command}: {result}")

        return result

    @override
    def create_branch_from_patch(
        self, old_branch_name: str, new_branch_name: str, patch_content: str
    ) -> bool:
        """
        Create a new branch from an existing branch and apply a patch inside Docker container.

        Parameters:
            old_branch_name: Branch to create from
            new_branch_name: Name of new branch
            patch_content: Patch content as string

        Returns:
            True if patch applied successfully, False otherwise
        """
        # Checkout old branch
        self._run_git(["checkout", old_branch_name])

        # Create and checkout new branch
        self._run_git(["checkout", "-b", new_branch_name])

        # Write patch to temp file in container and apply it
        temp_patch_path = f"/tmp/patch_{os.getpid()}.patch"

        try:
            # Write patch to container
            write_cmd = [
                "docker",
                "exec",
                "-i",
                self.container_name,
                "tee",
                temp_patch_path,
            ]
            subprocess.run(
                write_cmd, input=patch_content.encode(), check=True, capture_output=True
            )

            # Apply patch with 3-way merge
            apply_script = f"cd {self.repo_path} && git apply --3way {temp_patch_path}"
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    self.container_name,
                    "/bin/bash",
                    "-c",
                    apply_script,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Failed to apply generated patch: {result}")

            self._run_git(["add", "-A"])
            self._run_git(["commit", "-m", "Apply LLM-generated patch"])
            self._run_git(["checkout", old_branch_name])

            return result.returncode == 0

        finally:
            # Clean up temp patch file
            cleanup_cmd = [
                "docker",
                "exec",
                self.container_name,
                "rm",
                "-f",
                temp_patch_path,
            ]
            subprocess.run(cleanup_cmd, check=False, capture_output=True)
