# EMSL Data Analysis Summary

## Overview

This document summarizes findings from analyzing EMSL metadata structure requirements and the Bertron schema for BER data integration.

## EMSL Metadata Structure Analysis

### Structure Directory Overview

The `emsl/emsl_data_from_onedrive/` directory contains five different structure types, each with unique Excel file parsing requirements documented in their respective `ReadMe.txt` files.

### Structure 1: Standard Metadata Tab
**Location**: `Structure1/ReadMe.txt`
- **Excel Tab**: "Metadata"
- **Header Row**: Row 1 contains attribute labels
- **Data Start**: Row 5
- **Special Rules**:
  - Rows starting with "other" or "treatment" should use the term in row 2 for the attribute label
- **Project ID**: Available in "project_name" or "project_id" column

### Structure 2: Samples Tab with GUID Handling
**Location**: `Structure2/ReadMe.txt`
- **Excel Tab**: "Samples"
- **Header Row**: Row 1 contains attribute labels
- **Data Start**: Row 5
- **Special Rules**:
  - **ID Handling**: Merge "guid_source" and "unique_ID" columns for the "id" slot
  - If "guid_source" not available, use "unique_id" only
  - **Sample Type**: Located in "Sample Submission" tab, to the right of "Sample Type/Species" cell
  - **Data Cleaning**: Skip rows with "N/A" or "NA" values
- **Note**: References incomplete "macro file" documentation

### Structure 3: Variable Column Processing
**Location**: `Structure3/ReadMe.txt`
- **Excel Tab**: "Metadata"
- **Header Row**: Row 1 contains attribute labels
- **Data Start**: Row 4
- **Special Rules**:
  - Columns starting with "variable" should use information from "label" rows
  - Variable columns have corresponding "raw_value" data in the column to the right
- **Project ID**: Available in "project_name" column

### Structure 4: Experiment Metadata
**Location**: `Structure4/ReadMe.txt`
- **Excel Tab**: "Experiment_metadata"
- **Header Row**: Row 1 contains attribute labels
- **Data Start**: Row 2 (earliest start row)
- **Special Rules**:
  - "Globally Unique Persistent Identifier" should populate the "sample_name" attribute
  - GUID may not always be available
- **Project ID**: Available in "project_name" column

### Structure 5: Uncertain Processing
**Location**: `Structure5/ReadMe.txt`
- **Status**: Data "Submitted via SC" (Sample Collection system)
- **Question**: Requires determination if "boutique ETL" (Extract, Transform, Load) process is needed
- **Implication**: This structure may require custom processing different from the other four

## Bertron Schema Analysis

### Schema Purpose
The Bertron Schema is a **LinkML-based schema** for **BER (Biological and Environmental Research) data integration**, providing a common data model to harmonize data from multiple BER sources.

### Core Entity Structure

#### Required Fields
- `ber_data_source`: Source system (EMSL, ESS-DIVE, JGI, MONET, NMDC)
- `entity_type`: Array of entity types (sample, sequence, project, site, dataset, etc.)

#### Optional Fields
- `coordinates`: Geographic coordinates (latitude/longitude as decimal degrees)
- `description`: Textual description
- `id`: Unique identifier within the BER resource
- `name`: Human-readable string representation
- `alt_ids`: Alternative identifiers (CURIEs, database cross-references)
- `alt_names`: Alternative names/synonyms
- `properties`: Extensible attribute-value pairs for metadata

### Supported Data Sources
- **EMSL**: Environmental Molecular Sciences Laboratory
- **ESS-DIVE**: Environmental System Science Data Infrastructure for a Virtual Ecosystem
- **JGI**: Joint Genome Institute
- **MONET**: Molecular Observation Network
- **NMDC**: National Microbiome Data Collaborative

### Properties System Architecture

#### AttributeValue Base Class
- `attribute`: Property descriptor with label and optional ontology ID
- `raw_value`: Original string representation as found in source data

#### QuantityValue (extends AttributeValue)
For numeric measurements:
- `numeric_value`: Parsed numeric value
- `unit`: Unit of measurement (UCUM/Unit Ontology references)
- `minimum_numeric_value`/`maximum_numeric_value`: For range values
- `raw_value`: Original string representation (e.g., "25°C", "2-4 cm")

#### TextValue (extends AttributeValue)
For text-based properties:
- `value`: The text value
- `value_cv_id`: Controlled vocabulary ID when applicable

## Integration Strategy

### Expected EMSL Data Transformation

Each EMSL sample should be transformed to this structure:

```json
{
  "ber_data_source": "EMSL",
  "entity_type": ["sample"],
  "id": "EMSL:UUID:...",
  "name": "Sample Name from Excel",
  "uri": "https://sc-data.emsl.pnnl.gov/...",
  "description": "Generated from Excel metadata",
  "coordinates": {
    "latitude": 34.0,
    "longitude": -118.0
  },
  "properties": [
    {
      "attribute": {
        "label": "sample_type",
        "id": "MIXS:0000031"
      },
      "raw_value": "pure_culture"
    },
    {
      "attribute": {
        "label": "temperature"
      },
      "numeric_value": 25.0,
      "unit": "UO:0000027",
      "raw_value": "25°C"
    }
  ]
}
```

### Processing Requirements by Structure

1. **Structure 1 & 3**: Focus on "Metadata" tab with different starting rows
2. **Structure 2**: Handle GUID merging and cross-reference "Sample Submission" tab
3. **Structure 4**: Process "Experiment_metadata" with earliest data start (row 2)
4. **Structure 5**: Requires investigation for processing approach

### Key Transformation Considerations

#### Data Standardization
- **Geographic Coordinates**: Convert to decimal degrees format
- **Units**: Normalize to UCUM/UO ontology references
- **IDs**: Prefix with "EMSL:" and preserve UUIDs when available
- **Ontology Mapping**: Use MIXS terms where applicable for environmental samples

#### Data Quality
- Skip rows with "N/A" or "NA" values (especially Structure 2)
- Handle missing GUID scenarios gracefully
- Preserve original raw values while providing normalized data
- Validate required fields before transformation

#### Extensibility
- Properties array accommodates any Excel column as metadata
- Flexible attribute system supports future ontology integration
- Raw value preservation ensures no data loss during transformation

## Next Steps

1. **Structure 5 Investigation**: Determine appropriate processing approach for SC-submitted data
2. **Ontology Mapping**: Develop mapping tables for common EMSL attributes to controlled vocabularies
3. **Validation Pipeline**: Implement schema validation against Bertron schema
4. **Coordinate Extraction**: Develop geographic coordinate parsing from various Excel formats
5. **Unit Normalization**: Create unit conversion system for QuantityValue properties