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

from monplugin import Check,Status
import logging
from netapp_ontap.resources import Aggregate,Plex 
from netapp_ontap import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,item_filter,percent_to,to_percent,bytes_to,to_bytes,severity

__cmd__ = "aggregate-usage"
description = f"Mode {__cmd__} with -U / --unit % or size description like GB "
"""
Aggregate({
    '_links': {'self': {'href': '/api/storage/aggregates/01d71c4b-88d8-43c3-ae33-afa2b64a629d'}}, 
    'uuid': '01d71c4b-88d8-43c3-ae33-afa2b64a629d', 
    'space': {
        'footprint': 139780465348608, 
        'efficiency': {'ratio': 186.6856716029982, 'logical_used': 24291687892377600, 'savings': 24161567097976004}, 
        'cloud_storage': {'used': 0}, 
        'efficiency_without_snapshots': {'ratio': 2.08165380808469, 'logical_used': 252303379914752, 'savings': 131100046807748}, 
        'block_storage': {
            'available': 62257396912128, 
            'full_threshold_percent': 98, 
            'used': 134769329168384, 
            'size': 197026726080512, 
            'inactive_user_data': 0}
        }, 
    'name': 'storage.central.acme'})
Plex({
    'aggregate': {
        'uuid': '97e37d61-23b0-4917-85c8-ae9d5354bba5', 
        '_links': {'self': {'href': '/api/storage/aggregates/97e37d61-23b0-4917-85c8-ae9d5354bba5'}}, 
        'name': 'aggr1_01'
        }, 
    'resync': {'active': False}, 
    'online': True, 
    'pool': 'pool0', 
    'state': 'normal', 
    'raid_groups': [{
        'cache_tier': False, 
        'recomputing_parity': {'active': False}, 
        'reconstruct': {'active': False}, 
        'degraded': False, 
        'disks': [{
            'disk': {'name': '1.0.11'}, 
            'usable_size': 3838499094528, 
            'state': 'normal', 
            'type': 'fsas', 
            'position': 'dparity'
            }, {
            'disk' .....
            }], 
        'name': 'rg0'}], 
    'name': 'plex0'})
"""
def run():
    parser = cli.Parser()
    parser.set_description(description)
    parser.add_required_arguments(cli.Argument.WARNING,cli.Argument.CRITICAL)
    parser.add_optional_arguments(cli.Argument.EXCLUDE,
                                  cli.Argument.INCLUDE,
                                  cli.Argument.UNIT)
    args = parser.get_args()
    # Setup module logging
    logger = logging.getLogger(__name__)
    logger.disabled = True
    if args.verbose:
        for log_name, log_obj in logging.Logger.manager.loggerDict.items():
            log_obj.disabled = False
            logging.getLogger(log_name).setLevel(severity(args.verbose))

    check = Check()

    check.set_threshold(
        warning=args.warning,
        critical=args.critical
    )

    setup_connection(args.host, args.api_user, args.api_pass)

    try:
        aggr_count = Aggregate.count_collection()
        logger.debug(f"found {aggr_count} Aggregates")
        if aggr_count == 0:
            check.exit(Status.UNKNOWN, "no aggregates found")

        for aggr in Aggregate.get_collection():
            aggr.get(fields="space,uuid")
            if (args.exclude or args.include) and item_filter(args,aggr.name):
                aggr_count -= 1
                continue
            for plex in Plex.get_collection(aggr.uuid):
                plex.get(fields="raid_groups")
                logging.debug(f"Plex {plex.name}\n{plex.__dict__}") 
                for rg in plex.raid_groups:
                    if rg.reconstruct.active:
                        check.add_message(Status.CRITICAL, f"RaidGroup {rg.name} on Plex {plex.name} is reconstructing")

            pctUsage = to_percent(aggr.space.block_storage.size,aggr.space.block_storage.used)
            unitPerf = {'label': f'{aggr.name}_space',
                    'value': aggr.space.block_storage.used,
                    'uom': 'B',
                    'min': 0,
                    'max': aggr.space.block_storage.size,
                    }
            pctPerf = {
                'label': f'{aggr.name}_percent',
                'value': pctUsage,
                'uom': '%',
                'min': 0,
                'max': 100,
            }
            if args.unit and '%' in args.unit:
                pctPerf['threshold'] = check.threshold
                check.add_perfdata(**pctPerf)
                unitPerf['warning'] = percent_to(aggr.space.block_storage.size,args.warning)
                unitPerf['critical'] = percent_to(aggr.space.block_storage.size,args.critical)
                check.add_perfdata(**unitPerf)
                check.add_message(
                    check.threshold.get_status(pctUsage),
                    f"{aggr.name} (Usage {bytes_to(aggr.space.block_storage.used,'GB')}/{bytes_to(aggr.space.block_storage.size,'GB')}GB {pctUsage}%)"
                )
            elif args.unit:
                unitPerf['warning'] = to_bytes(args.warning,args.unit)
                unitPerf['critical'] = to_bytes(args.critical,args.unit)
                check.add_perfdata(**unitPerf)
                check.add_perfdata(**pctPerf)
                check.add_message(
                    check.threshold.get_status(bytes_to(aggr.space.block_storage.used, args.unit)),
                    f"{aggr.name} (Usage {bytes_to(aggr.space.block_storage.used,args.unit)}/{bytes_to(aggr.space.block_storage.size,args.unit)}{args.unit} {pctUsage}%)"
                )
            else:
                unitPerf['threshold'] = check.threshold
                check.add_perfdata(**unitPerf)
                check.add_perfdata(**pctPerf)
                check.add_message(
                    check.threshold.get_status(aggr.space.block_storage.used),
                    f"{aggr.name} (Usage {aggr.space.block_storage.used}/{aggr.space.block_storage.size}B {pctUsage}%)"
                )
        (code, message) = check.check_messages(separator='\n  ',allok=f"all {aggr_count} aggregates are fine")
        check.exit(code=code,message=message)

    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error.http_err_response.http_response.text))
    
if __name__ == "__main__":
    run()
