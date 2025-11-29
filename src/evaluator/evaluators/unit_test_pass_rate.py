from abc import ABC, abstractmethod
from contextlib import contextmanager
import os
import json
import subprocess
from typing import Dict, Any, List, Literal, Optional, Self, Tuple, Union
from pathlib import Path

from ..utils.unit_test_utils import (
    DockerPytestRunner,
    DockerUTPRGitManager,
    LocalPytestRunner,
    LocalUTPRGitManager,
    PytestRunner,
    UTPRGitManager,
)
from .base import AbstractEvaluator

UnitTestResultType = Union[Literal["pass", "fail", "skipped", "other"]]


class UnitTestResult:
    """
    Result of executing unit test suite.

    Each result is a dict with keys:
        - nodeid: str (test identifier)
        - outcome: "passed" | "failed" | "skipped" | "xfailed" | "xpassed" | "error"
        - when: str (last phase seen, usually "call" or "setup")
        - duration: float (seconds, sum over phases)
        - longrepr: str or None (traceback, skip reason, etc.)
    """

    def __init__(self, results: List[Dict[str, Any]]):
        """
        Parameters:
            results: List of test result dictionaries from pytest plugin
        """
        self.results = results

    def get_pass_count(self) -> int:
        """Count tests with outcome='passed'"""
        return sum(1 for r in self.results if r.get("outcome") == "passed")

    def get_fail_count(self) -> int:
        """Count tests with outcome='failed'"""
        return sum(1 for r in self.results if r.get("outcome") == "failed")

    def get_total_count(self) -> int:
        """Count all tests"""
        return len(self.results)

    def get_pass_rate(self) -> float:
        """Return percentage of passed tests (0-100)"""
        total = self.get_total_count()
        if total == 0:
            return 0.0
        return (self.get_pass_count() / total) * 100.0

    def get_passing_test_nodeids(self) -> set:
        """Return set of nodeids for tests with outcome='passed'"""
        return {r["nodeid"] for r in self.results if r.get("outcome") == "passed"}

    def get_test_outcome(self, nodeid: str) -> Optional[str]:
        """Get outcome for a specific test by nodeid"""
        for r in self.results:
            if r.get("nodeid") == nodeid:
                return r.get("outcome")
        return None

    def filter_by_nodeids(self, nodeid_set: set) -> "UnitTestResult":
        """Return new UnitTestResult containing only tests matching given nodeids"""
        filtered_results = [r for r in self.results if r.get("nodeid") in nodeid_set]
        return UnitTestResult(filtered_results)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage"""
        return {
            "total_count": self.get_total_count(),
            "pass_count": self.get_pass_count(),
            "fail_count": self.get_fail_count(),
            "pass_rate": self.get_pass_rate(),
            "results": self.results,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnitTestResult":
        """Deserialize from dictionary"""
        return cls(data.get("results", []))


class UnitTestPassRateEvalResult:
    """
    Result of unit test pass rate evaluation.

    Measures how well patches maintain tests that originally passed on pre-migration branch.
    The score is NOT about overall pass rate, but specifically about maintaining originally passing tests.
    """

    def __init__(
        self,
        pre_mig_result: UnitTestResult,
        gt_patch_result: UnitTestResult,
        gen_patch_result: UnitTestResult,
        gt_patch_score: float,
        gen_patch_score: float,
        baseline_passing_test_count: int,
        gt_maintained_passing_count: int,
        gen_maintained_passing_count: int,
    ):
        self.pre_mig_result = pre_mig_result
        self.gt_patch_result = gt_patch_result
        self.gen_patch_result = gen_patch_result
        self.gt_patch_score = gt_patch_score
        self.gen_patch_score = gen_patch_score
        self.baseline_passing_test_count = baseline_passing_test_count
        self.gt_maintained_passing_count = gt_maintained_passing_count
        self.gen_maintained_passing_count = gen_maintained_passing_count

    @classmethod
    def create_from_results(
        cls,
        pre_mig_result: UnitTestResult,
        gt_patch_result: UnitTestResult,
        gen_patch_result: UnitTestResult,
    ) -> Self:
        """
        Create evaluation result from three test runs and compute scores.

        Score = (# of originally passing tests that still pass) / (# of originally passing tests)

        This measures test regression, not overall pass rate.
        """
        # Get tests that pass on pre-migration (raw) branch - this is our baseline
        baseline_passing_tests = pre_mig_result.get_passing_test_nodeids()
        baseline_count = len(baseline_passing_tests)

        # Compute how many of those baseline tests still pass on each post-mig branch
        gt_patch_score, gt_maintained_count = cls._compute_score(
            baseline_passing_tests, gt_patch_result
        )
        gen_patch_score, gen_maintained_count = cls._compute_score(
            baseline_passing_tests, gen_patch_result
        )

        return cls(
            pre_mig_result,
            gt_patch_result,
            gen_patch_result,
            gt_patch_score,
            gen_patch_score,
            baseline_count,
            gt_maintained_count,
            gen_maintained_count,
        )

    @classmethod
    def load_from_json(cls, json_path: Path) -> Self:
        """Load evaluation result from JSON file"""
        with open(json_path, "r") as f:
            data = json.load(f)

        return cls(
            pre_mig_result=UnitTestResult.from_dict(data["pre_mig_result"]),
            gt_patch_result=UnitTestResult.from_dict(data["gt_patch_result"]),
            gen_patch_result=UnitTestResult.from_dict(data["gen_patch_result"]),
            gt_patch_score=data["gt_patch_score"],
            gen_patch_score=data["gen_patch_score"],
            baseline_passing_test_count=data["baseline_passing_test_count"],
            gt_maintained_passing_count=data["gt_maintained_passing_count"],
            gen_maintained_passing_count=data["gen_maintained_passing_count"],
        )

    def get_baseline_passing_tests(self) -> set:
        """Get set of test nodeids that passed on pre-migration branch"""
        return self.pre_mig_result.get_passing_test_nodeids()

    def compute_gt_patch_pass_rate(self) -> Tuple[float, int]:
        """
        Compute GT patch pass rate from stored results.

        Returns:
            Tuple of (score, maintained_count)
            - score: 0-1 normalized score (% of baseline passing tests that still pass)
            - maintained_count: number of baseline tests that still pass
        """
        baseline_passing_tests = self.get_baseline_passing_tests()
        return self._compute_score(baseline_passing_tests, self.gt_patch_result)

    def compute_gen_patch_pass_rate(self) -> Tuple[float, int]:
        """
        Compute generated patch pass rate from stored results.

        Returns:
            Tuple of (score, maintained_count)
            - score: 0-1 normalized score (% of baseline passing tests that still pass)
            - maintained_count: number of baseline tests that still pass
        """
        baseline_passing_tests = self.get_baseline_passing_tests()
        return self._compute_score(baseline_passing_tests, self.gen_patch_result)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage"""
        return {
            "pre_mig_result": self.pre_mig_result.to_dict(),
            "gt_patch_result": self.gt_patch_result.to_dict(),
            "gen_patch_result": self.gen_patch_result.to_dict(),
            "gt_patch_score": self.gt_patch_score,
            "gen_patch_score": self.gen_patch_score,
            "baseline_passing_test_count": self.baseline_passing_test_count,
            "gt_maintained_passing_count": self.gt_maintained_passing_count,
            "gen_maintained_passing_count": self.gen_maintained_passing_count,
        }

    @staticmethod
    def _compute_score(
        baseline_passing_tests: set, post_mig_result: UnitTestResult
    ) -> Tuple[float, int]:
        """
        Compute score based on how many originally passing tests still pass.

        Parameters:
            baseline_passing_tests: Set of nodeids that passed on pre-migration (raw) branch
            post_mig_result: Test results from post-migration branch

        Returns:
            Tuple of (score, maintained_count)
            - score: 0-1 normalized score
            - maintained_count: number of originally passing tests that still pass
        """
        if not baseline_passing_tests:
            return 0.0, 0

        # Filter to only baseline passing tests
        filtered_result = post_mig_result.filter_by_nodeids(baseline_passing_tests)

        # Count how many still pass
        maintained_count = filtered_result.get_pass_count()

        # Compute score: maintained / baseline
        score = maintained_count / len(baseline_passing_tests)

        return score, maintained_count


class UnitTestPassRateEvaluator(AbstractEvaluator):
    def __init__(
        self,
        config,
        pre_mig_branch_name: str,
        gt_patch_branch_name: str,
        gen_patch_branch_name: str,
        runner: PytestRunner,
        utpr_git_manager: UTPRGitManager,
        gen_patch_file: Path,
    ):
        """
        Parameters:
        pre_mig_branch_name (str): Branch name of the repo before migration
        gt_patch_branch_name (str): Branch name of the repo with ground-truth patch applied
        gen_patch_branch_name (str): Branch name for the generated patch (will be created from patch file)
        runner (PytestRunner): Pytest runner (local or Docker)
        utpr_git_manager (UTPRGitManager): Git manager
        gen_patch_file (Path): Path to patch file on host for creating gen-patch branch (required)
        """
        self.config = config
        self.eval_tests_path = config.eval_tests_path
        self.utpr_git_manager = utpr_git_manager
        self.runner = runner
        self.pre_mig_branch_name = pre_mig_branch_name
        self.gt_patch_branch_name = gt_patch_branch_name
        self.gen_patch_branch_name = gen_patch_branch_name
        self.gen_patch_file = Path(gen_patch_file)

    def _setup_git_info(self) -> None:
        self.utpr_git_manager._run_git(
            [
                "config",
                "--global",
                "user.name",
                "code-migration-pipeline",
            ]
        )
        self.utpr_git_manager._run_git(
            [
                "config",
                "--global",
                "user.email",
                "pipeline.local",
            ]
        )

    def _install_editable(self, extras: List[str] = []) -> None:
        # Only copy if using Docker runner
        if not isinstance(self.runner, DockerPytestRunner):
            return

        # eval_tests_path should be on the host (local path)
        local_tests_path = Path(self.eval_tests_path)
        if not local_tests_path.exists():
            raise FileNotFoundError(
                f"Eval tests path does not exist on host: {local_tests_path}"
            )

        # Destination: inside the repo folder in the container
        container_name = self.runner.container_name
        local_package = str(self.runner.repo_path)
        if extras:
            local_package += "["
            local_package += ",".join(extras)
            local_package += "]"

        # Copy tests into container's repo folder
        result = subprocess.run(
            [
                "docker",
                "exec",
                str(container_name),
                "/bin/bash",
                "-c",
                f"python -m pip install -e {local_package}",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to install package as editable w/ argument {extras}: {result.stderr}"
            )

    def _copy_tests_to_container(self) -> None:
        """
        Copy evaluation tests from host into the repo folder in Docker container.
        Tests will be copied as untracked files that won't interfere with git operations.
        """
        # Only copy if using Docker runner
        if not isinstance(self.runner, DockerPytestRunner):
            return

        # eval_tests_path should be on the host (local path)
        local_tests_path = Path(self.eval_tests_path)
        if not local_tests_path.exists():
            raise FileNotFoundError(
                f"Eval tests path does not exist on host: {local_tests_path}"
            )

        # Destination: inside the repo folder in the container
        container_name = self.runner.container_name
        repo_path = self.runner.repo_path
        dest_path = f"{container_name}:{repo_path}/eval-tests"

        # Copy tests into container's repo folder
        result = subprocess.run(
            ["docker", "cp", str(local_tests_path), dest_path],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to copy tests to container: {result.stderr}")

    def _cleanup_tests_from_container(self) -> None:
        """
        Remove evaluation tests from the repo folder in Docker container.
        This cleans up the untracked test files after evaluation is complete.
        """
        # Only cleanup if using Docker runner
        if not isinstance(self.runner, DockerPytestRunner):
            return

        container_name = self.runner.container_name
        repo_path = self.runner.repo_path
        tests_path_in_container = f"{repo_path}/eval-tests"

        # Remove tests from container's repo folder
        subprocess.run(
            ["docker", "exec", container_name, "rm", "-rf", tests_path_in_container],
            capture_output=True,
            text=True,
        )

    def _create_gen_patch_branch(self) -> None:
        """Create gen-patch branch from patch file on host"""
        if not self.gen_patch_file.exists():
            raise FileNotFoundError(
                f"Generated patch file not found: {self.gen_patch_file}"
            )

        # Read patch content from host
        with open(self.gen_patch_file, "r") as f:
            patch_content = f.read()

        # Create branch from patch using git manager
        # This works for both local and Docker (DockerUTPRGitManager handles container operations)
        self.utpr_git_manager.create_branch_from_patch(
            old_branch_name=self.pre_mig_branch_name,
            new_branch_name=self.gen_patch_branch_name,
            patch_content=patch_content,
        )

    def _delete_gen_patch_branch(self) -> None:
        """Delete gen-patch branch after evaluation"""
        try:
            self.utpr_git_manager.delete_branch(self.gen_patch_branch_name)
        except Exception:
            # Ignore errors during cleanup
            pass

    def evaluate(self) -> Dict[str, Any]:
        """
        Run unit tests on three branches and compute pass rate scores:
        - Pre-migration branch (baseline)
        - Ground-truth patch branch
        - LLM-generated patch branch (created from patch file)

        Returns:
            Dictionary with:
                - status: "success" or "failed"
                - eval_result: UnitTestPassRateEvalResult (if successful)
                - error: Error message (if failed)
        """
        try:
            # breakpoint()
            # Validate eval tests path exists on host
            eval_tests_path = Path(self.eval_tests_path)
            if not eval_tests_path.exists():
                return {
                    "error": f"Eval tests path does not exist: {self.eval_tests_path}",
                    "status": "failed",
                }

            # Create gen-patch branch from patch file
            self._setup_git_info()
            self._install_editable()
            self._create_gen_patch_branch()

            pre_mig_result = None
            gt_patch_result = None
            gen_patch_result = None

            # Evaluate pre-migration branch (required baseline)
            # Tests are copied/cleaned up inside _evaluate_for_branch
            try:
                pre_mig_result = self._evaluate_for_branch(self.pre_mig_branch_name)
            except Exception as e:
                return {
                    "error": f"Failed to evaluate pre-migration branch '{self.pre_mig_branch_name}': {str(e)}",
                    "status": "failed",
                }

            # Evaluate ground-truth patch branch
            try:
                gt_patch_result = self._evaluate_for_branch(self.gt_patch_branch_name)
            except Exception as e:
                return {
                    "error": f"Failed to evaluate GT patch branch '{self.gt_patch_branch_name}': {str(e)}",
                    "status": "failed",
                }

            # Evaluate generated patch branch
            try:
                gen_patch_result = self._evaluate_for_branch(self.gen_patch_branch_name)
            except Exception as e:
                return {
                    "error": f"Failed to evaluate generated patch branch '{self.gen_patch_branch_name}': {str(e)}",
                    "status": "failed",
                }

            # Create evaluation result
            eval_result = UnitTestPassRateEvalResult.create_from_results(
                pre_mig_result=pre_mig_result,
                gt_patch_result=gt_patch_result,
                gen_patch_result=gen_patch_result,
            )

            return {
                "eval_result": eval_result,
                "status": "success",
            }

        except Exception as e:
            return {
                "error": f"Failed to compute evaluation results: {str(e)}",
                "status": "failed",
            }
        finally:
            # Always cleanup: delete gen-patch branch
            # breakpoint()
            self._delete_gen_patch_branch()

    def _get_generated_patch_file(self) -> Optional[str]:
        """Find the most recent generated patch file in trajectory directory"""
        try:
            trajectory_dir = Path(self.config.trajectory_path)
            if not trajectory_dir.exists():
                return None

            # Find all patch files
            patch_files = list(trajectory_dir.rglob("*.patch"))
            if patch_files:
                # Return the most recent patch file
                latest_patch = max(patch_files, key=lambda p: p.stat().st_mtime)
                return str(latest_patch)

            return None
        except Exception as e:
            return None

    def _evaluate_for_branch(self, branch_name: str) -> UnitTestResult:
        """
        Run unit tests on a specific branch and return results.
        Tests are copied before evaluation and cleaned up after.

        Parameters:
            branch_name: Name of the branch to evaluate

        Returns:
            UnitTestResult containing test outcomes

        Raises:
            RuntimeError: If branch doesn't exist or tests fail to run
        """
        # Checkout the branch using context manager (automatically restores original branch)
        breakpoint()
        with self.utpr_git_manager.branch_context(branch_name):
            try:
                # Copy tests to container/repo before running
                self._copy_tests_to_container()

                # Determine test path based on runner type
                if isinstance(self.runner, DockerPytestRunner):
                    # For Docker, tests are copied to {repo_path}/eval-tests in container
                    test_path = Path(self.runner.repo_path)
                else:
                    # For local, use the configured eval_tests_path
                    test_path = Path(self.eval_tests_path)

                # Run pytest on the eval tests
                test_results = self.runner.run_pytest(test_path=test_path, args=[])

                # Create and return UnitTestResult object
                return UnitTestResult(test_results)

            finally:
                # Always cleanup tests after evaluation
                self._cleanup_tests_from_container()

    def save_results(self, result: UnitTestPassRateEvalResult) -> None:
        """Save evaluation results to JSON file"""
        try:
            os.makedirs(self.config.score_path, exist_ok=True)
            score_file = os.path.join(
                self.config.score_path, "unit_test_pass_rate.json"
            )

            results = {
                "evaluator": "UnitTestPassRateEvaluator",
                "pass_rate_result": result.to_dict(),
            }

            with open(score_file, "w") as f:
                json.dump(results, f, indent=2)
        except Exception as e:
            pass

    def load_results(self, result_path: Path) -> UnitTestPassRateEvalResult:
        return UnitTestPassRateEvalResult.load_from_json(result_path)


if __name__ == "__main__":
    # Example 1: Local execution
    local_pytest_runner = LocalPytestRunner(repo_path=Path("/path/to/repo"))
    local_utpr_git_manager = LocalUTPRGitManager(repo_path=Path("/path/to/repo"))

    local_utpr_eval = UnitTestPassRateEvaluator(
        {},
        "main",
        "gt-patch",
        "gen-patch",
        local_pytest_runner,
        local_utpr_git_manager,
    )
    result = local_utpr_eval.evaluate()

    # Example 2: Docker execution
    docker_pytest_runner = DockerPytestRunner(
        "<repo-container-name>", Path("/ws/<repo-folder-name>")
    )
    docker_utpr_git_manager = DockerUTPRGitManager(
        "<repo-container-name>", Path("/ws/<repo-folder-name>")
    )

    docker_utpr_eval = UnitTestPassRateEvaluator(
        {},
        "main",
        "gt-patch",
        "gen-patch",
        docker_pytest_runner,
        docker_utpr_git_manager,
    )
    result = docker_utpr_eval.evaluate()
