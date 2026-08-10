#!/bin/bash
set -e

INPUT_FILE="/app/numbers.txt"
OUTPUT_FILE="/app/output.txt"

python3 - "$INPUT_FILE" "$OUTPUT_FILE" <<'PY'
import sys
from pathlib import Path

input_file = Path(sys.argv[1])
output_file = Path(sys.argv[2])

numbers = [
    float(line.strip())
    for line in input_file.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

total = sum(numbers)

if total.is_integer():
    result = str(int(total))
else:
    result = str(total)

output_file.write_text(result + "\n", encoding="utf-8")
PY