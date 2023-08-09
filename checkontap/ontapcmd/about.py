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


from dataclasses import fields
import logging
from monplugin import Check,Status
from netapp_ontap.resources import Software
from netapp_ontap.error import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,severity

__cmd__ = "about"
description = f"{__cmd__} need just connection settings and show up the ontap version"

def run():
    parser = cli.Parser()
    parser.set_epilog("Connect to ONTAP API and check Software version")
    parser.set_description(description)
    args = parser.get_args()

    # Setup module logging 
    logger = logging.getLogger(__name__)
    logger.disabled=True
    if args.verbose:
        for log_name, log_obj in logging.Logger.manager.loggerDict.items():
            log_obj.disabled = False
            logging.getLogger(log_name).setLevel(severity(args.verbose))

    setup_connection(args.host, args.api_user, args.api_pass)
    
    check = Check()
    # About overview module
    try:
        software = Software()
        software.get(fields='version')
        logger.debug(f"Software info \n{software.__dict__}")
        check.add_message(Status.OK,f"current version id {software['version']}")
    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error))

    (code, message) = check.check_messages(separator="\n")
    check.exit(code=code,message=message)

if __name__ == "__main__":
    run()