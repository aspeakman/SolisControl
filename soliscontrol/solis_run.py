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
    parser.add_argument("-v", "--verbose", help="additional information messages are printed out", action='store_true')
    
    with open('secrets.yaml', 'r') as file:
        secrets = yaml.safe_load(file)
    with open('main.yaml', 'r') as file:
        config = yaml.safe_load(file)
    config.update(secrets)  
    periods = common.extract_periods(config)
    for p in periods:
        name_parts = p['long_name'].split()
        period_number = name_parts[2]
        if p['charge']:
            short = "-c%s" % (period_number)
            long = "--%s" % p['name']
            help = "%s duration in minutes (zero means no charging)" % p['long_name'].lower()
        else:
            short = "-d%s" % (period_number)
            long = "--%s" % p['name']
            help = "%s duration in minutes (zero means no discharging)" % p['long_name'].lower()
        parser.add_argument(short, long, help=help, type=int)
    args = parser.parse_args()    

    with solis_control.get_session() as session:
    
        connected = solis_control.connect(config, session)
        
        if connected:
            
            if not args.silent:
                common.print_status(config)
            
            error = False
            if args.remove:
                result = solis_control.set_inverter_data(config, session, inverter_data=None, verbose=args.verbose) # turns off all charging/discharging
                if not args.silent or args.verbose:
                    if result == 'OK':
                        print ('Cleared inverter data')
                    else:
                        print ('Error: clearing inverter data: %s' % (result))
                        error = True
            else:
                args_dict = dict(vars(args))
                #for k, v in args_dict.items():
                #     print(k, v)
                for p in periods:
                    period_name = p['name']
                    if args_dict.get(period_name) is not None and config.get(period_name):
                        config_period = config[period_name]
                        cstart, cend = common.start_end_from_minutes(config_period, args_dict[period_name])
                        cstart, cend = common.limit_times(config_period, cstart, cend)
                        params = { 'start': cstart, 'end': cend, 'amps': str(config_period['current']) }
                        result = solis_control.set_inverter_params(config, session, params, charge=p['charge'], timeslot=p['timeslot'], verbose=args.verbose)
                        if not args.silent or args.verbose:
                            if result == 'OK':
                                print ('***%s New: %s - %s (%sA)' % (p['long_name'], cstart, cend, str(config_period['current'])))
                            else:
                                print ('***%s Error: %s' % (p['long_name'], result))
                                error = True
            
            if error is False:          
                inverter_data = solis_control.get_inverter_data(config, session, verbose=args.verbose)
                if not args.silent or args.verbose:
                    if inverter_data:
                        for p in periods:
                            existing = common.extract_inverter_params(inverter_data, charge=p['charge'], timeslot=p['timeslot'])
                            print ('%s: %s - %s (%sA)' % (p['long_name'], existing['start'], existing['end'], existing['amps']))
                    else:
                        print ('Error: cannot get inverter data')