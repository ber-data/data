#!/usr/bin/env python3
"""
Script to fetch all public datasets from ESS-DIVE API and create Bertron
entities.

This script iterates through all public datasets in the ESS-DIVE API and
creates Bertron entities using the Pydantic models from the bertron-schema
package.

For datasets with spatial coverage (site entities):
- "ESS-DIVE" -> ber_data_source
- dataset.spatialCoverage.geo (center point) -> coordinates
- "site" -> entity_type
- dataset.name -> name
- id -> id
- dataset.spatialCoverage.description -> description
- dataset.@id -> alt_ids
- dataset.alternateName -> alt_names
- "https://data.ess-dive.lbl.gov/view/<id>" -> uri

For datasets without spatial coverage (dataset entities):
- "ESS-DIVE" -> ber_data_source
- "dataset" -> entity_type
- dataset.name -> name
- id#coordinates.latitude,coordinates.longitude_<sequence_number> -> id
- dataset.description -> description
- dataset.@id -> alt_ids
- dataset.alternateName -> alt_names
- "https://data.ess-dive.lbl.gov/view/<id>" -> uri

Requirements:
- bertron-schema package with Pydantic models
- requests library for API calls
- ESS_DIVE_AUTH_TOKEN environment variable or --token argument
"""

import os
import sys
import json
import requests
import time
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import quote

# Import schema validator for validation
from schema_validator import SchemaValidator

# Import Pydantic models from bertron-schema
try:
    from schema.datamodel.bertron_schema_pydantic import (
        Entity,
        Coordinates,
        BERSourceType,
        EntityType,
    )
except ImportError:
    print("Warning: Could not import bertron-schema Pydantic models.")
    print("Please install bertron-schema: pip install -r requirements.txt")
    sys.exit(1)


class EssDiveEntityFetcher:
    """Fetches and transforms ESS-DIVE datasets into Bertron entities."""

    def __init__(
        self, auth_token: Optional[str] = None, max_file_size_mb: float = 25.0
    ):
        """Initialize the fetcher with authentication token and file size limit."""
        self.base_url = "https://api.ess-dive.lbl.gov"
        self.auth_token = auth_token or os.getenv("ESS_DIVE_AUTH_TOKEN")
        self.session = requests.Session()
        self.max_file_size_bytes = int(max_file_size_mb * 1024 * 1024)

        if self.auth_token:
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.auth_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
            )
        else:
            print("Warning: No authentication token provided.")
            self.session.headers.update(
                {"Accept": "application/json", "Content-Type": "application/json"}
            )

    def process_datasets_by_page(
        self,
        page_size: int = 100,
        max_pages: Optional[int] = None,
        process_callback: callable = None,
    ) -> Tuple[int, int]:
        """
        Process public datasets from ESS-DIVE API page by page without loading all into memory.

        Args:
            page_size: Number of datasets to fetch per request (max 100)
            max_pages: Maximum number of pages to fetch (for testing/dry-run)
            process_callback: Function to call for each dataset, receives (dataset, page_info)

        Returns:
            Tuple of (total_datasets_processed, total_entities_created)
        """
        row_start = 1
        pages_fetched = 0
        total_datasets_processed = 0
        total_entities_created = 0
        total_datasets = None

        if max_pages:
            print(f"Dry run mode: processing maximum {max_pages} page(s)")

        while True:
            try:
                # Check if we've reached the page limit
                if max_pages and pages_fetched >= max_pages:
                    print(f"Reached dry-run limit of {max_pages} page(s), stopping.")
                    break

                # Fetch datasets with public filter
                params = {
                    "isPublic": True,
                    "pageSize": min(page_size, 100),  # API max is 100
                    "rowStart": row_start,
                }

                print(
                    f"Fetching datasets {row_start} to "
                    f"{row_start + page_size - 1}..."
                    + (f" (page {pages_fetched + 1}/{max_pages})" if max_pages else "")
                )

                response = self.session.get(
                    f"{self.base_url}/packages", params=params, timeout=30
                )
                response.raise_for_status()

                data = response.json()

                # Extract results
                results = data.get("result", [])
                if not results:
                    print("No more datasets found.")
                    break

                # Get total count on first page
                if total_datasets is None:
                    total_datasets = data.get("total", 0)
                    print(f"Total datasets available: {total_datasets}")

                # Process each dataset in this page
                for i, dataset in enumerate(results):
                    dataset_num = total_datasets_processed + i + 1
                    print(
                        f"Processing dataset {dataset_num}/{total_datasets}: {dataset.get('id', 'Unknown ID')}"
                    )

                    try:
                        if process_callback:
                            entities_created = process_callback(
                                dataset,
                                {
                                    "page": pages_fetched + 1,
                                    "dataset_in_page": i + 1,
                                    "total_processed": dataset_num,
                                    "total_available": total_datasets,
                                },
                            )
                            total_entities_created += entities_created
                    except Exception as e:
                        print(
                            f"Error processing dataset {dataset.get('id', 'Unknown')}: {e}"
                        )
                        continue

                pages_fetched += 1
                total_datasets_processed += len(results)

                print(
                    f"Processed {total_datasets_processed} of {total_datasets} total datasets"
                )

                # Check if we've processed all datasets
                if total_datasets_processed >= total_datasets:
                    break

                # Move to next page
                row_start += len(results)

                # Rate limiting - be nice to the API
                time.sleep(0.5)

            except requests.exceptions.RequestException as e:
                print(f"Error fetching datasets: {e}")
                break
            except KeyError as e:
                print(f"Unexpected response format: {e}")
                break

        print(f"Total datasets processed: {total_datasets_processed}")
        print(f"Total entities created: {total_entities_created}")
        if max_pages:
            print(f"Dry run completed after {pages_fetched} page(s)")

        return total_datasets_processed, total_entities_created

    def get_dataset_metadata(self, dataset_version: str) -> Optional[Dict[str, Any]]:
        """
        Fetch detailed metadata for a specific dataset.

        Args:
            dataset_id: The ESS-DIVE dataset identifier

        Returns:
            Full dataset metadata or None if error
        """
        try:
            # URL encode the identifier to handle DOIs and special characters
            encoded_id = quote(dataset_version, safe="")

            response = self.session.get(
                f"{self.base_url}/packages/{encoded_id}", timeout=30
            )
            response.raise_for_status()

            data = response.json()
            return data.get("dataset")

        except requests.exceptions.RequestException as e:
            print(f"Error fetching metadata for {dataset_version}: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for {dataset_version}: {e}")
            return None

    def calculate_center_point(
        self, geo_coords: List[Dict[str, Any]]
    ) -> Optional[Tuple[float, float]]:
        """
        Calculate the center point from a list of geo coordinates.

        Args:
            geo_coords: List of coordinate dictionaries with latitude/longitude

        Returns:
            Tuple of (latitude, longitude) for center point or None
        """
        if not geo_coords:
            return None

        # Extract valid coordinates
        valid_coords = []
        for coord in geo_coords:
            lat = coord.get("latitude")
            lon = coord.get("longitude")
            if lat is not None and lon is not None:
                try:
                    valid_coords.append((float(lat), float(lon)))
                except (ValueError, TypeError):
                    continue

        if not valid_coords:
            return None

        # Calculate center point
        total_lat = sum(coord[0] for coord in valid_coords)
        total_lon = sum(coord[1] for coord in valid_coords)
        count = len(valid_coords)

        center_lat = total_lat / count
        center_lon = total_lon / count

        return (center_lat, center_lon)

    def _extract_description(
        self, dataset: Dict[str, Any], spatial_coverage: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Extract description from dataset or spatial coverage."""
        description = None

        # For site entities, prefer spatial coverage description
        if spatial_coverage and spatial_coverage.get("description"):
            description = spatial_coverage["description"]
        elif dataset.get("description"):
            # Fallback to dataset description or use for dataset entities
            desc = dataset["description"]
            if isinstance(desc, list):
                description = " ".join(desc)
            else:
                description = desc

        return description

    def _extract_alt_ids(self, dataset: Dict[str, Any]) -> Optional[List[str]]:
        """Extract alternative IDs from dataset."""
        alt_ids = dataset.get("alternateName", [])

        # Add dataset@id to the beginning of alt_ids
        if dataset.get("@id"):
            alt_ids.insert(0, dataset.get("@id"))

        return alt_ids if alt_ids else None

    def _create_uri(self, dataset_version: str) -> str:
        """Create URI from dataset version."""
        return f"https://data.ess-dive.lbl.gov/view/{dataset_version}"

    def _create_base_entity(
        self,
        dataset_version: str,
        dataset: Dict[str, Any],
        entity_type: EntityType,
        entity_id: str,
        coordinates: Optional[Coordinates] = None,
        spatial_coverage: Optional[Dict[str, Any]] = None,
    ) -> Entity:
        """Create a base Entity with common fields."""
        return Entity(
            ber_data_source=BERSourceType.ESS_DIVE,
            entity_type=[entity_type],
            name=dataset.get("name"),
            id=entity_id,
            description=self._extract_description(dataset, spatial_coverage),
            coordinates=coordinates,
            alt_ids=self._extract_alt_ids(dataset),
            uri=self._create_uri(dataset_version),
        )

    def create_site_entity(
        self,
        dataset_version: str,
        dataset: Dict[str, Any],
        spatial_coverage: Dict[str, Any],
        sequence_number: Optional[int] = None,
    ) -> Entity:
        """
        Create a Bertron site entity from a dataset with spatial coverage.

        Args:
            dataset_version: The dataset version identifier
            dataset: The dataset metadata
            spatial_coverage: The spatial coverage information
            sequence_number: Optional sequence number for multiple sites

        Returns:
            Bertron site entity using Pydantic model
        """
        # Calculate center coordinates from spatial coverage
        geo_data = spatial_coverage.get("geo", [])
        if not isinstance(geo_data, list):
            geo_data = [geo_data]

        center_point = self.calculate_center_point(geo_data)
        coordinates = None
        if center_point:
            coordinates = Coordinates(
                latitude=center_point[0], longitude=center_point[1]
            )

        # Create unique ID for site entity using coordinates and optional sequence number
        # Create entity ID based on whether coordinates are available
        if coordinates:
            if sequence_number is not None:
                entity_id = f"{dataset_version}#{coordinates.latitude},{coordinates.longitude}_{sequence_number}"
            else:
                entity_id = (
                    f"{dataset_version}#{coordinates.latitude},{coordinates.longitude}"
                )
        else:
            entity_id = dataset_version

        return self._create_base_entity(
            dataset_version=dataset_version,
            dataset=dataset,
            entity_type=EntityType.site,
            entity_id=entity_id,
            coordinates=coordinates,
            spatial_coverage=spatial_coverage,
        )

    def create_dataset_entity(
        self, dataset_version: str, dataset: Dict[str, Any]
    ) -> Entity:
        """
        Create a Bertron dataset entity from a dataset without spatial coverage.

        Args:
            dataset_version: The dataset version identifier
            dataset: The dataset metadata

        Returns:
            Bertron dataset entity using Pydantic model
        """
        return self._create_base_entity(
            dataset_version=dataset_version,
            dataset=dataset,
            entity_type=EntityType.dataset,
            entity_id=dataset_version,
        )

    def process_dataset(self, dataset_summary: Dict[str, Any]) -> List[Entity]:
        """
        Process a single dataset and create appropriate Bertron entities.

        Args:
            dataset_summary: Summary dataset information from list API

        Returns:
            List of Bertron entities (could be multiple sites from one dataset)
        """
        dataset_version = dataset_summary.get("id")
        if not dataset_version:
            print("Warning: Dataset missing ID, skipping")
            return []

        # Get full metadata
        full_metadata = self.get_dataset_metadata(dataset_version)
        if not full_metadata:
            print(f"Warning: Could not fetch metadata for {dataset_version}, skipping")
            return []

        entities = []

        # Check for spatial coverage
        spatial_coverage = full_metadata.get("spatialCoverage")

        if spatial_coverage:
            # Handle spatial coverage - could be a list or single object
            if isinstance(spatial_coverage, list):
                # Create a site entity for each spatial coverage area with sequence numbers
                for i, coverage in enumerate(spatial_coverage):
                    if coverage.get("geo"):  # Only if it has geographic data
                        entity = self.create_site_entity(
                            dataset_version, full_metadata, coverage, sequence_number=i
                        )
                        entities.append(entity)
            else:
                # Single spatial coverage
                if spatial_coverage.get("geo"):
                    entity = self.create_site_entity(
                        dataset_version, full_metadata, spatial_coverage
                    )
                    entities.append(entity)

        # If no spatial entities were created, create a dataset entity
        if not entities:
            entity = self.create_dataset_entity(dataset_version, full_metadata)
            entities.append(entity)

        return entities

    def _write_entities_chunked(
        self, entities: List[Entity], output_prefix: str
    ) -> List[str]:
        """
        Write entities to multiple JSON files with size limits.

        Args:
            entities: List of entities to write
            output_prefix: Base name for output files (without .json extension)

        Returns:
            List of created file paths
        """
        if not entities:
            return []

        # Convert entities to dictionaries
        entities_dict = [entity.model_dump(exclude_none=True) for entity in entities]

        created_files = []
        current_batch = []
        current_size = 0
        file_counter = 1

        # JSON array overhead (brackets and formatting)
        array_overhead = 4  # "[\n]\n"

        for entity in entities_dict:
            # Estimate size of this entity when serialized
            entity_json = json.dumps(entity, ensure_ascii=False, separators=(",", ":"))
            entity_size = len(entity_json.encode("utf-8"))

            # Add comma and newline overhead if not the first item
            if current_batch:
                entity_size += 2  # ",\n"

            # Check if adding this entity would exceed the size limit
            projected_size = current_size + entity_size + array_overhead

            if projected_size > self.max_file_size_bytes and current_batch:
                # Save current batch
                filename = self._save_batch(current_batch, output_prefix, file_counter)
                created_files.append(filename)

                # Start new batch
                current_batch = [entity]
                current_size = entity_size
                file_counter += 1
            else:
                # Add to current batch
                current_batch.append(entity)
                current_size += entity_size

        # Save final batch if it has entities
        if current_batch:
            filename = self._save_batch(current_batch, output_prefix, file_counter)
            created_files.append(filename)

        return created_files

    def _save_batch(
        self, batch: List[Dict[str, Any]], output_prefix: str, file_number: int
    ) -> str:
        """
        Save a batch of entities to a JSON file.

        Args:
            batch: List of entity dictionaries to save
            output_prefix: Base filename prefix
            file_number: File number for naming

        Returns:
            Path to created file
        """
        filename = f"{output_prefix}_{file_number:05d}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(batch, f, indent=2, ensure_ascii=False)

        # Get actual file size
        file_size = os.path.getsize(filename)
        file_size_mb = file_size / (1024 * 1024)

        print(f"Created {filename}: {len(batch)} entities, {file_size_mb:.2f} MB")

        return filename

    def fetch_all_entities(
        self,
        output_prefix: Optional[str] = None,
        page_size: int = 100,
        max_pages: Optional[int] = None,
        debug_metadata: bool = False,
    ) -> Tuple[List[Entity], List[str]]:
        """
        Fetch all public datasets and convert them to Bertron entities using memory-efficient processing.

        Args:
            output_prefix: Optional prefix for output files (e.g., "essdive" -> "essdive_00001.json")
            page_size: Number of datasets to fetch per API request
            max_pages: Maximum number of pages to fetch (for testing/dry-run)

        Returns:
            Tuple of (all entities, list of created file paths)
        """
        print("Starting memory-efficient ESS-DIVE entity fetch...")

        # Initialize file writer if output is requested
        writer = None
        if output_prefix:
            writer = ChunkedEntityWriter(output_prefix, self.max_file_size_bytes)

        # Track entities for summary (but not accumulate all in memory)
        total_entities = []
        entity_counts = {"site": 0, "dataset": 0}

        # Debug metadata collection
        debug_datasets = [] if debug_metadata else None

        def process_dataset_callback(
            dataset: Dict[str, Any], page_info: Dict[str, Any]
        ) -> int:
            """Callback function to process each dataset and optionally write to files."""
            try:
                entities = self.process_dataset(dataset)

                # Collect dataset metadata for debug if requested
                if debug_metadata and debug_datasets is not None:
                    # Get full metadata that was fetched during processing
                    dataset_version = dataset.get("id")
                    if dataset_version:
                        full_metadata = self.get_dataset_metadata(dataset_version)
                        if full_metadata:
                            debug_datasets.append(full_metadata)

                # Update counters
                for entity in entities:
                    if EntityType.site in entity.entity_type:
                        entity_counts["site"] += 1
                    if EntityType.dataset in entity.entity_type:
                        entity_counts["dataset"] += 1

                # If we're writing to files, add to writer
                if writer:
                    writer.add_entities(entities)
                else:
                    # If not writing to files, keep in memory for return value
                    total_entities.extend(entities)

                # Rate limiting
                time.sleep(0.2)

                return len(entities)

            except Exception as e:
                print(f"Error processing dataset {dataset.get('id', 'Unknown')}: {e}")
                return 0

        # Process datasets page by page
        total_datasets_processed, total_entities_created = (
            self.process_datasets_by_page(
                page_size=page_size,
                max_pages=max_pages,
                process_callback=process_dataset_callback,
            )
        )

        # Finalize file writing if applicable
        created_files = []
        if writer:
            created_files = writer.finalize()

            if len(created_files) == 1:
                print(f"Entities saved to {created_files[0]}")
            else:
                print(f"Entities split into {len(created_files)} files:")
                for file_path in created_files:
                    print(f"  {file_path}")

        print(
            f"Created {total_entities_created} Bertron entities from {total_datasets_processed} datasets"
        )
        print(f"Site entities: {entity_counts['site']}")
        print(f"Dataset entities: {entity_counts['dataset']}")

        # Save debug metadata if requested
        if debug_metadata and debug_datasets:
            debug_filename = (
                f"{output_prefix}_00001_debug_metadata.json"
                if output_prefix
                else "debug_00001_metadata.json"
            )
            with open(debug_filename, "w", encoding="utf-8") as f:
                json.dump(debug_datasets, f, indent=2, ensure_ascii=False)
            print(f"Debug metadata saved to: {debug_filename}")
            print(f"Debug datasets collected: {len(debug_datasets)}")

        # Return total_entities for backward compatibility, but when writing files
        # we return a list with the entity counts for the summary
        if writer:
            # Create a minimal list for the summary without storing all entities
            summary_entities = []
            for _ in range(entity_counts["site"]):
                summary_entity = type(
                    "Entity", (), {"entity_type": [EntityType.site]}
                )()
                summary_entities.append(summary_entity)
            for _ in range(entity_counts["dataset"]):
                summary_entity = type(
                    "Entity", (), {"entity_type": [EntityType.dataset]}
                )()
                summary_entities.append(summary_entity)
            return summary_entities, created_files
        else:
            return total_entities, created_files


class ChunkedEntityWriter:
    """Helper class to write entities to chunked files in real-time."""

    def __init__(self, output_prefix: str, max_file_size_bytes: int = 25 * 1024 * 1024):
        self.output_prefix = output_prefix
        self.max_file_size_bytes = max_file_size_bytes
        self.current_batch = []
        self.current_size = 0
        self.file_counter = 1
        self.created_files = []
        self.array_overhead = 4  # "[\n]\n"

    def add_entities(self, entities: List[Entity]) -> None:
        """Add entities to the current batch, creating new files as needed."""
        for entity in entities:
            self._add_single_entity(entity)

    def _add_single_entity(self, entity: Entity) -> None:
        """Add a single entity to the current batch."""
        # Convert entity to dictionary
        entity_dict = entity.model_dump(exclude_none=True)

        # Estimate size of this entity when serialized
        entity_json = json.dumps(entity_dict, ensure_ascii=False, separators=(",", ":"))
        entity_size = len(entity_json.encode("utf-8"))

        # Add comma and newline overhead if not the first item
        if self.current_batch:
            entity_size += 2  # ",\n"

        # Check if adding this entity would exceed the size limit
        projected_size = self.current_size + entity_size + self.array_overhead

        if projected_size > self.max_file_size_bytes and self.current_batch:
            # Save current batch and start new one
            self._save_current_batch()
            self.current_batch = [entity_dict]
            self.current_size = entity_size
            self.file_counter += 1
        else:
            # Add to current batch
            self.current_batch.append(entity_dict)
            self.current_size += entity_size

    def _save_current_batch(self) -> None:
        """Save the current batch to a file."""
        if not self.current_batch:
            return

        filename = f"{self.output_prefix}_{self.file_counter:05d}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.current_batch, f, indent=2, ensure_ascii=False)

        # Get actual file size
        file_size = os.path.getsize(filename)
        file_size_mb = file_size / (1024 * 1024)

        print(
            f"Created {filename}: {len(self.current_batch)} entities, {file_size_mb:.2f} MB"
        )

        self.created_files.append(filename)
        self.current_batch = []
        self.current_size = 0

    def finalize(self) -> List[str]:
        """Save any remaining entities and return list of created files."""
        if self.current_batch:
            self._save_current_batch()
        return self.created_files


def main():
    """Main entry point for the script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch ESS-DIVE datasets and convert to Bertron entities"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file prefix (default: 'essdive'). Files will be created as "
        "PREFIX_00001.json, PREFIX_00002.json, etc. If dataset is small, only "
        "PREFIX_00001.json will be created.",
        default="essdive",
    )
    parser.add_argument(
        "--token",
        "-t",
        help="ESS-DIVE authentication token (or set ESS_DIVE_AUTH_TOKEN env var)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Number of datasets to fetch per API request (default: 100, max: 100)",
    )
    parser.add_argument(
        "--dry-run-pages",
        type=int,
        help="Test mode: only fetch the specified number of pages then exit "
        "(useful for testing with limited data)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate output files against schema (default: True)",
        default=True,
    )
    parser.add_argument(
        "--no-validate",
        dest="validate",
        action="store_false",
        help="Skip validation of output files",
    )
    parser.add_argument(
        "--debug-metadata",
        action="store_true",
        help="Save dataset metadata to debug file for inspection",
    )

    args = parser.parse_args()

    # Initialize fetcher
    fetcher = EssDiveEntityFetcher(auth_token=args.token)

    try:
        # Display dry run message if applicable
        if args.dry_run_pages:
            print(
                f"Running in dry-run mode: will fetch only {args.dry_run_pages} page(s)"
            )
            print(f"Each page contains up to {args.page_size} datasets")
            print(f"Total datasets to fetch: ~{args.dry_run_pages * args.page_size}")
            print()

        # Fetch all entities
        entities, created_files = fetcher.fetch_all_entities(
            output_prefix=args.output,
            page_size=args.page_size,
            max_pages=args.dry_run_pages,
            debug_metadata=args.debug_metadata,
        )

        print("\nSummary:")
        print(f"Total entities created: {len(entities)}")

        # Count by type using Pydantic model attributes
        site_count = sum(1 for e in entities if EntityType.site in e.entity_type)
        dataset_count = sum(1 for e in entities if EntityType.dataset in e.entity_type)

        print(f"Site entities: {site_count}")
        print(f"Dataset entities: {dataset_count}")

        if created_files:
            print(f"Results saved to: {created_files}")

            # Validate files if requested
            if args.validate:
                print("\nValidating output files...")
                validator = SchemaValidator()

                if len(created_files) == 1:
                    # Single file
                    is_valid, errors, entity_count = validator.validate_file(
                        created_files[0]
                    )
                    if is_valid:
                        print("✓ File passed validation")
                    else:
                        print(f"✗ Validation found {len(errors)} errors")
                        for error in errors[:5]:  # Show first 5 errors
                            print(f"  {error}")
                        if len(errors) > 5:
                            print(f"  ... and {len(errors) - 5} more errors")
                else:
                    # Multiple files - validate each individually
                    total_errors = []
                    total_entities = 0
                    valid_files = 0

                    for file_path in created_files:
                        is_valid, errors, entity_count = validator.validate_file(
                            file_path
                        )
                        total_entities += entity_count

                        if is_valid:
                            valid_files += 1
                        else:
                            for error in errors:
                                total_errors.append(
                                    f"{os.path.basename(file_path)}: {error}"
                                )

                    if not total_errors:
                        print("✓ All files passed validation")
                    else:
                        print(
                            f"✗ Validation found {len(total_errors)} errors in {len(created_files)} files"
                        )
                        for error in total_errors[:5]:  # Show first 5 errors
                            print(f"  {error}")
                        if len(total_errors) > 5:
                            print(f"  ... and {len(total_errors) - 5} more errors")
        else:
            print("No files were created (use --output to specify prefix)")

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
