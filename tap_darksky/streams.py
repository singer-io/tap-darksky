# streams: API URL endpoints to be called
# properties:
#   <root node>: Plural stream name for the endpoint
#   path: API endpoint relative path, when added to the base URL, creates the full path
#   key_properties: Primary key field(s) for the object endpoint
#   replication_method: FULL_TABLE or INCREMENTAL
#   replication_keys: bookmark_field(s), typically a date-time, used for filtering the results
#        and setting the state
#   params: Query, sort, and other endpoint specific parameters
#   data_key: JSON element containing the records for the endpoint
#   bookmark_query_field: Typically a date-time field used for filtering the query
#   bookmark_type: Data type for bookmark, integer or datetime
#   children: A collection of child endpoints (where the endpoint path includes the parent id)
#   parent: On each of the children, the singular stream name for parent element
STREAMS = {
    'forecast':
        {
            'path': 'forecast/<secret_key>/<location>,<forecast_date>',
            'key_properties': ['latitude', 'longitude', 'forecast_date'],
            'replication_method': 'INCREMENTAL',
            'replication_keys': ['forecast_date'],
            'bookmark_type': 'datetime',
            'params': {
                'exclude': '<exclusions_list>',
                'lang': '<language>',
                'units': '<units>'
            }
        }
    }
