# SOIL DATA ONLY

import json
import sys
import requests

input_file = sys.argv[1]
output_file = sys.argv[2]

def fetch_sample_data():
    samples = []
    page = 1
    while True:
        response = requests.get(f'https://sc-data-dev.emsl.pnl.gov/sample?page={page}&per_page=10')
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

sample_data = fetch_sample_data() 

def enrich(proposal_id, sampling_set, sample_data):
    enriched_keys = {}
    for sample in sample_data:
        if sample['proposal_id'] and sample['sampling_set']:
            enriched_keys['elevation'] = str(sample['elevation']['value'] + ' ' + sample['elevation']['unit'])
            enriched_keys['depth'] = str(sample['soil_metadata']['depth']['raw'])
            enriched_keys['biome'] = str(sample['biome'])
            enriched_keys['soil_type'] = str(sample['soil_metadata']['soil_type'])
            enriched_keys['soil_temperature'] = str(sample['soil_metadata']['soil_temperature']['raw'])
    return enriched_keys

with open(input_file, 'r') as f:
    data = json.load(f)

print("enriching MONET records...")
for entry in data:
    if entry['ber_data_source'] == 'MONET':
        proposal_id = entry.get('proposal_id', '')
        sampling_set = entry.get('sampling_set', '')
        enriched_data = enrich(proposal_id, sampling_set, sample_data)
        for enriched_key, enriched_value in enriched_data.items():
            # Check if enriched_key already exists as a label in any of the properties
            existing_labels = [prop.get('attribute', {}).get('label') for prop in entry.get('properties', [])]
            if enriched_key not in existing_labels:
                tmp_dict = {}
                tmp_dict['attribute'] = {
                    "id": "SOMEID:0000000",
                    "label": enriched_key
                }
                tmp_dict['raw_value'] = enriched_value
                entry['properties'].append(tmp_dict)

with open(output_file, 'w') as f:
    json.dump(data, f, indent=2)