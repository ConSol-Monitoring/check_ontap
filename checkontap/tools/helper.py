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

from netapp_ontap import config, HostConnection
from monplugin import Range
import re

# Connect to Host
def setup_connection(cluster: str, api_user: str, api_pass: str) -> None:
    """Configure the default connection for the application"""
    config.CONNECTION = HostConnection(
        cluster, username=api_user, password=api_pass, verify=False,
    )
    
# Include & Exclude filter
def item_filter(args,item=None) -> None:
    """ Filter for items like disks, sensors, etc.."""
    if args.exclude:
        if re.search(args.exclude,item):
            return(True)
        else:
            return(False)
    elif args.include:
        if re.search(args.include,item):
            return(False)
        else:
            return(True)

#
# uom_to_bytes(20,%,2000) => 400B
# uom_to_bytes(1024,MB) => 1048576B
def uom_to_bytes(value, uom, maximum=None, bsize=1024) -> None:
    a = {'kB' : 1, 'MB': 2, 'GB' : 3, 'TB' : 4, 'PB' : 5, 'EB' : 6 }
    try:
        if '%' in uom and maximum:
            r = round((float(maximum) / 100) * int(value),2)
        else:
            r = round(float(value) * (bsize ** a[uom]),3)
    except Exception as err:
        return err
    return(r)

def bytes_to_uom(value, uom, maximum=None, bsize=1024) -> None:
    a = {'kB' : 1, 'MB': 2, 'GB' : 3, 'TB' : 4, 'PB' : 5, 'EB' : 6 }
    try:
        if '%' in uom and maximum:
            r = round((float(value) / int(maximum) ) * 100,2)
        else:
            r = round(float(value) / (bsize ** a[uom]),3)
    except Exception as err:
        return err
    return(r)

# Percent returned with 2 decimals
def to_percent(max,value) -> None:
    try:
        pct = (float(value) / int(max) ) * 100
    except Exception as err:
        return err
    return(round(pct,2))

def percent_to(max, pct) -> None:
    try:
        value = (int(max) / 100) * int(pct)
    except Exception as err:
        return err
    return(int(value))

# Convert bytes to Mb, Gb, Tb ....
def bytes_to(bytes, to, bsize=1024) -> None: 
    a = {'kB' : 1, 'MB': 2, 'GB' : 3, 'TB' : 4, 'PB' : 5, 'EB' : 6 }
    #r = float(bytes)
    try:
        return round(bytes / (bsize ** a[to]),3)
    except:
        return (bytes)

# Convert Tb, Gb, Mb, Kb, into bytes
def to_bytes(bytes, start, bsize=1024) -> None:
    a = {'kB' : 1, 'MB': 2, 'GB' : 3, 'TB' : 4, 'PB' : 5, 'EB' : 6 }
    return round(float(bytes) * (bsize ** a[start]),3)

def range_in_bytes(r: Range, uom):
    start = uom_to_bytes(r.start, uom)
    end = uom_to_bytes(r.end, uom)

    return ('' if r.outside else '@') + \
        ('~' if start == float('-inf') else str(start)) + \
        ":" + ('' if end == float('+inf') else str(end))
        
# Security level mapping
def severity(level) -> None:
    if level > 5:
        level = 5
    log_levels = {
        1: 'CRITICAL',
        2: 'ERROR',
        3: 'WARNING',
        4: 'INFO',
        5: 'DEBUG',
    }
    return log_levels[level]

# Compare various version strings
def compareVersion(required,current) -> None:
    required = re.sub("[a-zA-Z]",".",required)
    current = re.sub("[a-zA-Z]",".",current)
    versions1 = [int(v) for v in required.split(".")]
    versions2 = [int(v) for v in current.split(".")]
    for i in range(max(len(versions1),len(versions2))):
       v1 = versions1[i] if i < len(versions1) else 0
       v2 = versions2[i] if i < len(versions2) else 0
       if v1 < v2:
           return 1
       elif v1 > v2:
           return 0
    return -1