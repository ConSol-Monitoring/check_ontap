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
from monplugin import Check,Status
from netapp_ontap.resources import CLI,Node
from netapp_ontap.error import NetAppRestError
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
                                  cli.Argument.PERFDATA)
    parser.add_optional_arguments({
        'name_or_flags': ['--type'],
        'options': {
            'action': 'store',
            'nargs': '+',
            'help': 'List of available sensor types (separated by space):\nfan thermal voltage current battery-life discrete fru nvmem counter minutes percent agent unknown',
        }
    })
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

    mapWarn = ['warn-low','warn-high','ok-with-suppressed']
    mapCrit = ['crit-low','crit-high','bad','failed','fault','degraded','unreachable']
    mapUnknown = ['unknown','not-present','ignored','uninitialized','init-failed','not-available','invalid']
    nvramOk = ['battery_ok','battery_partially_discharged','battery_fully_charged']
    nvramWarn = ['battery_near_end_of_life','battery_over_charged']
    nvramCrit = ['battery_full_discharged','battery_not_present','battery_at_end_of_life']
    nvramUnknown = ['battery_unknown']

    logger.info(f"checking sensors: {sType}")
    try:
        # Node info
        nodes_count = Node.count_collection()
        nodes = Node.get_collection(fields="*")
        for node in nodes:
            logger.info(f"{node.name}")
            logger.debug(f"{node}")
            if 'thermal' in sType:
                logger.info(f"Thermal {node.controller.over_temperature}")
                msg = f"Temperature on {node.name} is {node.controller.over_temperature}"
                if node.controller.over_temperature != "normal":
                    check.add_message(Status.WARNING, msg)
                else:
                    check.add_message(Status.OK, msg)
            if 'fan' in sType and hasattr(node.controller, 'failed_fan'):
                logger.info(f"FAN {node.controller.failed_fan}")
                msg = f"Fan on {node.name}: {node.controller.failed_fan.message.message}"
                if node.controller.failed_fan.count > 0:
                    check.add_message(Status.WARNING, msg)
                else:
                    check.add_message(Status.OK, msg)
            if ('voltage' in sType or 'current' in sType) and hasattr(node.controller, 'failed_power_supply'):
                logger.info(f"PSU {node.controller.failed_power_supply}")
                msg = f"PSU on {node.name}: {node.controller.failed_power_supply.message.message}"
                if node.controller.failed_power_supply.count > 0:
                    check.add_message(Status.WARNING, msg)
                else:
                    check.add_message(Status.OK, msg)
            if 'battery-life' in sType and hasattr(node, 'nvram'):
                logger.info(f"NVRAM {node.nvram}")
                msg = f"NVRAM on {node.name}: '{node.nvram.battery_state}'"
                if node.nvram.battery_state in nvramWarn:
                    check.add_message(Status.WARNING, msg)
                elif node.nvram.battery_state in nvramCrit:
                    check.add_message(Status.CRITICAL, msg)
                elif node.nvram.battery_state in nvramUnknown:
                    check.add_message(Status.UNKNOWN, msg)
                else:
                    check.add_message(Status.OK, msg)
            if 'fru' in sType and hasattr(node.controller, 'frus'):
                logger.info(f"FRUs for node {node.name}")
                for fru in node.controller.frus:
                    msg = f"FRU {fru.id} on {node.name} is {fru.state}"
                    if fru.state in mapWarn:
                        check.add_message(Status.WARNING, msg)
                    elif fru.state in mapCrit:
                        check.add_message(Status.CRITICAL, msg)
                    elif fru.state in mapUnknown:
                        check.add_message(Status.UNKNOWN, msg)
                    else:
                        check.add_message(Status.OK, msg)

        # Sensor environment
        response = CLI().execute("system node environment sensors show",fields="fru,state,name,type,value,units,discrete-state",type=f"{','.join(str(x) for x in sType)}")
        if response.http_response.json()['num_records'] == 0:
            check.exit(Status.UNKNOWN,f"no sensors found")
        for sensor in response.http_response.json()['records']:
            logger.debug(f"{sensor}")
            if (args.exclude or args.include) and item_filter(args,sensor['name']):
                continue

            msg = f"{sensor['type']} {sensor['name']} on node {sensor['node']} is {sensor['state']}"

            if args.perfdata:
                if 'value' in sensor and 'units' in sensor:
                    perfData = {'label': f"{sensor['node']}_{sensor['name']}",
                                'value': f"{sensor['value']}",
                                'uom': f"{sensor['units'].replace('mA*hr','mAh')}"}
                    check.add_perfdata(**perfData)

            if sensor['state'] in mapCrit:
                check.add_message(Status.CRITICAL,msg)
            elif sensor['state'] in mapWarn:
                check.add_message(Status.WARNING,msg)
            elif sensor['state'] in mapUnknown:
                check.add_message(Status.UNKNOWN,msg)

        (code, message) = check.check_messages(separator="\n")
        if code != Status.OK:
            check.exit(code=code,message=message)
        else:
            check.exit(code=code,message=f"all {response.http_response.json()['num_records']} checked sensors are fine\n{message}")

    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, f"Error => {error}")
    except Exception as error:
        logger.exception(error)

if __name__ == "__main__":
    run()