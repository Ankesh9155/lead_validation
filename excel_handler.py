import pandas as pd
import os
import time


# ==========================================
# Read Excel File
# ==========================================

def read_excel(file_name, sheet_name):
    
    if not os.path.exists(file_name):
        raise FileNotFoundError(
            f"Excel file not found: {file_name}"
        )

    try:
        data = pd.read_excel(
            file_name,
            sheet_name=sheet_name,
            dtype=str
        )

        # Replace NaN with empty string
        data = data.fillna("")

        print(
            "Excel loaded successfully"
        )

        print(
            f"Total rows found: {len(data)}"
        )

        return data


    except Exception as e:

        raise Exception(
            f"Unable to read Excel file: {e}"
        )


# ==========================================
# Save Excel File
# ==========================================

def save_excel(data, output_file):

    while True:

        try:
            data.to_excel(
                output_file,
                index=False,
                engine="openpyxl"
            )

            print(
                f"File saved successfully: {output_file}"
            )

            break


        except PermissionError:

            print(
                "\nOutput file is open in Excel."
            )

            input(
                "Please close the Excel file and press ENTER to retry..."
            )


        except Exception as e:

            raise Exception(
                f"Failed to save Excel: {e}"
            )


# ==========================================
# Create Output File Copy
# (Optional Utility)
# ==========================================

def create_output_file(data, output_file):

    try:

        data.to_excel(
            output_file,
            index=False,
            engine="openpyxl"
        )

        print(
            f"Output file created: {output_file}"
        )

    except Exception as e:

        raise Exception(
            f"Unable to create output file: {e}"
        )


# ==========================================
# Check Required Columns
# ==========================================

def validate_columns(data, required_columns):

    missing = []

    for column in required_columns:

        if column not in data.columns:

            missing.append(column)


    if missing:

        raise Exception(
            "Missing Excel columns: " +
            ", ".join(missing)
        )


    print(
        "All required Excel columns found"
    )