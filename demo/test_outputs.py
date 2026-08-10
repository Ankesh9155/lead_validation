from pathlib import Path


INPUT_FILE = Path("/app/numbers.txt")
OUTPUT_FILE = Path("/app/output.txt")


def test_output_file_contains_sum_of_input_numbers():
    """Verify that the output contains the sum calculated from the input numbers."""
    numbers = [
        float(line.strip())
        for line in INPUT_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    expected_total = sum(numbers)
    actual_output = OUTPUT_FILE.read_text(encoding="utf-8").strip()

    assert float(actual_output) == expected_total


def test_output_file_contains_a_valid_numeric_result():
    """Verify that the generated output contains a valid numeric result."""
    output = OUTPUT_FILE.read_text(encoding="utf-8").strip()

    assert output
    float(output)