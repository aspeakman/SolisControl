from requests import Session, RequestException
from http import HTTPStatus
import logging
import yaml
import json
from datetime import datetime

try:
    import solis_common as common
except ImportError:
    from soliscontrol import solis_common as common

""" Client module for Solis Cloud API access via requests library
See monitoring API https://oss.soliscloud.com/templet/SolisCloud%20Platform%20API%20Document%20V2.0.pdf
and separate control API https://oss.soliscloud.com/doc/SolisCloud%20Device%20Control%20API%20V2.0.pdf

For inspiration and basic details of how to configure requests
See https://github.com/stevegal/solis_control/
                                                                
Ideally this would capture connection state within a class and use asyncio/aiohttp libraries
however I could not get both of these aspects to work in Home Assistant pyscript
instead (kludge alert) connection state is passed between methods in the config dict
and requests are wrapped with task.executor
See https://hacs-pyscript.readthedocs.io/en/latest/index.html"""

try:
    task.executor()
except NameError:
    PYSCRIPT = False
except TypeError:
    PYSCRIPT = True
else: # default
    PYSCRIPT = False
    
if not PYSCRIPT:
    log = logging.getLogger(__name__)
    
def make_request(call, *args, **kwargs):
    if PYSCRIPT:
        return task.executor(call, *args, **kwargs)
    else:
        return call(*args, **kwargs)
        
def get_session():
    return Session()
    
def get_inverter_entry(config, session): 
    body = '{"stationId":"'+config['solis_station_id']+'"}'
    header = common.prepare_post_header(config, body, common.INVERTER_ENDPOINT)
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    inverter_entry = None
    try:
        with make_request(session.post, config['api_url']+common.INVERTER_ENDPOINT, data = body, headers = header) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('success') and result.get('data'):
                    for record in result['data']['page']['records']:
                      if record.get('stationId', '') == config['solis_station_id']:
                        common.add_fields(common.ENTRY_FIELDS, record, config)
                        inverter_entry = record
                else:
                    log.warning('Payload error getting inverter entry: %s %s' % (result.get('code'), result.get('msg')))
            else:
                log.warning('HTTP error getting inverter entry: %d %s' % (status, response.text))
    except RequestException as e:
        log.warning('Request exception getting inverter entry: ' + str(e))
    #print(inverter_entry)
    return inverter_entry
        
def get_inverter_detail(config, session): 
    if not config.get('inverter_id'):
        raise common.SolisControlException('Not connected')
    body = '{"id":"'+config['inverter_id']+'","sn":"'+config['inverter_sn']+'"}'
    header = common.prepare_post_header(config, body, common.DETAIL_ENDPOINT)
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    inverter_detail = None
    try:
        with make_request(session.post, config['api_url']+common.DETAIL_ENDPOINT, data = body, headers = header) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('success') and result.get('data'):
                    record = result['data']
                    common.add_fields(common.DETAIL_FIELDS, record, config)
                    inverter_detail = record
                else:
                    log.warning('Payload error getting inverter detail: %s %s' % (result.get('code'), result.get('msg')))
            else:
                log.warning('HTTP error getting inverter detail: %d %s' % (status, response.text))
    except RequestException as e:
        log.warning('Request exception getting inverter detail: ' + str(e))
    #print(json.dumps(inverter_detail, indent=2))
    return inverter_detail
        
def get_login_detail(config, session): 
    body = '{"userInfo":"'+config['solis_user_name']+'","passWord":"'+common.password_encode(config['solis_password'])+'"}'
    header = common.prepare_post_header(config, body, common.LOGIN_ENDPOINT)
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    login_detail = None
    try:
        with make_request(session.post, config['api_url']+common.LOGIN_ENDPOINT, data = body, headers = header) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                #result = response.json()
                result = common.json_strip(response.text) # deals with erroneous trailing commas in dicts
                if result.get('success') and result.get('data'):
                    record = result['data']
                    #config['login_token'] = result['csrfToken'] # alternative
                    common.add_fields(common.LOGIN_FIELDS, record, config)
                    login_detail = record
                else:
                    log.warning('Payload error getting login detail: %s %s' % (result.get('code'), result.get('msg')))
            else:
                log.warning('HTTP error getting login detail: %d %s' % (status, response.text))
    except RequestException as e:
        log.warning('Request exception getting login detail: ' + str(e))
    #print(login_detail)
    return login_detail

def set_inverter_params(config, session, params, charge=True, timeslot=0):
    # note sets one charge/discharge timeslot - keeps existing inverter data
    # note params is a dict with 'start' (HH:MM), 'end' (HH:MM) and optional 'amps' keys
    # charge should be True for charging, otherwise False for discharging
    # timeslot can be 0, 1 or 2
    if not config.get('login_token'):
        raise common.SolisControlException('Not logged in')
    check = common.check_all(config) # check time sync and current settings
    if check != 'OK':
        return check
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    set_times_msg = None                    
    try:
        body = common.prepare_body(config)
        headers = common.prepare_post_header(config, body, common.READ_ENDPOINT)
        headers['token'] = config['login_token']
        with make_request(session.post, config['api_url']+common.READ_ENDPOINT, data = body, headers = headers) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('code') == '0'  and result.get('data') and result['data'].get('msg'): 
                    inverter_data = result['data']['msg']
                else:
                    set_times_msg = 'Payload error getting charging/discharging times: %s' % (str(result))
            else:
                set_times_msg = 'HTTP error getting charging/discharging times: %d %s' % (status, response.text)
        if set_times_msg is not None:
            return set_times_msg
        
        #print(inverter_data)
        inverter_data = common.update_inverter_data(inverter_data, params, charge=charge, timeslot=timeslot)
        #print(inverter_data)
        
        body = common.prepare_body(config, inverter_data)
        headers = common.prepare_post_header(config, body, common.CONTROL_ENDPOINT)
        headers['token'] = config['login_token']
        with make_request(session.post, config['api_url']+common.CONTROL_ENDPOINT, data = body, headers = headers) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('code') == '0': 
                    set_times_msg = 'OK'
                else:
                    set_times_msg = 'Payload error setting charging/discharging times: %s' % (str(result))
            else:
                set_times_msg = 'HTTP error setting charging/discharging times: %d %s' % (status, response.text)
    except RequestException as e:
        set_times_msg = 'Request exception setting charging/discharging times: ' + str(e)
    return set_times_msg
    
def set_inverter_data(config, session, inverter_data=None):
    if not config.get('login_token'):
        raise common.SolisControlException('Not logged in')
    check = common.check_all(config) # check time sync and current settings
    if check != 'OK':
        return check
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    set_times_msg = None
    if inverter_data is None:
        inverter_data = common.DEFAULT_INVERTER_DATA
    try:
        body = common.prepare_body(config, inverter_data)
        headers = common.prepare_post_header(config, body, common.CONTROL_ENDPOINT)
        headers['token'] = config['login_token']
        with make_request(session.post, config['api_url']+common.CONTROL_ENDPOINT, data = body, headers = headers) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('code') == '0': 
                    set_times_msg = 'OK'
                else:
                    set_times_msg = 'Payload error setting charging/discharging times: %s' % (str(result))
            else:
                set_times_msg = 'HTTP error setting charging/discharging times: %d %s' % (status, response.text)
    except RequestException as e:
        set_times_msg = 'Request exception setting charging/discharging times: ' + str(e)
    return set_times_msg
    
def get_inverter_data(config, session):
    if not config.get('login_token'):
        raise common.SolisControlException('Not logged in')
    body = common.prepare_body(config)
    headers = common.prepare_post_header(config, body, common.READ_ENDPOINT)
    headers['token']= config['login_token']
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    inverter_data = None                    
    try:
        with make_request(session.post, config['api_url']+common.READ_ENDPOINT, data = body, headers = headers) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('code') == '0'  and result.get('data') and result['data'].get('msg'): 
                    inverter_data = result['data']['msg']
                else:
                    log.warning('Payload error getting charging/discharging times: %s' % (str(result)))
            else:
                log.warning('HTTP error getting charging/discharging times: %d %s' % (status, response.text))
    except RequestException as e:
        log.warning('Request exception getting charging/discharging times: ' + str(e))
    if not inverter_data:
        return None
    print(inverter_data)
    return inverter_data
        
def get_inverter_datetime(config, session):
    if not config.get('login_token'):
        raise common.SolisControlException('Not logged in')
    body = '{"inverterId":"'+config['inverter_id']+'","cid":"56"}'
    headers = common.prepare_post_header(config, body, common.READ_ENDPOINT)
    headers['token']= config['login_token']
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    inverter_datetime = None                    
    try:
        with make_request(session.post, config['api_url']+common.READ_ENDPOINT, data = body, headers = headers) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('code') == '0'  and result.get('data') and result['data'].get('msg'): 
                    inverter_datetime = datetime.fromisoformat(result['data']['msg'])
                    config['inverter_datetime'] = inverter_datetime
                    config['host_datetime'] = datetime.now()
                else:
                    log.warning('Payload error getting inverter time: %s' % (str(result)))
            else:
                log.warning('HTTP error getting inverter time: %d %s' % (status, response.text))
    except RequestException as e:
        log.warning('Request exception getting inverter time: ' + str(e))
    if not inverter_datetime:
        return None
    #print(inverter_datetime)
    return inverter_datetime
    
def set_inverter_datetime(config, session, inverter_datetime=None):
    if not config.get('login_token'):
        raise common.SolisControlException('Not logged in')
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    set_time_msg = None
    if inverter_datetime is None:
        inverter_datetime = datetime.now()
    else:
        if isinstance(inverter_datetime, str):
            inverter_datetime = datetime.fromisoformat(inverter_datetime)
        if not isinstance(inverter_datetime, datetime):
            raise SolisControlException('Bad inverter datetime -> %s' % str(inverter_datetime))
    try:
        value = inverter_datetime.strftime('%Y-%m-%d %H:%M:%S')
        body = '{"inverterId":"'+config['inverter_id']+'","cid":"56","value":"'+value+'"}'
        headers = common.prepare_post_header(config, body, common.CONTROL_ENDPOINT)
        headers['token'] = config['login_token']
        with make_request(session.post, config['api_url']+common.CONTROL_ENDPOINT, data = body, headers = headers) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('code') == '0': 
                    set_time_msg = 'OK'
                else:
                    set_time_msg = 'Payload error setting inverter time: %s' % (str(result))
            else:
                set_time_msg = 'HTTP error setting inverter time: %d %s' % (status, response.text)
    except RequestException as e:
        set_time_msg = 'Request exception setting inverter time: ' + str(e)
    return set_time_msg
       
def connect(config, session):
    if not get_inverter_entry(config, session):
        return False
    if not get_inverter_detail(config, session):
        return False
    if not get_login_detail(config, session):
        return False
    get_inverter_datetime(config, session)
    check = common.check_time(config) # default acceptable time difference = 1 min
    if check != 'OK':
        check = set_inverter_datetime(config, session)
    if check != 'OK':
        return False
    return True
                

        
