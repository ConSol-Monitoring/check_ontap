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
from netapp_ontap.error import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,severity,item_filter

__cmd__ = "volume-health"
description = "Check state of volumes online,offline,error or mixed"
"""
Volume({
    'snapshot_policy': {'name': 'none'},
    'analytics': {'state': 'off'},
    'space': {'size': 27487790694400, 'available': 13976673030144, 'used': 13511117664256},
    'type': 'rw',
    'size': 27487790694400,
    'cloud_retrieval_policy': 'default',
    'name': 'eald_p',
    'svm': {
        'name': 'acme01',
        'uuid': '21a63386-5483-11ea-8c65-00a098ef551e',
        '_links': {'self': {'href': '/api/svm/svms/21a63386-5483-11ea-8c65-00a098ef551e'}}},
    'aggregates': [{'uuid': '01d71c4b-88d8-43c3-ae33-afa2b64a629d', 'name': 'acme01_data'}],
    'snapmirror': {'is_protected': True},
    'style': 'flexvol',
    'uuid': '42b7ee25-a342-11eb-b488-00a098c53056',
    '_links': {'self': {'href': '/api/storage/volumes/42b7ee25-a342-11eb-b488-00a098c53056'}},
    'state': 'online',
    'nas': {'export_policy': {'name': 'default'}},
    'tiering': {'policy': 'none'},
    'clone': {'is_flexclone': False},
    'language': 'c.utf_8',
    'metric': {
        'status': 'ok',
        'timestamp': '2022-08-03T11:22:00+00:00',
        'latency': {'other': 214, 'write': 259, 'read': 173, 'total': 205},
        'duration': 'PT15S',
        'iops': {'other': 7, 'write': 2, 'read': 5, 'total': 15},
        'throughput': {'other': 0, 'write': 6967, 'read': 25478, 'total': 32445}},
    'comment': '',
    'create_time': '2021-04-22T10:10:54+02:00'})
"""
def run():
    parser = cli.Parser()
    parser.set_description(description)
    parser.set_epilog("")
    parser.add_optional_arguments(cli.Argument.WARNING,
                                  cli.Argument.CRITICAL,
                                  cli.Argument.EXCLUDE,
                                  cli.Argument.INCLUDE,
                                  cli.Argument.NAME)
    args = parser.get_args()
    # Setup module logging
    logger = logging.getLogger(__name__)
    logger.disabled = True
    if args.verbose:
        for log_name, log_obj in logging.Logger.manager.loggerDict.items():
            log_obj.disabled = False
            logging.getLogger(log_name).setLevel(severity(args.verbose))

    setup_connection(args.host, args.api_user, args.api_pass)

    check = Check()

    try:
        volumes_count = Volume.count_collection()
        logger.info(f"found {volumes_count} volumes")
        if volumes_count == 0:
            check.exit(Status.UNKNOWN, "no vols found")

        if args.name:
            volumes_count = len(args.name[0])
            for n in args.name[0]:
                vol = Volume.find(name=n)
                logger.info(f"find volume {n}")
                logger.debug(f"{vol}")
                if args.warning and vol.state in args.warning:
                    check.add_message(Status.WARNING, f"Vol: {vol.name} has state {vol.state}")
                elif args.critical and vol.state in args.critical:
                    check.add_message(Status.CRITICAL, f"Vol: {vol.name} has state {vol.state}")
                else:
                    check.add_message(Status.OK, f"Vol: {vol.name} has state {vol.state}")
        else:
            for vol in Volume.get_collection(fields="name,state,style,comment"):
                logger.info(f"get volume {vol.name}")
                logger.debug(f"{vol}")
                if not hasattr(vol,'state'):
                    volumes_count -= 1
                    continue
                if (args.exclude or args.include) and item_filter(args,vol.name):
                    volumes_count -= 1
                    continue
                logger.info(f"state: {vol.state}\tname: {vol.name}\tstyle: {vol.style}\tcomment: {vol.comment}")
                if args.warning and vol.state in args.warning:
                    check.add_message(Status.WARNING, f"Vol: {vol.name} has state {vol.state}")
                elif args.critical and vol.state in args.critical:
                    check.add_message(Status.CRITICAL, f"Vol: {vol.name} has state {vol.state}")
                else:
                    check.add_message(Status.OK, f"Vol: {vol.name} has state {vol.state}")
        short = f"checked {volumes_count} volumes"
        (code, message) = check.check_messages(separator='\n')
        check.exit(code=code,message=f"{short}\n{message}")

    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error))
    except Exception as error:
        logger.exception(error)

if __name__ == "__main__":
    run()