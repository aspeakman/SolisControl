import asyncio
from aiohttp import ClientError
from http import HTTPStatus
import logging
from datetime import datetime

import solis_common as common

""" Client module for Solis Cloud API access via aiohttp library and asyncio
See https://oss.soliscloud.com/templet/SolisCloud%20Platform%20API%20Document%20V2.0.pdf

For scant details of v2 control API
See https://github.com/stevegal/solis_control/
                                                                
Note should work on Home Assistant pyscript BUT seems to be a problem with imported classes
throws TypeError with EvalFunc"""

try:
    task.executor()
except NameError:
    PYSCRIPT = False
except TypeError:
    PYSCRIPT = True
else: # default
    PYSCRIPT = False
    
if not PYSCRIPT:
    from aiohttp import ClientSession
    log = logging.getLogger(__name__)
else:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

def get_session():
    if PYSCRIPT:
        return async_get_clientsession(hass)
    else:
        return ClientSession()
                                
async def get_inverter_entry(config, session): 
    body = '{"stationId":"'+config['station_id']+'"}'
    header = common.prepare_post_header(config, body, common.INVERTER_ENDPOINT)
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    inverter_entry = None
    try:    
        async with session.post(config['api_url']+common.INVERTER_ENDPOINT, data = body, headers = header) as response:
            status = response.status
            if status == HTTPStatus.OK:
                result = await response.json()
                if result.get('success') and result.get('data'):
                    for record in result['data']['page']['records']:
                      if record.get('id') and record.get('sn'):
                        config['inverter_id'] = record['id']
                        config['inverter_sn'] = record['sn']
                        config['station_name'] = record['stationName']
                        inverter_entry = record
                else:
                    log.warning('Payload error getting inverter entry: %s %s' % (result.get('code'), result.get('msg')))
            else:
                log.warning('HTTP error getting inverter entry: %d %s' % (status, await response.text()))
    except ClientError as e:
        log.warning('Client error getting inverter entry: ' + str(e))
    return inverter_entry
        
async def get_inverter_detail(config, session): 
    if not config.get('inverter_id'):
        raise common.SolisControlException('Not connected')
    body = '{"id":"'+config['inverter_id']+'","sn":"'+config['inverter_sn']+'"}'
    header = common.prepare_post_header(config, body, common.DETAIL_ENDPOINT)
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    inverter_detail = None
    try:
        async with session.post(config['api_url']+common.DETAIL_ENDPOINT, data = body, headers = header) as response:
            status = response.status
            if status == HTTPStatus.OK:
                result = await response.json()
                if result.get('success') and result.get('data'):
                    record = result['data']
                    config['battery_type'] = record['batteryType']
                    config['battery_soc'] = record['batteryCapacitySoc']
                    config['battery_ods'] = record['socDischargeSet']
                    #config['battery_discharge_max'] = record['batteryDischargeLimiting'] # does this value change?
                    config['inverter_power'] = record['power']
                    #print(record.get('daylight', 'no daylight'))
                    #print(record.get('daylightSwitch', 'no daylight switch'))
                    #print(record.get('timeZone', 'no timezone'))
                    config['inverter_datetime'] = datetime.fromtimestamp(float(record['dataTimestamp'])/1000.0)
                    config['host_datetime'] = datetime.now()
                    inverter_detail = record
                else:
                    log.warning('Payload error getting inverter detail: %s %s' % (result.get('code'), result.get('msg')))
            else:
                log.warning('HTTP error getting inverter detail: %d %s' % (status, await response.text()))
    except ClientError as e:
        log.warning('Client error getting inverter detail: ' + str(e))
    return inverter_detail
        
async def get_login_detail(config, session): 
    body = '{"userInfo":"'+config['user_name']+'","passWord":"'+common.password_encode(config['password'])+'"}'
    header = common.prepare_post_header(config, body, common.LOGIN_ENDPOINT)
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    login_detail = None
    try:
        async with session.post(config['api_url']+common.LOGIN_ENDPOINT, data = body, headers = header) as response:
            status = response.status
            if status == HTTPStatus.OK:
                result = await response.json()
                if result.get('success') and result.get('csrfToken'): 
                    config['login_token'] = result['csrfToken']
                    login_detail = result['data']
                else:
                    log.warning('Payload error getting login detail: %s %s' % (result.get('code'), result.get('msg')))
            else:
                log.warning('HTTP error getting login detail: %d %s' % (status, await response.text()))
    except ClientError as e:
        log.warning('Client error getting login detail: ' + str(e))
    return login_detail
            
async def set_inverter_times(config, session, charge_start=None, charge_end=None, discharge_start=None, discharge_end=None):
    if not config.get('login_token'):
        return 'Not logged in'
    check = common.check_all(config) # check time sync and current settings
    if check != 'OK':
        return check
    body = common.control_body(config, charge_start, charge_end, discharge_start, discharge_end)
    headers = common.prepare_post_header(config, body, common.CONTROL_ENDPOINT)
    headers['token']= config['login_token']
    if not config.get('api_url'):
        config['api_url'] = common.DEFAULT_API_URL
    set_times_msg = None
    try:
        async with session.post(config['api_url']+common.CONTROL_ENDPOINT, data = body, headers = headers) as response:
            status = response.status
            if status == HTTPStatus.OK:
                result = await response.json()
                if result.get('code') == '0': 
                    set_times_msg = 'OK'
                else:
                    set_times_msg = 'Payload error setting charging times: %s' % (str(result))
            else:
                set_times_msg = 'HTTP error setting charging times: %d %s' % (status, await response.text())
    except ClientError as e:
        set_times_msg = 'Client error getting login detail: ' + str(e)
    return set_times_msg
    
async def connect(config, session):
    if not await get_inverter_entry(config, session):
        return False
    if not await get_inverter_detail(config, session):
        return False
    if not await get_login_detail(config, session):
        return False
    return True
    
async def main(action=None, minutes=0, silent=False):
    with open('secrets.yaml', 'r') as file:
        secrets = yaml.safe_load(file)
    with open('main.yaml', 'r') as file:
        config = yaml.safe_load(file)
    config.update(secrets)    

    async with get_session() as session:
    
        await connect(config, session)
        
        if not silent:
            common.print_status(config)
        
        if action:
            if minutes <= 0:
                result = 'Invalid ' + action + ' minutes ' + str(minutes)
            elif action == 'charge':
                start = config['charge_period']['start']
                end = common.increment_hhmm(start, int(minutes))
                result = await set_inverter_times(config, session, charge_start = start, charge_end = end)
            elif action == 'discharge':
                start = config['discharge_period']['start']
                end = common.increment_hhmm(start, int(minutes))
                result = await set_inverter_times(config, session, discharge_start = start, discharge_end = end)
            else:  
                result = 'Invalid action ' + action
            if result == 'OK':
                print (action.capitalize(), 'Times Set:', start, end)
            else:
                print ('Error:', result)

if __name__ == "__main__":

    import argparse
    
    action_choices = [ 'charge', 'discharge' ]
    parser = argparse.ArgumentParser(description='Status and/or action for the Solis API client',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-s", "--silent", help="no status messages are printed out", action='store_true')
    parser.add_argument("action", help="Action for the Solis API client", choices=action_choices, nargs='?', default=None)
    parser.add_argument("minutes", help="Duration in minutes for the action", type=int, nargs='?', default=0)
    args = parser.parse_args()

    loop = asyncio.get_event_loop_policy().get_event_loop()
    loop.run_until_complete(main(args.action, args.minutes, args.silent))
    
        
        
        
        
