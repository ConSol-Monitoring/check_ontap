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
from netapp_ontap.resources import IpInterface,FcInterface,Svm
from netapp_ontap.error import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,item_filter,severity
import re

__cmd__ = "interface-health"
description = f"check interface status and home location"

"""
"""

def run():
    parser = cli.Parser()
    parser.set_description(description)
    parser.add_optional_arguments(cli.Argument.EXCLUDE,
                                  cli.Argument.INCLUDE)
    parser.add_optional_arguments( {
        'name_or_flags': ['--exclude-svm'],
        'options': {
            'action': 'store',
            'help': 'regexp to exclude interfaces from svm',
        }
    })
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

    SvmInt = []
    # check for running svm's
    try:
        svm = Svm.get_collection(fields="name,state,ip_interfaces,fc_interfaces")
        for s in svm:
            if hasattr(s, 'ip_interfaces') and 'stopped' in s.state:
                for int in s.ip_interfaces:
                    logger.info(f"found int {int.name} on stopped svm {s.name}")
                    SvmInt.append(int.name)
            elif hasattr(s, 'fc_interfaces') and 'stopped' in s.state:
                for int in s.fc_interfaces:
                    logger.info(f"found int {int.name} on stopped svm {s.name}")
                    SvmInt.append(int.name)
                
            
    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, f"Error => {error}")
    except Exception as error:
        check.exit(Status.UNKNOWN, f"{error}")
    
    Ints = []
    
    try:
        ##
        ## IP Interfaces
        ##
        interface_count = IpInterface.count_collection()
        logger.info(f"found {interface_count} ip interfaces")
        if interface_count >= 1:
            for IpInt in IpInterface.get_collection(fields="*"):
                if (args.exclude or args.include) and item_filter(args,IpInt.name):
                    logger.info(f"exclude interface {IpInt.name} due to include / exclude")
                    continue
                if args.exclude_svm and hasattr(IpInt, 'svm'):
                    if re.search(args.exclude_svm, IpInt.svm.name):
                        logger.info(f"exclude interface {IpInt.name} due to SVM exclude. SVM {IpInt.svm.name}")
                        continue
                logger.debug(f"INTERFACE {IpInt.name}\n{IpInt}")
                Ints.append(IpInt)

        ##
        ## FC Interfaces
        ##
        
        fcinterface_count = FcInterface.count_collection()
        logger.info(f"found {fcinterface_count} fc interfaces")
        if fcinterface_count >= 1:
            for FcInt in FcInterface.get_collection(fields="*"):
                if (args.exclude or args.include) and item_filter(args, FcInt.name):
                    logger.info(f"exclude interface {FcInt.name} due to include / exclude")
                    continue
                if args.exclude_svm and hasattr(FcInt, 'svm'):
                    if re.search(args.exclude_svm, FcInt.svm.name):
                        logger.info(f"exclude interface {FcInt.name} due to SVM exclude. SVM {FcInt.svm.name}")
                        continue
                    
                logger.debug(f"INTERFACE {FcInt.name}\n{FcInt}")
                Ints.append(FcInt)

            
    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, f"Error => {error}")
    except Exception as error:
        check.exit(Status.UNKNOWN, f"{error}")

    count = 0

    # check for state (up/down), enabled (true/false) and home node
    for Int in Ints:
        if not Int.enabled:
            logger.info(f"Interface {Int.name} is not enabled, ignore")
            continue
        if 'down' in Int.state and Int.name in SvmInt:
            logger.info(f"Interface {Int.name} for stopped svm {Int.svm.name}")
            continue
        elif 'down' in Int.state:
            check.add_message(Status.CRITICAL, f"int {Int.name} is {Int.state}")
            continue
        
        count += 1
        if not Int.location.is_home:
            check.add_message(Status.CRITICAL, f"Int {Int.name} is on {Int.location.node.name} but should be on {Int.location.home_node.name}")

    check.add_message(Status.OK, f"{count} up / {len(Ints) - count} down - {len(Ints)} Total ({interface_count} ip / {fcinterface_count} fc at all)")
    
    for Int in Ints:
        if hasattr(Int, 'ip'):
            ipaddress = Int.ip.address
            ipnetmask = Int.ip.netmask
        else:
            ipaddress = "no_ip"
            ipnetmask = ""
        if hasattr(Int.location, 'is_home' ):
            ishome = Int.location.is_home
        else:
            ishome = None
        if hasattr(Int, 'svm'):
            check.add_message(Status.OK, f"Int {Int.name:40}{Int.state:5}{ipaddress:16}/{ipnetmask:3} is homed {ishome} and belongs to SVM {Int.svm.name}")
        else:
            check.add_message(Status.OK, f"Int {Int.name:40}{Int.state:5}{ipaddress:16}/{ipnetmask:3} is homed {ishome}")
        
    (code, message) = check.check_messages(separator='\n  ')
    check.exit(code=code,message=message)

if __name__ == "__main__":
    run()