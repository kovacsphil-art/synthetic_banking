"""Optional packaging of already-existing generated CSV files."""

from synthetic_banking.config import CSV_OUTPUT_DIR, SOURCE_DIR


def zip_existing_csvs(output_dir=CSV_OUTPUT_DIR, *, local_path="/tmp/RCAR_generated_row_level.zip", volume_path=SOURCE_DIR + "/RCAR_generated_row_level.zip"):
    import os
    import zipfile
    import shutil

    # Existing CSVs in the Volume
    OUTPUT_DIR = output_dir

    csv_paths = [
        f"{OUTPUT_DIR}/PERSON.csv",
        f"{OUTPUT_DIR}/CUSTOMER_ACCOUNT_REL.csv",
        f"{OUTPUT_DIR}/CUSTOMER_RELATIONSHIP.csv",
        f"{OUTPUT_DIR}/TKQ_ACCOUNT.csv",
        f"{OUTPUT_DIR}/TKQ_ACCOUNT_BALANCE.csv",
        f"{OUTPUT_DIR}/TRADELINES.csv"
    ]

    # ---------------------------------------------------------
    # Create ZIP locally first
    # ---------------------------------------------------------

    local_zip_path = local_path

    with zipfile.ZipFile(
        local_zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED
    ) as zip_file:

        for csv_path in csv_paths:

            zip_file.write(
                csv_path,
                arcname=os.path.basename(csv_path)
            )

    print("Local ZIP created:")
    print(local_zip_path)

    # ---------------------------------------------------------
    # Copy completed ZIP into the Databricks Volume
    # ---------------------------------------------------------

    volume_zip_path = (
        volume_path
    )

    shutil.copyfile(
        local_zip_path,
        volume_zip_path
    )

    print("\nZIP copied to Volume:")
    print(volume_zip_path)
    return volume_zip_path
