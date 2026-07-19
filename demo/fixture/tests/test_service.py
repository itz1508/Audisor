from app.main import main
from app.service import process


def test_process() -> None:
    assert process(" demo ") == "demo"
    assert main() == "demo"
