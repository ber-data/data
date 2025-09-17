#!/usr/bin/env python3
"""
Standalone validation script for ESS-DIVE ingest files.

This script can validate individual JSON files or entire directories of
ESS-DIVE entity files against the Bertron schema. It's designed to work
independently of the fetch process for quality assurance.

Usage:
    python validate_essdive_ingest.py /path/to/file.json
    python validate_essdive_ingest.py /path/to/ingest/directory/
    python validate_essdive_ingest.py essdive_*.json
"""

import os
import sys
import glob
from pathlib import Path

# Add contrib/ess-dive to path to import validation modules
contrib_dir = Path(__file__).parent
if str(contrib_dir) not in sys.path:
    sys.path.insert(0, str(contrib_dir))

# Import after path setup
try:
    from schema_validator import SchemaValidator
except ImportError as e:
    print(f"Error importing schema_validator: {e}")
    print("Make sure schema_validator.py is in the same directory")
    sys.exit(1)


def validate_ingest_files(input_path: str, verbose: bool = False) -> int:
    """
    Validate ESS-DIVE ingest files.

    Args:
        input_path: Path to file, directory, or glob pattern
        verbose: Show detailed error messages

    Returns:
        Exit code (0 for success, 1 for validation errors)
    """
    validator = SchemaValidator()

    # Determine what we're validating
    if os.path.isfile(input_path):
        # Single file
        print(f"Validating file: {input_path}")
        is_valid, errors, entity_count = validator.validate_file(input_path)

        if is_valid:
            print(f"✓ File is valid ({entity_count} entities)")
            return 0
        else:
            print(f"✗ File has {len(errors)} validation errors:")
            if verbose:
                for error in errors:
                    print(f"  {error}")
            else:
                for error in errors[:10]:
                    print(f"  {error}")
                if len(errors) > 10:
                    print(f"  ... and {len(errors) - 10} more errors")
                    print("  Use --verbose to see all errors")
            return 1

    elif os.path.isdir(input_path):
        # Directory - look for essdive_*.json files
        pattern = os.path.join(input_path, "essdive_*.json")
        files = sorted(glob.glob(pattern))

        if not files:
            print(f"No essdive_*.json files found in {input_path}")
            return 1

        print(f"Validating {len(files)} files in {input_path}")
        is_valid, errors, total_entities = validator.validate_split_files(input_path)

        if is_valid:
            print(f"✓ All files are valid ({total_entities} total entities)")
            return 0
        else:
            print(f"✗ Found {len(errors)} validation errors:")
            if verbose:
                for error in errors:
                    print(f"  {error}")
            else:
                for error in errors[:10]:
                    print(f"  {error}")
                if len(errors) > 10:
                    print(f"  ... and {len(errors) - 10} more errors")
                    print("  Use --verbose to see all errors")
            return 1

    elif "*" in input_path or "?" in input_path:
        # Glob pattern
        files = sorted(glob.glob(input_path))

        if not files:
            print(f"No files found matching pattern: {input_path}")
            return 1

        print(f"Validating {len(files)} files matching pattern: {input_path}")

        total_errors = []
        total_entities = 0
        valid_files = 0

        for file_path in files:
            is_valid, errors, entity_count = validator.validate_file(file_path)
            total_entities += entity_count

            if is_valid:
                valid_files += 1
                print(f"  ✓ {os.path.basename(file_path)} ({entity_count} entities)")
            else:
                print(f"  ✗ {os.path.basename(file_path)} ({len(errors)} errors)")
                for error in errors:
                    total_errors.append(f"{os.path.basename(file_path)}: {error}")

        print(
            f"\nSummary: {valid_files}/{len(files)} files valid, {total_entities} total entities"
        )

        if total_errors:
            print(f"Total validation errors: {len(total_errors)}")
            if verbose:
                for error in total_errors:
                    print(f"  {error}")
            else:
                for error in total_errors[:10]:
                    print(f"  {error}")
                if len(total_errors) > 10:
                    print(f"  ... and {len(total_errors) - 10} more errors")
                    print("  Use --verbose to see all errors")
            return 1
        else:
            return 0

    else:
        print(f"Error: Input not found: {input_path}")
        return 1


def main():
    """CLI interface for ESS-DIVE ingest validation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate ESS-DIVE ingest files against Bertron schema",
        epilog="""
Examples:
  %(prog)s essdive_00001.json                    # Validate single file
  %(prog)s /path/to/ingest/ess-dive/             # Validate directory
  %(prog)s essdive_*.json                        # Validate files matching pattern
  %(prog)s --verbose essdive_00001.json          # Show detailed errors
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "input", help="Input JSON file, directory, or file pattern to validate"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed error messages"
    )
    parser.add_argument("--schema", help="Path to custom JSON schema file (optional)")

    args = parser.parse_args()

    # Override schema path if provided
    if args.schema:
        # This would require modifying SchemaValidator to accept custom schema
        print("Custom schema path not yet implemented")
        return 1

    try:
        exit_code = validate_ingest_files(args.input, args.verbose)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nValidation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
