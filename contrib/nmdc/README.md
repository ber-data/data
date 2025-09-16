# nmdc

## Development

### Quick start

Prerequisite(s):

- Python 3.12 is installed

Set up a Python virtual environment.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install --no-cache-dir -r requirements.txt
```

> I included `--no-cache-dir` in the installation command in an attempt to reduce the chances that any developer ends up using an out-of-date version of the BERtron schema, whose version number does not yet change from one "release" to the next.

Run the ingest script.

```sh
python ingest.py
```

Deactivate the Python virtual environment.

```sh
deactivate
```
