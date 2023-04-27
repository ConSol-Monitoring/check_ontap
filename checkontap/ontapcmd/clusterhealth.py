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
from netapp_ontap.resources import Cluster, Node, IpInterface
from netapp_ontap import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,severity,item_filter

__cmd__ = "cluster-health"

"""
"""
def run():
    parser = cli.Parser()
    parser.add_optional_arguments(cli.Argument.EXCLUDE,cli.Argument.INCLUDE)
    parser.add_optional_arguments({
        'name_or_flags': ['--mode'],
        'options': {
            'action': 'store',
            'choices': ['health', 'connect'],
            'default': 'health',
        'help': 'check health state or interconnect of a cluster',
        }
    })
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

    # Get data
    try:
        cluster = Cluster()
        cluster.get(fields="name,metric,version")
        logger.debug(f"Cluster info \n{cluster.__dict__}")
        nodes_count = Node.count_collection()
        logger.debug(f"found {nodes_count} nodes")
        nodes = list(Node.get_collection(fields="name,state,membership,ha,cluster_interfaces"))
        logger.debug(f"{nodes}")
        if args.mode == "connect":
            interfaces = []
            for node in nodes:
                # fetch cluster interfaces
                for ipint in node.cluster_interfaces:
                    Interface = IpInterface(uuid=ipint.uuid)
                    Interface.get()
                    interfaces.append(Interface)
    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error.http_err_response.http_response.text))
    #
    # Cluster health check
    #
    if args.mode == "health":
        # Cluster global health
        if 'ok' not in cluster.metric.status.lower():
            check.add_message(Status.CRITICAL,"Cluster global status is {}".format(cluster.metric.status))
        # Cluster node states
        for node in nodes:
            logger.debug(f"Node info \n{node.__dict__}")
            m = "{} state {} as {}; giveback: {}; takeover: {}".format(node.name,node.state,node.membership,node.ha.giveback.state,node.ha.takeover.state)
            if 'up' in node.state:
                check.add_message(Status.OK, m)
            elif 'down' in node.state:
                check.add_message(Status.CRITICAL, m)
            else:
                check.add_message(Status.WARNING, m)
        short = f"Checked {len(nodes)} Nodes"

    #
    # Cluster connect check
    #
    count = 0
    if args.mode == "connect":
        for IpInt in interfaces:
            logger.debug(f"Interface info {IpInt.name}\n{IpInt.__dict__}")
            if (args.exclude or args.include) and item_filter(args,IpInt.name):
                logger.debug(f"ex-/include interface {IpInt.name}")
                continue
            count += 1
            if 'down' in IpInt.state:
                check.add_message(Status.CRITICAL, f"Int {IpInt.name} is {IpInt.state}")
            elif not IpInt.location.is_home:
                check.add_message(Status.CRITICAL, f"Int {IpInt.name} is on {IpInt.location.node.name} but should be on {IpInt.location.home_node.name}")
            else:
                check.add_message(Status.OK, f"Int {IpInt.name} on {IpInt.location.node.name} port {IpInt.location.port.name} is {IpInt.state}")
        short = f"Checked {count} Interfaces"

    (code, message) = check.check_messages(separator="\n")
    check.exit(code=code,message=f"{short}\n{message}")

if __name__ == "__main__":
    run()