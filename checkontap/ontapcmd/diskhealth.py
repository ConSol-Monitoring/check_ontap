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
from netapp_ontap.resources import Disk,Software
from netapp_ontap import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,item_filter,severity,compareVersion
import re

__cmd__ = "disk-health"
"""
Disk({
    'rpm': 7200, 
    'node': {
        'uuid': 'f3a35903-68ae-11e8-8898-4b3d2df62ccf', 
        'name': 'acme01', 
        '_links': {'self': {'href': '/api/cluster/nodes/f3a35903-68ae-11e8-8898-4b3d2df62ccf'}}
        }, 
    'shelf': {'uid': '4713285323093248592'}, 
    'fips_certified': False, 
    'aggregates': [{
        'uuid': 'fa49074c-5d93-4e5d-8d36-332226fcbe91', 
        'name': 'aggr0_acme01', 
        '_links': {'self': {'href': '/api/storage/aggregates/fa49074c-5d93-4e5d-8d36-332226fcbe91'}}
        }, 
        {'uuid': '97e37d61-23b0-4917-85c8-ae9d5354bba5', 
        'name': 'aggr1_acme01', 
        '_links': {'self': {'href': '/api/storage/aggregates/97e37d61-23b0-4917-85c8-ae9d5354bba5'}}
        }], 
    'vendor': 'NETAPP', 
    'firmware_version': 'NA00', 
    'usable_size': 3992785256448, 
    'self_encrypting': False, 
    'class': 'capacity', 
    'home_node': {
        'uuid': 'f3a35903-68ae-11e8-8898-4b3d2df62ccf', 
        'name': 'acme01', 
        '_links': {'self': {'href': '/api/cluster/nodes/f3a35903-68ae-11e8-8898-4b3d2df62ccf'}}
        }, 
    'container_type': 'shared', 
    'name': '1.0.9', 
    'uid': '5000CCA2:6938888C:00000000:00000000:00000000:00000000:00000000:00000000:00000000:00000000', 
    'bay': 9, 
    'model': 'X336_HAKPE04TA07', 
    'serial_number': 'K7H02UUL', 
    'type': 'fsas', 
    'state': 'present', 
    'pool': 'pool0'})
"""

def run():
    parser = cli.Parser()
    parser.add_optional_arguments(cli.Argument.EXCLUDE,
                                  cli.Argument.INCLUDE)
    parser.add_optional_arguments( {
        'name_or_flags': ['--mode'],
        'options': {
            'action': 'store',
            'choices': [
                'multipath',
                'diskhealth',
            ],
        'help': 'which diskhealth mode to check',
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
    
    setup_connection(args.host, args.api_user, args.api_pass)
    
    try:
        software = Software()
        software.get(fields='version')
        disk_count = Disk.count_collection()
        logger.debug(f"Found {disk_count} disks")
        if disk_count == 0:
            logger.debug(f"found {disk_count} disks")
            check.exit(Status.UNKNOWN, "no disks found")
        Disks = Disk.get_collection()
    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, f"ERROR => {error.http_err_response.http_response.text}")

    if args.mode == "multipath":
        minimumVersion = "9.9"
        if compareVersion(minimumVersion,software["version"]):
            check_multipath(check,logger,args,Disks)
        else:
            check.exit(Status.UNKNOWN,f"at least ONTAP v{minimumVersion} is required. Currently v{software['version']}  is installed")
    elif args.mode == "diskstate":
        check_diskstate(check,logger,args,Disks)
    else:
        check_diskstate(check,logger,args,Disks)

    (code,message) = check.check_messages(separator='\n  ')
    check.exit(code=code,message=message)

def check_multipath(check,logger,args,Disks):
    """
    Minimum ONTAP v9.9 is required
    Disk({
        'paths': [
            {'wwnn': '5000039a88191df8', 'port_name': 'B', 'initiator': '0d', 'port_type': 'sas', 'wwpn': '5000039a88191dfa'}, 
            {'wwnn': '5000039a88191df8', 'port_name': 'A', 'initiator': '0a', 'port_type': 'sas', 'wwpn': '5000039a88191df9'}, 
            {'wwnn': '5000039a88191df8', 'port_name': 'A', 'initiator': '0d', 'port_type': 'sas', 'wwpn': '5000039a88191df9'}, 
            {'wwnn': '5000039a88191df8', 'port_name': 'B', 'initiator': '0a', 'port_type': 'sas', 'wwpn': '5000039a88191dfa'}
            ], 
    """
    logger.info("starting multipath check")
    count = 0
    out = {}
    for disk in Disks:
        if (args.exclude or args.include) and item_filter(args,disk.name):
            continue
        disk.get()
        if not hasattr(disk,'paths'):
            logger.debug(f"{disk}")
            continue
        if len(disk.paths) % 2 != 0:
            check.add_message(Status.WARNING, f"Disk {disk.name:7} on bay {disk.bay:2} of node {disk.node.name} has {len(disk.paths)} paths")
        count += 1
    check.add_perfdata(label=f"total",value=int(count))
    check.add_message(Status.OK,f"{count} disks has symetric paths")

def check_diskstate(check,logger,args,Disks):
    out = {}
    cType = {}
    disk_count = Disk.count_collection()
    for disk in Disks:
        if (args.exclude or args.include) and item_filter(args,disk.name):
            continue
        disk.get()
        logger.debug(f"{disk}")
        stateWarn = re.match('reconstructing', disk.state)
        stateCrit = re.match('(broken|offline)', disk.state)

        if disk.container_type not in cType:
            cType[disk.container_type] = 0
        cType[disk.container_type] += 1

        if disk.container_type != "remote":
            if disk.node.uuid != disk.home_node.uuid:
                check.add_message(Status.WARNING, f"Disk {disk.name} is on node {disk.node.name} instead of {disk.home_node.name}")
            m = f"Disk {disk.name:7} on bay {disk.bay:2} of node {disk.home_node.name} is {disk.state}"
            if stateWarn:
                check.add_message(Status.WARNING,m)
            elif stateCrit:
                check.add_message(Status.CRITICAL,m)
            else:
                out[disk.name] = {}
                out[disk.name]['name'] = disk.name
                out[disk.name]['state'] = disk.state
                out[disk.name]['bay'] = disk.bay
                out[disk.name]['node'] = disk.home_node.name
        else:
            if disk.node.name != disk.home_node.name:
                m = f"Disk {disk.name:7} on bay {disk.bay:2} of node {disk.home_node.name} is not on home node"
                check.add_message(Status.WARNING,m)


    for c in cType.keys():
        check.add_perfdata(label=c,value=int(cType[c]))
    check.add_perfdata(label=f"total",value=int(disk_count))
    check.add_message(Status.OK, f"found {disk_count} disks at all while { ' - '.join({ f'{v} {k}' for (k,v) in cType.items()}) } ")
    for d in sorted(out.keys()):
        check.add_message(Status.OK, f"Disk {out[d]['name']:7} on bay {out[d]['bay']:2} of node {out[d]['node']} is {out[d]['state']}")

if __name__ == "__main__":
    run()