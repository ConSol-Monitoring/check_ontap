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
from monplugin import Check,Status,Threshold
from netapp_ontap.resources import Volume
from netapp_ontap import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,to_percent,percent_to,to_bytes,bytes_to,item_filter,severity

__cmd__ = "volume-usage"
"""
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
    parser.set_epilog("Name of SVM will be prepended automaticaly to the volume name")
    parser.add_required_arguments(cli.Argument.WARNING, cli.Argument.CRITICAL)
    parser.add_optional_arguments(cli.Argument.EXCLUDE,
                                  cli.Argument.INCLUDE,
                                  cli.Argument.NAME,
                                  cli.Argument.UNIT,
                                  cli.Argument.INODE_WARN, cli.Argument.INODE_CRIT,
                                  cli.Argument.SNAP_WARN, cli.Argument.SNAP_CRIT,
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

        for vol in Volume.get_collection():
            vol.get(fields="svm,space,files")
            if not hasattr(vol,'space'):
                continue
            if (args.exclude or args.include) and item_filter(args,vol.name):
                logger.info(f"But item filter exclude: '{args.exclude}' or include: '{args.include}' has matched {vol.name}")
                volumes_count -= 1
                continue
            logger.debug(f"SVM {vol.svm.name} VOLUME {vol.name}\n{vol}")
            vols.append(vol)

    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error.http_err_response.http_response.text))

    for vol in vols:
        v = {
            'name': f"{vol.svm.name}_{vol.name}",
            'space': {
                'max': vol.space.size,
                'used': vol.space.used,
                'pct': to_percent(vol.space.size, vol.space.used)
            },
            'inodes': {
                'max': vol.files.maximum,
                'used': vol.files.used,
                'pct': to_percent(vol.files.maximum, vol.files.used)
            },
        }
        if hasattr(vol.space, 'afs_total'):
            v['data_total'] = vol.space.afs_total
        else:
            v['data_total'] = vol.space.size
        if hasattr(vol.space.snapshot, 'reserve_size'):
            v['snapshot'] = {
                'max': vol.space.snapshot.reserve_size,
                'used': vol.space.snapshot.used,
                'pct': to_percent(vol.space.snapshot.reserve_size, vol.space.snapshot.used)
            }
        else:
            v['snapshot'] = {
                'max': 0,
                'used': vol.space.snapshot.used,
                'pct': 0
            }
            
        # unchecked perfdata
        check.add_perfmultidata(v['name'], 'volume_usage', label="data_total",value=v['data_total'], uom="B")
        # Volume usage
        t = {}
        if args.unit and '%' in args.unit:
            t['warning'] = percent_to(v['space']['max'],args.warning)
            t['critical'] = percent_to(v['space']['max'],args.critical)
        elif args.unit:
            t['warning'] = to_bytes(args.warning,args.unit)
            t['critical'] = to_bytes(args.critical,args.unit)
        else:
            t['warning'] = args.warning
            t['critical'] = args.critical

        usage = Threshold(**t)
        output = (f"{v['name']} (Usage {bytes_to(v['space']['used'],'GB')}/{bytes_to(v['space']['max'],'GB')}GB {v['space']['pct']}%, Inodes {v['inodes']['pct']}%, Snapshots {v['snapshot']['pct']}%)")
        check.add_message(usage.get_status(v['space']['used']),f"space {output}")
        check.add_perfmultidata(v['name'], 'volume_usage',  label="space_used", value=v['space']['used'], uom="B", warning=t['warning'], critical=t['critical'], min=0, max=v['space']['max'])

        # Inode usage
        t = {}
        if args.inode_warning:
            t['warning'] = percent_to(v['inodes']['max'],args.inode_warning)
        else:
            t['warning'] = ""
        if args.inode_critical:
            t['critical'] = percent_to(v['inodes']['max'],args.inode_critical)
        else:
            t['critical'] = ""

        inodes = Threshold(**t)
        check.add_message(inodes.get_status(v['inodes']['used']),f"inodes {output}")
        check.add_perfmultidata(v['name'], 'volume_usage',  label="inodes_used", value=v['inodes']['used'], warning=t['warning'], critical=t['critical'],min=0, max=v['inodes']['max'])

        # Snapshot usage
        t = {}
        if args.snapshot_warning:
            t['warning'] = percent_to(v['snapshot']['max'],args.snapshot_warning)
        else:
            t['warning'] = ""
        if args.snapshot_critical:
            t['critical'] = percent_to(v['snapshot']['max'],args.snapshot_critical)
        else:
            t['critical'] = ""

        snap = Threshold(**t)
        check.add_message(snap.get_status(v['snapshot']['used']),f"snaps {output}")
        check.add_perfmultidata(v['name'], 'volume_usage',  label="snap_used", value=v['snapshot']['used'], uom="B", warning=t['warning'], critical=t['critical'],min=0, max=v['inodes']['max'])
        
    (code, message) = check.check_messages(separator='\n  ',separator_all='\n',allok=f"all {volumes_count} volumes are ok")
    check.exit(code=code,message=f"{message}")

if __name__ == "__main__":
    run()