"""
Demo script to run unit test pass rate evaluation on the foobar repository.
This script evaluates three branches using Docker container:
- main: original pandas implementation
- gt-patch: correct polars migration (ground truth)
- gen-patch: LLM-generated polars migration (with some bugs)
"""

import sys
import json
from pathlib import Path

# Add evaluator source to path
evaluator_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(evaluator_root / "src"))

from evaluator.evaluators.unit_test_pass_rate import (
    UnitTestPassRateEvaluator,
    UnitTestPassRateEvalResult,
)
from evaluator.utils.unit_test_utils import DockerPytestRunner, DockerUTPRGitManager


class Config:
    """Configuration for the demo evaluation"""

    def __init__(self, container_name: str, repo_container_path: str):
        demo_root = Path(__file__).parent.parent

        # Container configuration
        self.container_name = container_name
        self.repo_container_path = Path(repo_container_path)

        # eval_tests_path should be the HOST path (for copying to container)
        self.eval_tests_path = demo_root / "data" / "eval-tests" / "foobar"

        # Local output path
        self.score_path = demo_root / "output"
        self.trajectory_path = demo_root / "output"  # Not used in this demo

        # Ensure output directory exists
        self.score_path.mkdir(parents=True, exist_ok=True)


def print_results(result_dict):
    """Print evaluation results in a readable format"""
    print("\n" + "=" * 80)
    print("UNIT TEST PASS RATE EVALUATION RESULTS")
    print("=" * 80)

    if result_dict["status"] == "failed":
        print(f"\n❌ Evaluation FAILED: {result_dict['error']}")
        return

    eval_result = result_dict["eval_result"]

    print(f"\n📊 Status: {result_dict['status'].upper()}")

    if "warnings" in result_dict:
        print(f"\n⚠️  Warnings:")
        for warning in result_dict["warnings"]:
            print(f"   - {warning}")

    # Pre-migration results
    print("\n" + "-" * 80)
    print("PRE-MIGRATION BRANCH (main - pandas)")
    print("-" * 80)
    pre_mig = eval_result.pre_mig_result
    print(f"Total tests: {pre_mig.get_total_count()}")
    print(f"Passed: {pre_mig.get_pass_count()}")
    print(f"Failed: {pre_mig.get_fail_count()}")
    print(f"Pass rate: {pre_mig.get_pass_rate():.2f}%")

    # Ground truth patch results
    print("\n" + "-" * 80)
    print("GT-PATCH BRANCH (ground truth polars migration)")
    print("-" * 80)
    gt_patch = eval_result.gt_patch_result
    print(f"Total tests: {gt_patch.get_total_count()}")
    print(f"Passed: {gt_patch.get_pass_count()}")
    print(f"Failed: {gt_patch.get_fail_count()}")
    print(f"Pass rate: {gt_patch.get_pass_rate():.2f}%")
    print(
        f"\nBaseline passing tests maintained: {eval_result.gt_maintained_passing_count}/{eval_result.baseline_passing_test_count}"
    )
    print(f"GT Patch Score: {eval_result.gt_patch_score:.2%}")

    # Generated patch results
    print("\n" + "-" * 80)
    print("GEN-PATCH BRANCH (LLM-generated polars migration)")
    print("-" * 80)
    gen_patch = eval_result.gen_patch_result
    print(f"Total tests: {gen_patch.get_total_count()}")
    print(f"Passed: {gen_patch.get_pass_count()}")
    print(f"Failed: {gen_patch.get_fail_count()}")
    print(f"Pass rate: {gen_patch.get_pass_rate():.2f}%")
    print(
        f"\nBaseline passing tests maintained: {eval_result.gen_maintained_passing_count}/{eval_result.baseline_passing_test_count}"
    )
    print(f"Generated Patch Score: {eval_result.gen_patch_score:.2%}")

    # Comparison
    print("\n" + "=" * 80)
    print("COMPARISON")
    print("=" * 80)
    score_diff = eval_result.gt_patch_score - eval_result.gen_patch_score
    if score_diff > 0:
        print(f"✅ GT patch is {score_diff:.2%} better than generated patch")
    elif score_diff < 0:
        print(f"🎉 Generated patch is {abs(score_diff):.2%} better than GT patch!")
    else:
        print(f"🤝 Both patches have the same score")

    print("\n" + "=" * 80)


def main():
    """Main execution function"""
    # Parse command line arguments
    if len(sys.argv) < 3:
        print(
            "Usage: python run_utpr_eval.py <container_name> <repo_path_in_container>"
        )
        print("\nExample:")
        print("  python run_utpr_eval.py foobar-container /workspace/foobar")
        sys.exit(1)

    container_name = sys.argv[1]
    repo_container_path = sys.argv[2]

    print("Starting Unit Test Pass Rate Evaluation Demo (Docker Mode)")
    print("=" * 80)

    # Setup configuration
    config = Config(container_name, repo_container_path)

    print(f"\n🐳 Container: {container_name}")
    print(f"📁 Repository (in container): {repo_container_path}")
    print(f"📝 Tests (in container): {config.eval_tests_path}")
    print(f"💾 Output (local): {config.score_path}")

    # Create Docker runners
    print("\n🔧 Setting up Docker pytest runner and git manager...")
    pytest_runner = DockerPytestRunner(
        container_name=container_name, repo_path=Path(repo_container_path)
    )
    git_manager = DockerUTPRGitManager(
        container_name=container_name, repo_path=Path(repo_container_path)
    )

    # Create evaluator
    print("🏗️  Creating evaluator...")
    evaluator = UnitTestPassRateEvaluator(
        config=config,
        pre_mig_branch_name="main",
        gt_patch_branch_name="gt-patch",
        gen_patch_branch_name="gen-patch",
        runner=pytest_runner,
        utpr_git_manager=git_manager,
    )

    # Run evaluation
    print("\n🚀 Running evaluation on three branches in Docker container...")
    print("   This may take a few moments...\n")

    result = evaluator.evaluate()

    # Print results
    print_results(result)

    # Save detailed results
    output_file = config.score_path / "unit_test_pass_rate_detailed.json"
    with open(output_file, "w") as f:
        # Convert eval_result to dict for JSON serialization
        if "eval_result" in result:
            result_copy = {
                "status": result["status"],
                "eval_result": result["eval_result"].to_dict(),
            }
            if "warnings" in result:
                result_copy["warnings"] = result["warnings"]
            json.dump(result_copy, f, indent=2)
        else:
            json.dump(result, f, indent=2)

    print(f"\n💾 Detailed results saved to: {output_file}")
    print("\n✅ Evaluation complete!")


if __name__ == "__main__":
    main()
