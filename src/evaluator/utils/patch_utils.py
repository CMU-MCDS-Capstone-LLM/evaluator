import os
import subprocess
from pathlib import Path


class PatchApplier:
    def __init__(self, working_dir: str):
        self.working_dir = working_dir

    def apply_patch_from_file(self, patch_file_path: str) -> bool:
        try:
            original_cwd = os.getcwd()
            os.chdir(self.working_dir)
            
            result = subprocess.run(
                ["git", "apply", "--ignore-whitespace", "--reject", "--verbose", patch_file_path],
                capture_output=True,
                text=True,
            )
            
            if result.returncode != 0:
                if "Applied patch" in result.stdout or "Applied patch" in result.stderr:
                    applied_count = result.stdout.count("Applied patch") + result.stderr.count("Applied patch")
                    if applied_count > 0:
                        os.chdir(original_cwd)
                        return True
                
                result = subprocess.run(
                    ["git", "apply", "--ignore-whitespace", "--3way", "--reject", "--verbose", patch_file_path],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    applied_count = result.stdout.count("Applied patch") + result.stderr.count("Applied patch")
                    if applied_count > 0:
                        os.chdir(original_cwd)
                        return True
                    os.chdir(original_cwd)
                    return False
            
            os.chdir(original_cwd)
            return result.returncode == 0
        except Exception as e:
            return False
