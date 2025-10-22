import os
import tempfile
import shutil
import json
from typing import Dict, Any, Optional

from ..utils.patch_utils import PatchApplier
from ..utils.ast_utils import ASTComparator
from ..utils.git_utils import GitManager
from .base import AbstractEvaluator


class PatchSimilarityEvaluator(AbstractEvaluator):
    """Minimal evaluator for patch similarity using branch switching."""

    def __init__(self, config):
        self.config = config
        self.ast_comparator = ASTComparator()
        self.git_manager = GitManager(config.repo_path)

    def evaluate(self) -> Dict[str, Any]:
        """Run patch similarity evaluation."""
        try:
            patch_file = self._get_generated_patch_file()
            if not patch_file:
                return {"error": "No patch found", "status": "failed"}

            # Compare with post-migration branch
            similarity_score = self._compare_with_branches(patch_file)

            self._save_results(similarity_score)
            return {"similarity_score": similarity_score, "status": "success"}

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def _get_generated_patch_file(self) -> Optional[str]:
        try:
            trajectory_dir = self.config.trajectory_path
            if not os.path.exists(trajectory_dir):
                return None

            for file in os.listdir(trajectory_dir):
                if file.endswith(".patch"):
                    return os.path.join(trajectory_dir, file)
            return None
        except Exception:
            return None

    def _compare_with_branches(self, patch_file: str) -> float:
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                patched_dir = os.path.join(temp_dir, "patched")

                shutil.copytree(self.config.repo_path, patched_dir)

                applier = PatchApplier(patched_dir)
                if not applier.apply_patch_from_file(patch_file):
                    return 0.0

                with self.git_manager.branch_context(self.config.post_migration_branch):
                    similarities = self.ast_comparator.compare_directory_asts(
                        patched_dir, self.config.repo_path
                    )

                if not similarities:
                    return 0.0

                return sum(similarities.values()) / len(similarities)

        except Exception:
            return 0.0

    def _save_results(self, score: float) -> None:
        try:
            os.makedirs(self.config.score_path, exist_ok=True)
            score_file = os.path.join(self.config.score_path, "patch_similarity.json")

            results = {
                "evaluator": "PatchSimilarityEvaluator",
                "similarity_score": score,
            }

            with open(score_file, "w") as f:
                json.dump(results, f, indent=2)

        except Exception:
            pass
