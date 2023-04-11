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
from netapp_ontap.resources import Volume
from netapp_ontap import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,to_percent,percent_to,to_bytes,bytes_to,item_filter,severity

__cmd__ = "volume-usage"
"""
Volume({
    'type': 'rw', 
    'svm': {
        '_links': {'self': {'href': '/api/svm/svms/82b98e0f-68c7-11e8-ace3-00a098d32021'}}, 
        'uuid': '82b98e0f-68c7-11e8-ace3-00a098d32021', 
        'name': acme01'}, 
    'comment': '', 
    'aggregates': [{'name': 'aggr1_acme01', 'uuid': '97e37d61-23b0-4917-85c8-ae9d5354bba5'}],
    'size': 30918266974208, 
    'create_time': '2018-06-05T16:01:04+02:00', 
    '_links': {'self': {'href': '/api/storage/volumes/40a80741-d540-4900-a24f-050e9b5128b1'}}, 
    'clone': {'is_flexclone': False}, 
    'metric': {
        'timestamp': '2022-10-21T11:04:15+00:00', 
        'iops': {'total': 743, 'write': 235, 'read': 0, 'other': 507}, 
        'duration': 'PT15S', 
        'cloud': {
            'timestamp': '2021-06-21T06:53:30+00:00', 
            'iops': {'total': 0, 'write': 0, 'read': 0, 'other': 0}, 
            'duration': 'PT15S', 
            'latency': {'total': 0, 'write': 0, 'read': 0, 'other': 0}, 
            'status': 'ok'}, 
        'throughput': {'total': 13756079, 'write': 13753895, 'read': 2184, 'other': 0}, 
        'latency': {'total': 216, 'write': 239, 'read': 9864, 'other': 200}, 
        'status': 'ok'}, 
    'style': 'flexvol', 
    'cloud_retrieval_policy': 'default', 
    'uuid': '40a80741-d540-4900-a24f-050e9b5128b1', 
    'analytics': {'state': 'off'}, 
    'snapmirror': {'is_protected': False}, 
    'language': 'c.utf_8', 
    'nas': {'export_policy': {'name': 'default'}}, 
    'name': 'nasvol', 
    'space': {'available': 16884657414144, 'size': 30918266974208, 'used': 13723911647232}, 
    'state': 'online', 
    'tiering': {'policy': 'none'}, 
    'snapshot_policy': {'name': 'none'}
    })
"""
def run():
    parser = cli.Parser()
    parser.set_epilog("Name of SVM will be prepended automaticaly to the volume name")
    parser.add_required_arguments(cli.Argument.WARNING,cli.Argument.CRITICAL)
    parser.add_optional_arguments(cli.Argument.EXCLUDE,
                                  cli.Argument.INCLUDE,
                                  cli.Argument.NAME,
                                  cli.Argument.UNIT)
    args = parser.get_args()

    # Setup module logging
    logger = logging.getLogger(__name__)
    logger.disabled = True
    if args.verbose:
        for log_name, log_obj in logging.Logger.manager.loggerDict.items():
            log_obj.disabled = False
            logging.getLogger(log_name).setLevel(severity(args.verbose))

    check = Check(shortname="")

    check.set_threshold(
        warning=args.warning,
        critical=args.critical,
    )
    
    setup_connection(args.host, args.api_user, args.api_pass)
    vols = [] 
    try:
        volumes_count = Volume.count_collection()
        logger.info(f"found {volumes_count} volumes")
        if volumes_count == 0:
            check.exit(Status.UNKNOWN, "no vols found")
        
        for vol in Volume.get_collection():
            vol.get()
            if not hasattr(vol,'space'):
                continue
            if (args.exclude or args.include) and item_filter(args,vol.name):
                volumes_count -= 1
                continue
            logger.debug(f"VOLUME {vol.name}\n{vol}")
            vols.append(vol) 

    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error.http_err_response.http_response.text))

    for vol in vols: 
        if vol.svm.name:
            if vol.svm.name not in vol.name:
                volname = f"{vol.svm.name}_{vol.name}"
        else:
            volname = f"{vol.name}"
        pctUsage = to_percent(vol.space.size,vol.space.used)
        unitPerf = {'label': f'{volname}_space',
                'value': vol.space.used,
                'uom': 'B',
                'min': 0,
                'max': vol.space.size,
                }
        pctPerf = {
            'label': f'{volname}_percent',
            'value': pctUsage,
            'uom': '%',
            'min': 0,
            'max': 100,
        }
        if args.unit and '%' in args.unit:
            pctPerf['threshold'] = check.threshold
            check.add_perfdata(**pctPerf)
            unitPerf['warning'] = percent_to(vol.space.size,args.warning)
            unitPerf['critical'] = percent_to(vol.space.size,args.critical)
            check.add_perfdata(**unitPerf)
            check.add_message(
                check.threshold.get_status(pctUsage),
                f"{vol.name} (Usage {bytes_to(vol.space.used,'GB')}/{bytes_to(vol.space.size,'GB')}GB {pctUsage}%)"
            )
        elif args.unit:
            unitPerf['warning'] = to_bytes(args.warning,args.unit)
            unitPerf['critical'] = to_bytes(args.critical,args.unit)
            check.add_perfdata(**unitPerf)
            check.add_perfdata(**pctPerf)
            check.add_message(
                check.threshold.get_status(bytes_to(vol.space.used, args.unit)),
                f"{vol.name} (Usage {bytes_to(vol.space.used,args.unit)}/{bytes_to(vol.space.size,args.unit)}{args.unit} {pctUsage}%)"
            )
        else:
            unitPerf['threshold'] = check.threshold
            check.add_perfdata(**unitPerf)
            check.add_perfdata(**pctPerf)
            check.add_message(
                check.threshold.get_status(vol.space.used),
                f"{vol.name} (Usage {vol.space.used}/{vol.space.size}B {pctUsage}%)"
            )
    (code, message) = check.check_messages(separator='\n  ',allok=f"all {volumes_count} are ok")
    check.exit(code=code,message=message)

if __name__ == "__main__":
    run()
