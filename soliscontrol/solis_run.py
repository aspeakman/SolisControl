#!/usr/bin/env python
import logging
import yaml
import argparse

try:
    import solis_control_req_mod as solis_control
    import solis_common as common
except ImportError:
    # following lines add this file's parent directory to sys.path without using __file__ which is unreliable
    # see https://stackoverflow.com/questions/714063/importing-modules-from-parent-folder
    from inspect import getsourcefile
    import os.path as path, sys
    current_dir = path.dirname(path.abspath(getsourcefile(lambda:0)))
    sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])
    from soliscontrol import solis_control_req_mod as solis
    from soliscontrol import solis_common as common
    sys.path.pop(0) # restore sys.path

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description='Status and/or set charging/discharging times for the Solis API client',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-r", "--remove", help="remove all existing inverter charging/discharging times", action='store_true')
    parser.add_argument("-s", "--silent", help="no status messages are printed out", action='store_true')
    parser.add_argument("-t", "--test", help="test mode, no actions are taken", action='store_true')
    
    with open('secrets.yaml', 'r') as file:
        secrets = yaml.safe_load(file)
    with open('main.yaml', 'r') as file:
        config = yaml.safe_load(file)
    config.update(secrets)  
    periods = common.extract_periods(config)
    for p in periods:
        if p['charge']:
            short = "-c%d" % (p['timeslot'] + 1)
            long = "--%s" % p['name']
            help = "%s duration in minutes (zero means no charging)" % p['long_name'].lower()
        else:
            short = "-d%d" % (p['timeslot'] + 1)
            long = "--%s" % p['name']
            help = "%s duration in minutes (zero means no discharging)" % p['long_name'].lower()
        parser.add_argument(short, long, help=help, type=int)
    args = parser.parse_args()    

    with solis_control.get_session() as session:
    
        solis_control.connect(config, session)
        
        if args.remove:
            action = 'Notionally' if args.test else 'Actually'
            if args.test:
                result = 'OK'
            else:
                result = solis_control.set_inverter_data(config, session, inverter_data=None) # turns off all charging/discharging
            if not args.silent:
                if result == 'OK':
                    print ('%s cleared inverter data' % action)
                else:
                    print ('Error: clearing inverter data: %s' % (result))
        
        if not args.silent:
            common.print_status(config, args.test)
        
        inverter_data = solis_control.get_inverter_data(config, session)
        if inverter_data:
            
            if not args.silent:
                for p in periods:
                    existing = common.extract_inverter_params(inverter_data, charge=p['charge'], timeslot=p['timeslot'])
                    print ('%s: %s - %s (%sA)' % (p['long_name'], existing['start'], existing['end'], existing['amps']))
                    
            action = 'Notional' if args.test else 'Actual'
            
            args_dict = dict(vars(args))
            #for k, v in args_dict.items():
            #     print(k, v)
            for p in periods:
                period_name = p['name']
                if args_dict.get(period_name) is not None and config.get(period_name):
                    config_period = config[period_name]
                    cstart, cend = common.start_end_from_minutes(config_period, args_dict[period_name])
                    cstart, cend = common.limit_times(config_period, cstart, cend)
                    if args.test:
                        result = 'OK'
                    else:
                        params = { 'start': cstart, 'end': cend, 'amps': str(config_period['current']) }
                        result = solis_control.set_inverter_params(config, session, params, charge=p['charge'], timeslot=p['timeslot'])
                    if not args.silent:
                        if result == 'OK':
                            print ('%s New %s: %s - %s (%sA)' % (action, p['long_name'], cstart, cend, str(config_period['current'])))
                        else:
                            print ('%s Error: %s' % (p['long_name'], result))