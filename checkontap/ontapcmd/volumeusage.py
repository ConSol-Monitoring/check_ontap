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
from monplugin import Check,Status,Threshold, Range
from netapp_ontap.resources import Volume
from netapp_ontap.error import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,item_filter,severity,bytes_to_uom,range_in_bytes

__cmd__ = "volume-usage"
description = f"Mode {__cmd__} with -m / --metric usage or size description like used_GB. Inodes thresholds are alway given in %"
"""
space.used + space.available + snapshot.reserve_available = space.size
Volume({
    'files': {'maximum': 31122, 'used': 102},
    'name': 'foo_root',
    '_links': {'self': {'href': '/api/storage/volumes/ec5e675c-b124-11ed-8cdc-d039ea94786e'}},
    'svm': {
        'name': 'foo',
        '_links': {'self': {'href': '/api/svm/svms/e76b4940-b124-11ed-8cdc-d039ea94786e'}},
        'uuid': 'e76b4940-b124-11ed-8cdc-d039ea94786e'},
    'space': {
        'footprint': 6590464,
        'used_by_afs': 2080768,
        'volume_guarantee_footprint': 1056739328,
        'expected_available': 1017974784,
        'physical_used_percent': 1,
        'nearly_full_threshold_percent': 95,
        'used': 2080768,
        'over_provisioned': 0,
        'percent_used': 0,
        'size': 1073741824,
        'delayed_free_footprint': 10412032,
        'user_data': 40960,
        'available': 1017974784,
        'metadata': 11005952,
        'fractional_reserve': 100,
        'overwrite_reserve': 0,
        'filesystem_size': 1073741824,
        'available_percent': 99,
        'logical_space': {'used': 2080768, 'used_by_afs': 2080768, 'reporting': False, 'enforcement': False, 'used_by_snapshots': 0, 'used_percent': 0},
        'filesystem_size_fixed': False,
        'physical_used': 6590464,
        'size_available_for_snapshots': 1067151360,
        'total_footprint': 1084747776,
        'local_tier_footprint': 1084747776,
        'overwrite_reserve_used': 0,
        'afs_total': 1020055552,
        'full_threshold_percent': 98,
        'snapshot': {'used': 4509696, 'reserve_available': 49176576, 'reserve_percent': 5, 'space_used_percent': 8, 'autodelete_enabled': False, 'autodelete_trigger': 'volume', 'reserve_size': 53686272}}, 'uuid': 'ec5e675c-b124-11ed-8cdc-d039ea94786e'})
"""

def run():
    parser = cli.Parser()
    parser.set_description(description)
    parser.set_epilog("Name of SVM will be prepended automaticaly to the volume name")
    parser.add_required_arguments(cli.Argument.WARNING, cli.Argument.CRITICAL)
    parser.add_optional_arguments(cli.Argument.EXCLUDE,
                                  cli.Argument.INCLUDE,
                                  cli.Argument.NAME,
                                  cli.Argument.METRIC,
                                  cli.Argument.INODE_WARN, cli.Argument.INODE_CRIT,
                                  )
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
    vols = []

    try:
        volumes_count = Volume.count_collection()
        logger.info(f"found {volumes_count} volumes")
        if volumes_count == 0:
            check.exit(Status.UNKNOWN, "no volumes found")

        for vol in Volume.get_collection(fields="svm,space,files,space.snapshot"):
            if (args.exclude or args.include) and item_filter(args,vol.name):
                logger.info(f"But item filter exclude: '{args.exclude}' or include: '{args.include}' has matched {vol.name}")
                volumes_count -= 1
                continue
            else:
                if hasattr(vol,'space'):
                    if not hasattr(vol.space, 'used'):
                        logger.info(f"{vol.name} has no 'used' info in space object")
                        continue
                else:
                    logger.info(f"{vol.name} has no space info")
                    logger.debug(f"{vol.name}\n{vol}")
                    continue
                logger.info(f"SVM {vol.svm.name} VOLUME {vol.name}")
                logger.debug(f"{vol}")
                vols.append(vol)

        if volumes_count == 0:
            check.exit(Status.UNKNOWN, "no volumes found")

        for vol in vols:
            v = {
                'name': f"{vol.svm.name}_{vol.name}",
                'data_total': vol.space.size,
                'space': {
                    'max': vol.space.size,
                    'used': vol.space.used,
                    'usage': bytes_to_uom(vol.space.used, '%', vol.space.size),
                    'free': vol.space.available
                },
                'inodes': {
                    'max': vol.files.maximum,
                    'used': vol.files.used,
                    'usage': bytes_to_uom(vol.files.used, '%', vol.files.maximum),
                    'free': vol.files.maximum - vol.files.used
                },
            }
            if hasattr(vol.space, 'afs_total'):
                v['space']['usage'] = bytes_to_uom(vol.space.used, '%', vol.space.afs_total)
                v['space']['max'] = vol.space.afs_total
                
            if hasattr(vol.space.snapshot, 'reserve_size') and vol.space.snapshot.reserve_size > 0:
                v['snapshot'] = {
                    'max': vol.space.snapshot.reserve_size,
                    'used': vol.space.snapshot.used,
                    'usage': bytes_to_uom(vol.space.snapshot.used, '%' ,vol.space.snapshot.reserve_size)
                }
            elif vol.space.snapshot.used > 0:
                v['snapshot'] = {
                    'max': 0,
                    'used': vol.space.snapshot.used,
                    'usage': bytes_to_uom(vol.space.snapshot.used, '%', vol.space.size)
                }
            else:
                v['snapshot'] = {
                    'max': 0,
                    'used': vol.space.snapshot.used,
                    'usage': 0
                }

            # Space
            usage = Threshold(args.warning or None, args.critical or None)

            for metric in ['usage', 'used', 'free']:
                opts = {}
                typ, uom, *_ = (args.metric.split('_') + ['%' if 'usage' in args.metric else 'B'])
                if metric in args.metric:
                    threshold = {}
                    opts['threshold'] = {}
                    if '%' in uom:
                        s = usage.get_status(v['space']['usage'])
                        out = f"{v['space'][typ] :.2f}%"
                        if args.warning:
                            threshold['warning'] = args.warning
                        if args.critical:
                            threshold['critical'] = args.critical
                    else:
                        s = usage.get_status(bytes_to_uom(v['space'][typ],uom))
                        if 'free' in typ:
                            pct = 100 - v['space']['usage']
                        else:
                            pct = v['space']['usage']
                        out = f"{bytes_to_uom(v['space'][typ],uom)}{uom} ({pct :.2f}%)"
                        if args.warning:
                            threshold['warning'] = range_in_bytes(Range(args.warning), uom)
                        if args.critical:
                            threshold['critical'] = range_in_bytes(Range(args.critical), uom)

                    opts['threshold'] = Threshold(**threshold)
                    puom = '%' if metric == 'usage' else 'B'
                    check.add_perfdata(label=f"{v['name']} {typ}", value=v['space'][typ], uom=puom, **opts)

                    if s != Status.OK:
                        check.add_message(s, f"{args.metric} on {v['name']} is: {out}")

                else:
                    puom = '%' if metric == 'usage' else 'B'
                    check.add_perfdata(label=f"{v['name']} {metric}", value=v['space'][metric], uom=puom)

            # data_total as perdate
            check.add_perfdata(label=f"{v['name']} total",value=v['space']['max'], uom='B')

            # Inode usage
            if args.inode_warning or args.inode_critical:
                inodes = Threshold(args.inode_warning or None, args.inode_critical or None)
                opts = {}
                opts['threshold'] = {}
                threshold = {}
                s = inodes.get_status(v['inodes']['usage'])
                if args.inode_warning:
                    threshold['warning'] = args.inode_warning
                if args.inode_critical:
                    threshold['critical'] = args.inode_critical
                opts['threshold']= Threshold(**threshold)

                if s != Status.OK:
                    check.add_message(s, f"Inodes usage on {v['name']} is {v['inodes']['usage']}%")
                check.add_perfdata(label=f"{v['name']} inodes usage", value=v['inodes']['usage'], uom="%", **opts)
            else:
                check.add_perfdata(label=f"{v['name']} inodes usage", value=v['inodes']['usage'], uom="%")

            # Snapshot usage just as perfdata
            check.add_perfdata(label=f"{v['name']} snapshot usage" ,value=v['snapshot']['usage'], uom='%')

        (code, message) = check.check_messages(separator='\n  ',allok=f"all {volumes_count} volumes are ok")
        check.exit(code=code,message=f"{message}")

    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error))
    except Exception as error:
        logger.exception(error)

if __name__ == "__main__":
    run()