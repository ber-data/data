# ESS-DIVE Data Ingest

This directory contains tools for fetching, processing, and validating ESS-DIVE datasets for the BER Data Portal.

## Overview

The ESS-DIVE ingest pipeline fetches public datasets from the ESS-DIVE API and converts them into Bertron entities that conform to the [bertron-schema](https://github.com/ber-data/bertron-schema). The pipeline includes automatic file splitting for large datasets, comprehensive schema validation, and a test framework.

## Files

- **`fetch_essdive_entities.py`** - Main ETL script for fetching and converting ESS-DIVE data
- **`schema_validator.py`** - Schema validation utilities using Pydantic models
- **`validate_essdive_ingest.py`** - Standalone validation tool for existing JSON files
- **`test_workflow.py`** - Comprehensive test suite for the entire pipeline
- **`requirements.txt`** - Python dependencies

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Basic Usage

```bash
# Fetch all ESS-DIVE datasets and create bertron entities
python fetch_essdive_entities.py --output essdive_data

# Test run with limited data (1 page of 10 datasets)
python fetch_essdive_entities.py --dry-run-pages 1 --page-size 10 --output test_run

# Validate existing files
python validate_essdive_ingest.py essdive_data_*.json
```

## Main Features

### ETL Pipeline (`fetch_essdive_entities.py`)

**Core Functionality:**
- Fetches all public datasets from ESS-DIVE API
- Converts datasets to Bertron entities using Pydantic models
- Handles both site entities (with coordinates) and dataset entities
- Automatic file splitting to maintain ~25MB file size limits
- Built-in schema validation using Pydantic models

**CLI Options:**
```bash
usage: fetch_essdive_entities.py [-h] [--output OUTPUT] [--token TOKEN] 
                                 [--page-size PAGE_SIZE] [--dry-run-pages DRY_RUN_PAGES] 
                                 [--validate] [--no-validate]

options:
  -h, --help            show this help message and exit
  --output OUTPUT, -o OUTPUT
                        Output file prefix (default: 'essdive'). Files created as
                        PREFIX_00001.json, PREFIX_00002.json, etc.
  --token TOKEN, -t TOKEN
                        ESS-DIVE authentication token (or set ESS_DIVE_AUTH_TOKEN env var)
  --page-size PAGE_SIZE
                        Number of datasets per API request (default: 100, max: 100)
  --dry-run-pages DRY_RUN_PAGES
                        Test mode: only fetch specified number of pages (useful for testing)
  --validate            Validate output files against schema (default: True)
  --no-validate         Skip validation of output files
```

**Output Format:**
- Files named with prefix and sequential numbers: `essdive_00001.json`, `essdive_00002.json`, etc.
- JSON arrays containing Bertron entities
- File size limited to ~25MB with complete records only
- Automatic validation using Pydantic models

### Schema Validation (`schema_validator.py`)

**Features:**
- Primary validation using Pydantic models from bertron-schema
- Fallback to JSON schema validation when Pydantic unavailable
- Comprehensive entity validation including enums and field requirements
- Batch file validation capabilities

**Usage:**
```python
from schema_validator import SchemaValidator

validator = SchemaValidator()

# Validate single entity
is_valid, errors = validator.validate_entity(entity_dict)

# Validate entire file
is_valid, errors, entity_count = validator.validate_file("essdive_00001.json")
```

### Standalone Validation (`validate_essdive_ingest.py`)

**Features:**
- Independent validation tool for existing JSON files
- Supports single files, directories, or glob patterns
- Detailed error reporting with optional verbose output

**Usage:**
```bash
# Validate single file
python validate_essdive_ingest.py essdive_00001.json

# Validate all files in directory
python validate_essdive_ingest.py /path/to/ingest/directory/

# Validate files matching pattern
python validate_essdive_ingest.py essdive_*.json

# Verbose error reporting
python validate_essdive_ingest.py --verbose essdive_00001.json
```

## Data Transformation

### Site Entities (with spatial coverage)

ESS-DIVE datasets with spatial coverage are converted to site entities:

```json
{
  "id": "ess-dive-pid",
  "entity_type": ["site"],
  "ber_data_source": "ESS-DIVE",
  "name": "Dataset Name",
  "description": "Spatial coverage description or dataset description",
  "coordinates": {
    "latitude": 37.0,
    "longitude": -122.0
  },
  "uri": "https://data.ess-dive.lbl.gov/view/ess-dive-pid",
  "alt_ids": ["doi"]
}
```

### Dataset Entities (no spatial coverage)

ESS-DIVE datasets without spatial coverage become dataset entities:

```json
{
  "id": "ess-dive-pid", 
  "entity_type": ["dataset"],
  "ber_data_source": "ESS-DIVE",
  "name": "Dataset Name",
  "description": "Dataset description",
  "uri": "https://data.ess-dive.lbl.gov/view/ess-dive-pid",
  "alt_ids": ["doi"]
}
```

## Testing

### Test Suite (`test_workflow.py`)

Comprehensive test coverage including:

- **Import Tests**: Verify all required modules can be imported
- **File Splitting Tests**: Test integrated file splitting with size limits
- **Schema Validation Tests**: Test Pydantic model validation
- **Integration Tests**: End-to-end workflow validation
- **CLI Tests**: Command-line interface functionality
- **Dry Run Tests**: Test mode functionality

**Run Tests:**
```bash
python test_workflow.py
```

**Expected Output:**
```
ESS-DIVE ETL Workflow Test Suite
========================================
Testing imports...
  ✓ fetch_essdive_entities imported successfully
  ✓ schema_validator imported successfully
  ✓ requests imported successfully
  ✓ jsonschema imported successfully

Testing integrated file splitting...
  ✓ File splitting created 7 files
  ✓ All entities preserved across split files

Testing schema validator...
Using Pydantic models for schema validation
  ✓ Valid entity validation passed
  ✓ Invalid entity validation correctly failed (1 errors)
  ✓ File validation passed

Testing integration...
  ✓ Created 1 split files
  ✓ Integration validation passed (30 entities)

Testing command line tools...
  ✓ Fetch script CLI help works
  ✓ Validation CLI test passed

Testing dry run feature...
  ✓ fetch_all_entities method signature updated correctly
  ✓ get_all_public_datasets method signature updated correctly
  ✓ CLI dry-run-pages argument added successfully

========================================
Test Results: 6/6 passed
✓ All tests passed! The ETL workflow is ready for use.
```

## Authentication

ESS-DIVE API access can be configured with:

1. **Environment Variable**: `export ESS_DIVE_AUTH_TOKEN="your-token"`
2. **CLI Argument**: `--token your-token`

Note: Authentication is optional for public datasets but may be required for rate limiting or private data access.

## Examples

### Development and Testing

```bash
# Quick test with minimal data
python fetch_essdive_entities.py --dry-run-pages 1 --page-size 5 --output test

# Larger test run
python fetch_essdive_entities.py --dry-run-pages 5 --output sample_data

# Test without validation (faster)
python fetch_essdive_entities.py --dry-run-pages 2 --no-validate --output quick_test
```

### Production Usage

```bash
# Full ingest to specific directory
python fetch_essdive_entities.py --output ../../ingest/ess-dive/essdive

# With authentication token
python fetch_essdive_entities.py --token YOUR_TOKEN --output production_data

# Custom page size for rate limiting
python fetch_essdive_entities.py --page-size 50 --output slow_fetch
```

### Validation Workflows

```bash
# Validate files after manual edits
python validate_essdive_ingest.py modified_*.json

# Validate entire ingest directory
python validate_essdive_ingest.py ../../ingest/ess-dive/

# Get detailed error information
python validate_essdive_ingest.py --verbose problematic_file.json
```

## File Organization

### Input/Output Structure

```
data/
├── contrib/ess-dive/           # This directory
│   ├── fetch_essdive_entities.py
│   ├── schema_validator.py
│   ├── validate_essdive_ingest.py
│   └── test_workflow.py
└── ingest/ess-dive/           # Output directory
    ├── essdive_00001.json     # Generated files
    ├── essdive_00002.json
    └── ...
```

### File Naming Convention

- **Prefix**: Specified by `--output` parameter (default: "essdive")
- **Numbering**: Sequential 5-digit numbers: `00001`, `00002`, etc.
- **Extension**: Always `.json`
- **Example**: `essdive_00001.json`, `custom_prefix_00001.json`

## Schema Compliance

All generated entities conform to the [Bertron Schema](https://github.com/ber-data/bertron-schema):

- **Required Fields**: `ber_data_source`, `entity_type`, `uri`
- **Entity Types**: `site`, `dataset`, `sample`, `study`, etc.
- **Data Sources**: `ESS-DIVE`, `EMSL`, `JGI`, `MONET`, `NMDC`
- **Coordinates**: Optional latitude/longitude for site entities
- **Validation**: Automatic using Pydantic models

## Troubleshooting

### Debug Mode

Use dry run for debugging:
```bash
python fetch_essdive_entities.py --dry-run-pages 1 --page-size 2 --output debug
```

### Test Validation

Run the test suite to verify everything works:
```bash
python test_workflow.py
```
