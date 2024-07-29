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
from netapp_ontap.resources import Snapshot,Volume,Software
from netapp_ontap.error import NetAppRestError
from ..tools import cli
from ..tools.helper import setup_connection,severity,to_seconds,item_filter,compareVersion
from datetime import datetime,timedelta

__cmd__ = "snapshot-health"
description = f"{__cmd__} need just age settings and show up outdated snapshots. Warning and critical can be in plain sec or with timee identifiert (1d, 1.5h, 2w)"

def run():
    parser = cli.Parser()
    parser.set_epilog("Connect to ONTAP API and check snapshot age")
    parser.set_description(description)
    parser.add_optional_arguments(cli.Argument.WARNING,cli.Argument.CRITICAL,cli.Argument.COUNT,cli.Argument.INCLUDE,cli.Argument.EXCLUDE)
    parser.add_optional_arguments({
        'name_or_flags': ['--no-snapshot'],
        'options': {
            'action': 'store_true',
            'help': 'warning if no snapshot exists',
        }},
        {
        'name_or_flags': ['--mode'],
        'options': {
            'action': 'store',
            'choices': [
                'volume',
                'snapshot',
            ],
            'default': 'snapshot',
            'help': 'include / exclude volume- or snapshotnames',
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

    setup_connection(args.host, args.api_user, args.api_pass, args.port)

    check = Check()

    count_err = 0
    time_err = 0
    vol_with_snap = 0

    # snapshots module
    try:
        logger.debug(f"Start")
        software = Software()
        software.get(fields='version')
        minimumVersion = "9.10.1"
        if not compareVersion(minimumVersion,software["version"]):
            check.exit(Status.UNKNOWN, f"at least ONTAP v{minimumVersion} is required. Currently v{software['version']} is installed")
        Volumes = list(Volume.fast_get_collection(fields="snapshot_count"))
        # capture infos
        Snaps = []
        for v in Volumes:
            if (args.exclude or args.include) and args.mode == "volume" and item_filter(args,v.name):
                logger.info(f"But item filter exclude: '{args.exclude}' or include: '{args.include}' has matched {v.name}")
                continue
            if not hasattr(v, 'snapshot_count'):
                logger.debug(f"{v.name} has no snapshots")
                continue
            vol = {}
            vol['vname'] = v.name
            vol['count'] = v.snapshot_count
            vol['sname'] = None
            vol['oldest'] = None
            vol['seconds'] = 0

            if v.snapshot_count == 0:
                logger.debug(f"no snapshots found for {v.name}")
                Snaps.append(vol)
                continue
            else:
                Snapshots = list(Snapshot.fast_get_collection(f"{v.uuid}",fields="name,create_time"))
                logger.info(f"{v.name} has {v.snapshot_count} snapshots")
                Ages = []
                for s in Snapshots:
                    if (args.exclude or args.include) and args.mode == "snapshot" and item_filter(args,s.name):
                        continue
                    Ages.append((s.name,datetime.fromisoformat(s.create_time).timestamp()))

            if len(Ages) == 0:
                continue
            else:
                vol_with_snap += 1

            Ages = sorted(Ages, key=lambda tup: tup[1])
            logger.info(f"oldest snapshot => from {Ages[0][1]} name {Ages[0][0]} ")
            vol['sname'] = Ages[0][0]
            vol['rawdate'] = Ages[0][1]
            vol['date'] = timedelta(seconds = datetime.now().timestamp() - Ages[0][1])
            vol['seconds'] = timedelta(seconds = datetime.now().timestamp() - Ages[0][1]).total_seconds()
            Snaps.append(vol)

    except NetAppRestError as error:
        check.exit(Status.UNKNOWN, "Error => {}".format(error))

    for snap in Snaps:
        if args.count:
            count = Threshold(args.count, None)
            copts = {}
            threshold = {}
            threshold['warning'] = args.count
            copts['threshold'] = Threshold(**threshold)
            s = count.get_status(v.snapshot_count)
            if s != Status.OK:
                count_err += 1
                check.add_message(s,f"{snap['vname']} has {snap['count']} snapshots")
                check.add_perfdata(label=f"{snap['vname']}_snapshots",value=int(snap['count']),**copts)

        if args.warning or args.critical:
            time = Threshold(to_seconds(args.warning) or None, to_seconds(args.critical) or None)
            topts = {}
            threshold = {}
            threshold['warning'] = to_seconds(args.warning)
            threshold['critical'] = to_seconds(args.critical)
            topts['threshold'] = Threshold(**threshold)
            st = time.get_status(snap['seconds'])
            if st != Status.OK:
                time_err += 1
                check.add_message(st,f"Snapshot {snap['sname']} of volume {snap['vname']} is outdated")

        if args.no_snapshot:
            if snap['count'] == 0:
                check.add_message(Status.WARNING, f"no snapshosts for volume {snap['vname']}")

    check.add_perfdata(label="total_volumes",value=len(Volumes))
    check.add_perfdata(label="snapshoted_volumes",value=vol_with_snap)
    short = f"found {time_err} volumes with outdated snapshots"
    (code, message) = check.check_messages(separator="\n",allok=f"{vol_with_snap} of total {len(Volumes)} volumes with snapshots are fine")
    if code != Status.OK:
        check.exit(code=code,message=f"{short}\n{message}")
    else:
        check.exit(code=code,message=f"{message}")

if __name__ == "__main__":
    run()
