#!/usr/bin/env python3
"""
EMSL Excel Data Transformation Script
 
This script processes EMSL Excel metadata files from different structure types
and transforms them into Bertron schema-compliant JSON format.
 
Author: BER Data Team
Date: September 2025
"""
 
import argparse
import json
import logging
import sys
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from uuid import uuid4
import traceback
 
import pandas as pd
from openpyxl import load_workbook
 
from linkml.validator import validate
 
@dataclass
class ProcessingConfig:
    """Configuration for the EMSL data processing pipeline."""
    input_base_dir: Path
    output_file: Path
    structure_dirs: List[str] = field(default_factory=lambda: ['Structure1', 'Structure2', 'Structure3', 'Structure4', 'Structure5'])
    log_level: str = 'INFO'
    validate_schema: bool = True
    append_mode: bool = False
    max_workers: int = 4
    skip_existing: bool = True
 
 
class EMSLDataProcessor:
    """Main orchestrator for EMSL data processing."""
 
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.logger = self._setup_logging()
        self.parsers = self._initialize_parsers()
        self.transformer = DataTransformer()
        self.validator = SchemaValidator() if config.validate_schema else None
 
    def _setup_logging(self) -> logging.Logger:
        """Set up logging configuration."""
        logging.basicConfig(
            level=getattr(logging, self.config.log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('emsl_processing.log')
            ]
        )
        return logging.getLogger(__name__)
 
    def _initialize_parsers(self) -> Dict[str, 'BaseStructureParser']:
        """Initialize parser instances for each structure type."""
        return {
            'Structure1': Structure1Parser(),
            'Structure2': Structure2Parser(),
            'Structure3': Structure3Parser(),
            'Structure4': Structure4Parser(),
            # 'Structure5': Structure5Parser(),
        }
 
    def process_all_structures(self) -> List[Dict[str, Any]]:
        """Process all Excel files from all structure directories."""
        all_entities = []
 
        for structure_name in self.config.structure_dirs:
            structure_dir = self.config.input_base_dir / 'emsl_data_from_onedrive' / structure_name # uses pathlib
 
            if not structure_dir.exists():
                self.logger.warning(f"Structure directory not found: {structure_dir}")
                continue
 
            self.logger.info(f"Processing {structure_name} directory...")
 
            try:
                entities = self._process_structure_directory(structure_name, structure_dir)
                all_entities.extend(entities)
                self.logger.info(f"Successfully processed {len(entities)} entities from {structure_name}")
 
            except Exception as e:
                self.logger.error(f"Failed to process {structure_name}: {e}")
                self.logger.debug(traceback.format_exc())
                continue
 
        return all_entities
 
    def _process_structure_directory(self, structure_name: str, structure_dir: Path) -> List[Dict[str, Any]]:
        """Process all Excel files in a specific structure directory."""
        parser = self.parsers[structure_name]
        entities = []
 
        # Find all Excel files
        excel_files = list(structure_dir.glob('*.xlsx')) + list(structure_dir.glob('*.xls')) + list(structure_dir.glob('*.xlsm'))
 
        if not excel_files:
            self.logger.warning(f"No Excel files found in {structure_dir}")
            return entities
 
        self.logger.info(f"Found {len(excel_files)} Excel files in {structure_name}")
 
        for excel_file in excel_files:
            try:
                self.logger.debug(f"Processing file: {excel_file}")
                file_entities = parser.parse_file(excel_file)
 
                # Transform each entity to Bertron schema format
                for raw_entity in file_entities:
                    try:
                       
                        bertron_entity = self.transformer.transform_to_bertron_schema(
                            raw_entity, excel_file, structure_name
                        )

                        if bertron_entity is None:
                            continue  # Skip this entity
                       
                        if self.validator:
                            validation_result = self.validator.validate_entity(bertron_entity)
                            if not validation_result.is_valid:
                                self.logger.warning(f"Validation failed for entity {bertron_entity.get('id')}: {validation_result.errors}")
                                continue
                       
                        entities.append(bertron_entity)
 
                    except Exception as e:
                        self.logger.error(f"Failed to transform entity from {excel_file}: {e}")
                        continue
 
            except Exception as e:
                self.logger.error(f"Failed to process file {excel_file}: {e}")
                continue
 
        return entities
 
    def save_results(self, entities: List[Dict[str, Any]]) -> None:
        """Save processed entities to output file."""
        if not entities:
            self.logger.warning("No entities to save")
            return
 
        self.config.output_file.parent.mkdir(parents=True, exist_ok=True)
 
        if self.config.append_mode and self.config.output_file.exists():
            # Load existing data and append
            with open(self.config.output_file, 'r') as f:
                existing_data = json.load(f)
            existing_data.extend(entities)
            entities = existing_data
 
        with open(self.config.output_file, 'w', encoding='utf-8') as f:
            json.dump(entities, f, indent=2, ensure_ascii=False)
 
        self.logger.info(f"Saved {len(entities)} entities to {self.config.output_file}")
 
 
class BaseStructureParser(ABC):
    """Abstract base class for Excel structure parsers."""
 
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
 
    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """Return structure-specific configuration."""
        pass
 
    @abstractmethod
    def parse_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse an Excel file and return list of raw entity dictionaries."""
        pass
 
    def _read_excel_tab(self, file_path: Path, sheet_name: str, header_row: int = 0, data_start_row: int = 1) -> pd.DataFrame:
        """Common method to read Excel tabs with error handling."""
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
            # Skip to data start row if different from header
            if data_start_row > header_row + 1:
                df = df.iloc[data_start_row - header_row - 1:]
            return df
        except Exception as e:
            self.logger.error(f"Failed to read sheet '{sheet_name}' from {file_path}: {e}")
            raise
 
 
class DataTransformer:
    """Handles transformation of raw Excel data to Bertron schema format."""
 
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.ontology_mapping = self._load_ontology_mapping()
        self.unit_mapping = self._load_unit_mapping()
 
    def _load_ontology_mapping(self) -> Dict[str, Dict[str, str]]:
        """Load ontology mapping for common EMSL attributes."""
        # Common MIXS and other ontology mappings for EMSL attributes
        return {
            'altitude': {'id': 'MIXS:0000094', 'unit': 'UO:0000008'},  # meter
            'elevation': {'id': 'MIXS:0000093', 'unit': 'UO:0000009'},  # centimeter
            'lat_deg': {'id': 'MIXS:0000009'},  # latitude
            'lon_deg': {'id': 'MIXS:0000010'},  # longitude
            'temperature': {'id': 'MIXS:0000113', 'unit': 'UO:0000027'},  # degree Celsius
            'ph': {'id': 'MIXS:0001001'},  # pH
            'depth': {'id': 'MIXS:0000018', 'unit': 'UO:0000008'},  # meter
            'salinity': {'id': 'MIXS:0000183'},  # salinity
            'collection_date': {'id': 'MIXS:0000011'},  # collection date
            'sample_type': {'id': 'MIXS:0000031'},  # sample type
            'growth_facil': {'id': 'MIXS:0001056'},  # growth facility
            'host_common_name': {'id': 'MIXS:0000248'},  # host common name
            'host_taxid': {'id': 'MIXS:0000250'},  # host taxon id
            'plant_struc': {'id': 'MIXS:0001055'},  # plant structure
        }
 
    def _load_unit_mapping(self) -> Dict[str, str]:
        """Load unit mapping to UCUM/UO ontology."""
        return {
            'degree celsius': 'UO:0000027',
            '°c': 'UO:0000027',
            'celsius': 'UO:0000027',
            'meter': 'UO:0000008',
            'm': 'UO:0000008',
            'centimeter': 'UO:0000009',
            'cm': 'UO:0000009',
            'millimeter': 'UO:0000016',
            'mm': 'UO:0000016',
            'gram': 'UO:0000021',
            'g': 'UO:0000021',
            'milligram': 'UO:0000022',
            'mg': 'UO:0000022',
            'kilogram': 'UO:0000009',
            'kg': 'UO:0000009',
            'liter': 'UO:0000099',
            'l': 'UO:0000099',
            'milliliter': 'UO:0000098',
            'ml': 'UO:0000098',
            'percent': 'UO:0000187',
            '%': 'UO:0000187',
            'year': 'UO:0000036',
            'day': 'UO:0000033',
            'hour': 'UO:0000032',
            'minute': 'UO:0000031',
            'second': 'UO:0000010',
        }
 
    def transform_to_bertron_schema(self, raw_entity: Dict[str, Any], source_file: Path, structure_type: str) -> Dict[str, Any]:
        """Transform raw entity data to Bertron schema format."""
        # Generate unique ID
        entity_id = self._generate_entity_id(raw_entity)
 
        # Build base entity structure
        entity = {
            "ber_data_source": "EMSL",
            "entity_type": ["sample"],
            "id": entity_id,
            "name": self._extract_name(raw_entity),
            "description": f"EMSL sample from {source_file.name}:{raw_entity.get('_source_sheet', 'Unknown')}",
            "uri": f"https://sc-data.emsl.pnnl.gov/emsl?projectId={raw_entity.get('project_id', 'multi_project')}",
            "properties": []
        }
 
        # Add coordinates if available
        coordinates = self._extract_coordinates(raw_entity)
        if coordinates:
            entity["coordinates"] = coordinates
 
        # Transform all attributes to properties
        properties = self._transform_attributes_to_properties(raw_entity)

        # Filter out entities with no properties or auto-generated names
        if not properties or (entity.get("name", "").startswith("unknown_sample_")):
            return None  # Don't create entity

        entity["properties"] = properties
 
        return entity
 
    def _generate_entity_id(self, raw_entity: Dict[str, Any]) -> str:
        """Generate a unique entity ID."""
        # Try to use existing UUID/GUID if available
        for id_field in ['uuid', 'guid', 'unique_ID', 'id']:
            if id_field in raw_entity and raw_entity[id_field]:
                value = str(raw_entity[id_field])
                if value.startswith('UUID:'):
                    return f"EMSL:{value}"
                elif len(value) > 8:  # Likely a UUID or GUID
                    return f"EMSL:UUID:{value}"
 
        # Generate new UUID
        return f"EMSL:UUID:{uuid4()}"
 
    def _extract_name(self, raw_entity: Dict[str, Any]) -> str:
        """Extract entity name from raw data."""
        # Try common name fields in order of preference
        for name_field in ['sample_name', 'name', 'source_mat_ID', 'sample_id', 'unique_ID', 'id']:
            if name_field in raw_entity and raw_entity[name_field]:
                return str(raw_entity[name_field])
 
        # Generate fallback name using project ID if available
        project_id = raw_entity.get('project_id', raw_entity.get('project_name', 'unknown'))
        return f"{project_id}_sample_{str(uuid4())[:8]}"
 
    def _extract_coordinates(self, raw_entity: Dict[str, Any]) -> Optional[Dict[str, float]]:
        """Extract geographic coordinates from raw data."""
        lat_fields = ['latitude', 'lat', 'lat_deg', 'lat_start', 'geo_loc_lat']
        lon_fields = ['longitude', 'lon', 'lng', 'long', 'lon_deg', 'lon_start', 'geo_loc_lon']
 
        latitude = None
        longitude = None
 
        # Try to find latitude
        for field in lat_fields:
            if field in raw_entity and raw_entity[field] is not None:
                try:
                    lat_val = self._parse_coordinate(raw_entity[field])
                    if lat_val is not None and -90 <= lat_val <= 90:
                        latitude = lat_val
                        break
                except (ValueError, TypeError):
                    continue
 
        # Try to find longitude
        for field in lon_fields:
            if field in raw_entity and raw_entity[field] is not None:
                try:
                    lon_val = self._parse_coordinate(raw_entity[field])
                    if lon_val is not None and -180 <= lon_val <= 180:
                        longitude = lon_val
                        break
                except (ValueError, TypeError):
                    continue
 
        if latitude is not None and longitude is not None:
            return {"latitude": latitude, "longitude": longitude}
 
        return None
 
    def _parse_coordinate(self, coord_value: Any) -> Optional[float]:
        """Parse coordinate value handling various formats."""
        if pd.isna(coord_value):
            return None
 
        coord_str = str(coord_value).strip()
 
        # Handle common coordinate formats
        # Decimal degrees: 45.123 or -122.456
        try:
            return float(coord_str)
        except ValueError:
            pass
 
        # Degrees, minutes, seconds: 45°30'15"N or 122°15'30"W
        import re
        dms_pattern = r"(\d+)°\s*(\d+)'\s*(\d+(?:\.\d+)?)\"\s*([NSEW]?)"
        match = re.search(dms_pattern, coord_str)
        if match:
            degrees, minutes, seconds, direction = match.groups()
            decimal = float(degrees) + float(minutes)/60 + float(seconds)/3600
            if direction.upper() in ['S', 'W']:
                decimal = -decimal
            return decimal
 
        return None
 
    def _transform_attributes_to_properties(self, raw_entity: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Transform all entity attributes to Bertron property format."""
        properties = []
 
        # Skip internal fields and already processed fields
        skip_fields = {
            '_source_sheet', '_row_number', 'uuid', 'guid', 'sample_name', 'name',
            'source_mat_ID', 'sample_id', 'unique_ID', 'id', 'latitude', 'longitude',
            'lat', 'lon', 'lat_deg', 'lon_deg', 'lat_start', 'lon_start',
            'geo_loc_lat', 'geo_loc_lon', 'project_id', 'project_name'
        }
 
        for key, value in raw_entity.items():
            if key in skip_fields or value is None or value == '':
                continue
           
            # Skip N/A values
            # if str(value).upper() in ['N/A', 'NA', 'NULL', 'NONE', 'NaN', 'NAN', 'SELECT VALUE']:
            #     continue
 
            # Normalize the value first
            value_str = str(value).strip().lower()

            # Then do all comparisons on the normalized version
            if (value_str in ['n/a', 'na', 'null', 'none', 'nan'] or 
                value_str.startswith('select ') or 
                'select' in value_str and ('value' in value_str or 'type' in value_str)):
                continue
            
            # Create base property structure
            property_dict = {
                "attribute": {
                    "label": key
                },
                "raw_value": str(value)
            }
 
            # Add ontology mapping if available
            ontology_info = self.ontology_mapping.get(key.lower())
            if ontology_info and 'id' in ontology_info:
                property_dict["attribute"]["id"] = ontology_info["id"]
 
            # Try to parse numeric values and units
            numeric_info = self._parse_numeric_with_unit(value)
            if numeric_info:
                if 'numeric_value' in numeric_info:
                    property_dict["numeric_value"] = numeric_info["numeric_value"]
                if 'unit' in numeric_info:
                    property_dict["unit"] = numeric_info["unit"]
                if 'minimum_numeric_value' in numeric_info:
                    property_dict["minimum_numeric_value"] = numeric_info["minimum_numeric_value"]
                if 'maximum_numeric_value' in numeric_info:
                    property_dict["maximum_numeric_value"] = numeric_info["maximum_numeric_value"]
 
            properties.append(property_dict)
 
        return properties
 
    def _parse_numeric_with_unit(self, value: Any) -> Optional[Dict[str, Any]]:
        """Parse numeric values with units, handling ranges."""
        if pd.isna(value):
            return None
 
        value_str = str(value).strip()
 
        # Try simple numeric value first
        try:
            numeric_val = float(value_str)
            return {"numeric_value": numeric_val}
        except ValueError:
            pass
 
        # Parse ranges like "2-4", "2.5 - 3.7", "10 to 20"
        import re
        range_patterns = [
            r"(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)",  # 2-4, 2.5-3.7
            r"(\d+\.?\d*)\s+to\s+(\d+\.?\d*)",    # 2 to 4
            r"(\d+\.?\d*)\s*±\s*(\d+\.?\d*)",     # 2±0.5
        ]
 
        for pattern in range_patterns:
            match = re.search(pattern, value_str, re.IGNORECASE)
            if match:
                min_val, max_val = float(match.group(1)), float(match.group(2))
                if "±" in value_str:
                    # For ± notation, calculate actual min/max
                    center = min_val
                    error = max_val
                    result = {
                        "numeric_value": center,
                        "minimum_numeric_value": center - error,
                        "maximum_numeric_value": center + error
                    }
                else:
                    result = {
                        "minimum_numeric_value": min(min_val, max_val),
                        "maximum_numeric_value": max(min_val, max_val),
                        "numeric_value": (min_val + max_val) / 2  # Use midpoint as primary value
                    }
 
                # Try to extract unit
                unit = self._extract_unit(value_str)
                if unit:
                    result["unit"] = unit
 
                return result
 
        # Parse value with unit like "25°C", "2.5 mg", "100 ml"
        num_unit_pattern = r"(\d+\.?\d*)\s*([a-zA-Z°%]+)"
        match = re.search(num_unit_pattern, value_str)
        if match:
            numeric_val = float(match.group(1))
            unit_str = match.group(2)
 
            result = {"numeric_value": numeric_val}
 
            # Map unit to ontology
            unit_id = self._map_unit_to_ontology(unit_str)
            if unit_id:
                result["unit"] = unit_id
 
            return result
 
        return None
 
    def _extract_unit(self, value_str: str) -> Optional[str]:
        """Extract unit from a value string."""
        import re
        # Extract unit patterns
        unit_pattern = r"\d+\.?\d*\s*([a-zA-Z°%]+)"
        match = re.search(unit_pattern, value_str)
        if match:
            unit_str = match.group(1)
            return self._map_unit_to_ontology(unit_str)
        return None
 
    def _map_unit_to_ontology(self, unit_str: str) -> Optional[str]:
        """Map unit string to ontology identifier."""
        unit_lower = unit_str.lower().strip()
        return self.unit_mapping.get(unit_lower)
 
 
@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)
 
 
class SchemaValidator:
    """Validates entities against Bertron schema requirements."""
 
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._is_schema_present = self._validate_schema_setup()
        self.logger.info(f"Schema validation is using linkml schema files: {self._is_schema_present}")
 
        if self._is_schema_present:
            logging.getLogger('linkml_runtime.utils.schemaview').setLevel(logging.WARNING)
 
    def _validate_schema_setup(self):
        """Validate that schema files are available."""
        files = {
            'schema':  'bertron_schema.yaml',
            'types': 'bertron_types.yaml'
        }
 
        missing = [name for name, path in files.items() if not os.path.exists(path)]
        if missing:
            self.logger.warning(f"Missing schema files: {missing}")
       
        return not missing
 
    def validate_entity(self, entity: Dict[str, Any]) -> ValidationResult:
        """Validate an entity against Bertron schema requirements."""
        errors = []
 
        if 'ber_data_source' in entity and entity['ber_data_source'] != 'EMSL':
            errors.append("ber_data_source must be 'EMSL'")
       
        if self._is_schema_present:
            report = validate(entity, os.path.join("bertron_schema.yaml"), "Entity") # validate method from linkml module
 
            if report.results:
                for result in report.results:
                    errors.append(result.message)
        else:
            # Type checks
            if 'entity_type' in entity and not isinstance(entity['entity_type'], list):
                errors.append("entity_type must be a list")
 
            # Properties validation
            if 'properties' in entity:
                if not isinstance(entity['properties'], list):
                    errors.append("properties must be a list")
                else:
                    for i, prop in enumerate(entity['properties']):
                        if not isinstance(prop, dict):
                            errors.append(f"Property {i} must be a dictionary")
                            continue
                        if 'attribute' not in prop:
                            errors.append(f"Property {i} missing 'attribute' field")
                        if 'raw_value' not in prop:
                            errors.append(f"Property {i} missing 'raw_value' field")
 
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
 
 
# Structure-specific parser implementations
class Structure1Parser(BaseStructureParser):
    """
    Structure 1: Standard Metadata Tab
    - Excel Tab: "Metadata"
    - Header Row: Row 1 contains attribute labels
    - Data Start: Row 5
    - Special Rules: Rows starting with "other" or "treatment" should use term in row 2 for attribute label
    """
 
    def get_config(self):
        return {
            "sheet": "Metadata",
            "header_row": 0,
            "data_start": 4,
            "special_handling": ["other", "treatment"]
        }
 
    def parse_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Structure1 Excel file."""
        try:
            df = self._read_excel_tab(file_path, "Metadata", header_row=0, data_start_row=4)
            entities = []
 
            for idx, row in df.iterrows():
                if row.isna().all():  # Skip completely empty rows
                    continue
 
                entity = {"_source_sheet": "Metadata", "_row_number": idx + 5}
 
                for col in df.columns:
                    value = row[col]
                    if pd.isna(value) or value == '':
                        continue
 
                    # Handle special columns that start with "other" or "treatment"
                    col_name = str(col).lower()
                    if col_name.startswith(('other', 'treatment')):
                        # Use the term in row 2 (index 1) as the attribute label
                        try:
                            alt_df = pd.read_excel(file_path, sheet_name="Metadata", nrows=3, header=None)
                            if len(alt_df) > 1 and col in alt_df.columns:
                                label = alt_df.iloc[1, alt_df.columns.get_loc(col)]
                                if pd.notna(label):
                                    col = str(label)
                        except Exception:
                            pass  # Keep original column name if can't get alternative
 
                    entity[col] = value
 
                # Extract project ID
                if 'project_name' in entity:
                    entity['project_id'] = entity['project_name']
                elif 'project_id' in entity:
                    entity['project_id'] = entity['project_id']
 
                entities.append(entity)
 
            self.logger.info(f"Parsed {len(entities)} entities from Structure1 file: {file_path}")
            return entities
 
        except Exception as e:
            self.logger.error(f"Failed to parse Structure1 file {file_path}: {e}")
            raise
 
 
class Structure2Parser(BaseStructureParser):
    """
    Structure 2: Samples Tab with GUID Handling
    - Excel Tab: "Samples"
    - Header Row: Row 1 contains attribute labels
    - Data Start: Row 5
    - ID Handling: Merge "guid_source" and "unique_ID" columns for the "id" slot
    - Sample Type: Located in "Sample Submission" tab, to the right of "Sample Type/Species" cell
    - Data Cleaning: Skip rows with "N/A" or "NA" values
    """
 
    def get_config(self):
        return {
            "sheet": "Samples",
            "header_row": 0,
            "data_start": 4,
            "secondary_sheet": "Sample Submission",
            "guid_merge": True
        }
 
    def parse_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Structure2 Excel file."""
        try:
            # Read main Samples sheet
            df = self._read_excel_tab(file_path, "Samples", header_row=0, data_start_row=4)
 
            # Try to read sample type from Sample Submission sheet
            sample_type = None
            try:
                sub_df = pd.read_excel(file_path, sheet_name="Sample Submission")
                # Look for "Sample Type/Species" cell and get value to the right
                for idx, row in sub_df.iterrows():
                    for col_idx, cell_value in enumerate(row):
                        if pd.notna(cell_value) and "Sample Type/Species" in str(cell_value):
                            if col_idx + 1 < len(row):
                                sample_type = row.iloc[col_idx + 1]
                                break
                    if sample_type:
                        break
            except Exception as e:
                self.logger.warning(f"Could not read Sample Submission sheet from {file_path}: {e}")
 
            entities = []
 
            for idx, row in df.iterrows():
                if row.isna().all():  # Skip completely empty rows
                    continue
 
                # Skip rows with N/A or NA values
                has_na = any(str(val).upper() in ['N/A', 'NA'] for val in row.values if pd.notna(val))
                if has_na:
                    continue
 
                entity = {"_source_sheet": "Samples", "_row_number": idx + 5}
 
                # Handle GUID merging
                guid_source = row.get('guid_source')
                unique_id = row.get('unique_ID')
 
                if pd.notna(guid_source) and pd.notna(unique_id):
                    entity['id'] = f"{guid_source}:{unique_id}"
                elif pd.notna(unique_id):
                    entity['id'] = str(unique_id)
 
                # Add sample type if found
                if sample_type:
                    entity['sample_type'] = sample_type
 
                for col in df.columns:
                    value = row[col]
                    if pd.isna(value) or value == '':
                        continue
                    entity[col] = value
 
                entities.append(entity)
 
            self.logger.info(f"Parsed {len(entities)} entities from Structure2 file: {file_path}")
            return entities
 
        except Exception as e:
            self.logger.error(f"Failed to parse Structure2 file {file_path}: {e}")
            raise
 
 
class Structure3Parser(BaseStructureParser):
    """
    Structure 3: Variable Column Processing
    - Excel Tab: "Metadata"
    - Header Row: Row 1 contains attribute labels
    - Data Start: Row 4
    - Special Rules: Columns starting with "variable" should use information from "label" rows
    - Variable columns have corresponding "raw_value" data in the column to the right
    """
 
    def get_config(self):
        return {
            "sheet": "Metadata",
            "header_row": 0,
            "data_start": 3,
            "variable_handling": True
        }
 
    def parse_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Structure3 Excel file."""
        try:
            df = self._read_excel_tab(file_path, "Metadata", header_row=0, data_start_row=3)
 
            # Get the label row (row 1, 0-indexed) for variable columns
            label_df = pd.read_excel(file_path, sheet_name="Metadata", nrows=2, header=None)
 
            entities = []
 
            for idx, row in df.iterrows():
                if row.isna().all():  # Skip completely empty rows
                    continue
 
                entity = {"_source_sheet": "Metadata", "_row_number": idx + 4}
 
                col_names = list(df.columns)
                for i, col in enumerate(col_names):
                    value = row[col]
                    if pd.isna(value) or value == '':
                        continue
 
                    col_name = str(col).lower()
                    if col_name.startswith('variable'):
                        # Use label from row 1 for variable columns
                        try:
                            if len(label_df) > 1 and i < len(label_df.columns):
                                label = label_df.iloc[1, i]  # Row 1 (0-indexed)
                                if pd.notna(label):
                                    col = str(label)
                        except Exception:
                            pass  # Keep original column name if can't get label
 
                        # Check if there's a corresponding raw_value column to the right
                        if i + 1 < len(col_names):
                            raw_value = row.iloc[i + 1]
                            if pd.notna(raw_value):
                                entity[f"{col}_raw_value"] = raw_value
 
                    entity[col] = value
 
                # Extract project ID
                if 'project_name' in entity:
                    entity['project_id'] = entity['project_name']
 
                entities.append(entity)
 
            self.logger.info(f"Parsed {len(entities)} entities from Structure3 file: {file_path}")
            return entities
 
        except Exception as e:
            self.logger.error(f"Failed to parse Structure3 file {file_path}: {e}")
            raise
 
 
class Structure4Parser(BaseStructureParser):
    """
    Structure 4: Experiment Metadata
    - Excel Tab: "Experiment_metadata"
    - Header Row: Row 1 contains attribute labels
    - Data Start: Row 2 (earliest start row)
    - "Globally Unique Persistent Identifier" should populate the "sample_name" attribute
    - GUID may not always be available
    """
 
    def get_config(self):
        return {
            "sheet": "Experiment_metadata",
            "header_row": 0,
            "data_start": 1,
            "guid_field": "Globally Unique Persistent Identifier"
        }
 
    def parse_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Structure4 Excel file."""
        try:
            df = self._read_excel_tab(file_path, "Experiment_metadata", header_row=0, data_start_row=1)
            entities = []
 
            for idx, row in df.iterrows():
                if row.isna().all():  # Skip completely empty rows
                    continue
 
                entity = {"_source_sheet": "Experiment_metadata", "_row_number": idx + 2}
 
                for col in df.columns:
                    value = row[col]
                    if pd.isna(value) or value == '':
                        continue
 
                    # Handle GUID field
                    if "Globally Unique Persistent Identifier" in str(col):
                        entity['sample_name'] = value
                        entity['guid'] = value
                    else:
                        entity[col] = value
 
                # Extract project ID
                if 'project_name' in entity:
                    entity['project_id'] = entity['project_name']
 
                entities.append(entity)
 
            self.logger.info(f"Parsed {len(entities)} entities from Structure4 file: {file_path}")
            return entities
 
        except Exception as e:
            self.logger.error(f"Failed to parse Structure4 file {file_path}: {e}")
            raise
 
 
class Structure5Parser(BaseStructureParser):
    """
    Structure 5: Uncertain Processing
    - Status: Data "Submitted via SC" (Sample Collection system)
    - Question: Requires determination if "boutique ETL" process is needed
    - This structure may require custom processing
    """
 
    def get_config(self):
        return {
            "sheet": "Unknown",
            "header_row": 0,
            "data_start": 0,
            "status": "investigation_needed"
        }
 
    def parse_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Structure5 Excel file - placeholder implementation."""
        self.logger.warning(f"Structure5 processing not yet implemented for {file_path}")
        self.logger.info("Structure5 files were submitted via SC and may need boutique ETL")
 
        # For now, return empty list until processing approach is determined
        return []
 
 
def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Process EMSL Excel files to Bertron schema JSON')
    parser.add_argument('--input-dir', type=Path, default=Path('.'), help='Base input directory')
    parser.add_argument('--output-file', type=Path, default=Path('ingest/emsl/emsl_00001.json'), help='Output JSON file')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO', help='Logging level')
    parser.add_argument('--no-validation', action='store_true', help='Skip schema validation')
    parser.add_argument('--append', action='store_true', help='Append to existing output file')
    parser.add_argument('--max-workers', type=int, default=4, help='Maximum number of worker threads')
 
    args = parser.parse_args()
 
    config = ProcessingConfig(
        input_base_dir=args.input_dir,
        output_file=args.output_file,
        log_level=args.log_level,
        validate_schema=not args.no_validation,
        append_mode=args.append,
        max_workers=args.max_workers
    )
 
    processor = EMSLDataProcessor(config)
 
    try:
        entities = processor.process_all_structures()
        processor.save_results(entities)
        print(f"Successfully processed {len(entities)} entities")
 
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Processing failed: {e}")
        sys.exit(1)
 
 
if __name__ == '__main__':
    main()