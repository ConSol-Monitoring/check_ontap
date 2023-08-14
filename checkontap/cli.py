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


import sys
import os 
import signal
import logging
import importlib
import pkgutil
import checkontap.ontapcmd
from checkontap.tools import cli
from checkontap import CheckOntapTimeout
from netapp_ontap import utils
import urllib3.exceptions
import requests
requests.packages.urllib3.disable_warnings()

def timeout_handler(signum, frame):
    raise CheckOntapTimeout("Timeout reached")

def set_timeout(seconds=None, handler=None):
    if seconds is None:
        seconds = int(os.environ.get("TIMEOUT", "60"))
    signal.signal(signal.SIGALRM, (handler or timeout_handler))
    signal.alarm(seconds)
    
def dependencies():
    failed=[]
    packages=['monplugin','checkontap']
    for p in packages:
        if importlib.util.find_spec(p) is None:
            failed.append(p)
    if len(failed) > 0:
        print("Required modules not found !")
        for p in failed:
            print(f" - {p}")
        sys.exit(3)

def run():
    module = None
    try:
        module = sys.argv.pop(1)
    except:
        pass
    
    set_timeout()
    
    if module:
        mod = "".join(c for c in module if c.isalnum())
        try:
            runner = importlib.import_module(f"checkontap.ontapcmd.{mod}")
        except ModuleNotFoundError as e:
            if not e.name.startswith("ontapcmd."):
                raise e
            print(f"command not found: {module}")
            sys.exit(3)
        try:
            sys.argv[0] = f"{sys.argv[0]} {runner.__cmd__}"
        except:
            sys.argv[0] = f"{sys.argv[0]} {module}"
        runner.run()
    else:
        p = {}
        modules = set()
        for loader, name, is_pkg in pkgutil.walk_packages(checkontap.ontapcmd.__path__):
            if not is_pkg:
                full_name = checkontap.ontapcmd.__name__ + '.' + name
                p[name] = importlib.import_module(full_name)
                if hasattr(p[name], '__cmd__') and p[name].__cmd__:
                    modules.add(p[name].__cmd__)
        print("Specify cmd, one of:\n")
        for mod in sorted(modules):
            print(f" {mod}")
        print()

def main():
    import traceback
    
    dependencies()
    
    logging.basicConfig(format='%(asctime)s %(levelname)s %(module)s %(funcName)s %(lineno)d %(message)s', stream=sys.stdout)
    logging.getLogger().disabled = True
    logging.getLogger("urllib3").propagate = False
    utils.DEBUG = 1
    utils.LOG_ALL_API_CALLS = 1

    try:
        run()
    except SystemExit as e:
        if not isinstance(e.code, int) or e.code > 3:
            sys.exit(3)
        else:
            sys.exit(e.code)
    except urllib3.exceptions.NewConnectionError as e:
        print(f"UNKNOWN - connection issue {e}")
        sys.exit(3)
    except CheckOntapTimeout as e:
        print("UNKNOWN - Timeout reached")
        #traceback.print_exc(file=sys.stdout)
        sys.exit(3)
    except Exception as e:
        print(f"UNKNOWN - Unhandled exception: {e}")
        #traceback.print_exc()
        sys.exit(3)

if __name__ == "__main__":
    main()
