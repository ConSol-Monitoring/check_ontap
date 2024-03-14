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
import re
import datetime
from monplugin import Check,Status,Threshold
from netapp_ontap.resources import Software,SnapmirrorRelationship
from netapp_ontap.error import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,severity

__cmd__ = "snapmirror-health"
"""
"""
def TimeParser(netapptimeperiod):
    t = 0
    for i in re.findall(r"(\d+)([WDHMS])", netapptimeperiod):
        t += int(i[0]) * {"S": 1, "M": 60, "H": 60*60, "D": 60*60*24}[i[1]]
    return t

def run():
    parser = cli.Parser()
    parser.add_optional_arguments(cli.Argument.WARNING,
                                  cli.Argument.CRITICAL,
                                  cli.Argument.EXCLUDE,
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

    try:
        software = Software()
        software.get(fields='version')
        relationship = SnapmirrorRelationship()
        relship = relationship.get_collection(fields="*")
        relCount = 0
        relProblemCount = 0
        lagThreshold = Threshold(args.warning or None, args.critical or None)
        for rel in relship:
            relCount += 1
            lagTime = TimeParser(rel.lag_time)
            HRTime = str(datetime.timedelta(seconds=lagTime))
            
            msg = f"Relationship {rel.state} for {rel.source.path}"
            logger.info(f"Health: {rel.healthy} state: {rel.state} lag: {HRTime} {rel.source.path}")
           
            # check lag_time  
            lagCheck = lagThreshold.get_status(lagTime) 
            check.add_message(lagCheck, f"lag time for {rel.source.path} is {HRTime}")
            if lagCheck != Status.OK:
                relProblemCount +=1
           
            # check health status 
            if rel.healthy:
                continue
            elif not rel.healthy and rel.unhealthy_reason:
                relProblemCount += 1
                for msg in rel.unhealthy_reason:
                    check.add_message(Status.CRITICAL,f"{msg['message']}")
            elif not rel.healthy:
                relProblemCount += 1
                check.add_message(Status.CRITICAL,msg)
                
    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, f"ERROR => {error}")

    (code,message) = check.check_messages(separator='\n  ')
    if code != Status.OK:
        check.exit(code=code,message=f"{relProblemCount} Problems found\n  {message}")
    else:
        check.exit(code=code,message=f"No problems found ( {relCount} checked )")

if __name__ == "__main__":
    run()