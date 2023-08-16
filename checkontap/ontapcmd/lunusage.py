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
from monplugin import Check,Status,Threshold,Range
from netapp_ontap.resources import Lun
from netapp_ontap.error import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,item_filter,severity,bytes_to_uom,range_in_bytes

__cmd__ = "lun-usage"
description = f"Mode {__cmd__} with -m / --metric usage (%) or size desciption like used_GB"

"""
"""
def run():
    """
    Wenn alles passt steht hier die Hilfe
    """
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
        luns_count = Lun.count_collection()
        if luns_count == 0:
            check.exit(Status.UNKNOWN, "no luns found")
        for lun in Lun.get_collection():
            lun.get(fields="space")
            if (args.exclude or args.include) and item_filter(args,lun.name):
                logger.info(f"LUN {lun.name} filtered out and removed from check")
                luns_count -= 1
                continue
            logger.debug(f"lun info for {lun.name}\n{lun.__dict__}")

            value = {
                'usage': bytes_to_uom(lun.space.used, '%', lun.space.size),
                'used': lun.space.used,
                'free': lun.space.size - lun.space.used,
                'max': lun.space.size
            }
           
            for metric in ['usage', 'used', 'free']:
                opts = {}
                puom = '%' if metric == 'usage' else 'B'
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
                            threshold['warning'] = range_in_bytes(Range(args.warning),uom)
                        if args.critical:
                            threshold['critical'] = range_in_bytes(Range(args.critical),uom)
                    opts['threshold'] = Threshold(**threshold)
                    if s != Status.OK:
                        check.add_message(s, f"{args.metric} on {lun.name} is: {out}")
                        
                    check.add_perfdata(label=f"{lun.name} {metric}", value=value[metric], uom=puom, **opts)
                else:
                    check.add_perfdata(label=f"{lun.name} {metric}", value=value[metric], uom=puom)
            check.add_perfdata(label=f"{lun.name} total", value=value['max'], uom=puom)
        (code, message) = check.check_messages(separator='\n',allok=f"all {luns_count} luns are fine")
        check.exit(code=code,message=message)

    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error))
    except Exception as error:
        logger.exception(error)
    
if __name__ == "__main__":
    run()
