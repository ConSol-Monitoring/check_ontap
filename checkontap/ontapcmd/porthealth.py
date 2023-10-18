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
from netapp_ontap.resources import Port
from netapp_ontap.error import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,item_filter,severity

__cmd__ = "port-health"
description = f"check port status"

"""
Port({
    'mtu': 1500,
    'uuid': 'e5b8287b-b111-11ed-975c-d039ea958568',
    '_links': {'self': {'href': '/api/network/ethernet/ports/e5b8287b-b111-11ed-975c-d039ea958568'}},
    'reachability': 'not_repairable',
    'state': 'down',
    'mac_address': 'd0:39:ev:95:x5:5e',
    'type': 'physical',
    'node': {
        'uuid': '12c08d1a-e131-11ec-9572-d039ea958568',
        '_links': {'self': {'href': '/api/cluster/nodes/12c08d1a-e131-11ec-9572-d039ea958568'}},
        'name': 'Cluster01-Node02'},
    'enabled': False,
    'name': 'e0e'})
"""

def run():
    parser = cli.Parser()
    parser.set_description(description)
    parser.add_optional_arguments(cli.Argument.EXCLUDE,
                                  cli.Argument.INCLUDE)
    args = parser.get_args()

    # Setup module logging
    logger = logging.getLogger(__name__)
    logger.disabled = True
    if args.verbose:
        for log_name, log_obj in logging.Logger.manager.loggerDict.items():
            log_obj.disabled = False
            logging.getLogger(log_name).setLevel(severity(args.verbose))

    check = Check()

    setup_connection(args.host, args.api_user, args.api_pass)

    try:
        port_count = Port.count_collection()
        
        if port_count == 0:
            check.exit(Status.UNKNOWN,"no ports found on device")
            
        disabled = 0
        
        Ports = Port.get_collection(fields="*")
        
        for p in Ports:
            if not hasattr(p, "enabled") or not p.enabled:
                logger.info(f"Port isn't enabled {p.name}")
                disabled += 1
                continue

            if (args.exclude or args.include) and item_filter(args,p.name):
                logger.info(f"exclude port  {p.name}")
                port_count -= 1
                continue

            logger.info(f"checking {p.node.name} - {p.name} - {p.type}")
            logger.debug(f"{p}")
            out = f"{p.type} {p.name} on node {p.node.name} is {p.state}"
            # check for type lag
            if 'lag' in p.type:
                active = [a.name for a  in p.lag.active_ports]
                activePorts = set(active)
                logger.info(f"LAG port {p.name} has {activePorts} as active ports")
                missing = [ m.name for m in p.lag.member_ports if m.name not in activePorts ]
                if len(missing) > 0:
                    check.add_message(Status.CRITICAL,f"{out}, port {missing} is missing on lag")
                else:
                    check.add_message(Status.OK,f"{out}, with members {active}")
            # check for type vlan and physical
            else:
                if not 'up' in p.state:
                    check.add_message(Status.CRITICAL, out)
                else:
                    check.add_message(Status.OK,out)

    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error))
    except Exception as error:
        logger.exception(error)

    short = f"checked {port_count} Ports; ({port_count- disabled} enabled, {disabled} disabled)"
    (code, message) = check.check_messages(separator='\n')
    check.exit(code=code,message=f"{short}\n{message}")

if __name__ == "__main__":
    run()