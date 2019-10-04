import re
import time
import pytz

import singer
from singer.transform import unix_seconds_to_datetime
from singer.utils import strptime_to_utc

LOGGER = singer.get_logger()


# Convert camelCase to snake_case
def convert(name):
    regsub = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', regsub).lower()


# Convert keys in json array
def convert_array(arr):
    new_arr = []
    for i in arr:
        if isinstance(i, list):
            new_arr.append(convert_array(i))
        elif isinstance(i, dict):
            new_arr.append(convert_json(i))
        else:
            new_arr.append(i)
    return new_arr


# Convert keys in json
def convert_json(this_json):
    out = {}
    for key in this_json:
        try:
            new_key = convert(key)
        except TypeError as err:
            LOGGER.error('Error key = {}'.format(key))
            raise err
        if isinstance(this_json[key], dict):
            out[new_key] = convert_json(this_json[key])
        elif isinstance(this_json[key], list):
            out[new_key] = convert_array(this_json[key])
        else:
            out[new_key] = this_json[key]
    return out


def get_min_max_times(this_json):
    time_zone = this_json.get('timezone', 'UTC')
    time_frames = ['daily', 'hourly']
    max_time = 0
    min_time = int(time.time())
    for time_frame in time_frames:
        records = this_json.get(time_frame, {}).get('data', [])
        for record in records:
            rec_time = record.get('time', 0)
            if rec_time > max_time:
                max_time = rec_time
            if rec_time < min_time:
                min_time = rec_time
    # get time in UTC
    utc_dt = strptime_to_utc(unix_seconds_to_datetime(min_time))
    timezone = pytz.timezone(time_zone)
    local_dt = utc_dt.astimezone(timezone)
    local_dt_str = local_dt.strftime('%Y-%m-%d')
    return min_time, max_time, local_dt_str

# de-nest data nodes from daily
def denest_daily_data(this_json):
    new_json = this_json
    # Get first records of single record daily data list
    daily_data = next(iter(this_json.get('daily', {}).get('data', [])), None)
    if daily_data:
        new_json['daily'] = daily_data
    return new_json

# Run all transforms: convert camelCase to snake_case
def transform_json(this_json):
    converted_json = convert_json(this_json)
    start_time, end_time, local_date = get_min_max_times(converted_json)
    converted_json['start_time'] = start_time
    converted_json['end_time'] = end_time
    converted_json['local_date'] = local_date
    converted_json['forecast_date'] = '{}T00:00:00Z'.format(local_date)
    denested_json = denest_daily_data(converted_json)
    return denested_json
