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
from netapp_ontap.resources import Lun
from netapp_ontap import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,to_percent,percent_to,to_bytes,bytes_to,item_filter,severity

__cmd__ = "lun-usage"

"""
"""
def run():
    """
    Wenn alles passt steht hier die Hilfe
    """
    parser = cli.Parser()
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
        critical=args.critical,
    )
    
    setup_connection(args.host, args.api_user, args.api_pass)

    try:
        luns_count = Lun.count_collection()
        if luns_count == 0:
            check.exit(Status.UNKNOWN, "no luns found")
        for lun in Lun.get_collection():
            lun.get(fields="space")
            logger.debug(f"lun info for {lun.name}\n{lun.__dict__}")
            if (args.exclude or args.include) and item_filter(args,lun.name):
                luns_count -= 1
                continue

            pctUsage = to_percent(lun.space.size,lun.space.used)
            unitPerf = {'label': f'{lun.name}_space',
                    'value': lun.space.used,
                    'uom': 'B',
                    'min': 0,
                    'max': lun.space.size,
                    }
            pctPerf = {
                'label': f'{lun.name}_percent',
                'value': pctUsage,
                'uom': '%',
                'min': 0,
                'max': 100,
            }
            if args.unit and '%' in args.unit:
                pctPerf['threshold'] = check.threshold
                check.add_perfdata(**pctPerf)
                unitPerf['warning'] = percent_to(lun.space.size,args.warning)
                unitPerf['critical'] = percent_to(lun.space.size,args.critical)
                check.add_perfdata(**unitPerf)
                check.add_message(
                    check.threshold.get_status(pctUsage),
                    f"{lun.name} (Usage {bytes_to(lun.space.used,'GB')}/{bytes_to(lun.space.size,'GB')}GB {pctUsage}%)"
                )
            elif args.unit:
                unitPerf['warning'] = to_bytes(args.warning,args.unit)
                unitPerf['critical'] = to_bytes(args.critical,args.unit)
                check.add_perfdata(**unitPerf)
                pctPerf['warning'] = to_percent(lun.space.size,unitPerf['warning'])
                pctPerf['critical'] = to_percent(lun.space.size,unitPerf['critical'])
                check.add_perfdata(**pctPerf)
                check.add_message(
                    check.threshold.get_status(bytes_to(lun.space.used, args.unit)),
                    f"{lun.name} (Usage {bytes_to(lun.space.used,args.unit)}/{bytes_to(lun.space.size,args.unit)}{args.unit} {pctUsage}%)"
                )
            else:
                unitPerf['threshold'] = check.threshold
                check.add_perfdata(**unitPerf)
                pctPerf['warning'] = to_percent(lun.space.size,args.warning)
                pctPerf['critical'] = to_percent(lun.space.size,args.critical)
                check.add_perfdata(**pctPerf)
                check.add_message(
                    check.threshold.get_status(lun.space.used),
                    f"{lun.name} (Usage {lun.space.used}/{lun.space.size}B {pctUsage}%)"
                )
        (code, message) = check.check_messages(separator='\n  ', allok=f"all {luns_count} luns are ok")
        check.exit(code=code,message=message)

    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error.http_err_response.http_response.text))
    
if __name__ == "__main__":
    run()
