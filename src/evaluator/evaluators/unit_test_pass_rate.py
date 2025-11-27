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
    PytestRunner,
    UTPRGitManager,
)
from .base import AbstractEvaluator

UnitTestResultType = Union[Literal["pass", "fail", "skipped", "other"]]


class UnitTestResult:
    """
    Result of executing unit test suite
    """

    results: List[Tuple[str, UnitTestResultType]]

    pass


class UnitTestPassRateEvalResult:
    """
    Result of unit test pass rate evaluation
    """

    pre_mig_result: UnitTestResult
    gt_patch_result: UnitTestResult
    gen_patch_result: UnitTestResult

    def __init__(
        self,
        pre_mig_result: UnitTestResult,
        gt_patch_result: UnitTestResult,
        gen_patch_result: UnitTestResult,
        gt_patch_score: float,
        gen_patch_score: float,
    ):
        self.pre_mig_result = pre_mig_result
        self.gt_patch_result = gt_patch_result
        self.gen_patch_result = gen_patch_result
        self.gt_patch_score = gt_patch_score
        self.gen_patch_score = gen_patch_score

    @classmethod
    def create_from_results(
        cls,
        pre_mig_result: UnitTestResult,
        gt_patch_result: UnitTestResult,
        gen_patch_result: UnitTestResult,
    ) -> Self:
        gt_patch_score = cls._compute_score(pre_mig_result, gt_patch_result)
        gen_patch_score = cls._compute_score(pre_mig_result, gen_patch_result)

        return cls(
            pre_mig_result,
            gt_patch_result,
            gen_patch_result,
            gt_patch_score,
            gen_patch_score,
        )

    @classmethod
    def load_from_json(cls, json_path: Path) -> Self:
        raise NotImplementedError("")

    def to_dict(self) -> Dict:
        raise NotImplementedError("")

    @staticmethod
    def _compute_score(
        pre_mig_result: UnitTestResult, post_mig_result: UnitTestResult
    ) -> float:
        raise NotImplementedError("")
        return 0.0


class UnitTestPassRateEvaluator(AbstractEvaluator):
    def __init__(
        self,
        config,
        pre_mig_branch_name: str,
        gt_patch_branch_name: str,
        gen_patch_branch_name: str,
        runner: PytestRunner,
        utpr_git_manager: UTPRGitManager,
    ):
        """
        Parameters:
        pre_mig_branch_name (str): Branch name of the repo before migration
        gt_patch_branch_name (str): Branch name of the repo with ground-truth patch applied
        gen_patch_branch_name (str): Branch name of the repo with llm-generated patch applied
        """
        self.config = config
        self.eval_tests_path = config.eval_tests_path
        self.utpr_git_manager = utpr_git_manager
        self.runner = runner
        self.pre_mig_branch_name = pre_mig_branch_name
        self.gt_patch_branch_name = gt_patch_branch_name
        self.gen_patch_branch_name = gen_patch_branch_name

    def evaluate(self) -> Dict[str, Any]:
        """
        Copy repo into a temp folder, and run unit test and get pass rate three times
        - once on pre-mig branch
        - once on ground-truth migration branch
        - once on LLM-generated migration branch
        """
        try:
            patch_file = self._get_generated_patch_file()
            if not patch_file:
                return {"error": "No patch found", "status": "failed"}

            pre_mig_result = self._evaluate_for_branch(self.pre_mig_branch_name)
            gt_patch_result = self._evaluate_for_branch(self.gt_patch_branch_name)
            gen_patch_result = self._evaluate_for_branch(self.gen_patch_branch_name)

            eval_result = UnitTestPassRateEvalResult.create_from_results(
                pre_mig_result=pre_mig_result,
                gt_patch_result=gt_patch_result,
                gen_patch_result=gen_patch_result,
            )

            self._save_results(eval_result)
            return {"eval_result": eval_result, "status": "success"}

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def _get_generated_patch_file(self) -> Optional[str]:
        try:
            trajectory_dir = Path(self.config.trajectory_path)
            if not trajectory_dir.exists():
                return None

            self._evaluate_for_branch(sel)

        except Exception as e:
            return None

    def _evaluate_for_branch(self, branch_name: str) -> UnitTestResult:
        """
        Compute unit test pass rate on a branch. This includes
        - copy eval test to branch
        - run eval test
        """
        raise NotImplementedError("")
        return UnitTestResult()

    def _save_results(self, result: UnitTestPassRateEvalResult) -> None:
        try:
            os.makedirs(self.config.score_path, exist_ok=True)
            score_file = os.path.join(self.config.score_path, "patch_similarity.json")

            results = {
                "evaluator": "PatchSimilarityEvaluator",
                "pass_rate_result": result.to_dict(),
            }

            with open(score_file, "w") as f:
                json.dump(results, f, indent=2)
        except Exception as e:
            pass

    def _load_results(self, result_path: Path) -> UnitTestPassRateEvalResult:
        return UnitTestPassRateEvalResult.load_from_json(result_path)


if __name__ == "__main__":
    docker_pytest_runner = DockerPytestRunner(
        "<repo-container-name>", Path("/ws/<repo-folder-name>")
    )
    docker_utpr_git_manager = DockerUTPRGitManager(
        "<repo-container-name>", Path("/ws/<repo-folder-name>")
    )
    utpr_eval = UnitTestPassRateEvaluator(
        {},
        "main",
        "gt-patch",
        "gen-patch",
        docker_pytest_runner,
        docker_utpr_git_manager,
    )
    result = utpr_eval.evaluate()
