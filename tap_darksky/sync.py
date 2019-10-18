from datetime import timedelta
import re
import singer
from singer import metrics, metadata, Transformer, utils, UNIX_SECONDS_INTEGER_DATETIME_PARSING
from singer.utils import strptime_to_utc
from tap_darksky.transform import transform_json
from tap_darksky.streams import STREAMS

LOGGER = singer.get_logger()


def write_schema(catalog, stream_name):
    stream = catalog.get_stream(stream_name)
    schema = stream.schema.to_dict()
    try:
        singer.write_schema(stream_name, schema, stream.key_properties)
    except OSError as err:
        LOGGER.info('OS Error writing schema for: {}'.format(stream_name))
        raise err


def write_record(stream_name, record, time_extracted):
    try:
        singer.messages.write_record(stream_name, record, time_extracted=time_extracted)
    except OSError as err:
        LOGGER.info('OS Error writing record for: {}'.format(stream_name))
        LOGGER.info('record: {}'.format(record))
        raise err
    except TypeError as err:
        LOGGER.info('Type Error writing record for: {}'.format(stream_name))
        LOGGER.info('record: {}'.format(record))
        raise err


def get_bookmark(state, stream, location, default):
    if (state is None) or ('bookmarks' not in state):
        return default
    return (
        state
        .get('bookmarks', {})
        .get(stream, {})
        .get(location, default)
    )


def write_bookmark(state, stream, location, value):
    if 'bookmarks' not in state:
        state['bookmarks'] = {}
    if stream not in state['bookmarks']:
        state['bookmarks'][stream] = {}
    state['bookmarks'][stream][location] = value
    LOGGER.info('Write state for Stream: {}, Location: {}, value: {}'.format(
        stream, location, value))
    singer.write_state(state)


def transform_datetime(this_dttm):
    with Transformer() as transformer:
        new_dttm = transformer._transform_datetime(this_dttm)
    return new_dttm


def process_records(catalog, #pylint: disable=too-many-branches
                    stream_name,
                    records,
                    time_extracted,
                    bookmark_field=None,
                    max_bookmark_value=None,
                    last_datetime=None):
    stream = catalog.get_stream(stream_name)
    schema = stream.schema.to_dict()
    stream_metadata = metadata.to_map(stream.metadata)

    with metrics.record_counter(stream_name) as counter:
        for record in records:
            # Transform record for Singer.io
            with Transformer(integer_datetime_fmt=UNIX_SECONDS_INTEGER_DATETIME_PARSING) \
                as transformer:
                transformed_record = transformer.transform(
                    record,
                    schema,
                    stream_metadata)

                # Reset max_bookmark_value to new value if higher
                if transformed_record.get(bookmark_field):
                    if max_bookmark_value is None or \
                        transformed_record[bookmark_field] > transform_datetime(max_bookmark_value):
                        max_bookmark_value = transformed_record[bookmark_field]

                if bookmark_field and (bookmark_field in transformed_record):
                    last_dttm = transform_datetime(last_datetime)
                    bookmark_dttm = transform_datetime(transformed_record[bookmark_field])
                    # Keep only records whose bookmark is after the last_datetime
                    if bookmark_dttm:
                        if bookmark_dttm >= last_dttm:
                            write_record(stream_name, transformed_record, \
                                time_extracted=time_extracted)
                            counter.increment()
                else:
                    write_record(stream_name, transformed_record, time_extracted=time_extracted)
                    counter.increment()

        return max_bookmark_value, counter.value


# Sync a specific parent or child endpoint.
def sync_endpoint(client,
                  catalog,
                  state,
                  start_date,
                  stream_name,
                  url,
                  location,
                  bookmark_field=None):

    # Get the latest bookmark for the stream and set the last_integer/datetime
    last_datetime = get_bookmark(state, stream_name, location, start_date)
    max_bookmark_value = last_datetime

    end_dttm = utils.now()
    end_dt = end_dttm.date()
    start_dttm = strptime_to_utc(last_datetime)
    start_dt = start_dttm.date()

    # date_list provides one date for each date in range
    date_list = [str(start_dt + timedelta(days=x)) for x in range((end_dt - start_dt).days + 1)]

    total_records = 0
    for bookmark_date in date_list:
        LOGGER.info('Stream: {}, Syncing bookmark_date = {}'.format(
            stream_name, bookmark_date))
        forecast_date = '{}T00:00:00'.format(bookmark_date)
        forecast_url = url.replace('<forecast_date>', forecast_date)
        LOGGER.info('URL for Stream {}: {}'.format(stream_name, forecast_url))

        # API request data
        data = {}
        data = client.get(
            url=forecast_url,
            endpoint=stream_name)

        # time_extracted: datetime when the data was extracted from the API
        time_extracted = utils.now()
        if not data or data is None or data == {}:
            break # No data results

        # Transform data with transform_json from transform.py
        # LOGGER.info('data = {}'.format(data)) # TESTING, comment out
        transformed_data = [] # initialize the record list
        transformed_data.append(transform_json(data))

        # LOGGER.info('transformed_data = {}'.format(transformed_data)) # TESTING, comment out
        if not transformed_data or transformed_data is None or transformed_data == []:
            LOGGER.info('No transformed data for data = {}'.format(data))
            break # No data results

        # Process records and get the max_bookmark_value and record_count for the set of records
        max_bookmark_value, record_count = process_records(
            catalog=catalog,
            stream_name=stream_name,
            records=transformed_data,
            time_extracted=time_extracted,
            bookmark_field=bookmark_field,
            max_bookmark_value=max_bookmark_value,
            last_datetime=last_datetime)

        total_records = total_records + record_count
        LOGGER.info('Stream {}, location: {}, batch processed {} records'.format(
            stream_name, location, record_count))

        # Update the state with the max_bookmark_value for the stream
        if bookmark_field:
            write_bookmark(state, stream_name, location, max_bookmark_value)

    # Return total_records (for all pages)
    return total_records


# Currently syncing sets the stream currently being delivered in the state.
# If the integration is interrupted, this state property is used to identify
#  the starting point to continue from.
# Reference: https://github.com/singer-io/singer-python/blob/master/singer/bookmarks.py#L41-L46
def update_currently_syncing(state, stream_name):
    if (stream_name is None) and ('currently_syncing' in state):
        del state['currently_syncing']
    else:
        singer.set_currently_syncing(state, stream_name)
    singer.write_state(state)


def sync(client, config, catalog, state):
    start_date = config.get('start_date')
    language = config.get('language', 'en')
    units = config.get('units', 'auto')

    # Stitch UI config parameters may be text areas, but limited to varchar(16384), 5461 chars,
    #   approx. 227 lat,lon locations (without spaces, 6-digit precision)
    # locations_list should be delimited like: lat1,lon1;lat2,lon2;lat3,lon3
    #   commas separating lat,lon and semicolons ; separating locations
    locations = config.get('location_list')

    # Remove non-numeric chars except commas, semicolons, minus signs
    #   and Split to list of locations by semicolon
    location_list = re.sub('[^0-9,.;-]', '', locations).split(";")

    # Get selected_streams from catalog, based on state last_stream
    #   last_stream = Previous currently synced stream, if the load was interrupted
    last_stream = singer.get_currently_syncing(state)
    LOGGER.info('last/currently syncing stream: {}'.format(last_stream))
    selected_streams = []
    for stream in catalog.get_selected_streams(state):
        selected_streams.append(stream.stream)
    LOGGER.info('selected_streams: {}'.format(selected_streams))

    if not selected_streams or selected_streams == []:
        return

    # Loop through endpoints in selected_streams
    for stream_name, endpoint_config in STREAMS.items():
        if stream_name in selected_streams:
            LOGGER.info('START Syncing: {}'.format(stream_name))
            update_currently_syncing(state, stream_name)
            write_schema(catalog, stream_name)
            bookmark_field = next(iter(endpoint_config.get('replication_keys', [])), None)
            # Get exclusions based on catalog not selected
            exclusions_list = 'currently,minutely'
            if stream_name == 'forecast':
                # Create exclusions_list from catalog breadcrumb
                stream = catalog.get_stream(stream_name)
                mdata = metadata.to_map(stream.metadata)
                sections_all = ['hourly', 'daily', 'flags']
                for section in sections_all:
                    if not singer.metadata.get(mdata, ('properties', section), 'selected'):
                        # metadata is selected for the dimension
                        exclusions_list = '{},{}'.format(exclusions_list, section)

            # Replace in url and query params
            params = endpoint_config.get('params', {})
            # Squash params and replace language and units
            querystring = '&'.join(['%s=%s' % (key, value) for (key, value) in \
                params.items()]).replace('<language>', language).replace(
                    '<units>', units).replace('<exclusions_list>', exclusions_list)
            endpoint_total = 0
            # Loop for each lat,lon location in location_list
            for location in location_list:
                loc_path = endpoint_config.get('path').replace('<location>', location)
                url = '{}/{}?{}'.format(
                    client.base_url,
                    loc_path,
                    querystring)
                total_records = sync_endpoint(
                    client=client,
                    catalog=catalog,
                    state=state,
                    start_date=start_date,
                    stream_name=stream_name,
                    url=url,
                    location=location,
                    bookmark_field=bookmark_field)

                update_currently_syncing(state, None)
                LOGGER.info('FINISHED Syncing: {}, location: {}, total_records: {}'.format(
                    stream_name,
                    location,
                    total_records))
                endpoint_total = endpoint_total + total_records

            LOGGER.info('FINISHED Syncing: {}, total_records: {}'.format(
                stream_name,
                endpoint_total))
