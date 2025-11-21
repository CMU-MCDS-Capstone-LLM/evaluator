import ast
import os
import glob
from difflib import SequenceMatcher, unified_diff, ndiff


class ASTComparator:
    def compare_directory_asts(self, dir1_path: str, dir2_path: str) -> dict:
        similarities = {}

        py_files1 = set(glob.glob(os.path.join(dir1_path, "**/*.py"), recursive=True))
        py_files2 = set(glob.glob(os.path.join(dir2_path, "**/*.py"), recursive=True))

        rel_files1 = {os.path.relpath(f, dir1_path): f for f in py_files1}
        rel_files2 = {os.path.relpath(f, dir2_path): f for f in py_files2}

        common_files = set(rel_files1.keys()) & set(rel_files2.keys())
        
        if len(common_files) == 0:
            return similarities

        for rel_path in common_files:
            file1 = rel_files1[rel_path]
            file2 = rel_files2[rel_path]
            similarity = self._compare_files(file1, file2, rel_path)
            similarities[rel_path] = similarity

        return similarities

    def _compare_files(self, file1: str, file2: str, rel_path: str = None) -> float:
        try:
            # Parse files to AST
            with open(file1, "r", encoding="utf-8") as f:
                content1 = f.read()
                ast1 = ast.parse(content1)
            with open(file2, "r", encoding="utf-8") as f:
                content2 = f.read()
                ast2 = ast.parse(content2)

            # Convert to strings and compare
            if hasattr(ast, "unparse"):
                str1 = ast.unparse(ast1)
                str2 = ast.unparse(ast2)
            else:
                str1 = ast.dump(ast1)
                str2 = ast.dump(ast2)

            return SequenceMatcher(None, str1, str2).ratio()
        except SyntaxError as e:
            return 0.0
        except Exception as e:
            return 0.0
