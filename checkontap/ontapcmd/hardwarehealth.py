#!/usr/bin/env python3

#    Copyright (C) 2023  ConSol Consulting & Solutions Software GmbH
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
import json
from monplugin import Check,Status
from netapp_ontap.resources import CLI
from netapp_ontap import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,severity,item_filter

__cmd__ = "hardware-health"

"""
[-type {fan|thermal|voltage|current|battery-life|discrete|fru|nvmem|counter|minutes|percent|agent|unknown}] 
curl -X GET -kv 'https://user:pass@ip/api/private/cli/system/chassis/fru?fields=monitor,name,type,state,status'
curl -X GET -kv 'https://user:pass@ip/api/private/cli/system/health/subsystem?subsystem=environment'
"""

def run():
    """
    List Hardware sensors
    """
    parser = cli.Parser()
    parser.add_optional_arguments(cli.Argument.EXCLUDE,
                                  cli.Argument.INCLUDE,
                                  cli.Argument.TYPE,
                                  cli.Argument.PERFDATA)
    args = parser.get_args()
    # Setup module logging 
    logger = logging.getLogger(__name__)
    logger.disabled=True
    if args.verbose:
        for log_name, log_obj in logging.Logger.manager.loggerDict.items():
            log_obj.disabled = False
            logging.getLogger(log_name).setLevel(severity(args.verbose))

    setup_connection(args.host, args.api_user, args.api_pass)
    
    check = Check()
    """
    [-type {fan|thermal|voltage|current|battery-life|discrete|fru|nvmem|counter|minutes|percent|agent|unknown}] - Sensor Type
    [-state {normal|warn-low|warn-high|crit-low|crit-high|disabled|uninitialized|init-failed|not-available|invalid|retry|bad|not-present|failed|ignored|fault|unknown}]
    """
    if not args.type:
        sType = ['fan','thermal','voltage','current','battery-life','discrete','fru','nvmem','counter','minutes','percent','agent']
    else:
        sType = args.type

    mapWarn = ['warn-low','warn-high']
    mapCrit = ['crit-low','crit-high','bad','failed','fault']
    mapUnknown = ['unknown','not-present','ignored','uninitialized','init-failed','not-available','invalid']

    # Sensor environment
    try:
        response = CLI().execute("system node environment sensors show",fields="fru,state,name,type,value,units,discrete-state",type=f"{','.join(str(x) for x in sType)}")
        if response.http_response.json()['num_records'] == 0:
            check.exit(Status.UNKNOWN,f"no sensors found")
        for sensor in response.http_response.json()['records']:
            logger.debug(f"#--> {sensor}")
            if (args.exclude or args.include) and item_filter(args,sensor['name']):
                continue
            text = f"{sensor['type']} {sensor['name']} on node {sensor['node']} is {sensor['state']}"
            if args.perfdata:
                if 'value' in sensor and 'units' in sensor:

                    perfData = {'label': f"{sensor['node']}_{sensor['name']}",
                                'value': f"{sensor['value']}",
                                'uom': f"{sensor['units'].replace('mA*hr','mAh')}"}
                    check.add_perfdata(**perfData)
            if sensor['state'] in mapCrit:
                check.add_message(Status.CRITICAL,text)
            elif sensor['state'] in mapWarn:
                check.add_message(Status.WARNING,text)
            elif sensor['state'] in mapUnknown:
                check.add_message(Status.UNKNOWN,text)
        check.add_message(Status.OK,f"all {response.http_response.json()['num_records']} sensors are fine")
    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error.http_err_response.http_response.text))

    
    (code, message) = check.check_messages(separator="\n")
    check.exit(code=code,message=message)

if __name__ == "__main__":
    run()