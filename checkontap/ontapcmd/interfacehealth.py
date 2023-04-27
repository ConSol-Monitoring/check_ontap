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
from netapp_ontap.resources import IpInterface
from netapp_ontap import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,item_filter,severity

__cmd__ = "interface-health"
description = f"check interface status and home location"

"""
IpInterface(
    {'ip': {'address': '1.2.3.4', 'netmask': '24', 'family': 'ipv4'}, 
    'state': 'up', 
    ...
    'location': {
        'node': {
            'name': 'node-1', }
        'port': {
            'node': {'name': 'node-1'}, 
            'name': 'a0t', }
        'auto_revert': False, 
        'failover': 'default', 
        'home_port': {
            'node': {'name': 'node-1'}, 
            'name': 'a0t', }
        'home_node': {
            'name': 'node-1', 
            'is_home': True}, 
    'enabled': True, 
    'name': 'acme_data', 
    'scope': 'svm', 
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

    IpInts = []
    try:
        interface_count = IpInterface.count_collection()
        logger.info(f"found {interface_count} interfaces")
        if interface_count == 0:
            check.exit(Status.UNKNOWN, "no interfaces found")

        for IpInt in IpInterface.get_collection():
            IpInt.get()
            if (args.exclude or args.include) and item_filter(args,IpInt.name):
                logger.debug(f"exclude interface {IpInt.name}")
                continue
            logger.debug(f"INTERFACE {IpInt.name}\n{IpInt}")
            IpInts.append(IpInt)

    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error.http_err_response.http_response.text))

    count = 0

    for Int in IpInts:
        if not Int.enabled:
            logger.info(f"Interface {Int.name} is not enabled, ignore")
            continue
        count += 1
        if 'down' in Int.state:
            check.add_message(Status.CRITICAL, f"int {Int.name} is {Int.state}")
        if not Int.location.is_home:
            check.add_message(Status.CRITICAL, f"Int {Int.name} is on {Int.location.node.name} but should be on {Int.location.home_node.name}")

    check.add_message(Status.OK, f"{count} of {len(IpInts)} Interfaces are up")
    
    for Int in IpInts:
        check.add_message(Status.OK, f"Int {Int.name:40}{Int.state:5}{Int.ip.address:16}/{Int.ip.netmask:3} is homed {Int.location.is_home}")
        
    (code, message) = check.check_messages(separator='\n  ')
    check.exit(code=code,message=message)

if __name__ == "__main__":
    run()