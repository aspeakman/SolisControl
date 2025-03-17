from datetime import time, date, timedelta, datetime

import solis_control_req_mod as solis_control
import solis_common as common
try:
    import solis_s3_logger as logger
    DATA_LOGGER = True
except ImportError:
    DATA_LOGGER = False
    
ENERGY_USE = 'energy_use_history'
state.persist('pyscript.' + ENERGY_USE, default_value='')
FORECAST_MULTIPLIERS = 'forecast_multiplier_history'
state.persist('pyscript.' + FORECAST_MULTIPLIERS, default_value='')
FORECAST_YESTERDAY = 'solar_prediction_yesterday'
state.persist('pyscript.' + FORECAST_YESTERDAY, default_value='')
n_history = pyscript.app_config.get('history_days', 7) # number of old solar forecasts/ daily energy use values to store
    
config = dict(pyscript.app_config['solis_control'])
cron_before = pyscript.app_config.get('cron_before', 20) # integer
periods = common.extract_periods(config)
c_triggers = []; d_triggers = []
for i in range(3): # default is to never trigger
    c_triggers.append( { 'cron': 'once(now - 5 min)', 'kwargs': {} } ) 
    d_triggers.append( { 'cron': 'once(now - 5 min)', 'kwargs': {} } )
for p in periods:
    start_hhmm = p['start'] # HH:MM string
    end_hhmm = p['end'] # HH:MM string
    p['cron_before'] = p['cron_before'] if p.get('cron_before') else cron_before
    if start_hhmm != '00:00' or end_hhmm != '00:00':
        state.persist('pyscript.' + p['name'] + '_forecasts', default_value='')
        state.persist('pyscript.' + p['name'] + '_times', default_value='')
        start_time = time.fromisoformat(start_hhmm+':00') # start of period
        start_time = common.time_adjust(start_time, -p['cron_before']) # time to run before before charge period
        cron = "cron(%d %d * * *)" % (start_time.minute, start_time.hour)
        if p['charge']:
            c_triggers[p['timeslot']] = { 'cron': cron, 'kwargs': p } 
        else:
            d_triggers[p['timeslot']] = { 'cron': cron, 'kwargs': p } 
        log.info("Triggering %s assessment at %s" % (p['long_name'], start_time.strftime("%H:%M")))

log_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> set %s from %s to %s to reach %.1fkWh (%.0f%% SOC)'
log_off_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> set %s off (%s to %s) because %s'
log_err_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> error setting %s from %s to %s to reach %.1fkWh (%.0f%% SOC) -> %s'
log_err_off_msg = 'Current energy %.1fkWh (%.0f%% SOC) -> error setting %s off (%s to %s) because %s -> %s'

ENTITY_UNAVAILABLE = ( None, 'unavailable', 'unknown', 'none', 'None' )

def sensor_get(entity_name): # sensor must exist
    entity_name = entity_name if entity_name.startswith('sensor.') else 'sensor.' + entity_name
    result = state.get(entity_name)
    if result in ENTITY_UNAVAILABLE:
        return None
    return result
        
def pyscript_get(entity_name): # get pyscript state variable if it doesn't exist
    if not entity_name.startswith('pyscript.'):
        entity_name = 'pyscript.' + entity_name
    try:
        result = state.get(entity_name)
        if result in ENTITY_UNAVAILABLE:
            return None
        return result
    except NameError:
        state.persist(entity_name, default_value='') 
        return ''
        
def get_flist(list_name):
    lf = pyscript_get(list_name)
    if lf:
        lf = lf.split(sep=',')
        return [ float(f) for f in lf ]
    else:
        return []
        
def set_flist(list_name, values, maxlen=None, nround=1):
    fstring = '{:.%df}' % nround
    if not list_name.startswith('pyscript.'):
        list_name = 'pyscript.' + list_name
    lf = values[-maxlen:] if maxlen else values
    lf = [ fstring.format(f) for f in lf ]
    state.set(list_name, value=','.join(lf))
        
def get_forecast(period_name=None, save=False):
    # get the solar forecast (in kWh) for the rest of the day (or if not available use average of last n_history)
    forecast = sensor_get(pyscript.app_config['forecast_remaining'])
    if not period_name:
        return None if forecast is None else float(forecast) * pyscript.app_config['forecast_multiplier']
    old_forecasts = period_name+'_forecasts'
    lf = get_flist(old_forecasts)
    if forecast is None:
        forecast = sum(lf) / len(lf) if lf else 0.0 # use average of old forecasts if current solar power forecast not available
        log.info('Forecast not available - using %.1fkWh (mean of last %d forecasts)', forecast, len(lf))
    forecast = float(forecast)
    if forecast and save:
        lf.append(forecast)         # add new forecast to right side of list
        set_flist(old_forecasts, lf, n_history)
    if pyscript.app_config.get('forecast_multiplier'):
        forecast = forecast * pyscript.app_config['forecast_multiplier']
    elif pyscript.app_config.get('forecast_tomorrow'):
        lf = get_flist(FORECAST_MULTIPLIERS)
        if lf:
            multiplier = sum(lf) / len(lf)
            log.info('Forecast multiplier calculated as %.2f (mean of last %d multipliers)', multiplier, len(lf))
            forecast = forecast * multiplier
    return forecast

def calc_level(max_required, forecast, period_name, min_required=0.0):
    # if necessary reduce the required energy level by the predicted solar forecast
    level = max_required - forecast if forecast else max_required # target energy level in battery to meet requirement
    level = level if level >= min_required else min_required
    log.info('Aim %.1fkWh (min %.1fkWh) - solar %s forecast %.1fkWh => target %.1fkWh', max_required, min_required, period_name, forecast, level)
    return level
    
def find_requirement(source):
    required = source.get('kwh_requirement')
    if required is None:
        return calc_requirement(source) # see below
    if not isinstance(required, str):
        return required
    result = state.get(required)
    if result in ENTITY_UNAVAILABLE: # includes None
        return -1.0 # do nothing
    return float(result)
    
def calc_requirement(source): # calculate requirement based on daily consumption (history or specified number)
    if pyscript.app_config.get('daily_consumption_kwh'):
        req_kwh = pyscript.app_config['daily_consumption_kwh']
        if isinstance(req_kwh, str):
            result = state.get(req_kwh)
            if result in ENTITY_UNAVAILABLE: # includes None
                return -1.0 # do nothing
            req_kwh = float(result)
    else:
        lf = get_flist(ENERGY_USE)
        if not lf:
            sensor_name = pyscript.app_config.get('energy_monitor', 'solis_daily_grid_energy_used')
            st = sensor_get(sensor_name)
            if st:
                lf = [ float(st) ]
            else:
                return -1.0 # do nothing
        req_kwh = max(lf) # maximum of the stored values
    start = time.fromisoformat(source['start']+':00')
    prop_remain = (24.0 * 60.0 - (start.hour * 60.0) - start.minute) / (24.0 * 60.0) # proportion of day remaining
    result = req_kwh * prop_remain
    log.info('Calc requirement at %s -> %.1f * %.0f%% = %.1f' % (source['start'], req_kwh, prop_remain * 100, result))
    return result

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
    result = set_times(level_adjusted, period_name, charge=kwargs['charge'], timeslot=kwargs['timeslot'])
    if result != 'OK': # handle payload error - "'code': 'B0115'," = the current datalogger is offline or disconnected?
        task.sleep(kwargs['cron_before'] * 30) # try again once after after half interval
        log.info(result + ' - trying again')
        set_times(level_adjusted, period_name, charge=kwargs['charge'], timeslot=kwargs['timeslot'])
        
def set_times(level_required, period_name, charge=True, timeslot=0):
    result = 'Cannot connect session'
    msg_expl = 'already above' if charge else 'already below'
    with solis_control.get_session() as session:
        config = dict(pyscript.app_config['solis_control'])
        config_period = config[period_name]
        if DATA_LOGGER and config.get(logger.IP_FIELD) and config.get(logger.PASSWORD_FIELD):
            logger.check_logger(config, session) # check if data logger is connected to inverter - if not restart it
        connected = solis_control.connect(config, session)
        if connected:
            eah = config.get('energy_amp_hour')
            unavailable_energy, full_energy, current_energy, real_soc = common.energy_values(config)
            soc = (current_energy + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # state of battery charge
            if charge:
                action = 'charge'
                start, end, energy_after = common.charge_times(config_period, full_energy, current_energy, level_required, eah) # charge times to reach ideal energy level
            else:
                action = 'discharge'
                start, end, energy_after = common.discharge_times(config_period, current_energy, level_required, eah) # discharge times to reach ideal energy level
            start, end = common.limit_times(config_period, start, end)
            after_soc = (energy_after + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # actual target state of charge
            params = { 'start': start, 'end': end, 'amps': str(config_period['current']) }
            result = solis_control.set_inverter_params(config, session, params, charge=charge, timeslot=timeslot)
            if result == 'OK':
                set_times_entity(period_name, start, end, config_period['current'])
                if start == '00:00' and end == '00:00':
                    log.info(log_off_msg, current_energy, soc, action, start, end, msg_expl)
                else:
                    log.info(log_msg, current_energy, soc, action, start, end, energy_after, after_soc)
            else:
                if start == '00:00' and end == '00:00':
                    log.error(log_err_off_msg, current_energy, soc, action, start, end, msg_expl, result)
                else:
                    log.error(log_err_msg, current_energy, soc, action, start, end, energy_after, after_soc, result)
        else:
            result = 'Could not connect to Solis API'
            log.error(result)
    return result
    
def set_times_entity(period_name, start='00:00', end='00:00', current=None):
    # set entity exposing charge/discharge times after successful setting
    entity = 'pyscript.' + period_name + '_times'
    if pyscript_get(entity) is not None:
        if start == '00:00' and end == '00:00':
            value='Off'
        else: 
            value = start + ' to ' + end
            if current:
                value += ' @' + str(current) + 'A'
        value += datetime.now().strftime(' (set %H:%M %b %d)')
        state.set(entity, value=value)
            
@time_trigger("cron(50 23 * * *)")
def store_daily_energy_use():
    sensor_name = pyscript.app_config.get('energy_monitor', 'solis_daily_grid_energy_used')
    # note 'solis_daily_grid_energy_used' monitors total household consumption (of direct grid, battery discharge AND solar power)
    # whereas 'solis_daily_grid_energy_purchased' is just that which comes off the grid 
    st = sensor_get(sensor_name)
    if st:
        lf = get_flist(ENERGY_USE)
        lf.append(float(st))
        set_flist(ENERGY_USE, lf, n_history)
        
@time_trigger("cron(0 23 * * *)")
def store_daily_solar_accuracy():
    forecast_tomorrow_sensor = pyscript.app_config.get('forecast_tomorrow')
    if not forecast_tomorrow_sensor: # assessment of accuracy is based on this sensor
        return # so abort if not set
    pv_today = sensor_get('solis_energy_today') # solar energy today
    if pv_today:
        yesterday = date.today() - timedelta(days = 1)
        fy = pyscript_get(FORECAST_YESTERDAY) # solar_prediction yesterday
        fy = fy.split(' ') if fy else []
        if len(fy) == 2 and fy[1] == yesterday.isoformat():
            multiplier = float(pv_today) / float(fy[0]) # multiplier to prediction to produce todays value
            lf = get_flist(FORECAST_MULTIPLIERS)
            lf.append(multiplier)
            set_flist(FORECAST_MULTIPLIERS, lf, n_history, 2)
            log.info("Forecast yesterday %s, solar energy today %s = multiplier %f" % (fy[0], pv_today, multiplier))
    forecast_tomorrow = sensor_get(forecast_tomorrow_sensor) # solar prediction tomorrow
    if forecast_tomorrow:
        value = '%s %s' % (forecast_tomorrow, date.today().isoformat())
        state.set('pyscript.' + FORECAST_YESTERDAY, value)

@service("pyscript.test_" + __name__, supports_response="only")
def test_solis(period_name, level_required, starting_level=None):
    """yaml
name: Test service
description: Tests connection to the Solis API, calculates notional charge/discharge times (ignoring solar forecast and current energy)
fields:
  period_name:
     description: name of a configured charge or discharge period
     example: charge_period
     required: true
  level_required:
     description: target energy level (kWh) available after charge or discharge period
     example: 5.0
     required: true
  starting_level:
     description: optional starting energy level (kWh)
     example: 
     required: false
"""
    result = { 'status': 'Error', 'message': 'Cannot connect session' }
    period = None
    for p in periods:
        if p['name'] == period_name:
            period = p
            break
    if not period:
        result['message'] = "Test of solis inverter not possible - invalid period_name '%s' supplied" % period_name
        return result
    with solis_control.get_session() as session:
        config = dict(pyscript.app_config['solis_control'])
        config_period = config[period_name]
        if DATA_LOGGER and config.get(logger.IP_FIELD) and config.get(logger.PASSWORD_FIELD):
            logger.check_logger(config, session) # check if data logger is connected to inverter - if not restart it
        connected = solis_control.connect(config, session)
        if connected:
            unavailable_energy, full_energy, current_energy, real_soc = common.energy_values(config)
            current = '(%s-%s at %sA)' % (config_period['start'], config_period['end'],config_period['current'])
            energy_start = float(starting_level) if starting_level is not None else -1.0
            if period_name.startswith('charge'):
                energy_start = 0.0 if energy_start < 0.0 or energy_start > full_energy else energy_start
                start, end, energy_after = common.charge_times(config_period, full_energy, energy_start, level_required) 
                # charge times from 0% to reach ideal energy level
                action = 'charge'
            else:
                energy_start = full_energy if energy_start <= 0.0 or energy_start > full_energy else energy_start
                start, end, energy_after = common.discharge_times(config_period, energy_start, level_required) 
                # discharge times from 100% to reach ideal energy level
                action = 'discharge'
            start_soc = (energy_start + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # actual target state of charge
            after_soc = (energy_after + unavailable_energy) / (full_energy + unavailable_energy) * 100.0 # actual target state of charge
            #start, end = common.limit_times(config_period, start, end)
            msg_expl = 'remain at' if start == '00:00' and end == '00:00' else 'reach'
            msg = "'%s' %s notional %s times starting from %.1fkWh (%.0f%% SOC) -> %s to %s to %s %.1fkWh (%.0f%% SOC)"
            result['message'] = msg % (period_name, current, action, energy_start, start_soc, start, end, msg_expl, energy_after, after_soc)
            result['status'] = 'OK'
        else:
            result['message'] = 'Could not connect to Solis API'
    return result
    
@service("pyscript.check_s3_logger", supports_response="only")
def check_logger():
    """yaml
name: Check logger
description: Tests connection to the Solis S3 Logger and resets it if necessary
"""
    result = { 'status': 'Error', 'message': 'Cannot connect session' }
    with solis_control.get_session() as session:
        config = dict(pyscript.app_config['solis_control'])
        if DATA_LOGGER and config.get(logger.IP_FIELD) and config.get(logger.PASSWORD_FIELD):
            result['message'] = logger.check_logger(config, session) # check if data logger is connected to inverter - if not restart it
            if result['message'].startswith('OK - '):
                result['status'] = 'OK'
                result['message'] = result['message'][5:]
        else:
            result['message'] = 'Data logger not configured'
    return result
    
@service("pyscript.calc_energy_amp_hour", supports_response="only")
def calc_energy_amp_hour(period_or_current, minutes, start_soc, end_soc):
    """yaml
name: Calculates the energy_amp_hour constant from real charging/discharging figures
description: Enter the values to view the calculated result
fields:
  period_or_current:
     description: name of a configured charge/discharge period OR current used in amps
     example: charge_period
     required: true
  minutes:
     description: duration of the charge or discharge period (mins)
     example: 180
     required: true
  start_soc:
     description: battery state of charge (SOC) at the beginning (%)
     example: 10
     required: true
  end_soc:
     description: battery state of charge (SOC) at the end (%)
     example: 90
     required: true
"""
    config = dict(pyscript.app_config['solis_control'])
    capacity = config['battery_capacity']
    ctype = ''
    if str(period_or_current).startswith('charge_'):
        ctype = 'charge_'
    elif str(period_or_current).startswith('discharge_'):
        ctype = 'discharge_'
    if ctype:
        current = config[period_or_current]['current']
    else:
        current = float(period_or_current)
    result = common.eah_from_soc(capacity, current, int(minutes), int(start_soc), int(end_soc))
    return { 'energy_amp_hour': result, ctype+'current': current, 'battery_capacity': capacity }
        
@service("pyscript.clear_inverter_times", supports_response="only")
def clear_inverter_times():
    """yaml
name: Clear out all charge/discharge times
description: Clears out any scheduled charging / discharging times on the inverter
"""
    result = { 'status': 'Error', 'message': 'Cannot connect session' }
    with solis_control.get_session() as session:
        config = dict(pyscript.app_config['solis_control'])
        connected = solis_control.connect(config, session)
        if connected:
            result['message'] = solis_control.set_inverter_data(config, session)
            if result['message'] == 'OK':
                result['status'] = 'OK'
                result['message'] = 'Charging/discharging schedule cleared'
                for p in periods:
                    set_times_entity(p['name'])
        else:
            result['message'] = 'Could not connect to Solis API'
    return result

