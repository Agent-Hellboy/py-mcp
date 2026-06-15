from pymcp.util.completion import (
    build_completion_result,
    extract_template_variables,
    rank_completions,
)


def test_extract_template_variables():
    assert extract_template_variables("memo://{topic}/{section}") == ["topic", "section"]


def test_rank_completions_prefix_and_substring():
    values = rank_completions(["python", "pytorch", "pyside", "java"], "py")
    assert values == ["python", "pytorch", "pyside"]


def test_build_completion_result_paginates():
    candidates = [f"item-{index}" for index in range(105)]
    result = build_completion_result(candidates, prefix="")
    assert len(result["values"]) == 100
    assert result["total"] == 105
    assert result["hasMore"] is True
