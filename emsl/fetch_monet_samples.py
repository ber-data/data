# SOIL DATA ONLY
# Schema version 9-15-2025

import json
import sys
import requests

output_file = sys.argv[1]

def fetch_sample_data():
    samples = []
    page = 1
    while True:
        response = requests.get(f'https://sc-data-dev.emsl.pnl.gov/sample?page={page}&per_page=50')
        response.raise_for_status()
        response_json = response.json()
        samples.extend(response_json['samples'])
        total_pages = response_json.get('pages', 1)
        current_page = response_json.get('page', 1)

        print(f"fetching samples - page {current_page} / {total_pages}") 

        if current_page >= total_pages:
            break 
        page += 1

    return samples

sample_data_from_api = fetch_sample_data() 

ber_output = []
count = 0
for sample in sample_data_from_api:
    count += 1
    ber_sample = {
        "ber_data_source": "EMSL",
        "coordinates": {
            "latitude": float(sample['latitude']),
            "longitude": float(sample['longitude'])
        },
        "entity_type": [
            "soil"
        ],
        "description": "MONet Soil Core",
        "id": sample["id"], # UUID for samplingActivity table in Analysis DB (Core B metadata)
        "uri": "https://sc-data.emsl.pnnl.gov/monet",
        "properties": [
            {
                "attribute": {
                    "id": "MIXS:0000332",
                    "label": "soil_type"
                },
                "raw_value": sample["soil_metadata"].get("soil_type", "unknown")
            },
            {
                "attribute": {
                    "id": "MIXS:0000010",
                    "label": "geo_loc_name"
                },
                "raw_value": sample.get("geolocation", "unknown")
            },
            {
                "attribute": {
                    "id": "MIXS:0000093",
                    "label": "elevation"
                },
                "raw_value": f"{sample['elevation']['value']} {sample['elevation']['unit']}" if sample.get("elevation") else "unknown" # Handle missing elevation
            },
            {
                "attribute": {
                    "id": "MIXS:0000012",
                    "label": "env_broad_scale"
                },
                "raw_value": sample.get("biome", "unknown")
            },
            {
                "attribute": {
                    "id": "MIXS:0000018",
                    "label": "depth"
                },
                "raw_value": f"{sample['soil_metadata']['depth']['raw']}" if sample.get("soil_metadata", {}).get("depth") else "unknown"
            }
        ]
    }
    ber_output.append(ber_sample)
print(f"Processed {count} samples.")
with open(output_file, 'w') as f:
    json.dump(ber_output, f, indent=2)