from pathlib import Path
from typing import Optional

from nmdc_schema import nmdc
from rich import print
from schema.datamodel import bertron_schema_pydantic as bertron
from typing_extensions import Annotated
import httpx
import json
import typer


# Create a CLI application.
app = typer.Typer(
    name="ingest",
    no_args_is_help=True,  # treats the absence of args like the `--help` arg
    add_completion=False,  # hides the shell completion options from `--help` output
    rich_markup_mode="markdown",  # enables use of Markdown in docstrings and CLI help
)


class Fetcher:
    """Methods that can be used to fetch resources from the NMDC Runtime API."""

    def __init__(self, api_base_url: str = "https://api.microbiomedata.org"):
        self.api_base_url = api_base_url
        """Base URL of the NMDC Runtime API."""

        self.biosamples: list[dict] = []
        """List of fetched biosamples."""

    def fetch_all_biosamples(self) -> list[dict]:
        """Fetch all biosamples in the NMDC database via the NMDC Runtime API."""

        page_num: int = 1
        page_cursor: Optional[str] = "*"  # the "*" cursor refers to the first page
        while True:
            print(
                f"Fetching page number {page_num} via cursor `{page_cursor}`: ",
                end="",
            )
            response = httpx.get(
                f"{self.api_base_url}/biosamples",
                params={
                    "per_page": 2000,
                    "cursor": page_cursor,
                },
            )

            # Count the biosamples in this batch.
            response_payload = response.json()
            biosamples = response_payload["results"]
            print(f"{len(biosamples)} biosamples")

            # Add the biosamples to our list of all of them.
            self.biosamples.extend(biosamples)

            # If there is an additional batch of biosamples available, prepare to fetch it.
            next_page_cursor = response_payload["meta"]["next_cursor"]
            if next_page_cursor is not None:
                page_num += 1
                page_cursor = next_page_cursor
            else:
                break

        print(f"Fetched {len(self.biosamples)} biosamples")
        return self.biosamples


class BiosampleMapper(nmdc.Biosample):
    """A Biosample—as defined in NMDC Schema—but with some helper methods.

    Reference: https://microbiomedata.github.io/nmdc-schema/Biosample/
    """

    def get_name(self) -> Optional[str]:
        """Returns the `samp_name` of this Biosample, if it has one.

        Note: I opted to use this instead of `name`, after noticing that some `name` values seemed to me
              to be duplicates of `description` values.
        """
        if isinstance(self.samp_name, str):
            return self.samp_name
        return None

    def get_description(self) -> Optional[str]:
        """Returns the `description` of this Biosample, if it has one."""
        if isinstance(self.description, str):
            return self.description
        return None

    def get_coordinates(self) -> Optional[bertron.Coordinates]:
        """Returns a `Coordinates` instance—as defined in the BERtron schema—if this Biosample has a `lat_lon`.

        Reference: https://ber-data.github.io/bertron-schema/Coordinates/
        """
        if isinstance(self.lat_lon, nmdc.GeolocationValue):
            return bertron.Coordinates(
                latitude=self.lat_lon.latitude,
                longitude=self.lat_lon.longitude,
            )
        return None

    def get_alt_ids(self) -> list[str]:
        """Returns a list of alternative identifiers, if any exist, for this Biosample.

        I got the names of these fields by searching (command+F) the Biosample schema
        documentation page, for slots whose names contained `_identifiers`. Some of
        those slots have a range of `Uriorcurie` (multivalue), and others have a range
        of `ExternalIdentifier` (multivalue). Meanwhile, the BERtron schema said an
        `Entity`'s `alt_ids` slot has a range of `Uriorcurie` (multivalue) only.

        References:
        - https://microbiomedata.github.io/nmdc-schema/Uriorcurie/
        - https://microbiomedata.github.io/nmdc-schema/ExternalIdentifier/
        """
        alt_ids = set()
        alt_ids.update(set(self.img_identifiers or []))
        alt_ids.update(set(self.neon_biosample_identifiers or []))
        alt_ids.update(set(self.gold_biosample_identifiers or []))
        alt_ids.update(set(self.insdc_biosample_identifiers or []))
        alt_ids.update(set(self.emsl_biosample_identifiers or []))
        alt_ids.update(set(self.igsn_biosample_identifiers or []))
        alt_ids.update(set(self.alternative_identifiers or []))
        return sorted(list(alt_ids))

    def get_alt_names(self) -> list[str]:
        """Returns a list of alternative names, if any exist, for this Biosample."""
        alt_names = set()
        alt_names.update(set(self.alternative_names or []))
        return sorted(list(alt_names))

    def get_uri(self) -> str:
        """Returns a URI for this Biosample."""
        return f"https://api.microbiomedata.org/biosamples/{self.id}"

    def get_part_of_collection(self) -> list[bertron.DataCollection]:
        """Returns a list of `DataCollection` instances, each describing one of the Biosample's associated studies.

        References:
        - https://ber-data.github.io/bertron-schema/DataCollection/
        - https://microbiomedata.github.io/nmdc-schema/associated_studies/

        TODO: Retrieve the name and description of the Study from the NMDC Runtime API, then include it here.
        """
        data_collections = []
        if self.associated_studies is not None and len(self.associated_studies) > 0:
            for study_id in self.associated_studies:
                data_collection = bertron.DataCollection(
                    id=study_id,
                    url=f"https://api.microbiomedata.org/studies/{study_id}",
                )
                data_collections.append(data_collection)
        return data_collections

    def get_properties(self) -> list[dict]:
        """Returns a list of properties derived from the underlying Biosample.

        TODO: Add support for additional properties.
        """
        properties = []
        if isinstance(self.collection_date, nmdc.TimestampValue):
            raw_value = self.collection_date.has_raw_value
            if raw_value is not None:
                # TODO: Document the origin of the attribute values.
                #       (I copied them from a sample data file in the
                #       `bertron-schema` repo). Where are they defined?
                properties.append(
                    {
                        "attribute": {
                            "id": "MIXS:0000011",
                            "label": "collection date",
                        },
                        "raw_value": raw_value,
                    }
                )
        return properties

    def get_entity(self) -> bertron.Entity:
        """Returns an `Entity` instance—as defined in the BERtron schema.

        Reference: https://ber-data.github.io/bertron-schema/Entity/
        """
        params: dict = {
            "ber_data_source": bertron.BERSourceType.NMDC,
            "coordinates": self.get_coordinates(),
            "entity_type": [bertron.EntityType.sample],
            "description": self.get_description(),
            "id": self.id,
            "name": self.get_name(),
            "alt_ids": self.get_alt_ids(),
            "alt_names": self.get_alt_names(),
            "part_of_collection": self.get_part_of_collection(),
            "uri": self.get_uri(),
            "properties": self.get_properties(),
        }

        return bertron.Entity(**params)


@app.command()
def main(
    # Reference: https://typer.tiangolo.com/tutorial/parameter-types/path/
    cache_input_file_path: Annotated[
        Optional[Path],
        typer.Option(
            "--cache-from",
            dir_okay=False,
            writable=False,
            readable=True,
            resolve_path=True,
            help=(
                "Path to a JSON file previously created via `--cache-to`, from which you want "
                "the script to load NMDC data. If not specified, the script will download NMDC "
                "data from the Internet."
            ),
        ),
    ] = None,
    cache_output_file_path: Annotated[
        Optional[Path],
        typer.Option(
            "--cache-to",
            dir_okay=False,
            writable=True,
            readable=False,
            resolve_path=True,
            help=(
                "Path at which you want the script to create a JSON file containing the NMDC data "
                "the script downloads from the Internet. That path can then be specified to the "
                "script via `--cache-from` on a subsequent run, in order to avoid downloading the "
                "same data again from the Internet."
            ),
        ),
    ] = None,
    result_output_file_path: Annotated[
        Path,
        typer.Option(
            "-o",
            "--output",
            dir_okay=False,
            writable=True,
            readable=False,
            resolve_path=True,
            help=(
                "Path at which you want the JSON file containing BERtron data to be created."
            ),
        ),
    ] = Path("./nmdc_00001.json"),
):
    """
    Fetch NMDC data, transform it into BERtron-compliant data, and write it to a JSON file.

    This script fetches biosample data from the NMDC Runtime API (or loads it from a file,
    if specified), validates it against the NMDC Schema, transforms it into a shape that is
    compliant with the BERtron Schema, then writes it to a JSON file.
    """

    # If a cache input file path was specified, read the biosamples from there.
    # Otherwise, fetch them from the NMDC Runtime API.
    if isinstance(cache_input_file_path, Path):
        with open(cache_input_file_path, "r") as file:
            biosamples = json.load(file)
        print(f"Loaded {len(biosamples)} biosamples from: {cache_input_file_path}")
    else:
        fetcher = Fetcher()
        fetcher.fetch_all_biosamples()

        # If a cache output file path was specified, dump the fetched biosamples to that file.
        if isinstance(cache_output_file_path, Path):
            with open(cache_output_file_path, "w") as file:
                json.dump(fetcher.biosamples, file, indent=2)
            print(
                f"Cached {len(fetcher.biosamples)} biosamples in: {cache_output_file_path}"
            )
        biosamples = fetcher.biosamples

    # Create a `bertron.Entity` instance corresponding to each biosample.
    entity_instances: list[bertron.Entity] = []
    for biosample in biosamples:
        mapper = BiosampleMapper(**biosample)
        entity_instance = mapper.get_entity()
        entity_instances.append(entity_instance)

    # Create a Python dictionary corresponding to each `bertron.Entity` instance.
    entity_dicts: list[dict] = [
        entity.model_dump(exclude_none=True) for entity in entity_instances
    ]

    # Write the list of Python dictionaries (as an array of JSON objects) to the result output file.
    with open(result_output_file_path, "w") as file:
        json.dump(entity_dicts, file, indent=2)

    print(f"Wrote {len(entity_instances)} entities to: {result_output_file_path}")


if __name__ == "__main__":
    app()
