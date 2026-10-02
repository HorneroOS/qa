from hornero_qa.cli import main


def test_help_runs() -> None:
    assert main([]) == 0
