#!/usr/bin/env python3
"""
Schema validation utility for ESS-DIVE entity data.

This module provides functionality to validate ESS-DIVE entity JSON files
against the Bertron schema using both Pydantic models and JSON schema validation.
"""

import json
import os
import sys
from typing import List, Dict, Any, Tuple, Optional
import jsonschema

# Import Pydantic models from bertron-schema
try:
    from schema.datamodel.bertron_schema_pydantic import Entity

    PYDANTIC_AVAILABLE = True
except ImportError as e:
    print(
        f"Warning: Pydantic models not available ({e}). Only JSON schema validation will be used."
    )
    PYDANTIC_AVAILABLE = False


class SchemaValidator:
    """Utility class for validating ESS-DIVE entities against Bertron schema."""

    def __init__(self, schema_path: Optional[str] = None):
        """
        Initialize the SchemaValidator.

        Args:
            schema_path: Path to the JSON schema file. If None, will attempt to
                        find it in the bertron-schema package. JSON schema is
                        only used as fallback if Pydantic models aren't available.
        """
        self.schema_path = schema_path
        self.json_schema = None

        # Display validation strategy
        if PYDANTIC_AVAILABLE:
            print("Using Pydantic models for schema validation")
        else:
            print(
                "Pydantic models not available, falling back to JSON schema validation"
            )
            self._load_json_schema()

    def _load_json_schema(self):
        """Load the JSON schema for validation (fallback only)."""
        schema_paths = []

        if self.schema_path:
            schema_paths.append(self.schema_path)

        # Try common locations for the schema
        schema_paths.extend(
            [
                "../../bertron-schema/src/schema/jsonschema/bertron_schema.json",
                "../../../bertron-schema/src/schema/jsonschema/bertron_schema.json",
                "bertron_schema.json",
            ]
        )

        for path in schema_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self.json_schema = json.load(f)
                    print(f"Loaded JSON schema from: {path}")
                    return
                except Exception as e:
                    print(f"Warning: Could not load schema from {path}: {e}")
                    continue

        print(
            "Warning: Could not load JSON schema. Only basic field validation will be performed."
        )

    def validate_entity(self, entity: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate a single entity against the schema.

        Args:
            entity: Entity dictionary to validate

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Basic structure validation
        if not isinstance(entity, dict):
            errors.append("Entity must be a dictionary")
            return False, errors

        # Primary validation: Use Pydantic models if available
        if PYDANTIC_AVAILABLE:
            try:
                # Use Pydantic model validation which is more comprehensive
                Entity.model_validate(entity)
                # If we get here, Pydantic validation passed
                return True, []
            except Exception as e:
                # Parse Pydantic validation errors for better error messages
                errors.append(f"Schema validation failed: {str(e)}")
                # Don't return here - let's also do fallback validation for more details

        # Fallback validation: Basic field checks (for when Pydantic isn't available)
        if not PYDANTIC_AVAILABLE:
            # Check required fields
            required_fields = ["id", "entity_type", "ber_data_source"]
            for field in required_fields:
                if field not in entity:
                    errors.append(f"Missing required field: {field}")

            # Validate ber_data_source
            if "ber_data_source" in entity:
                valid_sources = ["EMSL", "ESS-DIVE", "JGI", "MONET", "NMDC"]
                if entity["ber_data_source"] not in valid_sources:
                    errors.append(
                        f"Invalid ber_data_source: {entity['ber_data_source']}. "
                        f"Must be one of: {valid_sources}"
                    )

            # Validate entity_type
            if "entity_type" in entity:
                valid_types = ["site", "dataset", "sample", "study"]
                entity_types = entity["entity_type"]
                if isinstance(entity_types, str):
                    entity_types = [entity_types]
                if isinstance(entity_types, list):
                    for etype in entity_types:
                        if etype not in valid_types:
                            errors.append(
                                f"Invalid entity_type: {etype}. "
                                f"Must be one of: {valid_types}"
                            )
                else:
                    errors.append("entity_type must be a string or list of strings")

            # Validate coordinates if present
            if "coordinates" in entity and entity["coordinates"] is not None:
                coord_errors = self._validate_coordinates(entity["coordinates"])
                errors.extend(coord_errors)

        # Optional: JSON Schema validation as additional check (if available and Pydantic failed)
        if self.json_schema and not PYDANTIC_AVAILABLE:
            try:
                # Only use JSON schema if Pydantic isn't available
                jsonschema.validate(entity, self.json_schema)
            except jsonschema.ValidationError as e:
                errors.append(f"JSON Schema validation error: {e.message}")
            except Exception as e:
                errors.append(f"JSON Schema validation error: {e}")

        return len(errors) == 0, errors

    def _validate_coordinates(self, coordinates: Dict[str, Any]) -> List[str]:
        """Validate coordinates structure."""
        errors = []

        if not isinstance(coordinates, dict):
            errors.append("coordinates must be a dictionary")
            return errors

        # Check for required lat/lon
        if "latitude" not in coordinates:
            errors.append("coordinates missing latitude")
        elif not isinstance(coordinates["latitude"], (int, float)):
            errors.append("latitude must be a number")
        elif not (-90 <= coordinates["latitude"] <= 90):
            errors.append("latitude must be between -90 and 90")

        if "longitude" not in coordinates:
            errors.append("coordinates missing longitude")
        elif not isinstance(coordinates["longitude"], (int, float)):
            errors.append("longitude must be a number")
        elif not (-180 <= coordinates["longitude"] <= 180):
            errors.append("longitude must be between -180 and 180")

        return errors

    def validate_file(self, file_path: str) -> Tuple[bool, List[str], int]:
        """
        Validate all entities in a JSON file.

        Args:
            file_path: Path to JSON file to validate

        Returns:
            Tuple of (is_valid, list_of_errors, entity_count)
        """
        errors = []
        entity_count = 0

        if not os.path.exists(file_path):
            return False, [f"File does not exist: {file_path}"], 0

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            return False, [f"Invalid JSON: {e}"], 0
        except Exception as e:
            return False, [f"Error reading file: {e}"], 0

        if not isinstance(data, list):
            return False, ["File must contain a JSON array of entities"], 0

        entity_count = len(data)

        for i, entity in enumerate(data):
            is_valid, entity_errors = self.validate_entity(entity)
            if not is_valid:
                for error in entity_errors:
                    errors.append(f"Entity {i}: {error}")

        return len(errors) == 0, errors, entity_count

    def validate_split_files(self, file_pattern: str) -> Tuple[bool, List[str], int]:
        """
        Validate multiple split files matching a pattern.

        Args:
            file_pattern: Pattern like "essdive_*.json" or directory containing files

        Returns:
            Tuple of (is_valid, list_of_errors, total_entity_count)
        """
        import glob

        errors = []
        total_entities = 0

        # Handle directory vs file pattern
        if os.path.isdir(file_pattern):
            pattern = os.path.join(file_pattern, "essdive_*.json")
        else:
            pattern = file_pattern

        files = sorted(glob.glob(pattern))

        if not files:
            return False, [f"No files found matching pattern: {pattern}"], 0

        print(f"Validating {len(files)} files...")

        for file_path in files:
            print(f"  Validating {os.path.basename(file_path)}...")
            is_valid, file_errors, entity_count = self.validate_file(file_path)
            total_entities += entity_count

            if not is_valid:
                for error in file_errors:
                    errors.append(f"{os.path.basename(file_path)}: {error}")

        return len(errors) == 0, errors, total_entities


def main():
    """CLI interface for schema validation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate ESS-DIVE entity JSON files against Bertron schema"
    )
    parser.add_argument(
        "input", help="Input JSON file, directory, or file pattern to validate"
    )
    parser.add_argument("--schema", help="Path to JSON schema file (optional)")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed error messages"
    )

    args = parser.parse_args()

    # Initialize validator
    validator = SchemaValidator(schema_path=args.schema)

    try:
        # Determine validation approach
        if os.path.isfile(args.input):
            # Single file
            print(f"Validating file: {args.input}")
            is_valid, errors, entity_count = validator.validate_file(args.input)

            print(f"Entities: {entity_count}")

        elif os.path.isdir(args.input) or "*" in args.input:
            # Multiple files
            print(f"Validating files matching: {args.input}")
            is_valid, errors, entity_count = validator.validate_split_files(args.input)

            print(f"Total entities: {entity_count}")

        else:
            print(f"Error: Input not found: {args.input}")
            sys.exit(1)

        # Report results
        if is_valid:
            print("✓ All entities are valid")
        else:
            print(f"✗ Found {len(errors)} validation errors:")
            if args.verbose:
                for error in errors:
                    print(f"  {error}")
            else:
                # Show first 10 errors
                for error in errors[:10]:
                    print(f"  {error}")
                if len(errors) > 10:
                    print(f"  ... and {len(errors) - 10} more errors")
                    print("  Use --verbose to see all errors")

            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
