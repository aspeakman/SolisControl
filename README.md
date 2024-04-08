# SolisControl

Includes a Python package **soliscontrol** which has modules for controlling a Solis inverter using the Solis Cloud API. 
This can be used to view key inverter parameters and to 
set daily charge times (within a cheap rate period) or discharge times (within a peak rate period). 

The project also includes **solis_flux_times** a [pyscript](https://hacs-pyscript.readthedocs.io/en/latest/) Home Assistant app specifically for use 
with the [Octopus Flux](https://octopus.energy/smart/flux/) tariff (for details see below).

Note this project is heavily based on [solis_control](https://github.com/stevegal/solis_control) which
has the only details I could find for the v2 solis control API. 

### Pre-requisites

You should access the Solis Cloud API by following [these 
instructions](https://solis-service.solisinverters.com/en/support/solutions/articles/44002212561-request-api-access-soliscloud).
Based on the values returned you will need to create a `secrets.yaml` - replace xxxx in the following example:
```
solis_key_id: "xxxx"
solis_key_secret: "xxxx"
solis_user_name: "xxxx"
solis_password: "xxxx"
solis_station_id: "xxxx"
```

On your inverter you will also need to enable _Self Use_ mode and 
set _Time of Use: Optimal Income_ to _Run_ - see <https://www.youtube.com/watch?v=h1A80cSOrhA>


## _soliscontrol_ package 

### Configuration

Put your `secrets.yaml` in the _soliscontrol_ folder then edit `main.yaml` to suit - an example as follows:

```
battery_capacity: 7.1 # in kWh - nominal stored energy of battery at 100% SOC (eg 2 * Pylontech US3000C with Nominal Capacity of 3.55 kWh each)
battery_max_current: 74 # in amps (eg 2 * Pylontech US3000C with spec Recommend Charge Current of 37A each)
  # Also see https://www.youtube.com/watch?v=h1A80cSOrhA to view battery Dis/Charging Current Limits
inverter_max_current: 62.5 # in amps - see inverter datasheet specs for 'Max. charge / discharge current'  (eg 62.5A or 100A)
charge_period: # morning cheap period when energy can be imported from the grid at low rates
  start: "02:05"
  end: "04:55" 
  current: 50 # charge current setting in amps
discharge_period: # evening peak period when energy can be exported to the grid at high rates
  start: "16:05"
  end: "18:55"
  current: 50 # discharge current setting in amps
#api_url: = 'https://www.soliscloud.com:13333' # default
```

### Actions
Use the `solis_control_req_mod.py` module. The other modules in the package 
(`solis_control_req_class.py`, `solis_control_async_mod.py`, `solis_control_async_class.py`) 
are experimental. You should save your `secrets.yaml` in the same folder.

To get help:

> python solis_control_req_mod.py -h

To get inverter status information:

> python solis_control_req_mod.py

To set inverter charge and discharge times to one hour per day:

> python solis_control_req_mod.py 60 60


## _solis_flux_times_ Home Assistant app 

### Description

The app sets inverter charge and discharge times daily just before the start of the charge and discharge periods defined in `config.yaml`.
The duration of the charge or discharge period is based on the predicted solar yield, the 
existing battery charge level and the _requirement_ values set in the configuration (see below).

_morning_requirement_ is the target energy 'reserve' you want to
have in place after your morning cheap rate. The 'reserve' consists of the predicted solar yield for 
the rest of the day and the battery energy stored after charging.

_evening_requirement_ is the target energy 'reserve' you want to
have in place after your evening peak rate. The 'reserve' consists of the predicted solar yield for the rest
the day and the battery energy remaining after discharging. **Set this to zero if you don't want any discharging
to take place**.


### Installation
First install the [Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/) integration.
Next copy `solis_flux_times.py` to the pyscript _apps_ folder
and copy `solis_common.py` and `solis_control_req_mod.py` to the pyscript _modules_ folder. Finally append 
the contents of your `secrets.yaml` to the pyscript `secrets.yaml`.

### Configuration
Configuration is via the pyscript `config.yaml` - an example as follows:
```
allow_all_imports: true
hass_is_global: false
apps:
  solis_flux_times:
    forecast_remaining: 'energy_production_today_remaining' # entity id of solar forecast remaining energy today (kWh) - in 'sensor' domain
    morning_requirement: 11 # target kWh level (solar predicted + battery stored) at morning charge period
    evening_requirement: 4 # target kWh level (solar predicted + battery stored) at evening discharge period
    cron_before: 20 # minutes before start of periods below to set charging/discharging times
    solis_control:
      key_secret: !secret solis_key_secret
      key_id: !secret solis_key_id
      user_name: !secret solis_user_name
      password: !secret solis_password
      station_id: !secret solis_station_id
      #api_url: = 'https://www.soliscloud.com:13333' # default
      battery_capacity: 7.1 # in kWh - nominal stored energy of battery at 100% SOC (eg 2 * Pylontech US3000C with Nominal Capacity of 3.55 kWh each)
      battery_max_current: 74 # in amps (eg 2 * Pylontech US3000C with Recommend Charge Current of 37A each)
          # Also see https://www.youtube.com/watch?v=h1A80cSOrhA to view battery Dis/Charging Current Limits
      inverter_max_current: 62.5 # in amps - see inverter datasheet specs for 'Max. charge / discharge current'  (eg 62.5A or 100A)
      charge_period: # Cheap period when energy can be imported from the grid at low rates
        start: "02:05"
        end: "04:55" 
        current: 50 # charge current setting in amps
      discharge_period: # Peak period when energy can be exported to the grid at high rates
        start: "16:05"
        end: "18:55"
        current: 50 # discharge current setting in amps
```

### Actions

Look in the logs for entries tagged _solis_flux_times_. In the example the charge time
will be set _cron_before_ ie 20 mins before the start of the morning cheap rate period at 01:45 and the discharge time
will be set _cron_before_ ie 20 mins before the start of the peak evening rate period at 15:45.

There is also a _test_solis_ pyscript service which allows you test different 
settings and view the results in the log (without taking any action).