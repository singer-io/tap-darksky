# tap-darksky

This is a [Singer](https://singer.io) tap that produces JSON-formatted data
following the [Singer
spec](https://github.com/singer-io/getting-started/blob/master/SPEC.md).

This tap:

- Pulls raw data from the [Darksky API](https://darksky.net/dev/docs#overview)
- Extracts the following resource:
  - [Forecast](https://darksky.net/dev/docs#time-machine-request)
- Outputs the schema for each resource
- Incrementally pulls data based on the input state

## Streams

[forecast](https://darksky.net/dev/docs#time-machine-request)
- Endpoint: https://api.darksky.net/forecast/{SECRET_KEY}/{latitude,longitued},{bookmark-datetime}?exclude=currently,minutely
- Primary key fields: latitude, longitude, forecast_date
- Foreign key fields: None
- Replication strategy: INCREMENTAL (query filtered)
  - Bookmark query fields: forecast_date
  - Bookmark: time (date-time)
- Transformations: de-nest daily data, add start/end times and local date, camelCase to snake_case


## Quick Start

1. Install

    Clone this repository, and then install using setup.py. We recommend using a virtualenv:

    ```bash
    > virtualenv -p python3 venv
    > source venv/bin/activate
    > python setup.py install
    OR
    > cd .../tap-darksky
    > pip install .
    ```
2. Dependent libraries
    The following dependent libraries were installed.
    ```bash
    > pip install singer-python
    > pip install singer-tools
    > pip install target-stitch
    > pip install target-json
    
    ```
    - [singer-tools](https://github.com/singer-io/singer-tools)
    - [target-stitch](https://github.com/singer-io/target-stitch)

3. Create your tap's `config.json` file. The `start_date` is the absolute minimum date for collecing weather data from your locations. The `user_agent` should list the tap-name and API user email address (for API logging purposes). The `secret_key` may be obtained from [Darksky.net](https://darksky.net/dev) with a free account (limited to 1000 API calls/day) or a subscription account (paying for additional API calls). The `languge` should be the 2-letter code of one of the supported [translation languages](https://github.com/darkskyapp/translations/tree/master/lib/lang); `en` is default.  The `units` should be the 2-letter code for the desired measurement units: `si`, `us`, `auto`, `uk2`, or `ca`; default is `auto`. The `location_list_1,2,3` are for storing lists of geo-locations in the format with comma separating latitude,longitude and semicolon separating each location: 
`latitude_1,longitude_1;latitude_2,longitude_2;latitude_3,longitude_3;...` 

    ```json
    {
    "secret_key": "YOUR_SECRET_KEY",
    "language": "en",
    "units": "us",
    "location_list_1": "38.840544, -105.0444233; 45.587467, -122.404503",
    "location_list_2": "45.304104, -121.754761; 39.191097, -106.817535",
    "location_list_3": "27.988121, 86.924973; 44.039170, -121.333700",
    "start_date": "2019-01-01T00:00:00Z",
    "user_agent": "tap-darksky <api_user_email@your_company.com>"
    }
    ```
    
    Optionally, also create a `state.json` file. `currently_syncing` is an optional attribute used for identifying the last object to be synced in case the job is interrupted mid-stream. The next run would begin where the last job left off. For this tap, each `location` is bookmarked.

    ```json
    {
        "currently_syncing": "forecast",
        "bookmarks": {
            "forecast": {
                "44.039170,-121.333700": "2019-10-01T00:00:00Z",
                "27.988121,86.924973": "2019-10-04T00:00:00Z",
                "39.191097,-106.817535": "2019-10-03T00:00:00Z"
            }
        }
    }
    ```

1. Run the Tap in Discovery Mode
    This creates a catalog.json for selecting objects/fields to integrate:
    ```bash
    tap-darksky --config config.json --discover > catalog.json
    ```
   See the Singer docs on discovery mode
   [here](https://github.com/singer-io/getting-started/blob/master/docs/DISCOVERY_MODE.md#discovery-mode).

2. Run the Tap in Sync Mode (with catalog) and [write out to state file](https://github.com/singer-io/getting-started/blob/master/docs/RUNNING_AND_DEVELOPING.md#running-a-singer-tap-with-a-singer-target)

    For Sync mode:
    ```bash
    > tap-darksky --config tap_config.json --catalog catalog.json > state.json
    > tail -1 state.json > state.json.tmp && mv state.json.tmp state.json
    ```
    To load to json files to verify outputs:
    ```bash
    > tap-darksky --config tap_config.json --catalog catalog.json | target-json > state.json
    > tail -1 state.json > state.json.tmp && mv state.json.tmp state.json
    ```
    To pseudo-load to [Stitch Import API](https://github.com/singer-io/target-stitch) with dry run:
    ```bash
    > tap-darksky --config tap_config.json --catalog catalog.json | target-stitch --config target_config.json --dry-run > state.json
    > tail -1 state.json > state.json.tmp && mv state.json.tmp state.json
    ```

3. Test the Tap
    
    While developing the darksky tap, the following utilities were run in accordance with Singer.io best practices:
    Pylint to improve [code quality](https://github.com/singer-io/getting-started/blob/master/docs/BEST_PRACTICES.md#code-quality):
    ```bash
    > pylint tap_darksky -d missing-docstring -d logging-format-interpolation -d too-many-locals -d too-many-arguments
    ```
    Pylint test resulted in the following score:
    ```bash
    Your code has been rated at 9.84/10
    ```

    To [check the tap](https://github.com/singer-io/singer-tools#singer-check-tap) and verify working:
    ```bash
    > tap-darksky --config tap_config.json --catalog catalog.json | singer-check-tap > state.json
    > tail -1 state.json > state.json.tmp && mv state.json.tmp state.json
    ```
    Check tap resulted in the following:
    ```bash
    Checking stdin for valid Singer-formatted data
    The output is valid.
    It contained 56 messages for 1 streams.

        1 schema messages
        24 record messages
        31 state messages

    Details by stream:
    +----------+---------+---------+
    | stream   | records | schemas |
    +----------+---------+---------+
    | forecast | 24      | 1       |
    +----------+---------+---------+
    ```
---

Copyright &copy; 2019 Stitch
