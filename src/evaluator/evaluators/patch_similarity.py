import os
import tempfile
import shutil
import json
import subprocess
from typing import Dict, Any, Optional
from pathlib import Path

from ..utils.patch_utils import PatchApplier
from ..utils.ast_utils import ASTComparator
from ..utils.git_utils import GitManager
from ..utils.mig_diff_filter import MigDiffFilter, filter_file_using_mig_diff
from .base import AbstractEvaluator


class PatchSimilarityEvaluator(AbstractEvaluator):
    def __init__(self, config, mig_diff_yaml_path: Optional[Path] = None):
        self.config = config
        self.ast_comparator = ASTComparator()
        self.git_manager = GitManager(config.repo_path)

        if mig_diff_yaml_path is None:
            raise ValueError(
                "mig_diff_yaml_path must be provided. Infra task should find and pass it."
            )

        self.mig_diff_yaml_path = Path(mig_diff_yaml_path)
        if not self.mig_diff_yaml_path.exists():
            raise FileNotFoundError(
                f"mig-diff.yaml path does not exist: {self.mig_diff_yaml_path}. "
                f"Please ensure the YAML file exists at this location."
            )

    def evaluate(self) -> Dict[str, Any]:
        try:
            patch_file = self._get_generated_patch_file()
            if not patch_file:
                return {"error": "No patch found", "status": "failed"}

            similarity_score = self._compare_with_branches(patch_file)
            self._save_results(similarity_score)
            return {"similarity_score": similarity_score, "status": "success"}

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def _get_generated_patch_file(self) -> Optional[str]:
        try:
            trajectory_dir = Path(self.config.trajectory_path)
            if not trajectory_dir.exists():
                return None

            patch_files = list(trajectory_dir.rglob("*.patch"))
            if patch_files:
                latest_patch = max(patch_files, key=lambda p: p.stat().st_mtime)
                return str(latest_patch)

            return None
        except Exception as e:
            return None

    def _compare_with_branches(self, patch_file: str) -> float:
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                patched_dir = os.path.join(temp_dir, "patched")

                with self.git_manager.branch_context(self.config.pre_migration_branch):
                    shutil.copytree(self.config.repo_path, patched_dir)

                applier = PatchApplier(patched_dir)
                if not applier.apply_patch_from_file(patch_file):
                    return 0.0

                if self.mig_diff_yaml_path and self.mig_diff_yaml_path.exists():
                    return self._compare_with_filtered_branch(patched_dir, temp_dir)
                else:
                    return self._compare_with_raw_branch(patched_dir)

        except Exception as e:
            return 0.0

    def _compare_with_raw_branch(self, patched_dir: str) -> float:
        with self.git_manager.branch_context(self.config.post_migration_branch):
            similarities = self.ast_comparator.compare_directory_asts(
                patched_dir, self.config.repo_path
            )

        if similarities:
            avg_score = sum(similarities.values()) / len(similarities)
            return avg_score
        else:
            return 0.0

    def _compare_with_filtered_branch(self, patched_dir: str, temp_dir: str) -> float:
        filtered_repo_path = os.path.join(temp_dir, "filtered_repo")

        mig_filter = MigDiffFilter(
            Path(self.mig_diff_yaml_path), Path(self.config.repo_path)
        )

        if not mig_filter.is_available():
            return self._compare_with_raw_branch(patched_dir)

        shutil.copytree(self.config.repo_path, filtered_repo_path)

        with self.git_manager.branch_context(self.config.post_migration_branch):
            mig_diff_data = mig_filter.mig_diff_data

            for file_config in mig_diff_data["files"]:
                file_path_rel = file_config["path"]
                file_path = Path(self.config.repo_path) / file_path_rel
                filtered_file_path = Path(filtered_repo_path) / file_path_rel
                old_file_path = Path(patched_dir) / file_path_rel

                if not file_path.exists() or not old_file_path.exists():
                    continue

                try:
                    with open(old_file_path, "r", encoding="utf-8") as f:
                        old_file_content = f.read()

                    with open(file_path, "r", encoding="utf-8") as f:
                        new_file_content = f.read()

                    code_changes = file_config.get("code_changes", [])
                    if code_changes:
                        old_file_temp = os.path.join(
                            temp_dir, "old_files", file_path_rel
                        )
                        os.makedirs(os.path.dirname(old_file_temp), exist_ok=True)
                        with open(old_file_temp, "w", encoding="utf-8") as f:
                            f.write(old_file_content)

                        filter_file_using_mig_diff(
                            Path(old_file_temp),
                            file_path,
                            code_changes,
                            filtered_file_path,
                        )
                    else:
                        shutil.copy(old_file_path, filtered_file_path)

                except Exception as e:
                    continue

        similarities = self.ast_comparator.compare_directory_asts(
            patched_dir, filtered_repo_path
        )

        if similarities:
            avg_score = sum(similarities.values()) / len(similarities)
            return avg_score
        else:
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
        except Exception as e:
            pass
