from datetime import time

import solis_control_req_mod as solis_control
import solis_common as common
try:
    import solis_s3_logger as logger
    DATA_LOGGER = True
except ImportError:
    DATA_LOGGER = False
    
config = dict(pyscript.app_config['solis_control'])
cron_before = pyscript.app_config.get('cron_before', 20) # integer
periods = common.extract_periods(config)
c_triggers = []; d_triggers = []
for i in range(3):
    c_triggers.append( { 'cron': 'once(now - 5 min)', 'kwargs': {} } )
    d_triggers.append( { 'cron': 'once(now - 5 min)', 'kwargs': {} } )
for p in periods:
    start_hhmm = p['start'] # HH:MM string
    end_hhmm = p['end'] # HH:MM string
    p['cron_before'] = p['cron_before'] if p.get('cron_before') else cron_before
    if start_hhmm != '00:00' or end_hhmm != '00:00':
        start_time = time.fromisoformat(start_hhmm+':00') # start of period
        start_time = common.time_adjust(start_time, -p['cron_before']) # time to run before before charge period
        cron = "cron(%d %d * * *)" % (start_time.minute, start_time.hour)
        if p['charge']:
            c_triggers[p['timeslot']] = { 'cron': cron, 'kwargs': p } 
        else:
            d_triggers[p['timeslot']] = { 'cron': cron, 'kwargs': p } 
        log.info("Triggering %s assessment at %s" % (p['long_name'], start_time.strftime("%H:%M")))

n_forecasts = 7 # number of old solar forecasts to store
log_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> set %s from %s to %s to reach %.1fkWh (%.0f%% SOC)'
log_off_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> set %s off (%s to %s) because %s'
log_err_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> error setting %s from %s to %s to reach %.1fkWh (%.0f%% SOC) -> %s'
log_err_off_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> error setting %s off (%s to %s) because %s -> %s'

ENTITY_UNAVAILABLE = ( None, 'unavailable', 'unknown', 'none' )

def sensor_get(entity_name): # sensor must exist
    entity_name = entity_name if entity_name.startswith('sensor.') else 'sensor.' + entity_name
    result = state.get(entity_name)
    if result in ENTITY_UNAVAILABLE:
        return None
    return result
        
def pyscript_get(entity_name): # creates persistent pyscript state variable if it doesn't exist
    try:
        result = state.get(entity_name)
        if result in ENTITY_UNAVAILABLE:
            return None
        return result
    except NameError:
        state.persist(entity_name, default_value='') 
        return ''
        
def get_forecast(forecast_type=None, save=False):
    # get the solar forecast (in kWh) or if not available use average of last n_forecasts
    forecast = sensor_get(pyscript.app_config['forecast_remaining'])
    if not forecast_type:
        return None if forecast is None else float(forecast)
    old_forecasts = 'pyscript.' +forecast_type+'_forecasts'
    lf = pyscript_get(old_forecasts)
    if lf:
        lf = lf.split(sep=',')
        lf = [ float(f) for f in lf ]
    else:
        lf = []
    if forecast is None:
        forecast = sum(lf) / len(lf) if lf else 0.0 # use average of old forecasts if current solar power forecast not available
        log.info('Forecast not available - using %.1fkWh (mean of last %d forecasts)', forecast, len(lf))                                                                                                
    else:
        forecast = float(forecast)
        if save:
            lf.append(forecast)         # add new forecast to right side of list
            lf = lf[-n_forecasts:]      # maxlen = n_forecasts
            lf = [ '{:.1f}'.format(f) for f in lf ]
            state.set(old_forecasts, value=','.join(lf))
    if pyscript.app_config.get('forecast_uplift'):
        forecast = forecast * pyscript.app_config['forecast_uplift']
    return forecast

def calc_level(max_required, forecast, forecast_type, min_required=0.0):
    # if necessary reduce the required energy level by the predicted solar forecast
    level = max_required - forecast if forecast else max_required # target energy level in battery to meet requirement
    level = level if level >= min_required else min_required
    log.info('Aim %.1fkWh (min %.1fkWh) - solar %s forecast %.1fkWh => target %.1fkWh', max_required, min_required, forecast_type, forecast, level)
    return level
    
def find_requirement(source):
    required = source.get('kwh_after')
    if required is None:
        return -1.0 # do nothing
    if not isinstance(required, str):
        return required
    result = state.get(required)
    if result in ENTITY_UNAVAILABLE: # includes None
        return -1.0 # do nothing
    return float(result)

@time_trigger(c_triggers[0]['cron'], kwargs=c_triggers[0]['kwargs'])
@time_trigger(c_triggers[1]['cron'], kwargs=c_triggers[1]['kwargs'])
@time_trigger(c_triggers[2]['cron'], kwargs=c_triggers[2]['kwargs'])
@time_trigger(d_triggers[0]['cron'], kwargs=d_triggers[0]['kwargs'])
@time_trigger(d_triggers[1]['cron'], kwargs=d_triggers[1]['kwargs'])
@time_trigger(d_triggers[2]['cron'], kwargs=d_triggers[2]['kwargs'])
def set_charge_discharge_times(**kwargs):
    if not kwargs:
        return
    required = find_requirement(kwargs)
    if required is None or required < 0.0 or (kwargs['start'] == '00:00' and kwargs['end'] == '00:00'):
        return
    period_name = kwargs['name']
    min_reserve = required * 0.25 
    forecast = get_forecast(period_name, save=True)
    level_adjusted = calc_level(required, forecast, period_name, min_reserve)
    result = set_times(level_adjusted, period_name, charge=kwargs['charge'], timeslot=kwargs['timeslot'], test=False)
    if result != 'OK': # handle payload error - "'code': 'B0115'," = the current datalogger is offline or disconnected?
        task.sleep(kwargs['cron_before'] * 30) # try again once after after half interval
        log.info(result + ' - trying again')
        set_times(level_adjusted, period_name, charge=kwargs['charge'], timeslot=kwargs['timeslot'], test=False)
        
def set_times(level_required, period_name, charge=True, timeslot=0, test=True):
    result = None
    msg_expl = 'already above' if charge else 'already below'
    with solis_control.get_session() as session:
        config = dict(pyscript.app_config['solis_control'])
        config_period = config[period_name]
        if DATA_LOGGER and config.get(logger.IP_FIELD) and config.get(logger.PASSWORD_FIELD):
            logger.check_logger(config, session) # check if data logger is connected to inverter - if not restart it
        connected = solis_control.connect(config, session)
        if connected:
            unavailable_energy, full_energy, current_energy, real_soc = common.energy_values(config)
            soc = (current_energy + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # state of battery charge
            if charge:
                action = 'charge'
                start, end, energy_after = common.charge_times(config_period, full_energy, current_energy, level_required) # charge times to reach ideal energy level
            else:
                action = 'discharge'
                start, end, energy_after = common.discharge_times(config_period, current_energy, level_required) # discharge times to reach ideal energy level
            start, end = common.limit_times(config_period, start, end)
            after_soc = (energy_after + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # actual target state of charge
            if test:
                result = common.check_all(config) # check time sync and current settings only
            else:
                params = { 'start': start, 'end': end, 'amps': str(config_period['current']) }
                result = solis_control.set_inverter_params(config, session, params, charge=charge, timeslot=timeslot)
            log_action = 'notional ' + action if test else action
            if result == 'OK':
                if not test:
                    set_times_entity(period_name, start, end)
                if start == '00:00' and end == '00:00':
                    log.info(log_off_msg, current_energy, soc, log_action, start, end, msg_expl)
                else:
                    log.info(log_msg, current_energy, soc, log_action, start, end, energy_after, after_soc)
            else:
                if start == '00:00' and end == '00:00':
                    log.error(log_err_off_msg, current_energy, soc, log_action, start, end, msg_expl, result)
                else:
                    log.error(log_err_msg, current_energy, soc, log_action, start, end, energy_after, after_soc, result)
        else:
            log.error('Could not connect to Solis API')
    return result
    
def set_times_entity(period_name, start, end):
    # set entity exposing charge/discharge times after successful setting
    entity = 'pyscript.' + period_name + '_times'
    if pyscript_get(entity) is not None:
        if start == '00:00' and end == '00:00':
            state.set(entity, value='Off')
        else: 
            value = start + ' to ' + end
            state.set(entity, value=value)

@service("pyscript.test_" + __name__)
def test_solis(period_name, level_required=None, use_forecast=False):
    """yaml
name: Test service
description: Tests connection to the Solis API, calculates charge/discharge times and logs results
fields:
  period_name:
     description: name of a configured charge or discharge period
     example: charge_period
     required: true
  level_required:
     description: target energy level (kWh) available after charge or discharge period (default = 'kwh_after' value in config.yaml)
     example: 5.0
     required: false
  use_forecast:
     description: whether to subtract the solar forecast remaining today from the level_required value
     example: false
     required: false
     default: false
"""
    period = None
    for p in periods:
        if p['name'] == period_name:
            period = p
            break
    if not period:
        log.warning("Test of solis inverter not possible - invalid period_name '%s' supplied" % period_name)
        return
    if level_required is None:
        level_required = find_requirement(period)
    if level_required >= 0.0:
        if use_forecast:
            forecast = get_forecast(period_name, save=False)
            if forecast:
                level_required = calc_level(level_required, forecast, forecast_type)
        set_times(level_required, period_name, charge=period['charge'], timeslot=period['timeslot'], test=True)
    else:
        log.info("Test of solis inverter skipped = level_required below zero" % period_name)
        
@service("pyscript.test_logger_" + __name__)
def test_logger():
    """yaml
name: Test service
description: Tests connection to the Solis S3 Logger
"""
    with solis_control.get_session() as session:
        config = dict(pyscript.app_config['solis_control'])
        if DATA_LOGGER and config.get(logger.IP_FIELD) and config.get(logger.PASSWORD_FIELD):
            logger.check_logger(config, session) # check if data logger is connected to inverter - if not restart it
        else:
            log.warning('Test of data logger not possible')
        

