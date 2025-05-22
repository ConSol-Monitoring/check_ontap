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
from netapp_ontap.resources import Port,FcPort
from netapp_ontap.error import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,item_filter,severity

__cmd__ = "port-health"
description = f"check port status"

"""
Check Port and FcPort endpoints. Disabled interfaces are ignored.
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

    setup_connection(args.host, args.api_user, args.api_pass, args.port)

    try:
        ##
        ## fibre channel ports
        ##
        """
        The operational state of the FC port. - startup - The port is booting up. - link_not_connected - The port has finished initialization, but a link with the fabric is not established. - online - The port is initialized and a link with the fabric has been established. - link_disconnected - The link was present at one point on this port but is currently not established. - offlined_by_user - The port is administratively disabled. - offlined_by_system - The port is set to offline by the system. This happens when the port encounters too many errors. - node_offline - The state information for the port cannot be retrieved. The node is offline or inaccessible.

        Valid choices:
        
        startup
        link_not_connected
        online
        link_disconnected
        offlined_by_user
        offlined_by_system
        node_offline
        unknown

        """
        FcPortOk = ['online']
        FcPortWarning = ['startup','link_disconnected']
        FcPortCritical = ['node_offline','offlined_by_system']
        FcPortUnknown = ['unknown']
        # Not interessted in link_not_connected or offlined_by_user
       
        fcport_count = FcPort.count_collection()
        if fcport_count == 0:
            check.add_message(Status.UNKNOWN,"no fc-ports found on device")
            
        FcPorts = FcPort.fast_get_collection(fields="*")
        # count of disabled ports 
        disabled = 0
        
        for fc in FcPorts:
            # filter
            if (args.exclude or args.include) and item_filter(args,fc.name):
                logger.info(f"exclude port  {fc.name}")
                fcport_count -= 1
                continue

            # Just use real fibre channel ports
            if fc.physical_protocol != "fibre_channel":
                logger.info(f"FcPort isn't a fibre channel {fc.name} {fc.physical_protocol}")
                fcport_count -= 1
                continue
                
            # not enabled or disabled by user     
            if not hasattr(fc, "enabled") or not fc.enabled or 'offlined_by_user' in fc.state:
                logger.info(f"FcPort isn't enabled {fc.name}")
                disabled += 1
                continue

            logger.info(f"checking {fc.node['name']} - {fc.name} - {fc.physical_protocol}")
            logger.debug(f"{fc}")
            out = f"{fc.physical_protocol} {fc.name} on node {fc.node['name']} is {fc.state}"
            
            if fc.state in FcPortOk:
                check.add_message(Status.OK, out)
            elif fc.state in FcPortWarning:
                check.add_message(Status.WARNING, out)
            elif fc.state in FcPortCritical:
                check.add_message(Status.CRITICAL, out)
            elif fc.state in FcPortUnknown:
                check.add_message(Status.UNKNOWN, out)
            else:
                pass
        
        ##
        ## Physical ports
        ##   
        port_count = Port.count_collection()
        if port_count == 0:
            check.add_message(Status.UNKNOWN,"no ports found on device")
        port_count += fcport_count     
        
        Ports = Port.get_collection(fields="*")
        for p in Ports:
            if (args.exclude or args.include) and item_filter(args,p.name):
                logger.info(f"exclude port  {p.name}")
                port_count -= 1
                continue

            if not hasattr(p, "enabled") or not p.enabled:
                logger.info(f"Port isn't enabled {p.name}")
                disabled += 1
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