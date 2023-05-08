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

from monplugin import Check,Threshold,Status
import logging
from netapp_ontap.resources import Aggregate,Plex
from netapp_ontap import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,item_filter,severity,bytes_to_uom,uom_to_bytes

__cmd__ = "aggregate-usage"
description = f"Mode {__cmd__} with -m / --metric % or size description like used_GB "
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
                                  cli.Argument.METRIC)
    args = parser.get_args()
    # Setup module logging
    logger = logging.getLogger(__name__)
    logger.disabled = True
    if args.verbose:
        for log_name, log_obj in logging.Logger.manager.loggerDict.items():
            log_obj.disabled = False
            logging.getLogger(log_name).setLevel(severity(args.verbose))

    check = Check(threshold = Threshold(args.warning or None, args.critical or None))
    setup_connection(args.host, args.api_user, args.api_pass)

    try:
        aggr_count = Aggregate.count_collection()
        logger.info(f"found {aggr_count} Aggregates")
        if aggr_count == 0:
            check.exit(Status.UNKNOWN, "no aggregates found")

        for aggr in Aggregate.get_collection():
            aggr.get(fields="space,uuid")
            if (args.exclude or args.include) and item_filter(args,aggr.name):
                logger.info(f"{aggr.name} filtered out and removed from check")
                aggr_count -= 1
                continue
            logger.info(f"Aggregate {aggr.name}")
            logger.debug(f"{aggr.__dict__}")
            
            plex_count = Plex.count_collection(aggr.uuid)
            if plex_count != 0:
                for plex in Plex.get_collection(aggr.uuid):
                    plex.get(fields="raid_groups")
                    logging.debug(f"Plex {plex.name}\n{plex.__dict__}")
                    for rg in plex.raid_groups:
                        if rg.reconstruct.active:
                            check.add_message(Status.CRITICAL, f"RaidGroup {rg.name} on Plex {plex.name} is reconstructing")
    
            value = {
                'usage': bytes_to_uom(aggr.space.block_storage.used,'%',aggr.space.block_storage.size),
                'used': aggr.space.block_storage.used,
                'free': aggr.space.block_storage.size - aggr.space.block_storage.used,
                'max': aggr.space.block_storage.size
                }

            for metric in ['usage','used','free']:
                opts = {}
                if metric in args.metric:
                    typ, uom, *_ = (args.metric.split('_') + ['%' if 'usage' in args.metric else 'B'])
                    threshold = {}
                    opts['threshold'] = {}
                    if '%' in uom:
                        s = check.threshold.get_status(value['usage'])
                        out = f"{value[typ] :.2f}%"
                        if args.warning:
                            threshold['warning'] = args.warning
                        if args.critical:
                            threshold['critical'] = args.critical
                    else:
                        s = check.threshold.get_status(bytes_to_uom(value[typ],uom))
                        if 'free' in typ:
                            pct = 100 - value['usage']
                        else:
                            pct = value['usage']

                        out = f"{bytes_to_uom(value[metric],uom)}{uom} ({pct :.2f} %) "
                        if args.warning:
                            threshold['warning'] = str(uom_to_bytes(args.warning,uom))
                        if args.critical:
                            threshold['critical'] = str(uom_to_bytes(args.critical,uom))
                    opts['threshold'] = Threshold(**threshold)
                    if s != Status.OK:
                        check.add_message(s, f"{args.metric} on {aggr.name} is: {out}")

                puom = '%' if metric == 'usage' else 'B'
                check.add_perfmultidata(aggr.name, 'aggregates',  label=metric, value=value[metric], uom=puom, **opts)
        (code, message) = check.check_messages(separator=' ',allok=f"all {aggr_count} aggregates are fine")
        check.exit(code=code,message=message)

    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error.http_err_response.http_response.text))
    except Exception as error:
        logger.exception(error)

if __name__ == "__main__":
    run()