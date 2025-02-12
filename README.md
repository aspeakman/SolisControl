# SolisControl

A Python package **soliscontrol** which has modules for controlling a Solis battery/inverter setup using the Solis Cloud API. 
This can be used to view key inverter parameters and to 
set daily charge times (within a cheap rate period) or discharge times (within a peak rate period). It will also
check that times are synchronised with the inverter and that charge currents do not exceed the configured maxima.

The project also includes **solis_flux_times** a [Pyscript](https://hacs-pyscript.readthedocs.io/en/latest/) Home Assistant app 
 for use with energy suppliers that offer cheap rate charging periods and peak rate discharging periods
such as the [Octopus Flux](https://octopus.energy/smart/flux/) tariff. For details see [README2](./README2.md).

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
solis_key_id: "xxxx"
solis_key_secret: "xxxx"
solis_user_name: "xxxx"
solis_password: "xxxx"
solis_station_id: "xxxx"
```

On your inverter you will also need to enable _Self Use_ mode and 
set _Time of Use: Optimal Income_ to _Run_ - see <https://www.youtube.com/watch?v=h1A80cSOrhA>

## Configuration

Put your `secrets.yaml` in the _soliscontrol_ folder then edit `main.yaml` to suit - an example as follows:

```
battery_capacity: 7.1 # in kWh - nominal stored energy of battery at 100% SOC (eg 2 * Pylontech US3000C with Nominal Capacity of 3.55 kWh each)
battery_max_current: 74 # in amps (eg 2 * Pylontech US3000C with spec Recommend Charge Current of 37A each)
# Also see https://www.youtube.com/watch?v=h1A80cSOrhA to view battery Dis/Charging Current Limits
inverter_max_current: 62.5 # in amps - see inverter datasheet specs for 'Max. charge / discharge current'  (eg 62.5A or 100A)
#api_url: = 'https://www.soliscloud.com:13333' # default
charge_period: # First period when energy can be imported from the grid at low rates
  start: "02:01"
  end: "04:59" 
  current: 50 # charge current setting in amps
  sync: 'random' # if 'start', charging is tied to start of period or if 'end' it is tied to the end (otherwise it starts randomly)
discharge_period: # First period when energy can be exported to the grid at high rates
  start: "16:01" # set both to "00:00" if no discharging
  end: "18:59" # set both to "00:00" if no discharging
  current: 50 # discharge current setting in amps
  sync: 'start' # if 'start', discharging is tied to start of period or if 'end' it is tied to the end (otherwise it starts randomly)
```

**Note there can be up to 3 charge_periods and 3 discharge periods** with different start and end times. 
As well as _charge_period_ and _discharge_period_ you could also define _charge_period2_, _charge_period3_,
_discharge_period2_ and _discharge_period3_ in the example above.

## Actions
Use the `solis_run.py` module. You should save your `secrets.yaml` in the same folder.

To get help:

> python solis_run.py -h

To get inverter status information:

> python solis_run.py

To set inverter charge and discharge times for the periods above to one hour per day:

> python solis_run.py -c1 60 -d1 60

To turn inverter charge and discharge times off:

> python solis_run.py -c1 0 -d1 0

If _charge_period3_ was configured, you could clear all existing settings and then set timeslot 3 to charge for one hour like this:

> python solis_run.py -r -c3 60

