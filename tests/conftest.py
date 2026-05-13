from __future__ import annotations


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--test-verbosity",
        action="store",
        default=0,
        type=int,
        help="Per-test scenario trace verbosity. 0 disables helper output; 1+ enables progressively more detail.",
    )


def pytest_report_header(config) -> str:
    return f"word_play test verbosity: {config.getoption('test_verbosity')}"


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "scenario: marks end-to-end environment scenario tests that support --test-verbosity tracing",
    )


def pytest_generate_tests(metafunc) -> None:
    if "test_verbosity" in metafunc.fixturenames:
        metafunc.parametrize("test_verbosity", [metafunc.config.getoption("test_verbosity")])
