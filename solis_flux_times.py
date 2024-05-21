from datetime import time

import solis_control_req_mod as solis_control
import solis_common as common

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
log_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> set %s from %s to %s to reach %.1fkWh (%.0f%% SOC) target'
log_off_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> set %s off (%s to %s) because %s %.1fkWh (%.0f%% SOC) target'
log_err_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> error setting %s from %s to %s to reach %.1fkWh (%.0f%% SOC) target -> %s'
log_err_off_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> error setting %s off (%s to %s) because %s %.1fkWh (%.0f%% SOC) target -> %s'

def sensor_get(entity_name): # sensor must exist
    entity_name = entity_name if entity_name.startswith('sensor.') else 'sensor.' + entity_name
    result = state.get(entity_name)
    if result in ['unavailable', 'unknown', 'none']:
        return None
    return result
        
def pyscript_get(entity_name): # creates persistent pyscript state variable if it doesn't exist
    try:
        result = state.get(entity_name)
        if result in ['unavailable', 'unknown', 'none']:
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

@time_trigger("cron(" + charge_start_cron + ")")
def set_charge_times():
    required = pyscript.app_config.get('morning_requirement')
    if required is None or required < 0.0:
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
    required = pyscript.app_config.get('evening_requirement')
    if required is None or required < 0.0:
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
        connected = solis_control.connect(config, session)
        if connected:
            unavailable_energy, full_energy, current_energy, real_soc = common.energy_values(config)
            soc = (current_energy + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # state of battery charge
            target_soc = (level_required + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # target state of charge
            if action == "charge":
                start, end = common.charge_times(config, level_required) # discharge times to reach required energy level
                if test:
                    result = common.check_all(config) # check time sync and current settings only
                else:
                    result = solis_control.set_inverter_times(config, session, charge_start = start, charge_end = end)
            elif action == "discharge":
                start, end = common.discharge_times(config, level_required) # discharge times to reach required energy level
                if test:
                    result = common.check_all(config) # check time sync and current settings only
                else:
                    result = solis_control.set_inverter_times(config, session, discharge_start = start, discharge_end = end)
            log_action = 'notional ' + action if test else action
            if result == 'OK':
                if start == '00:00':
                    log.info(log_off_msg, current_energy, soc, log_action, start, end, msg_expl, level_required, target_soc)
                else:
                    log.info(log_msg, current_energy, soc, log_action, start, end, level_required, target_soc)
            else:
                if start == '00:00':
                    log.error(log_err_msg, current_energy, soc, log_action, start, end, msg_expl, level_required, target_soc, result)
                else:
                    log.error(log_err_off_msg, current_energy, soc, log_action, start, end, level_required, target_soc, result)
        else:
            log.error('Could not connect to Solis API')
    return result
            
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
            level_required = pyscript.app_config['morning_requirement']
        elif action == "discharge":
            level_required = pyscript.app_config.get('evening_requirement')
    if level_required is not None and level_required >= 0.0:
        if use_forecast:
            if action == "charge":
                forecast_type = 'morning'
            elif action == "discharge":
                forecast_type = 'evening'
            forecast = get_forecast(forecast_type, save=False)
            if forecast:
                level_required = calc_level(level_required, forecast, forecast_type)
        set_times(action, level_required, test=True)


