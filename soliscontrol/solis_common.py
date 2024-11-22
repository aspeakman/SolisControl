import hashlib
import hmac
import base64
import json
from datetime import datetime, timezone, time
from random import randint
import re

""" Common module for Solis Cloud API access
See monitoring API https://oss.soliscloud.com/templet/SolisCloud%20Platform%20API%20Document%20V2.0.pdf
and separate control API https://oss.soliscloud.com/doc/SolisCloud%20Device%20Control%20API%20V2.0.pdf

For inspiration and basic details of how to configure requests
See https://github.com/stevegal/solis_control/
"""
    
LOGIN_ENDPOINT = '/v2/api/login'
CONTROL_ENDPOINT = '/v2/api/control'
READ_ENDPOINT = '/v2/api/atRead'
INVERTER_ENDPOINT = '/v1/api/inverterList'
DETAIL_ENDPOINT = '/v1/api/inverterDetail'
DEFAULT_API_URL = 'https://www.soliscloud.com:13333'
ENERGY_AMP_HOUR = 0.05 # kWh added to battery for each amp hour charged
# Based on charging rule = 20A times 1 hour adds 1 kWh of charge – see https://www.youtube.com/watch?v=ps22E30OUEk
ENTRY_FIELDS = {
    'id': 'inverter_id',
    'sn': 'inverter_sn',
    'stationName': 'station_name',
}
DETAIL_FIELDS = {
    'batteryType': 'battery_type',
    'batteryCapacitySoc': 'battery_soc',
    'socDischargeSet': 'battery_ods',
    'power': 'inverter_power',
    'eToday': 'energy_today',
}
LOGIN_FIELDS = {
    'token': 'login_token',
}

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
    return time(hour=int(rminutes/60), minute=int(rminutes%60))
    
def time_diff(stime, etime): 
    # difference in minutes between two times (datetime.time objects)
    sminutes = (stime.hour * 60) + stime.minute # start time as minutes from midnight
    eminutes = (etime.hour * 60) + etime.minute # end time as minutes from midnight
    if eminutes >= sminutes:
        return eminutes - sminutes
    else:
        return 24 * 60 - sminutes + eminutes # eg 23:00 to 01:00
    
def limit_times(config_period, start=None, end=None):
    # limit charging/discharging times so they are always within allowed periods
    if start == '00:00' and end == '00:00':
        pass
    elif not start and not end: 
        start = '00:00' # default no charging/discharging
        end = '00:00'
    else:
        if not start:
            start = config_period['start'] # default use full period for charging/discharging
        elif start < config_period['start'] or start > config_period['end']:
            start = config_period['start']
        if not end or end == '00:00':
            end = config_period['end'] # default use full period for charging/discharging
        elif end < start or end > config_period['end']:
            end = config_period['end']
    return start, end
        
"""def prepare_control_body(config, charge_start=None, charge_end=None, discharge_start=None, discharge_end=None):
    # set body of API v2 request to change charge and discharge time schedule 
    # derived from https://github.com/hultenvp/solis-sensor/discussions/246
    # and https://github.com/stevegal/solis_control
    # and https://oss.soliscloud.com/doc/SolisCloud%20Device%20Control%20API%20V2.0.pdf
    # format of 'value' string is:
    # charge_current1,discharge_current1,charge_start1,charge_end1,discharge_start1,discharge_end1,
    # etc for 3 time slots
    if not config.get('inverter_id'):
        raise SolisControlException('Not connected')
    charge_current = str(config['charge_period']['current'])
    discharge_current = str(config['discharge_period']['current'])
    charge_start, charge_end, discharge_start, discharge_end = limit_times(config, charge_start, charge_end, discharge_start, discharge_end)
    body = '{"inverterId":"'+config['inverter_id']+'","cid":"103","value":"'
    body = body+charge_current+","+discharge_current+",%s,%s,%s,%s,"
    body = body+charge_current+","+discharge_current+",00:00,00:00,00:00,00:00,"
    body = body+charge_current+","+discharge_current+",00:00,00:00,00:00,00:00"
    body = body+'"}'
    return body % (charge_start, charge_end, discharge_start, discharge_end)"""
    
def prepare_body(config, inverter_data=None):
    # set body of API v2 request to read or alter charge and discharge time schedule 
    # derived from https://github.com/hultenvp/solis-sensor/discussions/246
    # and https://github.com/stevegal/solis_control
    # and https://oss.soliscloud.com/doc/SolisCloud%20Device%20Control%20API%20V2.0.pdf
    # format of inverter_data is:
    # charge_current1,discharge_current1,charge_start1,charge_end1,discharge_start1,discharge_end1,
    # etc for 2 and 3 time slots
    if not config.get('inverter_id'):
        raise SolisControlException('Not connected')
    if inverter_data:
        inverter_data = inverter_data.replace('-', ',')
        ivt = inverter_data.split(',')
        if len(ivt) != 18:
            raise SolisControlException('Bad inverter data: len != 18 -> %s' % inverter_data)
        return '{"inverterId":"'+config['inverter_id']+'","cid":"103","value":"'+inverter_data+'"}'
    else:
        return '{"inverterId":"'+config['inverter_id']+'","cid":"103"}'
    
def extract_inverter_params(inverter_data, charge=True, timeslot=0):
    # get one entry from the full inverter_data string (which has charge/discharge time and amp settings for 3 time slots)
    # charge should be True for charging, otherwise False for discharging
    # timeslot can be 0, 1 or 2
    inverter_data = inverter_data.replace('-', ',')
    ivt = inverter_data.split(',')
    if len(ivt) != 18:
        raise SolisControlException('Bad inverter data: len != 18 -> %s' % inverter_data)
    if timeslot < 0 or timeslot > 2:
        raise SolisControlException('Bad time slot: should be 0, 1 or 2 -> %d' % timeslot)
    offset = timeslot * 6
    if charge:
        return { 'start': ivt[offset+2], 'end': ivt[offset+3], 'amps': ivt[offset+0] }
    else: # discharge
        return { 'start': ivt[offset+4], 'end': ivt[offset+5], 'amps': ivt[offset+1] }
        
def setup_params(config_period, start, end):
    # params dict - limit times and add in amps data
    s, e = limit_times(config_period, start, end)
    return { 'start': s, 'end': e, 'amps': str(config_period['current']) }
        
def update_inverter_data(inverter_data, params, charge=True, timeslot=0):
    # update one entry in the full inverter_data string (which has charge/discharge time and amp settings for 3 time slots)
    # note params is a dict with 'start' (HH:MM), 'end' (HH:MM) and optional 'amps' keys
    # charge should be True for charging, otherwise False for discharging
    # timeslot can be 0, 1 or 2
    inverter_data = inverter_data.replace('-', ',')
    ivt = inverter_data.split(',')
    if len(ivt) != 18:
        raise SolisControlException('Bad inverter data: len != 18 -> %s' % inverter_data)
    if not params or 'start' not in params or 'end' not in params:
        raise SolisControlException("Bad params: requires 'start' and 'end' keys")
    if timeslot < 0 or timeslot > 2:
        raise SolisControlException('Bad time slot: should be 0, 1 or 2 -> %d' % timeslot)
    offset = timeslot * 6
    if charge:
        ivt[offset+2] = params['start'] 
        ivt[offset+3] = params['end']  
        if 'amps' in params:
            ivt[offset+0] = str(params['amps'])
    else: # discharge
        ivt[offset+4] = params['start'] 
        ivt[offset+5] = params['end']  
        if 'amps' in params:
            ivt[offset+1] = str(params['amps'])
    return ','.join(ivt)
    
def energy_values(config):
    # return 4 values representing energy available from the battery
    if not config.get('battery_ods') or not config.get('battery_soc'):
        raise SolisControlException('No battery details from connection')
    unavailable_energy = config['battery_capacity'] * config['battery_ods'] / 100.0 # battery cannot discharge energy below Over Discharge SOC
    full_energy = config['battery_capacity'] - unavailable_energy # energy available if fully charged
    current_energy = (config['battery_soc'] * config['battery_capacity'] / 100.0) - unavailable_energy # currently available energy
    real_soc = current_energy / full_energy * 100.0 # real state of available charge
    return unavailable_energy, full_energy, current_energy, real_soc
    
def charge_times(config_period, full_energy, current_energy, target_level):
    # calculate battery charge_start and end values required to reach a particular level of available energy (kWH)
    if target_level <= 0.0: # the target level is invalid
        return '00:00', '00:00', current_energy
    energy_gap = target_level - current_energy # additional energy required to reach target
    if energy_gap <= 0.0: # the target level is already attained or exceeded
        return '00:00', '00:00', current_energy
    if energy_gap > (full_energy - current_energy): # the target level is beyond the battery capacity
        energy_gap = full_energy - current_energy # set to max
    charge_minutes = calc_minutes(config_period['current'], energy_gap)
    start, end = start_end_from_minutes(config_period, charge_minutes)
    energy_after = current_energy + calc_energy_kwh(config_period['current'], start, end)
    return start, end, energy_after
        
def discharge_times(config_period, current_energy, target_level):
    # calculate battery discharge_start and end values required to reduce to a particular level of available energy (kWH)
    if target_level <= 0.0: # the target level is invalid
        return '00:00', '00:00', current_energy
    energy_gap = current_energy - target_level # surplus energy to dump in order to reach target
    discharge_minutes = calc_minutes(config_period['current'], energy_gap)
    start, end = start_end_from_minutes(config_period, discharge_minutes)
    energy_after = current_energy - calc_energy_kwh(config_period['current'], start, end)
    return start, end, energy_after
    
def start_end_from_minutes(config_period, minutes):
    # tie episode to begining or end of the period or to position randomly within it
    max_minutes = diff_hhmm(config_period['start'], config_period['end'])
    minutes = minutes if minutes <= max_minutes else max_minutes
    sync = config_period.get('sync', 'none')
    if sync.lower() == 'start':
        period_start = config_period['start']; period_end = None
    elif sync.lower() == 'end':
        period_start = None; period_end = config_period['end']
    else:
        period_start = config_period['start']; period_end = config_period['end']
    return start_end_times(period_start, minutes, period_end)

def calc_minutes(current, energy_kwh): 
    # calculate minutes required to charge/discharge a particular amount of available energy (kWH)
    if energy_kwh <= 0.0:
        return 0
    return int(60.0 * energy_kwh / (current * ENERGY_AMP_HOUR)) # minutes charging/discharging required to reach target
    
def calc_energy_kwh(current, start, end): 
    # calculate amount of energy (kwH) after charging/discharging from start to end times
    minutes = diff_hhmm(start, end)
    if minutes <= 0.0:
        return 0.0
    return minutes * current * ENERGY_AMP_HOUR / 60.0 
    
def start_end_times(period_start, minutes, period_end=None): 
    # work out the start, end times and position them within the charge/discharge period
    if minutes <= 0:
        return '00:00', '00:00'
    if period_start and period_end: # if we know the start and the end, then position randomly within the period
        duration = diff_hhmm(period_start, period_end) # duration of the charge period in mins
        leftover = duration - minutes # is there any fallow period?
        offset = randint(0, leftover) if leftover > 0 else 0 # offset from the beginning of the charge period
        return increment_hhmm(period_start, offset), increment_hhmm(period_start, offset+minutes)
    elif period_start:
        return period_start, increment_hhmm(period_start, minutes)
    elif period_end:
        return increment_hhmm(period_end, -minutes), period_end
    return '00:00', '00:00'
    
def increment_hhmm(hhmm, minutes): # increment / decrement an HH:MM time
    if not minutes:
        return hhmm
    stime = time.fromisoformat(hhmm+':00')
    etime = time_adjust(stime, minutes)
    return etime.strftime('%H:%M')
    
def diff_hhmm(shhmm, ehhmm): # find difference in minutes between 2 HH:MM times
    stime = time.fromisoformat(shhmm+':00')
    etime = time.fromisoformat(ehhmm+':00')
    return time_diff(stime, etime)
    
def check_time(config, diff_mins=5.0):
    # time at inverter and host must be in sync
    if not config.get('inverter_datetime'):
        raise SolisControlException('No timestamp details from connection')
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
    inverter_max = config['inverter_max_current'] - config['inverter_power']
    battery_max = config['battery_max_current'] - config['inverter_power'] # was config['battery_discharge_max']
    periods = extract_periods(config)
    for p in periods:
        current = p['current']
        if current > battery_max: 
            return '%s current %.1fA > battery max %.1fA' % (p['name'], current, battery_max)
        if current > inverter_max:
            return '%s current %.1fA > inverter max %.1fA' % (p['name'], current, inverter_max)
    return 'OK'
    
def extract_periods(config): # extract configured charge/discharge periods from the config
    # note in output 'timeslot' can be 0, 1 or 2
    # which in 'long name' is converted to Time Slot 1, Time Slot 2 or Time Slot 3 
    result = [ ]
    for k, v in config.items():
        if (k.startswith('charge_period') or k.startswith('discharge_period')) and isinstance(v, dict):
            if k.startswith('charge_period'): 
                timeslot = int(k[13:]) if k[13:].isdigit() else 1
                timeslot = timeslot if timeslot in (1, 2, 3) else 1
                long_name = "Charge Time Slot %d ('%s')" % (timeslot, k)
                period = { 'name': k, 'charge': True, 'timeslot': timeslot-1, 'long_name': long_name } # NB timeslot is zero based
            elif k.startswith('discharge_period'):
                timeslot = int(k[16:]) if k[16:].isdigit() else 1
                timeslot = timeslot if timeslot in (1, 2, 3) else 1
                long_name = "Discharge Time Slot %d ('%s')" % (timeslot, k)
                period = { 'name': k, 'charge': False, 'timeslot': timeslot-1, 'long_name': long_name } # NB timeslot is zero based
            else:
                continue
            period.update(v)
            result.append(period)
    return result
    
def check_all(config, diff_mins=5.0):
    # check time sync and current settings
    check = check_time(config, diff_mins)
    if check != 'OK':
        return check
    check = check_current(config)
    if check != 'OK':
        return check
    return 'OK'
    
def add_fields(field_map, source, dest):
    for k, v in field_map.items():
        if k in source:
            dest[v] = source[k]
        if source.get('dataTimestamp'):
            dest['inverter_datetime'] = datetime.fromtimestamp(float(source['dataTimestamp'])/1000.0)
            dest['host_datetime'] = datetime.now()
            
def json_strip(response_text): # strip erroneous trailing commas in JSON dicts 
    json_string = re.sub(r'\s*,(\s*})', r'\1', response_text) 
    return json.loads(json_string)

def print_status(config, debug=False):
    print ('ID:', config['inverter_id'])
    print ('SN:', config['inverter_sn'])
    
    print ('Inverter Power:', config['inverter_power'])
    print ('Energy Today:', config['energy_today'])
    print ('Inverter HH:MM:', config['inverter_datetime'].strftime('%H:%M'))
    print('Check Time:', check_time(config))
    
    print ('Battery SOC:', config['battery_soc'])
    print ('Over Discharge SOC:', config['battery_ods'])
    print ('Battery Type:', config['battery_type'])
    print ('Login Token:', config['login_token'])
    
    unavailable_energy, full_energy, current_energy, real_soc = energy_values(config)
    print ('Available Energy: %.1fkWh (%.0f%% of max %.1fkWh)' % (current_energy, real_soc, full_energy))
    #soc = (current_energy + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # state of battery charge
    #print(soc)
    #target_soc = (1.7 + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # target state of charge
    #print(target_soc)
    
    print('Check Current:', check_current(config))
    
    if debug:
        periods = extract_periods(config)
        for p in periods:
            if p['charge']:
                print ('Notional %s charging times to reach 1,3,7 kWh available' % p['name'])
                print(charge_times(p, full_energy, current_energy, 1.0))
                print(charge_times(p, full_energy, current_energy, 3.0))
                print(charge_times(p, full_energy, current_energy, 7.0))
            else:
                print ('Notional %s discharging times to reach 1,3,7 kWh available' % p['name'])
                print(discharge_times(p, current_energy, 1.0))
                print(discharge_times(p, current_energy, 3.0))
                print(discharge_times(p, current_energy, 7.0))

    
           

        
        
