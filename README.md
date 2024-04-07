# SolisControl

Python controller modules for Solis inverters using the Solis Cloud API. At the moment this can be used for one action
- to set the daily charge times (within a cheap rate period) and/or discharge times (within a peak rate period). 

You can enable access and view details of the Solis Cloud v1 API by following these 
instructions[https://solis-service.solisinverters.com/en/support/solutions/articles/44002212561-request-api-access-soliscloud].
You will also need to enable Self Use mode and set Time of Use: Optimal Income to Run
on your inverter - see[https://www.youtube.com/watch?v=h1A80cSOrhA]

This project is heavily based on solis_control[https://github.com/stevegal/solis_control] which
has the only details I could find for the v2 solis control API. 

The project includes a pyscript[https://hacs-pyscript.readthedocs.io/en/latest/] Home Assistant app specifically for use 
with the Octopus Flux tariff (for details see below).

## Standalone module configuration
Configuration is via 'main.yaml' - an example as follows:
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
API credentials are held in 'secrets.yaml' - details as follows:
```
key_id: "xxxx"
key_secret: "xxxx"
user_name: "xxxx"
password: "xxxx"
station_id: "xxxx"
```

## Standalone module actions
To get help:
```
python solis_control_req_mod.py -h
```
To get inverter status information:
```
python solis_control_req_mod.py
```
To set inverter charge and discharge times to one hour per day:
```
python solis_control_req_mod.py -s -a 60 60
```

## Pyscript installation
You will need to install the (Forecast.Solar integration)[https://www.home-assistant.io/integrations/forecast_solar/]
Copy 'solis_flux_times.py' to the pyscript 'apps' folder
Copy 'solis_common.py' and 'solis_control_req_mod.py' to the pyscript 'modules' folder

In the config.py a key parameter is 'morning_requirement' which is the target energy reserve you want to
have in place after your morning cheap rate. The 'reserve' consists of the predicted solar yield for the rest
the day and the battery energy stored after charging.

The other key parameter is 'evening_requirement' which is the target energy reserve you want to
have in place after your evening peak rate. The 'reserve' consists of the predicted solar yield for the rest
the day and the battery energy remaining after discharging. Set this to zero if you don't want any discharging
to take place.

## Pyscript configuration
Configuration is via the pyscript 'config.yaml' - an example as follows:
```
allow_all_imports: true
hass_is_global: false
apps:
  solis_flux_times:
    forecast_remaining: 'energy_production_today_remaining' # entity id of solar forecast remaining energy today (kWh) - in 'sensor' domain
    morning_requirement: 11 # target kWh level (solar predicted + battery stored) before morning charge period
    evening_requirement: 4 # target kWh level (solar predicted + battery stored) before evening discharge period
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
API credentials are held in the pyscript 'secrets.yaml' - details as follows:
```
solis_key_id: "xxxx"
solis_key_secret: "xxxx"
solis_user_name: "xxxx"
solis_password: "xxxx"
solis_station_id: "xxxx"
```