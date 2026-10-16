import argparse
import json
import sys

from app.adapters.meddi_json import load_ground_truth, load_patients
from app.config import settings
from app.eval.metrics import evaluate
from app.eval.replay import replay
from app.eval.report import table


def run(dataset: str, use_llm: bool) -> dict:
    outputs = [output for _, _, output in replay(list(load_patients(dataset)), use_llm)]
    result = evaluate(outputs, load_ground_truth(dataset))
    result["dataset"], result["use_llm"] = dataset, use_llm
    result["outputs"] = [output.model_dump(mode="json") for output in outputs]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.eval")
    parser.add_argument("--dataset", choices=["dev", "rozsirena", "all"], default="dev")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--errors", action="store_true", help="print the error list")
    args = parser.parse_args(argv)
    use_llm = not args.no_llm and settings.llm_enabled
    reports = settings.cache_dir.parent / "reports"
    reports.mkdir(exist_ok=True)
    for dataset in (["dev", "rozsirena"] if args.dataset == "all" else [args.dataset]):
        result = run(dataset, use_llm)
        (reports / f"eval_{dataset}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print(table(f"{dataset} ({'LLM + lexicon' if use_llm else 'rules + lexicon only'})", result))
        if args.errors:
            for error in result["errors"]:
                print(f"  {error['kind']:<7} {error['checkin_id']:<14} GT{error['expected']} → {error['predicted']}  {error['rules']}  "
                      f"{'' if error['expected_contact'] == error['predicted_contact'] else '[contact ' + str(error['predicted_contact']) + ' vs ' + str(error['expected_contact']) + ']'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
