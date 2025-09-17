#!/usr/bin/env python3
"""
Validation script to verify Pydantic model compatibility and entity creation.

This script tests that the fetch_essdive_entities.py ETL pipeline can successfully
create Bertron entities using the Pydantic models from bertron-schema package.
It verifies import functionality, entity creation, and model serialization.
"""

import sys
import os

# Add the current directory to the path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from fetch_essdive_entities import EssDiveEntityFetcher

    print("✓ Successfully imported EssDiveEntityFetcher")

    # Test creating the fetcher
    fetcher = EssDiveEntityFetcher()
    print("✓ Successfully created EssDiveEntityFetcher instance")

    # Test creating a mock site entity
    mock_dataset_version = "ess-dive-test123-20250917T120000000"
    mock_dataset = {
        "@id": "doi:10.15485/test123",
        "name": "Test Dataset",
        "description": "A test dataset for validation",
        "alternateName": ["TEST_001", "MockData"],
    }

    mock_spatial_coverage = {
        "description": "Test site location",
        "geo": {"latitude": 45.0, "longitude": -120.0},
    }

    # Test site entity creation
    site_entity = fetcher.create_site_entity(
        dataset_version=mock_dataset_version,
        dataset=mock_dataset,
        spatial_coverage=mock_spatial_coverage,
    )
    print("✓ Successfully created site entity with Pydantic model")
    print(f"  Entity type: {type(site_entity)}")
    print(f"  BER source: {site_entity.ber_data_source}")
    print(f"  Entity types: {site_entity.entity_type}")
    print(f"  Name: {site_entity.name}")
    print(f"  URI: {site_entity.uri}")

    # Test dataset entity creation
    dataset_entity = fetcher.create_dataset_entity(
        dataset_version=mock_dataset_version, dataset=mock_dataset
    )
    print("✓ Successfully created dataset entity with Pydantic model")
    print(f"  Entity type: {type(dataset_entity)}")
    print(f"  BER source: {dataset_entity.ber_data_source}")
    print(f"  Entity types: {dataset_entity.entity_type}")

    # Test JSON serialization
    site_dict = site_entity.model_dump(exclude_none=True)
    dataset_dict = dataset_entity.model_dump(exclude_none=True)
    print("✓ Successfully serialized entities to dictionaries")
    print(f"  Site entity keys: {list(site_dict.keys())}")
    print(f"  Dataset entity keys: {list(dataset_dict.keys())}")

    print("\n🎉 All tests passed! The script is ready to use with Pydantic models.")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure bertron-schema is installed: pip install -r requirements.txt")
    sys.exit(1)
except Exception as e:
    print(f"❌ Test failed: {e}")
    sys.exit(1)
