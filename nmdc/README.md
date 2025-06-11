# NMDC

This directory contains a Python notebook you can use to fetch location-related metadata about biosamples residing
in the NMDC database—via the NMDC API—and store that metadata in a CSV file. This directory also contains an example
CSV file that was created that way.

Here's a diagram depicting the relationships between the NMDC database, the Python notebook in this directory,
and the CSV file in this directory.

```mermaid
flowchart LR
    subgraph NMDC Infrastructure
        nmdc_db[("NMDC<br>Database")]
        nmdc_api["NMDC<br>API"]
        nmdc_db -.-> nmdc_api
        nmdc_api --> nmdc_db
    end
    
    notebook[["Python notebook<br>get_nmdc_biosample_geo_coordinates.ipynb"]]
    notebook -- Biosample metadata<br>requests --> nmdc_api
    notebook -- Biosample metadata --> csv_file
    nmdc_api -. Biosample metadata .-> notebook
    csv_file["CSV File<br>nmdc_biosample_geo_coordinates.csv"]
```

## References

Here are some other documents you may find helpful when exploring the contents of this directory.

- [Using Python to access the NMDC API](https://docs.microbiomedata.org/runtime/nb/api_access_via_python/)
- [NMDC Schema documentation page about the `Biosample` schema class](https://microbiomedata.github.io/nmdc-schema/Biosample/)
- [NMDC Schema documentation page about the `lat_lon` schema slot](https://microbiomedata.github.io/nmdc-schema/lat_lon/)
