from datetime import time

import solis_control_req_mod as solis_control
import solis_common as common
try:
    import solis_s3_logger as logger
    DATA_LOGGER = True
except ImportError:
    DATA_LOGGER = False

cron_before = pyscript.app_config.get('cron_before', 20) # integer
charge_start_hhmm = pyscript.app_config['solis_control']['charge_period']['start'] # HH:MM string
discharge_start_hhmm = pyscript.app_config['solis_control']['discharge_period']['start'] # HH:MM string
charge_start_time = time.fromisoformat(charge_start_hhmm+':00') # start of morning cheap charging
discharge_start_time = time.fromisoformat(discharge_start_hhmm+':00') # start of evening peak discharging
charge_start_time = common.time_adjust(charge_start_time, -cron_before) # time to run before before charge period
discharge_start_time = common.time_adjust(discharge_start_time, -cron_before) # time to run before discharge period
charge_start_cron = "%d %d * * *" % (charge_start_time.minute, charge_start_time.hour)
discharge_start_cron = "%d %d * * *" % (discharge_start_time.minute, discharge_start_time.hour)
n_forecasts = 7 # number of old solar forecasts to store
log_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> set %s from %s to %s to reach %.1fkWh (%.0f%% SOC)'
log_off_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> set %s off (%s to %s) because %s'
log_err_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> error setting %s from %s to %s to reach %.1fkWh (%.0f%% SOC) -> %s'
log_err_off_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> error setting %s off (%s to %s) because %s -> %s'
charge_times_entity = 'pyscript.charge_times'
discharge_times_entity = 'pyscript.discharge_times'
entity_unavailable = ( None, 'unavailable', 'unknown', 'none' )

def sensor_get(entity_name): # sensor must exist
    entity_name = entity_name if entity_name.startswith('sensor.') else 'sensor.' + entity_name
    result = state.get(entity_name)
    if result in entity_unavailable:
        return None
    return result
        
def pyscript_get(entity_name): # creates persistent pyscript state variable if it doesn't exist
    try:
        result = state.get(entity_name)
        if result in entity_unavailable:
            return None
        return result
    except NameError:
        state.persist(entity_name, default_value='') # comma separated list of last n_forecasts
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
    
def find_requirement(config_setting):
    required = pyscript.app_config.get(config_setting)
    if required is None:
        return -1.0 # do nothing
    if not isinstance(required, str):
        return required
    result = state.get(required)
    if result in entity_unavailable: # includes None
        return -1.0 # do nothing
    return float(result)

@time_trigger("cron(" + charge_start_cron + ")")
def set_charge_times():
    required = find_requirement('morning_requirement')
    if required < 0.0:
        return
    min_reserve = required * 0.25 # min reserve before sun up
    forecast = get_forecast('morning', save=True)
    level_adjusted = calc_level(required, forecast, 'morning', min_reserve)
    result = set_times('charge', level_adjusted, test=False)
    if result != 'OK':
        task.sleep(5 * 60) # try again once after 5 mins
        set_times('charge', level_adjusted, test=False)
            
@time_trigger("cron(" + discharge_start_cron + ")")
def set_discharge_times():
    required = find_requirement('evening_requirement')
    if required < 0.0:
        return
    min_reserve = required * 0.25 # min reserve after sun down
    forecast = get_forecast('evening', save=True)
    level_adjusted = calc_level(required, forecast, 'evening', min_reserve)
    result = set_times('discharge', level_adjusted, test=False)
    if result != 'OK':
        task.sleep(5 * 60) # try again once after 5 mins
        set_times('discharge', level_adjusted, test=False)
        
def set_times(action, level_required, test=True):
    result = None
    if action not in ('charge', 'discharge'):
        log.warning('Invalid action: ' + action)
        return result
    msg_expl = 'already above' if action == 'charge' else 'already below'
    with solis_control.get_session() as session:
        config = dict(pyscript.app_config['solis_control'])
        if DATA_LOGGER and config.get('s3_ip') and config.get('s3_password'):
            logger.check_logger(config, session) # check if data logger is connected to Solis servers - if not restart it
        connected = solis_control.connect(config, session)
        if connected:
            unavailable_energy, full_energy, current_energy, real_soc = common.energy_values(config)
            soc = (current_energy + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # state of battery charge
            #level_required = full_energy if level_required > full_energy else level_required # now limited internally in dis/charge_times
            #target_soc = (level_required + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # ideal target state of charge
            if action == "charge":
                start, end, energy_after = common.charge_times(config, level_required) # discharge times to reach ideal energy level
                after_soc = (energy_after + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # actual target state of charge
                if test:
                    result = common.check_all(config) # check time sync and current settings only
                else:
                    result = solis_control.set_inverter_charge_times(config, session, start, end)
            elif action == "discharge":
                start, end, energy_after = common.discharge_times(config, level_required) # discharge times to reach ideal energy level
                after_soc = (energy_after + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # actual target state of charge
                if test:
                    result = common.check_all(config) # check time sync and current settings only
                else:
                    result = solis_control.set_inverter_discharge_times(config, session, start, end)
            log_action = 'notional ' + action if test else action
            if result == 'OK':
                if not test:
                    set_entities(config, session)
                if start == '00:00':
                    log.info(log_off_msg, current_energy, soc, log_action, start, end, msg_expl)
                else:
                    log.info(log_msg, current_energy, soc, log_action, start, end, energy_after, after_soc)
            else:
                if start == '00:00':
                    log.error(log_err_off_msg, current_energy, soc, log_action, start, end, msg_expl, result)
                else:
                    log.error(log_err_msg, current_energy, soc, log_action, start, end, energy_after, after_soc, result)
        else:
            log.error('Could not connect to Solis API')
    return result
    
def set_entities(config, session):
    # set entities listing charge/discharge times after successfully setting times
    existing = solis_control.get_inverter_times(config, session)
    if existing and pyscript_get(charge_times_entity) is not None:
        if existing['charge_start'] == '00:00' and existing['charge_end'] == '00:00':
            state.set(charge_times_entity, value='Off')
        else: 
            value = existing['charge_start'] + ' to ' + existing['charge_end']
            state.set(charge_times_entity, value=value)
    if existing and pyscript_get(discharge_times_entity) is not None:
        if existing['discharge_start'] == '00:00' and existing['discharge_end'] == '00:00':
            state.set(discharge_times_entity, value='Off')
        else: 
            value = existing['discharge_start'] + ' to ' + existing['discharge_end']
            state.set(discharge_times_entity, value=value)

@service
def test_solis(action=None, level_required=None, use_forecast=False):
    """yaml
name: Test service
description: Tests connection to the Solis API, calculates charge/discharge times and logs results
fields:
  action:
     description: log either charge (morning/cheap) or discharge (evening/peak) times
     example: charge
     required: true
     selector:
       select:
         options:
           - charge
           - discharge
  level_required:
     description: target energy level (kWh) available after charge or discharge period (default = 'morning_requirement'/'evening_requirement' values in config.yaml)
     example: 5.0
     required: false
  use_forecast:
     description: whether to subtract the solar forecast remaining today from the level_required value
     example: false
     required: false
     default: false
"""
    if level_required is None:
        if action == "charge":
            level_required = find_requirement['morning_requirement']
        elif action == "discharge":
            level_required = find_requirement('evening_requirement')
    if level_required >= 0.0:
        if use_forecast:
            if action == "charge":
                forecast_type = 'morning'
            elif action == "discharge":
                forecast_type = 'evening'
            forecast = get_forecast(forecast_type, save=False)
            if forecast:
                level_required = calc_level(level_required, forecast, forecast_type)
        set_times(action, level_required, test=True)


