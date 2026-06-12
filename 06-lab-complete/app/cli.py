from __future__ import annotations

import argparse

from app.graph import ShoppingAssistant


from pathlib import Path
import json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Student scaffold CLI.")
    parser.add_argument("--question", help="Run one question through the graph.")
    parser.add_argument("--test-file", default="data/test.json")
    parser.add_argument("--trace-file", default=None)
    parser.add_argument("--batch", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    assistant = ShoppingAssistant()

    if args.batch:
        test_file_path = Path(args.test_file)
        output_dir = assistant.settings.traces_dir
        print(f"Running batch tests from {test_file_path}...")
        summary = assistant.run_batch(test_file=test_file_path, output_dir=output_dir)
        print(f"Batch tests completed. Results saved in: {output_dir / 'summary.json'}")
        print(f"Route Accuracy: {summary['metrics']['route_accuracy']:.2%}")
        print(f"Status Accuracy: {summary['metrics']['status_accuracy']:.2%}")
    elif args.question:
        trace_path = Path(args.trace_file) if args.trace_file else None
        print(f"Asking: '{args.question}'...")
        result = assistant.ask(question=args.question, trace_file=trace_path)
        print("\n=== FINAL ANSWER ===")
        print(result.get("final_answer"))
        print("====================\n")
        if trace_path:
            print(f"Trace saved to: {trace_path}")
    else:
        print("Please provide --question <question> or --batch. Use --help for usage.")


if __name__ == "__main__":
    main()
