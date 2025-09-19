#!/usr/bin/env python3
"""
Test script for ESS-DIVE ETL workflow.

This script tests the complete ESS-DIVE data processing pipeline:
1. Imports and basic functionality tests
2. Schema validation functionality
3. Integration tests (without making API calls)

Run this script to verify the ETL pipeline is working correctly.
"""

import os
import sys
import json
import tempfile
from pathlib import Path

# Add current directory to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))


def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")

    try:
        import fetch_essdive_entities  # noqa: F401

        print("  ✓ fetch_essdive_entities imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import fetch_essdive_entities: {e}")
        return False

    try:
        import schema_validator  # noqa: F401

        print("  ✓ schema_validator imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import schema_validator: {e}")
        return False

    try:
        import requests  # noqa: F401

        print("  ✓ requests imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import requests: {e}")
        return False

    try:
        import jsonschema  # noqa: F401

        print("  ✓ jsonschema imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import jsonschema: {e}")
        return False

    return True


def test_fetch_script_splitting():
    """Test integrated file splitting functionality."""
    print("\nTesting integrated file splitting...")

    try:
        from fetch_essdive_entities import EssDiveEntityFetcher

        # Create a mock fetcher with small file size limit
        fetcher = EssDiveEntityFetcher(max_file_size_mb=0.01)  # 10KB to force splits

        # Create test entities
        test_entities = []
        for i in range(50):
            entity_dict = {
                "id": f"test-entity-{i:03d}",
                "entity_type": ["dataset"],
                "ber_data_source": "ESS-DIVE",
                "name": f"Test Entity {i}",
                "description": "This is a test entity for file splitting validation. "
                * 20,  # Make it larger
                "uri": f"https://example.com/test-{i}",
            }
            test_entities.append(entity_dict)

        # Convert to Entity objects for the test
        from fetch_essdive_entities import Entity, BERSourceType, EntityType

        pydantic_entities = []
        for entity_dict in test_entities:
            entity = Entity(
                id=entity_dict["id"],
                entity_type=[EntityType.dataset],
                ber_data_source=BERSourceType.ESS_DIVE,
                name=entity_dict["name"],
                description=entity_dict["description"],
                uri=entity_dict["uri"],
            )
            pydantic_entities.append(entity)

        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)  # Change to temp dir for file creation

            created_files = fetcher._write_entities_chunked(
                pydantic_entities, "test_essdive"
            )

            if len(created_files) <= 1:
                print("  ✗ File splitting did not create multiple files as expected")
                return False

            print(f"  ✓ File splitting created {len(created_files)} files")

            # Check that all files exist and have content
            total_entities_in_files = 0
            for file_path in created_files:
                if not os.path.exists(file_path):
                    print(f"  ✗ Created file does not exist: {file_path}")
                    return False

                with open(file_path, "r") as f:
                    file_entities = json.load(f)
                    total_entities_in_files += len(file_entities)

            if total_entities_in_files != len(test_entities):
                print(
                    f"  ✗ Entity count mismatch: expected {len(test_entities)}, got {total_entities_in_files}"
                )
                return False

            print("  ✓ All entities preserved across split files")

        return True

    except Exception as e:
        print(f"  ✗ Integrated file splitting test failed: {e}")
        return False


def test_schema_validator():
    """Test schema validation functionality."""
    print("\nTesting schema validator...")

    try:
        from schema_validator import SchemaValidator

        validator = SchemaValidator()

        # Test valid entity
        valid_entity = {
            "id": "test-entity-001",
            "entity_type": ["site"],
            "ber_data_source": "ESS-DIVE",
            "name": "Test Site",
            "description": "A test site entity",
            "coordinates": {"latitude": 37.8719, "longitude": -122.2585},
            "uri": "https://example.com/test-001",
        }

        is_valid, errors = validator.validate_entity(valid_entity)

        if not is_valid:
            print(f"  ✗ Valid entity validation failed: {errors}")
            return False

        print("  ✓ Valid entity validation passed")

        # Test invalid entity
        invalid_entity = {
            "id": "test-entity-002",
            "entity_type": ["invalid_type"],
            "ber_data_source": "INVALID_SOURCE",
            "coordinates": {
                "latitude": 91.0,  # Invalid latitude
                "longitude": -200.0,  # Invalid longitude
            },
        }

        is_valid, errors = validator.validate_entity(invalid_entity)

        if is_valid:
            print("  ✗ Invalid entity validation should have failed")
            return False

        print(f"  ✓ Invalid entity validation correctly failed ({len(errors)} errors)")

        # Test file validation
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([valid_entity], f, indent=2)
            temp_file = f.name

        try:
            is_valid, errors, entity_count = validator.validate_file(temp_file)

            if not is_valid:
                print(f"  ✗ File validation failed: {errors}")
                return False

            if entity_count != 1:
                print(f"  ✗ Entity count mismatch: expected 1, got {entity_count}")
                return False

            print("  ✓ File validation passed")

        finally:
            os.unlink(temp_file)

        return True

    except Exception as e:
        print(f"  ✗ Schema validator test failed: {e}")
        return False


def test_integration():
    """Test integration of file splitting and validation."""
    print("\nTesting integration...")

    try:
        from fetch_essdive_entities import (
            EssDiveEntityFetcher,
            Entity,
            BERSourceType,
            EntityType,
        )
        from schema_validator import SchemaValidator

        # Create test entities
        test_entities = []

        # Valid entities
        for i in range(30):
            entity = Entity(
                id=f"integration-test-{i:03d}",
                entity_type=[EntityType.site if i % 2 == 0 else EntityType.dataset],
                ber_data_source=BERSourceType.ESS_DIVE,
                name=f"Integration Test Entity {i}",
                description=f"This is integration test entity number {i}. " * 10,
                uri=f"https://example.com/integration-test-{i}",
                coordinates=(
                    {
                        "latitude": 37.0 + (i * 0.01),
                        "longitude": -122.0 - (i * 0.01),
                    }
                    if i % 2 == 0
                    else None
                ),
            )
            test_entities.append(entity)

        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)  # Change to temp dir

            # Create fetcher with small file size to force splits
            fetcher = EssDiveEntityFetcher(
                max_file_size_mb=0.02
            )  # Small size to force splits
            created_files = fetcher._write_entities_chunked(
                test_entities, "integration_test"
            )

            print(f"  ✓ Created {len(created_files)} split files")

            # Validate all files
            validator = SchemaValidator()

            total_errors = []
            total_entities = 0
            valid_files = 0

            for file_path in created_files:
                is_valid, errors, entity_count = validator.validate_file(file_path)
                total_entities += entity_count

                if is_valid:
                    valid_files += 1
                else:
                    total_errors.extend(
                        [f"{os.path.basename(file_path)}: {error}" for error in errors]
                    )

            if total_errors:
                print(f"  ✗ Integration validation failed: {total_errors[:3]}")
                return False

            if total_entities != len(test_entities):
                print(
                    f"  ✗ Entity count mismatch: expected {len(test_entities)}, got {total_entities}"
                )
                return False

            print(f"  ✓ Integration validation passed ({total_entities} entities)")

        return True

    except Exception as e:
        print(f"  ✗ Integration test failed: {e}")
        return False


def test_command_line_tools():
    """Test command line interfaces."""
    print("\nTesting command line tools...")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)  # Change to temp dir

            # Test basic CLI help
            import subprocess

            result = subprocess.run(
                [sys.executable, "fetch_essdive_entities.py", "--help"],
                capture_output=True,
                text=True,
                cwd=current_dir,
            )

            if result.returncode != 0:
                print(f"  ✗ Fetch script help failed: {result.stderr}")
                return False

            print("  ✓ Fetch script CLI help works")

            # Test validation CLI with a simple test file
            test_data = [
                {
                    "id": "cli-test-001",
                    "entity_type": ["dataset"],
                    "ber_data_source": "ESS-DIVE",
                    "name": "CLI Test",
                    "description": "Command line interface test",
                    "uri": "https://example.com/cli-test-001",
                }
            ]

            test_file = os.path.join(temp_dir, "cli_test_00001.json")
            with open(test_file, "w") as f:
                json.dump(test_data, f, indent=2)

            # Test validation CLI
            result = subprocess.run(
                [sys.executable, "validate_essdive_ingest.py", test_file],
                capture_output=True,
                text=True,
                cwd=current_dir,
            )

            if result.returncode != 0:
                print(f"  ✗ Validation CLI failed: {result.stderr}")
                print(f"    stdout: {result.stdout}")
                return False

            print("  ✓ Validation CLI test passed")

        return True

    except Exception as e:
        print(f"  ✗ CLI test failed: {e}")
        return False


def test_dry_run_feature():
    """Test the dry run functionality."""
    print("\nTesting dry run feature...")

    try:
        from fetch_essdive_entities import EssDiveEntityFetcher

        # Create a fetcher instance
        fetcher = EssDiveEntityFetcher()

        # Test dry run with small limits - using mock data since we don't want to hit API in tests
        # Instead, we'll test that the method signature works with the new parameters
        try:
            # Test that fetch_all_entities accepts the new parameters
            # We don't actually run this since it would hit the API
            # Just verify the method signature
            import inspect

            sig = inspect.signature(fetcher.fetch_all_entities)
            params = list(sig.parameters.keys())

            required_params = ["output_prefix", "page_size", "max_pages"]
            for param in required_params:
                if param not in params:
                    print(f"  ✗ Missing parameter {param} in fetch_all_entities")
                    return False

            print("  ✓ fetch_all_entities method signature updated correctly")

            # Test get_all_public_datasets signature
            sig = inspect.signature(fetcher.get_all_public_datasets)
            params = list(sig.parameters.keys())

            if "max_pages" not in params:
                print("  ✗ Missing max_pages parameter in get_all_public_datasets")
                return False

            print("  ✓ get_all_public_datasets method signature updated correctly")

            # Test CLI argument parsing
            import subprocess

            result = subprocess.run(
                [sys.executable, "fetch_essdive_entities.py", "--help"],
                capture_output=True,
                text=True,
                cwd=current_dir,
            )

            if result.returncode != 0:
                print(f"  ✗ CLI help failed: {result.stderr}")
                return False

            if "--dry-run-pages" not in result.stdout:
                print("  ✗ --dry-run-pages option not found in help output")
                return False

            print("  ✓ CLI dry-run-pages argument added successfully")

            return True

        except Exception as e:
            print(f"  ✗ Dry run feature test failed: {e}")
            return False

    except Exception as e:
        print(f"  ✗ Dry run test setup failed: {e}")
        return False


def main():
    """Run all tests."""
    print("ESS-DIVE ETL Workflow Test Suite")
    print("=" * 40)

    tests = [
        ("Import Tests", test_imports),
        ("Integrated File Splitting Tests", test_fetch_script_splitting),
        ("Schema Validator Tests", test_schema_validator),
        ("Integration Tests", test_integration),
        ("Command Line Tool Tests", test_command_line_tools),
        ("Dry Run Feature Tests", test_dry_run_feature),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                print(f"\n{test_name}: FAILED")
        except Exception as e:
            print(f"\n{test_name}: ERROR - {e}")

    print("\n" + "=" * 40)
    print(f"Test Results: {passed}/{total} passed")

    if passed == total:
        print("✓ All tests passed! The ETL workflow is ready for use.")
        return 0
    else:
        print("✗ Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
