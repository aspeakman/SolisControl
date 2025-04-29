# _solis_flux_times_ Home Assistant pyscript app 

**solis_flux_times** is a [Pyscript](https://hacs-pyscript.readthedocs.io/en/latest/) Home Assistant app 
 for use with energy suppliers that offer cheap rate charging periods and peak rate discharging periods
such as the [Octopus Flux](https://octopus.energy/smart/flux/) tariff.

It is based on the **soliscontrol** Python project which has modules for controlling a Solis battery/inverter setup 
using the Solis Cloud API
(see the _soliscontrol_ [README](./README.md)).

## Pre-requisites

You should access the Solis Cloud API by following [these 
instructions](https://solis-service.solisinverters.com/en/support/solutions/articles/44002212561-request-api-access-soliscloud).

Note down the following values for use in the pyscript `secrets.yaml` (see below) -> _key_id_, _key_secret_,
_user_name_, _password_, _station_id_

On your inverter you will also need to enable _Self Use_ mode and 
set _Time of Use: Optimal Income_ to _Run_ - see <https://www.youtube.com/watch?v=h1A80cSOrhA>

## Description

You can define charge or discharge periods which correspond to the cheap and peak rate tariffs
offered by your provider. Just before each of these defined periods the app will assess your household 
energy needs for the rest of the day and, if necessary, set up charging or discharging episodes within the periods. 

You can also set up a charging period before your peak rate - so that the system tops up your battery at medium rates to avoid
importing at peak rates.

You can either define fixed values for your energy requirements or the app can work it out based on historical readings. If you 
define a solar forecast integration, the assessment will also take into account the solar forecast 
for the rest of the day (and its historical accuracy).

## Installation
If required, install a solar forecast integration either [Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/) or
[Solcast](https://github.com/tabascoz/ha-solcast-solar) (which I have found to be more accurate).

Next install [Pyscript](https://hacs-pyscript.readthedocs.io/en/latest/) and copy `solis_flux_times.py` to the pyscript _apps_ folder.

From the `SolisControl/solis_control` folder copy `solis_common.py` and `solis_control_req_mod.py` to the pyscript _modules_ folder (and if necessary `solis_s3_logger.py` see below). 

Finally edit `config.yaml` and `secrets.yaml` (see below) in the main pyscript folder.

## Settings

### solis_flux_times settings


The app decides internally on the length of each charge/discharge period (see below) based on the household energy 
requirement remaining at that time of day. **By default** this is based on the _energy_monitor_ sensor which is used to keep track of the 
maximum daily consumption over the previous _history_days_ period, then adjusts it based on the proportion of the day remaining.
**Alternatively** you can set _daily_consumption_kwh_ or _kwh_requirement_ which are exact household consumption requirements. 

**Either**

>_energy_monitor_ by default this is 'solis_daily_grid_energy_used' but you can specify any alternative sensor entity id which monitors daily overall household 
energy consumption (kWh)

>_history_days_ duration of stored forecast and energy use history (the default for this is 7 days)

**Or**

>_daily_consumption_kwh_ which sets an estimated daily household energy consumption requirement (kWh) (or can be the id of an entity which defines the value eg a helper = 
'input_number.daily_kwh_consumption')

**Or**

>_kwh_requirement_ set within each charge or discharge period (see below) which is the exact target energy 'reserve' you want to
have in place after that time period (or can be the id of an entity which defines the value eg a helper = 
'input_number.morning_reserve')

Note that the household energy requirements calculated or set above consist of the battery energy stored after charging (or remaining 
after discharging) AND the predicted solar yield for the rest of the day (if the optional _forecast_remaining_ setting is filled in)

_forecast_remaining_ (optional) remaining forecast solar energy today (kWh) (the id of an entity in the 'sensor' domain)

>If you do use a solar forecaster, then the accuracy of any solar predictions can be adjusted, either by a fixed multiplier (_forecast_multiplier_) or by comparing  
the history of a solar prediction sensor (_forecast_tomorrow_) against actual solar energy yielded (over _history_days_)

>**Either**

>>_forecast_tomorrow_  predicted solar energy tomorrow (kWh) (the id of an entity in the 'sensor' domain)

>**Or** 

>>_forecast_multiplier_ if set, this is a fixed multiplier applied to adjust solar forecast values if they prove to be pessimistic or optimistic

_cron_before_ The app sets inverter times just before each of the defined charge/discharge periods (see below). It runs _cron_before_ minutes before 
the start of each period (default 20). 

_base_reserve_kwh_ This is a default energy reserve that the system tries to maintain in the battery as a contingency independently of daily needs 
(default 15% of _battery_capacity_ see below)

### solis_control settings

_battery_capacity_ is the nominal stored energy of the battery at 100% State Of Charge (eg 7.1 = 2 * Pylontech US3000C with Nominal Capacity of 3.55 kWh each)

_battery_max_current_ is the recommended charge current for your batteries in amps (eg 74 = 2 * Pylontech US3000C with Recommend Charge Current of 37A each). 
Also see https://www.youtube.com/watch?v=h1A80cSOrhA to find battery 'Dis/Charging Current Limits'

_inverter_max_current_ is the max charge and discharge inverter current in amps - see Solis inverter datasheet specs for 'Max. charge / discharge current'  (eg 62.5A or 100A)

_energy_amp_hour_ energy (in kWh) stored/released for each hour and amp of current (default 0.05). The app converts the household energy
requirement into a charging/discharging period based on this setting. By default it is based on a rough rule of thumb that 20A times
 1 hour adds 1 kWh of stored energy - see https://www.youtube.com/watch?v=ps22E30OUEk You can adjust this depending on the age and state of your
 battery (see _calc_energy_amp_hour_ service below)

_api_url_ default is 'https://www.soliscloud.com:13333' 

_solis_key_secret_ see `config.yaml` example below

_solis_key_id_ see `config.yaml` example below

_solis_user_name_ see `config.yaml` example below

_solis_password_ see `config.yaml` example below

_solis_station_id_ see `config.yaml` example below

### charge_period / discharge_period settings

You can define up to 3 charge and 3 discharge periods (non-overlapping) for your inverter/battery setup (
_charge_period_, _charge_period2_, _charge_period3_, _discharge_period_, _discharge_period2_ and _discharge_period3_ ).

To set up a period, define the _start_ and _end_ times and the _current_ to use in amps. The system will restrict each charge or 
discharge episode to within the appropriate start/end period, and it will check the current does not exceed the maxima defined by
_battery_capacity_, _battery_max_current_ and _inverter_max_current_ (see above)

You can also set a _sync_ setting for the appropriate period to choose whether
the charge/discharge episode is tied to the 'start' or 'end' of the period or takes place at a random point within it (the default).

You can define an optional _cron_before_ setting within each period which overrides the main _solis_control_ setting above.

Within each defined period you can also set an optional _kwh_requirement_ which is the exact target energy 'reserve' you want to
have in place after that time period (this overrides the _daily_consumption_kwh_ and the _energy_monitor_ sensor settings above)

**Note** that you can set _kwh_requirement_ to zero which means charge/discharge activity will be actively turned off each day.
Alternatively a negative number will disable any action for this period (preserving any existing charge/discharge times)
Also _kwh_requirement_ can be the id of an entity which defines the value eg a helper = 
'input_number.morning_reserve')

## Basic Configuration
Setup of pyscript is via the HA `configuration.yaml` - an example as follows:
```
pyscript: !include pyscript/config.yaml
```
Configuration of _solis_flux_times_ is via the pyscript `config.yaml` - a short example using defaults as follows:
```
hass_is_global: false
apps:
  solis_flux_times:
    forecast_remaining: 'solcast_pv_forecast_forecast_remaining_today' # entity id of Solcast forecast for remaining solar energy today (kWh) - in 'sensor' domain
    forecast_tomorrow: 'solcast_pv_forecast_forecast_tomorrow' # entity id of Solcast tomorrow prediction (kWh) - in 'sensor' domain
    solis_control:
      solis_key_secret: !secret solis_key_secret
      solis_key_id: !secret solis_key_id
      solis_user_name: !secret solis_user_name
      solis_password: !secret solis_password
      solis_station_id: !secret solis_station_id
      battery_capacity: 7.1 
      battery_max_current: 74 
      inverter_max_current: 62.5 
      charge_period: # First period when energy can be imported from the grid at low rates
        start: "02:01"
        end: "04:59" 
        current: 50 # charge current setting in amps
      discharge_period: # First period when energy can be exported to the grid at high rates
        start: "16:01" 
        end: "18:59" 
        current: 50 # discharge current setting in amps
```
Based on the settings above you will need to add the following lines to the pyscript `secrets.yaml` replacing xxxx:
```
solis_key_id: "xxxx"
solis_key_secret: "xxxx"
solis_user_name: "xxxx"
solis_password: "xxxx"
solis_station_id: "xxxx"
```

## Alternative Configuration

This is an alternative example of a `config.yaml` with many optional settings in place 
```
hass_is_global: false
apps:
  solis_flux_times:
    #energy_monitor: 'solis_daily_grid_energy_used' # entity id of household daily energy monitor (kWh) - in 'sensor' domain
    history_days: 10 
    daily_consumption_kwh: 'input_number.kwh_consumption' # estimated daily household energy use (kWh) (overrides use of 'energy_monitor')
    forecast_remaining: 'energy_production_today_remaining' #  entity id of Forecast.Solar remaining energy today (kWh) - in 'sensor' domain
    #forecast_tomorrow: 'energy_production_tomorrow' # entity id of Forecast.Solar tomorrow prediction (kWh) - in 'sensor' domain 
    forecast_multiplier: 1.1 # overrides use of 'forecast_tomorrow'
    cron_before: 10 
    base_reserve_kwh: 1.5 # accessible energy contingency to maintain in the battery (kWh)
    solis_control:
      solis_key_secret: !secret solis_key_secret
      solis_key_id: !secret solis_key_id
      solis_user_name: !secret solis_user_name
      solis_password: !secret solis_password
      solis_station_id: !secret solis_station_id
      api_url: 'https://www.soliscloud.com:13333' # default
      battery_capacity: 7.1 
      battery_max_current: 74 
      inverter_max_current: 62.5 
      energy_amp_hour: 0.05 # default
      charge_period: # First period when energy can be imported from the grid at low rates
        start: "02:01"
        end: "04:59" 
        current: 55 # charge current setting in amps
        sync: 'random' # if 'start', charging is tied to start of period or if 'end' it is tied to the end (otherwise it starts randomly)
        kwh_requirement: 12.0 # overrides daily_consumption_kwh above
      charge_period2: # 2nd period when energy can be imported from the grid eg top up to avoid importing during peak period
        start: "14:15"
        end: "15:45" 
        current: 50 # charge current setting in amps
        sync: 'start' 
      discharge_period: # First period when energy can be exported to the grid at high rates
        start: "16:01" 
        end: "18:59" 
        current: 50 # discharge current setting in amps
        sync: 'end'
        kwh_requirement: 0 # zero means no discharging takes place, -1 means no action is taken (preserves existing settings)
```

## Solis S3 Logger

If you have an S3 data logger that occasionally disconnects 
(and have installed `solis_s3_logger.py` see above) you can add these lines under _solis_control_ in the _solis_flux_times_ section
of `config.yaml`.
This will check for access just before each charge or discharge period and if necessary restart the logger.

```
solis_flux_times:
  solis_control:
    solis_s3_username: !secret solis_s3_username
    solis_s3_password: !secret solis_s3_password
    solis_s3_ip: !secret solis_s3_ip
```

You will then need to add the following lines to the pyscript `secrets.yaml` replacing xxxx:

```
solis_s3_username: "xxxx" # usually 'admin'
solis_s3_password: "xxxx" # after setup this will be the same as your WiFi password
solis_s3_ip: "xxxx" # usually starts with '192.168.'
```

## Services

Some useful services offered by the app:

>_test_solis_flux_times_ which tests the connection to the Solis API and shows notional charge/discharge times for various settings (ignoring solar forecast and current energy)

>_check_logger_ which (if configured) tests that the S3 logger is connected and restarts it if necessary

>_clear_inverter_times_ which clears out any existing scheduled charge/discharge settings

>_set_inverter_times_ which manually sets a defined number of minutes of charging/discharging within a period

>_calc_energy_amp_hour_ which calculates the constant from observed charging/discharging values

## Entity States

Examples of useful entities which are set by the app (depending on the configured charge/discharge periods):

>_pyscript.charge_period2_forecasts_ = solar forecast energy (kWh) for the rest of the day for the currently set #2 charge period (list of the previous _history_days_ values)

>_pyscript.discharge_period_times_ = either 'Off' or the currently set #1 discharge period and current (HH:MM to HH:MM @??A) and when it was set (HH:MM MMM DD)

>_pyscript.energy_use_history_ = list of daily _energy_monitor_ values (kWh) for the previous _history_days_ period

>_pyscript.forecast_multiplier_history_ = list of multiplier adjustments to solar forecast for the previous _history_days_ period