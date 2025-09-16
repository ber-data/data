import os
import unittest
import logging
# import sys
from typing import Dict #, Optional
import psycopg2
from psycopg2 import OperationalError
import pandas as pd
import json
import httpx

from schema.datamodel.bertron_schema_pydantic import Entity
from jsonschema import validate, ValidationError

# pip install psycopg2-binary

logger = logging.getLogger(__name__)

# JGI Genome Portal documentation: https://sites.google.com/a/lbl.gov/genome-portal/home/documentation/look-up-for-portals
# The Genome Portal will be decommissioned soon, but the URLs will be mapped to Advanced Search queries in the JGI Data Portal.

DBNAME: str = "n4l_corpus"
DBUSER: str = "n4luser"
DBPASS: str = "n4lpass"
DBHOST: str = "localhost"

def validate_json(schema, data: Dict) -> bool:
    """Validate data against the loaded schema."""
    assert isinstance(schema, dict), "Schema has not been loaded"

    logger.debug(data)

    try:
        validate(instance=data, schema=schema)
        _ = Entity(**data)  # Validate against Pydantic model
        return True
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        return False

def convert_record_to_json(schema, rec: dict):
    # pre-compute candidate coordinates
    coord_lat: float = 0.0
    coord_lon: float = 0.0
    has_coords = False

    if pd.notna(rec.get("samp_lat")) and pd.notna(rec.get("samp_lon")):
        coord_lat = float(rec["samp_lat"])
        coord_lon = float(rec["samp_lon"])
        has_coords = True
    elif pd.notna(rec.get("org_lat")) and pd.notna(rec.get("org_lon")):
        coord_lat = float(rec["org_lat"])
        coord_lon = float(rec["org_lon"])
        has_coords = True

    json_obj = {
        "id": rec.get("gold_project_id"),
        "alt_ids": [
                       rec.get("gold_study_id"),
                       rec.get("gold_organism_id"),
                       rec.get("gold_analysis_id"),
                       rec.get("project_legacy_gold_id"),
                       rec.get("ncbi_bioproject_accession"),
                       rec.get("ncbi_biosample_accession"),
                   ] + (rec.get("sra_experiment_ids").split("|") if pd.notna(
            rec.get("sra_experiment_ids")) else []),
        "name": rec.get("seqproj_name"),
        "alt_names": [
            {"name": n} for n in [
                rec.get("study_name"),
                rec.get("sample_name"),
                rec.get("sample_ncbi_tax_name"),
            ] if pd.notna(n)
        ],
        "ber_data_source": "JGI",
        "coordinates": (
            {
                "latitude": coord_lat,
                "longitude": coord_lon,
            }
        ) if has_coords else "null",
        "description": rec.get("study_desc"),
        "entity_type": ["project"],
        "part_of_collection": [
            {
                "id": str(rec.get("its_proposal_id")),
                "title": "ITS Proposal ID", "url": f"http://genome.jgi.doe.gov/portal/lookup?keyName=proposalId&keyValue={rec.get("its_proposal_id")}&groupOnly=1&app=Info"
            } if pd.notna(rec.get("its_proposal_id")) else None,
            {
                "id": str(rec.get("its_sequencing_project_id")),
                "title": "ITS Sequencing Project ID", "url": f"http://genome.jgi.doe.gov/portal/lookup?keyName=jgiProjectId&keyValue={rec.get("its_sequencing_project_id")}&app=Info"
            } if pd.notna(rec.get("its_sequencing_project_id")) else None,
            {
                # JGI User Project ID
                "id": str(rec.get("pmo_project_id")),
                "title": "PMO Project ID", "url": f"https://data.jgi.doe.gov/search?q={rec.get("pmo_project_id")}"
            } if pd.notna(rec.get("pmo_project_id")) else None,
        ],
        "properties": [
            {"attribute": {"label": "funding source"}, "value": rec.get("seqproj_funding")},
            {"attribute": {"label": "award DOI"}, "value": rec.get("seqproj_award_dois")},
            {"attribute": {"label": "sequencing strategy"}, "value": rec.get("sequencing_strategy")},
            {"attribute": {"label": "project status"}, "value": rec.get("project_status")},
            {"attribute": {"label": "sequencing status"}, "value": rec.get("sequencing_status")},
            {"attribute": {"label": "ecosystem"}, "value": rec.get("sample_ecosystem")},
            {"attribute": {"label": "ecosystem category"}, "value": rec.get("sample_ecosystem_category")},
            {"attribute": {"label": "ecosystem type"}, "value": rec.get("sample_ecosystem_type")},
            {"attribute": {"label": "ecosystem subtype"}, "value": rec.get("sample_ecosystem_subtype")},
            {"attribute": {"label": "specific ecosystem"}, "value": rec.get("sample_specific_ecosystem")},
            {"attribute": {"label": "gene count"}, "numeric_value": rec.get("analysis_gene_count") if pd.notna(
                rec.get("analysis_gene_count")) else None},
            {"attribute": {"label": "estimated size"},
             "numeric_value": rec.get("analysis_estimated_size") if pd.notna(
                 rec.get("analysis_estimated_size")) else None},
        ],
        "uri": f"https://gold.jgi.doe.gov/projects/{rec.get('gold_project_id')}"
    }

    # Clean empty or None values
    json_obj["alt_ids"] = [i for i in json_obj["alt_ids"] if i not in [None, "", float("nan")]]
    json_obj["alt_names"] = [i for i in json_obj["alt_names"] if i]
    json_obj["part_of_collection"] = [i for i in json_obj["part_of_collection"] if i]
    json_obj["properties"] = [
        i for i in json_obj["properties"]
        if i.get("value") not in [None, ""] and i.get("value") == i.get("value")  # remove NaN
           or i.get("numeric_value") not in [None, ""]
    ]

    # Validate the JSON object against the schema.
    if validate_json(schema, json_obj):
        logger.debug("Record validates!")
    else:
        logger.debug("Record failed validation!")

    return json_obj

def csv_to_json(schema, csv_filename, out_filename = None):
    if not out_filename:
        out_filename = csv_filename + ".json"

    df = pd.read_csv(csv_filename)

    json_objects: list = []

    for _, row in df.iterrows():
        json_objects.append(convert_record_to_json(schema, row.to_dict()))

    # Save to file if requested
    if out_filename:
        with open(out_filename, "w") as f:
            json.dump(json_objects, f, indent=2)

    return


def load_schema(schema_path) -> Dict:
    """Load the JSON schema from file."""
    assert isinstance(schema_path, str), "Schema path has not been set"
    schema = None

    try:
        logger.info(f"Loading schema from {schema_path}")
        if schema_path.startswith(("http://", "https://")):
            response = httpx.get(schema_path)
            response.raise_for_status()
            schema = response.json()
        else:
            with open(schema_path, "r") as f:
                schema = json.load(f)
        if not isinstance(schema, dict):
            raise ValueError("Failed to parse schema into a Python dictionary")
        return schema
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load schema: {e}")
        raise e



def export_json_from_gold_limit(schema, base_filename="jgi_gold_seqprojects.json", geo_only = False, max_file_size = 25 * 1024 * 1024):
    conn = None
    try:
        conn = psycopg2.connect(database=DBNAME, user=DBUSER, password=DBPASS, host=DBHOST)

        cursor = conn.cursor()

        if geo_only:
            # Export only JGI records with geographic coordinates.
            cursor.execute("SELECT COUNT(*) FROM jgi_geodata WHERE (samp_has_geodata = TRUE OR org_has_geodata = TRUE)")
        else:
            # Export all JGI records.
            cursor.execute("SELECT COUNT(*) FROM jgi_geodata")

        total = cursor.fetchone()[0]

        if geo_only:
            # Export only JGI records with geographic coordinates.
            cursor.execute("SELECT * FROM jgi_geodata WHERE (samp_has_geodata = TRUE OR org_has_geodata = TRUE)")
        else:
            # Export all JGI records.
            cursor.execute("SELECT * FROM jgi_geodata")

        colnames = [desc[0] for desc in cursor.description]

        file_index = 1
        current_file = None
        first_record_in_file = True

        def open_new_file():
            nonlocal current_file, first_record_in_file, file_index
            if current_file:
                current_file.write("\n]\n")
                current_file.close()
            out_name = f"{os.path.splitext(base_filename)[0]}_{file_index:05d}.json"
            current_file = open(out_name, "w")
            current_file.write("[\n")
            first_record_in_file = True
            file_index += 1
            return current_file

        current_file = open_new_file()

        logger.info(f"Exporting {total} records...")

        # for record in cursor:
        for i, record in enumerate(cursor.fetchall(), start=1):
            rec_dict = dict(zip(colnames, record))

            if i % 100 == 0 or i == total:
                pct = (i / total) * 100
                logger.info(f"Processed {i}/{total} records ({pct:.1f}%)")

            json_obj = convert_record_to_json(schema, rec_dict)

            if not first_record_in_file:
                current_file.write(",\n")
            current_file.write(json.dumps(json_obj, indent=2))
            first_record_in_file = False
            current_file.flush()

            if current_file.tell() >= max_file_size:
                current_file = open_new_file()

        # close final file properly
        if current_file:
            current_file.write("\n]\n")
            current_file.close()

    finally:
        if conn:
            conn.close()

def test_gold_database_to_json():
    logger.setLevel(logging.INFO)  # prints out export status

    tag = "v0.1.0-alpha.12"

    if not tag:
        schema_uri = "https://raw.githubusercontent.com/ber-data/bertron-schema/refs/heads/main/src/schema/jsonschema/bertron_schema.json"
    else:
        schema_uri = f"https://raw.githubusercontent.com/ber-data/bertron-schema/refs/tags/{tag}/src/schema/jsonschema/bertron_schema.json"

    schema = load_schema(schema_uri)
    export_json_from_gold_limit(schema, "../../jgi/jgi.json")

if __name__ == '__main__':
    unittest.main()
