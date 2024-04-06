import logging
from requests import Session
from http import HTTPStatus
from datetime import datetime
import yaml

import solis_common as common

""" Client module for Solis Cloud API access via requests class
See https://oss.soliscloud.com/templet/SolisCloud%20Platform%20API%20Document%20V2.0.pdf

For scant details of v2 control API
See https://github.com/stevegal/solis_control/
                                                                
Note should work on Home Assistant pyscript ie requests are wrapped with task.executor
See https://hacs-pyscript.readthedocs.io/en/latest/index.html

However seems to be a problem with imported classes
throws TypeError: 'EvalFunc' object is not callable"""

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

class SolisAPIClient: 
    """ Client for read/write from Solis Cloud API """
    
    def __init__(self, config):
                
        self.config = config
        if not self.config.get('api_url'):
            self.config['api_url'] = common.DEFAULT_API_URL
        
        self._session = Session()
        
        self.inverter_entry = None
        self.inverter_detail = None
        self.login_detail = None
            
        self._get_inverter_entry()
        self._get_inverter_detail()
        self._get_login_detail()
        
        msg = 'Connected to %s' % (self.station_name)
        log.info(msg)
            
    def __del__(self):
        if hasattr(self, '_session') and self._session is not None:
            self._session.close()
    
    @property
    def inverter_id(self):   
        return self.inverter_entry['id']
        
    @property
    def inverter_sn(self):   
        return self.inverter_entry['sn']
    
    @property
    def station_name(self):   
        return self.inverter_entry['stationName']
        
    @property
    def battery_type(self):   
        return self.inverter_detail['batteryType']
        
    @property
    def battery_soc(self):   
        return self.inverter_detail['batteryCapacitySoc']
        
    @property
    def battery_ods(self):   
        return self.inverter_detail['socDischargeSet']
        
    @property
    def inverter_power(self):   
        return self.inverter_detail['power']
        
    @property
    def login_token(self):   
        return self.login_detail['token']
        
    def _get_inverter_entry(self): # note has to work - exception if it does not
        body = '{"stationId":"'+self.config['station_id']+'"}'
        header = common.prepare_post_header(self.config, body, common.INVERTER_ENDPOINT)
        with make_request(self._session.post, self.config['api_url']+common.INVERTER_ENDPOINT, data = body, headers = header) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('success') and result.get('data'):
                    for record in result['data']['page']['records']:
                      if record.get('id') and record.get('sn'):
                        self.config['inverter_id'] = record['id']
                        self.config['inverter_sn'] = record['sn']
                        self.config['station_name'] = record['stationName']
                        self.inverter_entry = record
                        return
                else:
                    err_msg = 'Payload error getting inverter entry: %s %s' % (result.get('code'), result.get('msg'))
            else:
                err_msg = 'HTTP error getting inverter entry: %d %s' % (status, response.text)
            raise SolisAPIException(err_msg)
            
    def _get_inverter_detail(self): # note has to work - exception if it does not
        if not self.inverter_entry:
            raise common.SolisControlException('Not connected')
        body = '{"id":"'+self.config['inverter_id']+'","sn":"'+self.config['inverter_sn']+'"}'
        header = common.prepare_post_header(self.config, body, common.DETAIL_ENDPOINT)
        with make_request(self._session.post, self.config['api_url']+common.DETAIL_ENDPOINT, data = body, headers = header) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('success') and result.get('data'):
                    record = result['data']
                    self.config['battery_type'] = record['batteryType']
                    self.config['battery_soc'] = record['batteryCapacitySoc']
                    self.config['battery_ods'] = record['socDischargeSet']
                    #self.config['battery_discharge_max'] = record['batteryDischargeLimiting'] # does this value change?
                    self.config['inverter_power'] = record['power']
                    #print(record.get('daylight', 'no daylight'))
                    #print(record.get('daylightSwitch', 'no daylight switch'))
                    #print(record.get('timeZone', 'no timezone'))
                    self.config['inverter_datetime'] = datetime.fromtimestamp(float(record['dataTimestamp'])/1000.0)
                    self.config['host_datetime'] = datetime.now()
                    self.inverter_detail = record
                    return
                else:
                    err_msg = 'Payload error getting inverter detail: %s %s' % (result.get('code'), result.get('msg'))
            else:
                err_msg = 'HTTP error getting inverter detail: %d %s' % (status, response.text)
            raise SolisAPIException(err_msg)
            
    def _get_login_detail(self): # note has to work - exception if it does not
        body = '{"userInfo":"'+self.config['user_name']+'","passWord":"'+ common.password_encode(self.config['password'])+'"}'
        header = common.prepare_post_header(self.config, body, common.LOGIN_ENDPOINT)
        with make_request(self._session.post, self.config['api_url']+common.LOGIN_ENDPOINT, data = body, headers = header) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('success') and result.get('csrfToken'): 
                    self.config['login_token'] = result['csrfToken']
                    # note also available as result['data']['token']
                    self.login_detail = result['data']
                    return
                else:
                    err_msg = 'Payload error getting login token: %s %s' % (result.get('code'), result.get('msg'))
            else:
                err_msg = 'HTTP error getting login token: %d %s' % (status, response.text)
            raise SolisAPIException(err_msg)
            
    def set_inverter_times(self, charge_start=None, charge_end=None, discharge_start=None, discharge_end=None):
        check = common.check_all(self.config)
        if check != 'OK':
            return check
        body = common.prepare_control_body(self.config, charge_start, charge_end, discharge_start, discharge_end)
        headers = common.prepare_post_header(self.config, body, common.CONTROL_ENDPOINT)
        headers['token']= self.login_token
        with make_request(self._session.post, self.config['api_url']+common.CONTROL_ENDPOINT, data = body, headers = headers) as response:
            status = response.status_code
            if status == HTTPStatus.OK:
                result = response.json()
                if result.get('code') == '0': 
                    return 'OK'
                else:
                    return 'Payload error setting charging times: %s' % (str(result))
            else:
                return 'HTTP error setting charging times: %d %s' % (status, response.text)

# creates and initializes an instance
def create_client(config):
    # Create an instance using the constructor
    return SolisAPIClient(config)

def main(action=None, minutes=0, silent=False):
    with open('secrets.yaml', 'r') as file:
        secrets = yaml.safe_load(file)
    with open('main.yaml', 'r') as file:
        config = yaml.safe_load(file)
    config.update(secrets)    

    client = SolisAPIClient(config)
    config = client.config
    
    if not silent:
        common.print_status(config)
        
    if action:
        if minutes <= 0:
            result = 'Invalid ' + action + ' minutes ' + str(minutes)
        elif action == 'charge':
            start = config['charge_period']['start']
            end = common.increment_hhmm(start, int(minutes))
            result = set_inverter_times(config, session, charge_start = start, charge_end = end)
        elif action == 'discharge':
            start = config['discharge_period']['start']
            end = common.increment_hhmm(start, int(minutes))
            result = set_inverter_times(config, session, discharge_start = start, discharge_end = end)
        else:  
            result = 'Invalid action ' + action
        if result == 'OK':
            print (action.capitalize(), 'Times Set:', start, end)
        else:
            print ('Error:', result)
                
if __name__ == "__main__":

    import argparse
    
    action_choices = [ 'charge', 'discharge' ]
    parser = argparse.ArgumentParser(description='Status and/or action for the Solis client',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-s", "--silent", help="no status messages are printed out", action='store_true')
    parser.add_argument("action", help="Action for the Solis client", choices=action_choices, nargs='?', default=None)
    parser.add_argument("minutes", help="Duration in minutes for the action", type=int, nargs='?', default=0)
    args = parser.parse_args()

    main(args.action, args.minutes, args.silent)
    
        
        
        
        
