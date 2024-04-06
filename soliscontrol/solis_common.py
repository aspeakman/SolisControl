import hashlib
import hmac
import base64
import json
from datetime import datetime, timezone, time

""" Common module for Solis Cloud API access 
See https://oss.soliscloud.com/templet/SolisCloud%20Platform%20API%20Document%20V2.0.pdf

For inspiration and basic details of v2 control API
See https://github.com/stevegal/solis_control/
"""
    
LOGIN_ENDPOINT = '/v2/api/login'
CONTROL_ENDPOINT = '/v2/api/control'
INVERTER_ENDPOINT = '/v1/api/inverterList'
DETAIL_ENDPOINT = '/v1/api/inverterDetail'
DEFAULT_API_URL = 'https://www.soliscloud.com:13333'
ENERGY_AMP_HOUR = 0.05 # kWh added to battery for each amp hour charged
# Based on charging rule = 20A times 1 hour adds 1 kWh of charge – see https://www.youtube.com/watch?v=ps22E30OUEk

class SolisControlException(Exception):
    pass
            
def digest(body):
    return base64.b64encode(hashlib.md5(body.encode('utf-8')).digest()).decode('utf-8')
    
def password_encode(password):
    return hashlib.md5(password.encode('utf-8')).hexdigest()
        
def time_adjust(stime, minutes): 
    # add or subtract minutes from stime (a datetime.time object)
    sminutes = (stime.hour * 60) + stime.minute # start time as minutes from midnight
    rminutes = sminutes + minutes # result time as minutes from midnight
    return time(hour=int(rminutes/60), minute=int(rminutes%60), second=stime.second, microsecond=stime.microsecond)
        
def prepare_control_body(config, charge_start=None, charge_end=None, discharge_start=None, discharge_end=None):
    # set body of API v2 request to change charge and discharge time schedule 
    if not config.get('inverter_id'):
        raise SolisControlException('Not connected')
    charge_current = str(config['charge_period']['current'])
    discharge_current = str(config['discharge_period']['current'])
    if not charge_start and not charge_end: 
        charge_start = '00:00' # default no charging
        charge_end = '00:00'
    else:
        if not charge_start:
            charge_start = config['charge_period']['start'] # default use full period for charging
        elif charge_start < config['charge_period']['start'] or charge_start > config['charge_period']['end']:
            charge_start = config['charge_period']['start']
        if not charge_end:
            charge_end = config['charge_period']['end'] # default use full period for charging
        elif charge_end < charge_start or charge_end > config['charge_period']['end']:
            charge_end = config['charge_period']['end']
    if not discharge_start and not discharge_end:
        discharge_start = '00:00' # default no discharging
        discharge_end = '00:00'
    else:
        if not discharge_start:
            discharge_start = config['discharge_period']['start'] # default use full period for discharging
        elif discharge_start < config['discharge_period']['start'] or discharge_start > config['discharge_period']['end']:
            discharge_start = config['discharge_period']['start']
        if not discharge_end:
            discharge_end = config['discharge_period']['end'] # default use full period for discharging
        elif discharge_end < discharge_start or discharge_end > config['discharge_period']['end']:
            discharge_end = config['discharge_period']['end']
    body = '{"inverterId":"'+config['inverter_id']+'","cid":"103","value":"'
    body = body+charge_current+","+discharge_current+",%s,%s,%s,%s,"
    body = body+charge_current+","+discharge_current+",00:00,00:00,00:00,00:00,"
    body = body+charge_current+","+discharge_current+",00:00,00:00,00:00,00:00"
    body = body+'"}'
    return body % (charge_start, charge_end, discharge_start, discharge_end)
    
def energy_values(config):
    # return 4 values representing energy available from the battery
    if not config.get('battery_ods') or not config.get('battery_soc'):
        raise SolisControlException('No battery details from connection')
    unavailable_energy = config['battery_capacity'] * config['battery_ods'] / 100.0 # battery cannot discharge energy below Over Discharge SOC
    full_energy = config['battery_capacity'] - unavailable_energy # energy available if fully charged
    current_energy = (config['battery_soc'] * config['battery_capacity'] / 100.0) - unavailable_energy # currently available energy
    real_soc = current_energy / full_energy * 100.0 # real state of charge
    return unavailable_energy, full_energy, current_energy, real_soc
    
def charge_times(config, target_level):
    # calculate battery charge_start and end values required to reach a particular level of available energy (kwH)
    if target_level <= 0.0: # the target level is invalid
        return '00:00', '00:00'
    unavailable_energy, full_energy, current_energy, real_soc = energy_values(config)
    energy_gap = target_level - current_energy # additional energy required to reach target
    if energy_gap <= 0.0: # the target level is already attained or exceeded
        return '00:00', '00:00'
    if energy_gap > (full_energy - current_energy): # the target level is beyond the battery capacity
        energy_gap = full_energy - current_energy # set to max
    return start_end_times(config['charge_period']['current'], config['charge_period']['start'], energy_gap)
        
def discharge_times(config, target_level):
    # calculate battery discharge_start and end values required to reduce to a particular level of available energy (kwH)
    if target_level <= 0.0: # the target level is invalid
        return '00:00', '00:00'
    unavailable_energy, full_energy, current_energy, real_soc = energy_values(config)
    energy_gap = current_energy - target_level # surplus energy to dump in order to reach target
    if energy_gap <= 0.0: # the target level is already attained or exceeded
        return '00:00', '00:00'
    return start_end_times(config['discharge_period']['current'], config['discharge_period']['start'], energy_gap)
          
def start_end_times(current, period_start, energy_kwh): 
    # calculate battery end time values required to charge/discharge a particular amount of available energy (kwH)
    charge_minutes = 60.0 * energy_kwh / (current * ENERGY_AMP_HOUR) # minutes charging/discharging required to reach target
    return period_start, increment_hhmm(period_start, charge_minutes)
    
def increment_hhmm(hhmm, minutes):
    stime = time.fromisoformat(hhmm+':00')
    etime = time_adjust(stime, minutes)
    return etime.strftime('%H:%M')
    
def check_time(config, diff_mins=5.0):
    # time at inverter and host must be in sync
    host = config['host_datetime']
    inv = config['inverter_datetime']
    difference = float(abs((host-inv).total_seconds())) / 60.0
    if difference > diff_mins:
        return 'Inverter date/time (%s) more than %.1f minutes out of sync with host (%s)' % (inv.isoformat(), diff_mins, host.isoformat())
    return 'OK'
                
def prepare_post_header(config, body, canonicalized_resource):
    content_md5 = digest(body)
    content_type = "application/json"
    now = datetime.now(timezone.utc)
    date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
    encrypt_str = ("POST" + "\n"
        + content_md5 + "\n"
        + content_type + "\n"
        + date + "\n"
        + canonicalized_resource
    )
    hmac_obj = hmac.new(
        config['key_secret'].encode('utf-8'),
        msg=encrypt_str.encode('utf-8'),
        digestmod=hashlib.sha1
    )
    sign = base64.b64encode(hmac_obj.digest())
    authorization = "API " + config['key_id'] + ":" + sign.decode('utf-8')
    header = {
        "Content-MD5":content_md5,
        "Content-Type":content_type,
        "Date":date,
        "Authorization":authorization
    }
    return header
                        
def check_current(config):
    # current for charging/discharging must be below inverter max and also below battery_max_current
    if not config.get('inverter_power'):
        raise SolisControlException('No battery details from connection')
    charge_current = config['charge_period']['current']
    discharge_current = config['discharge_period']['current']
    inverter_max = config['inverter_max_current'] - config['inverter_power']
    battery_max = config['battery_max_current'] - config['inverter_power'] # was config['battery_discharge_max']
    if charge_current > battery_max: 
        return 'Charge current %.1fA > battery max %.1fA' % (charge_current, battery_max)
    if discharge_current > battery_max: 
        return 'Discharge current %.1fA > battery max %.1fA' % (discharge_current, battery_max)
    if charge_current > inverter_max:
        return 'Charge current %.1fA > inverter max %.1fA' % (charge_current, inverter_max)
    if discharge_current > inverter_max:
        return 'Discharge current %.1fA > inverter max %.1fA' % (discharge_current, inverter_max)
    return 'OK'
    
def check_all(config, diff_mins=5.0):
    # check time sync and current settings
    check = check_time(config, diff_mins)
    if check != 'OK':
        return check
    check = check_current(config)
    if check != 'OK':
        return check
    return 'OK'

def print_status(config):
    print ('ID:', config['inverter_id'])
    print ('SN:', config['inverter_sn'])
    
    print ('Inverter HH:MM:', config['inverter_datetime'].strftime('%H:%M'))
    
    print('Check Time:', check_time(config))
    
    print ('Battery SOC:', config['battery_soc'])
    print ('Over Discharge SOC:', config['battery_ods'])
    print ('Battery Type:', config['battery_type'])
    print ('Login Token:', config['login_token'])
    
    unavailable_energy, full_energy, current_energy, real_soc = energy_values(config)
    print ('Available Energy: %.1fkWh (%.0f%% of max %.1fkWh)' % (current_energy, real_soc, full_energy))
    
    print('Check Current:', check_current(config))
    
    print ('Notional morning charging times to reach 1,3,7 kWh available')
    print(charge_times(config, 1.0))
    print(charge_times(config, 3.0))
    print(charge_times(config, 7.0))
    
    print ('Notional evening discharging times to reach 1,3,7 kWh available')
    print(discharge_times(config, 1.0))
    print(discharge_times(config, 3.0))
    print(discharge_times(config, 7.0))
    
           

        
        
