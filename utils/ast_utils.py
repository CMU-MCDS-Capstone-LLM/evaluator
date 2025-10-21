import ast
import os
import glob
from difflib import SequenceMatcher


class ASTComparator:
    def compare_directory_asts(self, dir1_path: str, dir2_path: str) -> dict:
        similarities = {}

        py_files1 = set(glob.glob(os.path.join(dir1_path, "**/*.py"), recursive=True))
        py_files2 = set(glob.glob(os.path.join(dir2_path, "**/*.py"), recursive=True))

        rel_files1 = {os.path.relpath(f, dir1_path): f for f in py_files1}
        rel_files2 = {os.path.relpath(f, dir2_path): f for f in py_files2}

        for rel_path in set(rel_files1.keys()) & set(rel_files2.keys()):
            file1 = rel_files1[rel_path]
            file2 = rel_files2[rel_path]
            similarity = self._compare_files(file1, file2)
            similarities[rel_path] = similarity

        return similarities

    def _compare_files(self, file1: str, file2: str) -> float:
        try:
            # Parse files to AST
            with open(file1, "r", encoding="utf-8") as f:
                ast1 = ast.parse(f.read())
            with open(file2, "r", encoding="utf-8") as f:
                ast2 = ast.parse(f.read())

            # Convert to strings and compare
            str1 = ast.unparse(ast1) if hasattr(ast, "unparse") else ast.dump(ast1)
            str2 = ast.unparse(ast2) if hasattr(ast, "unparse") else ast.dump(ast2)

            # print("AST 1")
            # print(ast1)
            # print("AST 2")
            # print(ast2)

            return SequenceMatcher(None, str1, str2).ratio()

        except Exception:
            return 0.0
