# SolisControl

Includes a Python package **soliscontrol** which has modules for controlling a Solis inverter using the Solis Cloud API. 
This can be used to view key inverter parameters and to 
set daily charge times (within a cheap rate period) or discharge times (within a peak rate period). It will also
check that times are synchronised with the inverter and that charge currents do not exceed the configured maxima.

The project also includes **solis_flux_times** a [Pyscript](https://hacs-pyscript.readthedocs.io/en/latest/) Home Assistant app 
 for use with energy suppliers that offer a cheap rate charging period and a peak rate discharging period
such as the [Octopus Flux](https://octopus.energy/smart/flux/) tariff (for details see below).

This project is based on the Solis API docs for 
[monitoring](https://oss.soliscloud.com/templet/SolisCloud%20Platform%20API%20Document%20V2.0.pdf)
and [control](https://oss.soliscloud.com/doc/SolisCloud%20Device%20Control%20API%20V2.0.pdf)	
(and on the [solis_control](https://github.com/stevegal/solis_control) project which
has the practical details for constructing requests to the Solis API). 

## Pre-requisites

You should access the Solis Cloud API by following [these 
instructions](https://solis-service.solisinverters.com/en/support/solutions/articles/44002212561-request-api-access-soliscloud).
Based on the values returned you will need to create a `secrets.yaml` - replace xxxx in the following example:
```
key_id: "xxxx"
key_secret: "xxxx"
user_name: "xxxx"
password: "xxxx"
station_id: "xxxx"
```

On your inverter you will also need to enable _Self Use_ mode and 
set _Time of Use: Optimal Income_ to _Run_ - see <https://www.youtube.com/watch?v=h1A80cSOrhA>

----------

# _soliscontrol_ python package 

## Configuration

Put your `secrets.yaml` in the _soliscontrol_ folder then edit `main.yaml` to suit - an example as follows:

```
battery_capacity: 7.1 # in kWh - nominal stored energy of battery at 100% SOC (eg 2 * Pylontech US3000C with Nominal Capacity of 3.55 kWh each)
battery_max_current: 74 # in amps (eg 2 * Pylontech US3000C with spec Recommend Charge Current of 37A each)
# Also see https://www.youtube.com/watch?v=h1A80cSOrhA to view battery Dis/Charging Current Limits
inverter_max_current: 62.5 # in amps - see inverter datasheet specs for 'Max. charge / discharge current'  (eg 62.5A or 100A)
charge_period: # Cheap period when energy can be imported from the grid at low rates
  start: "02:05"
  end: "04:55" 
  current: 50 # charge current setting in amps
  sync: 'random' # if 'start', charging is tied to start of period or if 'end' it is tied to the end (otherwise it starts randomly)
discharge_period: # Peak period when energy can be exported to the grid at high rates
  start: "16:05" # set both to "00:00" if no discharging
  end: "18:55" # set both to "00:00" if no discharging
  current: 50 # discharge current setting in amps
  sync: 'start' # if 'start', discharging is tied to start of period or if 'end' it is tied to the end (otherwise it starts randomly)
#api_url: = 'https://www.soliscloud.com:13333' # default
```

## Actions
Use the `solis_control_req_mod.py` module. The other modules in the package 
(`solis_control_req_class.py`, `solis_control_async_mod.py`, `solis_control_async_class.py`) 
are experimental. You should save your `secrets.yaml` in the same folder.

To get help:

> python solis_control_req_mod.py -h

To get inverter status information:

> python solis_control_req_mod.py

To set inverter charge and discharge times to one hour per day:

> python solis_control_req_mod.py -c 60 -d 60

----------

# _solis_flux_times_ Home Assistant pyscript app 

## Description

The pyscript app sets inverter charge (and discharge) times daily just before the start of the  
cheap and peak rate periods (it runs a defined number of 
minutes (_cron_before_) these periods). 
Each charge or discharge episode is restricted to within the appropriate period
but its duration takes into account the solar forecast and the 
current battery charge level. You can use the _sync_ setting of the appropriate period to choose whether
the charge/discharge episode is tied to the beginning or end of the period or takes place at a random point within it.

You should work out the following two values depending on your household usage:

* _morning_requirement_ 
> This is the target energy 'reserve' you want to
have in place after your cheap rate period. The 'reserve' consists of the predicted solar yield for 
the rest of the day and the battery energy stored after charging.

> **Set this to zero if you don't want any charging
to take place or to a negative number if you don't want to take any action (for example if you have an existing charging 
schedule that you want to preserve)**

> (note you can use more intuitive names for this setting _kwh_after_charge_ or _post_charge_target_ if your provider offers cheap rate charging outside the morning period)

* _evening_requirement_ 
> This is the target energy 'reserve' you want to
have in place after your peak rate period. The 'reserve' consists of the predicted solar yield for the rest
of the day and the battery energy remaining after discharging. 

> **Set this to zero if you don't want any discharging
to take place or to a negative number if you don't want to take any action (for example if you have an existing discharging 
schedule that you want to preserve)**.

> (note you can use more intuitive names for this setting _kwh_after_discharge_ or _post_discharge_target_ if your provider offers peak rate discharging outside the evening period)

You should also monitor the accuracy of solar forecast values for your home (they can be adjusted using the
 _forecast_uplift_ multiplication factor in the configuration below).

## Installation
First install a solar forecast integration either [Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/) or
[Solcast](https://github.com/tabascoz/ha-solcast-solar) (which I have found to be more accurate).

Next install [Pyscript](https://hacs-pyscript.readthedocs.io/en/latest/). 
Now copy `solis_flux_times.py` to the pyscript _apps_ folder
and copy `solis_common.py` and `solis_control_req_mod.py` to the pyscript _modules_ folder (and if necessary `solis_s3_logger.py` see below). 
Finally create `config.yaml` and `secrets.yaml` (see below) in the main pyscript folder.

## Configuration
Setup of pyscript is via the HA `configuration.yaml` - an example as follows:
```
pyscript: !include pyscript/config.yaml
```
Configuration of _solis_flux_times_ is via the pyscript `config.yaml` - an example as follows:
```
allow_all_imports: true
hass_is_global: false
apps:
  solis_flux_times:
    forecast_remaining: 'solcast_pv_forecast_forecast_remaining_today' # entity id of Solcast remaining energy today (kWh) - in 'sensor' domain
    # forecast_remaining: 'energy_production_today_remaining' #  alternative entity id of Forecast.Solar remaining energy today (kWh) - in 'sensor' domain
    forecast_uplift: 1.0 # multiplication factor for forecast values if they prove to be pessimistic or optimistic
    morning_requirement: 12.0 # ideal target kWh level for rest of the day (solar predicted + battery reserve) at cheap rate charge period
    # zero means cheap charging will be actively turned off each day (a negative number will disable any action)
    # can also be the id of an entity which defines this value eg a helper = 'input_number.morning_reserve'
    evening_requirement: 5.0 # ideal target kWh level for rest of the day (solar predicted + battery reserve) at peak rate discharge period
    # zero means peak discharging will be actively turned off each day (a negative number will disable any action)
    # can also be the id of an entity which defines this value eg a helper = 'input_number.evening_reserve'
    cron_before: 20 # minutes before start of periods below to assess forecast and set charging/discharging times
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
        sync: 'random' # if 'start', charging is tied to start of period or if 'end' it is tied to the end (otherwise it starts randomly)
      discharge_period: # Peak period when energy can be exported to the grid at high rates
        start: "16:05" # set both to "00:00" if no discharging
        end: "18:55" # set both to "00:00" if no discharging
        current: 50 # discharge current setting in amps
        sync: 'random' # if 'start', discharging is tied to start of period or if 'end' it is tied to the end (otherwise it starts randomly)
      #Uncomment these lines if you have an S3 data logger that occasionally disconnects - checks access and if necessart restarts the logger
      #s3_username: !secret solis_s3_username
      #s3_password: !secret solis_s3_password
      #s3_ip: !secret solis_s3_ip
```
Based on the settings above you will need to add the following lines to the pyscript `secrets.yaml` replacing xxxx:
```
solis_key_id: "xxxx"
solis_key_secret: "xxxx"
solis_user_name: "xxxx"
solis_password: "xxxx"
solis_station_id: "xxxx"
#solis_s3_username: "xxxx" # see above
#solis_s3_password: "xxxx" # see above
#solis_s3_ip: "xxxx" # see above
```

## Actions

Look in the logs for entries tagged _solis_flux_times_. In the example the charge times
will be set _cron_before_ ie 20 mins before the start of the cheap rate period at 01:45 and the discharge times
will be set _cron_before_ ie 20 mins before the start of the peak rate period at 15:45.

There is also a _test_solis_ pyscript service which allows you to test different 
settings and view the results in the log (without taking any action).