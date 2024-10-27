from requests import Session, RequestException
from http import HTTPStatus
import logging
import yaml

import solis_common as common

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
    body = '{"stationId":"'+config['station_id']+'"}'
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
                      if record.get('stationId', '') == config['station_id']:
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
    #print(inverter_detail)
    return inverter_detail
        
def get_login_detail(config, session): 
    body = '{"userInfo":"'+config['user_name']+'","passWord":"'+common.password_encode(config['password'])+'"}'
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
    return login_detail

def set_inverter_charge_times(config, session, start=None, end=None):
    existing = get_inverter_times(config, session)
    if isinstance(existing, dict):
        return set_inverter_times(config, session, charge_start=start, charge_end=end, 
            discharge_start=existing['discharge_start'], discharge_end=existing['discharge_end'])
    return 'Cannot get inverter times'
    
def set_inverter_discharge_times(config, session, start=None, end=None):
    existing = get_inverter_times(config, session)
    if isinstance(existing, dict):
        return set_inverter_times(config, session, discharge_start=start, discharge_end=end, 
            charge_start=existing['charge_start'], charge_end=existing['charge_end'])
    return 'Cannot get inverter times'
    
def set_inverter_times(config, session, charge_start=None, charge_end=None, discharge_start=None, discharge_end=None):
    if not config.get('login_token'):
        raise common.SolisControlException('Not logged in')
    check = common.check_all(config) # check time sync and current settings
    if check != 'OK':
        return check
    body = common.prepare_control_body(config, charge_start, charge_end, discharge_start, discharge_end)
    headers = common.prepare_post_header(config, body, common.CONTROL_ENDPOINT)
    headers['token']= config['login_token']
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    set_times_msg = None                    
    try:
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
    
def get_inverter_times(config, session):
    if not config.get('login_token'):
        raise common.SolisControlException('Not logged in')
    body = common.prepare_read_body(config)
    headers = common.prepare_post_header(config, body, common.READ_ENDPOINT)
    headers['token']= config['login_token']
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    inverter_times = None                    
    try:
        with make_request(session.post, config['api_url']+common.READ_ENDPOINT, data = body, headers = headers) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('code') == '0'  and result.get('data') and result['data'].get('msg'): 
                    inverter_times = result['data']['msg']
                else:
                    log.warning('Payload error getting charging/discharging times: %s' % (str(result)))
            else:
                log.warning('HTTP error getting charging/discharging times: %d %s' % (status, response.text))
    except RequestException as e:
        log.warning('Request exception getting charging/discharging times: ' + str(e))
    if not inverter_times:
        return None
    ivt = inverter_times.split(',')
    return { 'charge_start': ivt[2][:5], 'charge_end': ivt[2][6:], 'charge_amps': ivt[0],
        'discharge_start': ivt[3][:5], 'discharge_end': ivt[3][6:], 'discharge_amps': ivt[1] }
    
def connect(config, session):
    if not get_inverter_entry(config, session):
        return False
    if not get_inverter_detail(config, session):
        return False
    if not get_login_detail(config, session):
        return False
    return True
    
def main(charge_minutes=None, discharge_minutes=None, silent=False, test=True):
    with open('secrets.yaml', 'r') as file:
        secrets = yaml.safe_load(file)
    with open('main.yaml', 'r') as file:
        config = yaml.safe_load(file)
    config.update(secrets)    

    with get_session() as session:
    
        connect(config, session)
        
        if not silent:
            common.print_status(config, test)
            
        existing = get_inverter_times(config, session)
        if existing:
            if not silent:
                print ('Current Charge Period: %s - %s (%sA)' % (existing['charge_start'], existing['charge_end'], existing['charge_amps']))
                print ('Current Discharge Period: %s - %s (%sA)' % (existing['discharge_start'], existing['discharge_end'], existing['discharge_amps']))

            if charge_minutes is not None or discharge_minutes is not None:
                if charge_minutes is None: 
                    cstart = existing['charge_start']; cend = existing['charge_end'] 
                else:
                    cstart, cend = common.start_end_times(config['charge_period']['start'], charge_minutes, config['charge_period']['end'])
                if discharge_minutes is None: 
                    dstart = existing['discharge_start']; dend = existing['discharge_end'] 
                else:
                    dstart, dend = common.start_end_times(config['discharge_period']['start'], discharge_minutes, config['discharge_period']['end'])
                cstart, cend, dstart, dend = common.limit_times(config, cstart, cend, dstart, dend)
                if test:
                    result = 'OK'
                else:
                    result = set_inverter_times(config, session, cstart, cend, dstart, dend)
                if result == 'OK':
                    action = 'Notional' if test else 'Actual'
                    print (action, 'Charge Times Set:', cstart, cend)
                    print (action, 'Discharge Times Set:', dstart, dend)
                else:
                    print ('Error:', result)
                
if __name__ == "__main__":

    import argparse
    
    parser = argparse.ArgumentParser(description='Status and/or set charging/discharging times for the Solis API client',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-s", "--silent", help="no status messages are printed out", action='store_true')
    parser.add_argument("-t", "--test", help="test mode, no actions are taken", action='store_true')
    parser.add_argument("charge", help="Charging duration in minutes (zero means no charging)", type=int, nargs='?')
    parser.add_argument("discharge", help="Discharging duration in minutes for the action (zero means no discharging)", type=int, nargs='?')
    args = parser.parse_args()

    main(args.charge, args.discharge, args.silent, args.test)
    
        
        
        
        
