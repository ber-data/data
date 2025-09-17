import json
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Any, Optional

import httpx
import typer
from linkml_runtime.linkml_model import SlotDefinition
from linkml_runtime.utils.formatutils import camelcase
from nmdc_schema import nmdc
from nmdc_schema.get_nmdc_view import ViewGetter
from rich import print
from rich.progress import Progress
from schema.datamodel import bertron_schema_pydantic as bertron
from typing_extensions import Annotated

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

    def __init__(self, *args, **kwargs):
        if "nmdc_schema_view" in kwargs:
            self._nmdc_schema_view = kwargs.pop("nmdc_schema_view")
        else:
            self._nmdc_schema_view = ViewGetter().get_view()
        self._nmdc_schema_enum_names = {
            camelcase(e) for e in self._nmdc_schema_view.all_enums().keys()
        }
        super().__init__(*args, **kwargs)

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

        def _append_property(slot_definition: SlotDefinition, slot_value: Any) -> None:
            """Append one or more properties to the `properties` list, based on the given slot
            definition and value.
            """

            # If the slot value is a list, append a property for each item in the list.
            if isinstance(slot_value, list):
                for item in slot_value:
                    _append_property(slot_definition, item)
                return

            # The attribute dictionary is common to all property types.
            attribute = {
                "id": f"nmdc:{slot_definition.name}",
                "label": slot_definition.title
                if slot_definition.title
                else slot_definition.name,
            }
            # If the value is a simple primitive type, stringify it and use it as a raw_value.
            if isinstance(slot_value, (str, int, float, bool)):
                properties.append(
                    {
                        "attribute": attribute,
                        "raw_value": str(slot_value),
                    }
                )
            # If the value is a QuantityValue, map as many fields as possible to the property.
            elif isinstance(slot_value, nmdc.QuantityValue):
                properties.append(
                    {
                        "attribute": attribute,
                        "raw_value": slot_value.has_raw_value,
                        "maximum_numeric_value": slot_value.has_maximum_numeric_value,
                        "minimum_numeric_value": slot_value.has_minimum_numeric_value,
                        "numeric_value": slot_value.has_numeric_value,
                        "unit": str(slot_value.has_unit),
                    }
                )
            # If the value is a ControlledIdentifiedTermValue, map the term ID to the property's
            # value.
            elif isinstance(slot_value, nmdc.ControlledIdentifiedTermValue):
                properties.append(
                    {
                        "attribute": attribute,
                        "value": slot_value.term.id,
                    }
                )
            # If the value is a ControlledTermValue, map the term ID to the property's value if the
            # term exists.
            elif isinstance(slot_value, nmdc.ControlledTermValue):
                if slot_value.term is not None:
                    properties.append(
                        {
                            "attribute": attribute,
                            "value": slot_value.term.id,
                        }
                    )
            # If the value is a GeolocationValue, do nothing because we handle lat_lon separately,
            # via get_coordinates().
            elif isinstance(slot_value, nmdc.GeolocationValue):
                pass
            # If the value is an AttributeValue subclass not handled above, map its raw_value to
            # the property's raw_value.
            elif isinstance(slot_value, nmdc.AttributeValue):
                properties.append(
                    {
                        "attribute": attribute,
                        "raw_value": slot_value.has_raw_value,
                    }
                )
            # If the value is an enum, map its string representation to the property's raw_value.
            elif slot_value.__class__.__name__ in self._nmdc_schema_enum_names:
                properties.append(
                    {
                        "attribute": attribute,
                        "raw_value": str(slot_value),
                    }
                )
            # If we don't know how to handle the slot value, print a warning.
            else:
                print(
                    f"[yellow]Warning: Unhandled slot '{slot_definition.name}' of type '{slot_value.__class__.__name__}'[/yellow]"
                )

        # Iterate over all Biosample slots defined in the NMDC Schema and append properties for
        # those that have values in this Biosample instance.
        for slot_definition in self._nmdc_schema_view.class_induced_slots(
            self.class_name
        ):
            slot_value = getattr(self, slot_definition.name, None)
            if not slot_value:
                continue
            _append_property(slot_definition, slot_value)

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


class Dumper:
    """Methods that can be used to dump `bertron.Entity` instances to JSON files."""

    @staticmethod
    def dump_entities_to_json_files(
        entities: list[bertron.Entity],
        output_dir: Path,
        target_file_size_bytes: int = 25_000_000,
    ) -> None:
        """Dump the given list of `bertron.Entity` instances to JSON files."""

        class Token(str, Enum):
            """Tokens that can be used when generating JSON strings."""

            OPEN = "[\n"
            DELIMIT = ",\n"
            CLOSE = "\n]"

        # Count the number of entities, so we can show a percent completion.
        num_entities_total = len(entities)

        # Iterate through the `Entity` instances, dumping each one in JSON format into a buffer.
        # When the buffer contains at least one dumped instance and the size of the buffer exceeds
        # `target_file_size_bytes`, terminate the JSON array in the buffer and dump the buffer to
        # a file. Then, create a new buffer and repeat the process with the next entity and file.
        file_number = 1
        buffer = StringIO()
        num_entities_in_buffer = 0
        with Progress(refresh_per_second=1) as progress:
            task = progress.add_task(
                "Dumping entities as JSON...", total=num_entities_total
            )
            for entity_num, entity in enumerate(
                entities, start=1
            ):  # use a 1-based index
                progress.update(task, advance=1)

                # If we're about to write the buffer's first entity, start the JSON array.
                if num_entities_in_buffer == 0:
                    buffer.write(Token.OPEN.value)

                # Write this entity to the buffer.
                buffer.write(entity.model_dump_json(indent=2))
                num_entities_in_buffer += 1

                # If either (a) this was the final entity in our list or (b) the buffer size is
                # at or above our threshold, end the JSON array, dump the buffer to the file,
                # and prepare a new buffer and filename.
                buffer_size_bytes = len(buffer.getvalue().encode("utf-8"))
                if (
                    entity_num == num_entities_total
                    or buffer_size_bytes >= target_file_size_bytes
                ):
                    buffer.write(Token.CLOSE.value)
                    result_output_file_path = Path(
                        output_dir / f"nmdc_{file_number:05d}.json"
                    )
                    with open(result_output_file_path, "w") as file:
                        file.write(buffer.getvalue())
                    print(
                        f"Dumped {num_entities_in_buffer} entities "
                        f"({buffer_size_bytes} bytes) "
                        f"to: {result_output_file_path}"
                    )
                    buffer = StringIO()
                    num_entities_in_buffer = 0
                    file_number += 1
                else:
                    # Add an element delimiter and continue to add entities to the buffer.
                    buffer.write(Token.DELIMIT.value)

            # Remove the progress bar.
            progress.remove_task(task)


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
    result_output_dir_path: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            dir_okay=True,
            writable=True,
            readable=False,
            resolve_path=True,
            help=(
                "Path to directory in which you want the JSON file(s) containing BERtron entities "
                "to be created."
            ),
        ),
    ] = Path("./"),
    target_output_file_size: Annotated[
        int,
        typer.Option(
            "--target-file-size",
            min=1,
            help=(
                "Number of bytes you want each JSON file to contain. Each time the script writes "
                "an additional BERtron entity to a file, it will compare the file's size to this "
                "number, in order to determine whether to continue growing the file or start a "
                "new file. This is not a hard limit."
            ),
        ),
    ] = 25_000_000,
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

    # Get a `SchemaView` of the NMDC Schema, which can be used during the mapping process.
    nmdc_schema_view = ViewGetter().get_view()

    # Create a `bertron.Entity` instance corresponding to each biosample.
    entity_instances: list[bertron.Entity] = []
    for biosample in biosamples:
        mapper = BiosampleMapper(**biosample, nmdc_schema_view=nmdc_schema_view)
        entity_instance = mapper.get_entity()
        entity_instances.append(entity_instance)

    # Dump the `bertron.Entity` instances to JSON file(s).
    Dumper.dump_entities_to_json_files(
        entities=entity_instances,
        output_dir=result_output_dir_path,
        target_file_size_bytes=target_output_file_size,
    )


if __name__ == "__main__":
    app()
