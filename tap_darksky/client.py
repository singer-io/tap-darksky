import backoff
import requests
from requests.exceptions import ConnectionError
from singer import metrics, utils
from singer.utils import strftime
import singer

LOGGER = singer.get_logger()


class Server5xxError(Exception):
    pass


class Server429Error(Exception):
    pass


class DarkskyError(Exception):
    pass


class DarkskyBadRequestError(DarkskyError):
    pass


class DarkskyUnauthorizedError(DarkskyError):
    pass


class DarkskyPaymentRequiredError(DarkskyError):
    pass


class DarkskyNotFoundError(DarkskyError):
    pass


class DarkskyConflictError(DarkskyError):
    pass


class DarkskyForbiddenError(DarkskyError):
    pass


class DarkskyInternalServiceError(DarkskyError):
    pass


ERROR_CODE_EXCEPTION_MAPPING = {
    400: DarkskyBadRequestError,
    401: DarkskyUnauthorizedError,
    402: DarkskyPaymentRequiredError,
    403: DarkskyForbiddenError,
    404: DarkskyNotFoundError,
    409: DarkskyForbiddenError,
    500: DarkskyInternalServiceError}


def get_exception_for_error_code(status_code):
    return ERROR_CODE_EXCEPTION_MAPPING.get(status_code, DarkskyError)

def raise_for_error(response):
    try:
        response.raise_for_status()
    except (requests.HTTPError, requests.ConnectionError) as error:
        try:
            content_length = len(response.content)
            if content_length == 0:
                # There is nothing we can do here since Darksky has neither sent
                # us a 2xx response nor a response content.
                return
            response_json = response.json()
            status_code = response.status_code
            message = 'RESPONSE: {}'.format(response_json)
            ex = get_exception_for_error_code(status_code)
            raise ex(message)
        except (ValueError, TypeError):
            raise DarkskyError(error)


class DarkskyClient(object):
    def __init__(self,
                 secret_key,
                 user_agent=None):
        self.__secret_key = secret_key
        self.__user_agent = user_agent
        self.__session = requests.Session()
        self.base_url = 'https://api.darksky.net'
        self.__verified = False

    def __enter__(self):
        self.__verified = self.check_secret_key()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.__session.close()

    @backoff.on_exception(backoff.expo,
                          Server5xxError,
                          max_tries=7,
                          factor=3)
    def check_secret_key(self):
        if self.__secret_key is None:
            raise Exception('Error: Missing secret_key.')
        headers = {}
        if self.__user_agent:
            headers['User-Agent'] = self.__user_agent
        headers['Accept'] = 'application/json'
        endpoint = 'forecast'
        location = '38.840544,-105.0444233'
        now_date = strftime(utils.now())[0:10]
        param_string = 'exclude=currently,minutely,hourly,daily,alerts,flags&lang=en&units=us'
        url = '{}/{}/{}/{},{}T00:00:00?{}'.format(
            self.base_url,
            endpoint,
            self.__secret_key,
            location,
            now_date,
            param_string)
        response = self.__session.get(
            # Simple endpoint that returns 1 record (to check API secret_key access):
            url=url,
            headers=headers)
        if response.status_code != 200:
            LOGGER.error('Error status_code = {}'.format(response.status_code))
            raise_for_error(response)
        else:
            resp = response.json()
            if 'latitude' in resp:
                return True
            else:
                return False


    @backoff.on_exception(backoff.expo,
                          (Server5xxError, ConnectionError, Server429Error),
                          max_tries=7,
                          factor=3)
    @utils.ratelimit(800, 60)
    def request(self, method, url, **kwargs):
        if not self.__verified:
            self.__verified = self.check_secret_key()

        url = url.replace('<secret_key>', self.__secret_key)

        if 'endpoint' in kwargs:
            endpoint = kwargs['endpoint']
            del kwargs['endpoint']
        else:
            endpoint = None

        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        kwargs['headers']['Accept'] = 'application/json'

        if self.__user_agent:
            kwargs['headers']['User-Agent'] = self.__user_agent

        if method == 'POST':
            kwargs['headers']['Content-Type'] = 'application/json'

        with metrics.http_request_timer(endpoint) as timer:
            response = self.__session.request(method, url, **kwargs)
            timer.tags[metrics.Tag.http_status_code] = response.status_code

        if response.status_code >= 500:
            raise Server5xxError()

        if response.status_code != 200:
            raise_for_error(response)

        return response.json()

    def get(self, url, **kwargs):
        return self.request('GET', url=url, **kwargs)

    def post(self, url, **kwargs):
        return self.request('POST', url=url, **kwargs)
