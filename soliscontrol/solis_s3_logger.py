from requests import Session, RequestException
import logging
import yaml
import time

""" Check the local S3 data logger is working and if necessary restart it to reconnect to Solis servers

Requires configuration settings in secrets.yaml:
s3_username: # default is 'admin'
s3_password: # same as WiFi password
s3_ip: # local IP address of logger
                                                                
For use with Pyscript 
connection state is passed between methods in the config dict
and requests are wrapped with task.executor
See https://hacs-pyscript.readthedocs.io/en/latest/index.html"""

#Also see https://www.youtube.com/watch?v=JNnSJZCg39A for manual reboot

DEFAULT_USERNAME = 'admin'
DEFAULT_PASSWORD = '123456789'
DEFAULT_IP = '10.10.100.254'
USERNAME_FIELD = 's3_username'
PASSWORD_FIELD = 's3_password'
IP_FIELD = 's3_ip'

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
        
def sleep(secs):
    if PYSCRIPT:
        return task.sleep(secs)
    else:
        return time.sleep(secs)
        
def get_session():
    return Session()
    
def get_inverter_data(config, session): 
    user = config.get(USERNAME_FIELD, DEFAULT_USERNAME)
    pwd = config.get(PASSWORD_FIELD, DEFAULT_PASSWORD)
    url = 'http://' + config.get(IP_FIELD, DEFAULT_IP) + '/inverter.cgi'
    
    inverter_data = None
    try:
        with make_request(session.get, url, auth=(user, pwd)) as response:
            if response.ok:
                result = response.text.strip('\x00\r\n').split(';')
                inverter_data = {}
                inverter_data['Serial'] = result[0]
                inverter_data['Firmware'] = result[1]
                inverter_data['Model'] = result[2]
                inverter_data['Temperature_C'] = float(result[3])
                inverter_data['Current_Power_W'] = float(result[4])
                inverter_data['Yield_Today_kWh'] = float(result[5])
                inverter_data['Total_Yield_kWh'] = float(result[6])
                inverter_data['Alerts'] = result[7] not in [ 'NO', 'No', 'no' ]
                config['inverter'] = inverter_data
            else:
                log.warning('HTTP error getting inverter data: %d %s' % (response.status_code, response.text))
    except RequestException as e:
        log.warning('Request exception getting inverter data: ' + str(e))
    return inverter_data
        
def get_device_data(config, session): 
    user = config.get(USERNAME_FIELD, DEFAULT_USERNAME)
    pwd = config.get(PASSWORD_FIELD, DEFAULT_PASSWORD)
    url = 'http://' + config.get(IP_FIELD, DEFAULT_IP) + '/moniter.cgi'
    
    device_data = None
    try:
        with make_request(session.get, url, auth=(user, pwd)) as response:
            if response.ok:
                result = response.text.strip('\x00\r\n').split(';')
                device_data = {}
                device_data['Serial'] = result[0]
                device_data['Firmware'] = result[1]
                mode = 'None'
                if result[2] == 'Enable':
                    mode = 'AP'
                elif result[6] == 'Enable':
                    mode = 'STA'
                device_data['Mode'] = mode
                device_data['SSID'] = result[7]
                device_data['Signal_%'] = result[8] # result can be non-numeric ? none?
                device_data['IP'] = result[9]
                device_data['MAC'] = result[10]
                device_data['Connected'] = result[11] == 'Connected' or result[12] == 'Connected'
                config['device'] = device_data 
            else:
                log.warning('HTTP error getting device data: %d %s' % (response.status_code, response.text))
    except RequestException as e:
        log.warning('Request exception getting device data: ' + str(e))
    return device_data
        
def restart(config, session):
    user = config.get(USERNAME_FIELD, DEFAULT_USERNAME)
    pwd = config.get(PASSWORD_FIELD, DEFAULT_PASSWORD)
    url = 'http://' + config.get(IP_FIELD, DEFAULT_IP) + '/restart.cgi'
    
    try:
        with make_request(session.get, url, auth=(user, pwd)) as response:
            if not response.ok:
                return 'HTTP error during restart: %d %s' % (response.status_code, response.text)
    except RequestException as e:
        return 'Request exception during restart: ' + str(e)
        
    return 'OK'
    
def check_logger(config, session): # does basic check and restart if necessary
    data = get_device_data(config, session)
    if data:
        if data['Connected'] is False:
            log.info('Inverter not connected to logger - restarting data logger')
            restarted = restart(config, session)
            if restarted == 'OK':
                log.info('Restarted OK')
                sleep(15)
            else:
                log.warning(restarted)
        else:
            log.info('Inverter connected to logger - OK')
    
def connect(config, session):
    
    if not get_inverter_data(config, session):
        return False
        
    if not get_device_data(config, session):
        return False
    
    return True
    
def main(force=False, test=True, verbose=False):

    with open('secrets.yaml', 'r') as file:
        config = yaml.safe_load(file)
    
    with get_session() as session:
    
        connected = connect(config, session)
        
        if connected:
        
            if verbose:
                print ('Inverter ->', config['inverter'])
                print ('Device ->', config['device'])
                
            if force or (not test and config['device']['Connected'] is False):
            
                print ('Restarting ...')
                
                restarted = restart(config, session)
                
                if restarted == 'OK':
                    sleep(10.0)
                    print ('Successfully restarted')
                else:
                    print ('Error restarting: %s' % restarted)

        else:
                
            print ('Cannot connect')

                
if __name__ == "__main__":

    import argparse
    
    parser = argparse.ArgumentParser(description='Check access to a local Solis S3 data logger and if necessary restart it',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-f", "--force", help="force restart, even if not necessary", action='store_true')
    parser.add_argument("-t", "--test", help="test mode, no actions are taken", action='store_true')
    parser.add_argument("-v", "--verbose", help="additional status messages are printed out", action='store_true')
    args = parser.parse_args()

    main(args.force, args.test, args.verbose)
    
        
        
        
        
