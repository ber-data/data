import requests
import json
res = requests.get("https://sc-data.emsl.pnnl.gov/ber/geofence?lat=46.34758&lon=-119.2779&fence=100000")
with open("latlon_project_ids.json", 'w') as f:
    json_res = json.loads(res.text)
    f.write(json.dumps(json_res, indent=4))
