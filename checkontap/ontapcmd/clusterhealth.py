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
from netapp_ontap.resources import Cluster, Node
from netapp_ontap import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,severity

__cmd__ = "cluster-health"

"""
"""
def run():
    parser = cli.Parser()
    args = parser.get_args()
    # Setup module logging 
    logger = logging.getLogger(__name__)
    logger.disabled=True
    if args.verbose:
        for log_name, log_obj in logging.Logger.manager.loggerDict.items():
            log_obj.disabled = False
            logging.getLogger(log_name).setLevel(severity(args.verbose))

    setup_connection(args.host, args.api_user, args.api_pass)
    
    check = Check(shortname="")
    # Cluster global state
    try:
        cluster = Cluster()
        cluster.get(fields="name,metric,version")
        logger.debug(f"Cluster info \n{cluster.__dict__}")
        if 'ok' in cluster.metric.status:
            check.add_message(Status.OK, "{}".format(cluster.version.full))
        else:
            check.add_message(Status.CRITICAL,"Cluster global status is {}".format(cluster.metric.status))
    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error.http_err_response.http_response.text))

    # Cluster node states
    try:
        for node in Node.get_collection(fields="name,state,membership,ha"):
            logger.debug(f"Node info \n{node.__dict__}")
            m = "{} state {} as {}; giveback: {}; takeover: {}".format(node.name,node.state,node.membership,node.ha.giveback.state,node.ha.takeover.state)
            if 'up' in node.state: 
                check.add_message(Status.OK, m)
            elif 'down' in node.state:
                check.add_message(Status.CRITICAL, m)
            else:
                check.add_message(Status.WARNING, m)
    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error.http_err_response.http_response.text))
    
    (code, message) = check.check_messages(separator="\n")
    check.exit(code=code,message=message)

if __name__ == "__main__":
    run()