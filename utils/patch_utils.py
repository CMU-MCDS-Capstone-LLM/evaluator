import os
import subprocess

class PatchApplier:
    def __init__(self, working_dir: str):
        self.working_dir = working_dir

    def apply_patch_from_file(self, patch_file_path: str) -> bool:
        try:
            original_cwd = os.getcwd()
            os.chdir(self.working_dir)
            result = subprocess.run(
                ["git", "apply", "--ignore-whitespace", patch_file_path],
                capture_output=True,
                text=True,
            )
            os.chdir(original_cwd)
            return result.returncode == 0
        except Exception:
            return False
