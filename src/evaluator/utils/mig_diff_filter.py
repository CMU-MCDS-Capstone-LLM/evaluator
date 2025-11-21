import os
import shutil
from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path
import yaml


def clever_way_to_replace_old_range_with_new_range(
    all_changes: List[Tuple[Tuple[int, int], Tuple[int, int]]],
    old_file: List[str],
    new_file: List[str],
) -> List[str]:
    """
    Replace specified ranges in old_file with corresponding ranges from new_file.
    
    all_changes[i][0]: range in old file (start, end) - inclusive, 1-indexed
    all_changes[i][1]: range in new file (start, end) - inclusive, 1-indexed
    
    Note: Line numbers are 1-indexed, while python lists are 0-indexed
    """
    if not all_changes:
        # No changes specified, return old file as-is
        return old_file.copy()
    
    # Sort changes by old file line number
    all_changes = sorted(all_changes, key=lambda x: x[0][0])

    new_file_mig_only = []
    old_lineno = 1
    cur_change_idx = 0

    def should_replace(old_lineno: int) -> bool:
        if cur_change_idx >= len(all_changes):
            return False
        cur_change = all_changes[cur_change_idx]
        cur_old_range = cur_change[0]
        if old_lineno < cur_old_range[0]:
            return False
        return True

    while old_lineno <= len(old_file):
        if not should_replace(old_lineno):
            # Keep the old line
            new_file_mig_only.append(old_file[old_lineno - 1])
            old_lineno += 1
            continue
        
        # Replace with new range
        cur_change = all_changes[cur_change_idx]
        cur_old_range = cur_change[0]
        cur_new_range = cur_change[1]
        
        # Skip old lines that are being replaced
        old_lineno = cur_old_range[1] + 1
        
        # Add new lines (convert to 0-indexed for list slicing)
        new_file_mig_only.extend(new_file[cur_new_range[0] - 1 : cur_new_range[1]])
        cur_change_idx += 1

    return new_file_mig_only


def parse_line_spec(line_spec: str) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """
    Parse a line specification like "3:3" or "2:6-9" into ranges.
    
    Format: "{old_start}[-{old_end}]:{new_start}[-{new_end}]"
    Returns: ((old_start, old_end), (new_start, new_end))
    """
    old_range_str, new_range_str = line_spec.split(":")
    
    # Parse old range
    old_range_parts = [int(n) for n in old_range_str.split("-")]
    if len(old_range_parts) == 1:
        old_range = (old_range_parts[0], old_range_parts[0])
    else:
        old_range = (old_range_parts[0], old_range_parts[1])
    
    # Parse new range
    new_range_parts = [int(n) for n in new_range_str.split("-")]
    if len(new_range_parts) == 1:
        new_range = (new_range_parts[0], new_range_parts[0])
    else:
        new_range = (new_range_parts[0], new_range_parts[1])
    
    return (old_range, new_range)


def filter_file_using_mig_diff(
    old_file_path: Path,
    new_file_path: Path,
    code_changes: List[Dict[str, Any]],
    output_path: Path,
) -> bool:
    """
    Filter a file to only include migration changes specified in the YAML.
    
    Args:
        old_file_path: Path to the pre-migration version
        new_file_path: Path to the post-migration version
        code_changes: List of code changes from YAML, each with a "line" field
        output_path: Path to write the filtered output
    
    Returns:
        True if successful, False otherwise
    """
    try:
        if not old_file_path.exists() or not new_file_path.exists():
            return False
            
        with open(old_file_path, "r", encoding="utf-8") as f:
            old_file = f.readlines()
        with open(new_file_path, "r", encoding="utf-8") as f:
            new_file = f.readlines()

        code_change_ranges = []
        for code_change in code_changes:
            line_spec = code_change.get("line", "")
            if not line_spec:
                continue
            try:
                old_range, new_range = parse_line_spec(line_spec)
                code_change_ranges.append((old_range, new_range))
            except (ValueError, IndexError):
                continue

        if not code_change_ranges:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(old_file_path, output_path)
            return True

        new_file_mig_only = clever_way_to_replace_old_range_with_new_range(
            code_change_ranges, old_file, new_file
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("".join(new_file_mig_only))
        
        return True
    except Exception as e:
        return False


class MigDiffFilter:
    """Filter post-migration branch files to only include migration changes."""
    
    def __init__(self, mig_diff_yaml_path: Path, repo_path: Path):
        """
        Initialize the filter.
        
        Args:
            mig_diff_yaml_path: Path to the mig-diff.yaml file
            repo_path: Path to the repository root
        """
        self.mig_diff_yaml_path = mig_diff_yaml_path
        self.repo_path = repo_path
        self.mig_diff_data = None
        self._load_mig_diff()
    
    def _load_mig_diff(self):
        """Load the migration diff YAML file."""
        if self.mig_diff_yaml_path.exists():
            with open(self.mig_diff_yaml_path, "r", encoding="utf-8") as f:
                self.mig_diff_data = yaml.safe_load(f)
        else:
            self.mig_diff_data = None
    
    def is_available(self) -> bool:
        """Check if migration diff YAML is available and valid."""
        return (
            self.mig_diff_data is not None 
            and isinstance(self.mig_diff_data, dict)
            and "files" in self.mig_diff_data
            and isinstance(self.mig_diff_data["files"], list)
        )

